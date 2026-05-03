from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.models import Fixture, League, Season, TeamSotFeature, TeamSotPrediction
from app.services.ingestion_service import IngestionService

WEIGHTS_BASELINE_V0_1 = {
    "season_avg_sot_for": 0.30,
    "opponent_season_avg_sot_conceded": 0.25,
    "home_away_avg_sot_for": 0.15,
    "opponent_home_away_avg_sot_conceded": 0.10,
    "last5_avg_sot_for": 0.10,
    "opponent_last5_avg_sot_conceded": 0.10,
}


def _num_to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


class SotPredictionService:
    model_version = BASELINE_SOT_MODEL_VERSION

    @staticmethod
    def feature_dict_from_orm(fr: TeamSotFeature) -> dict[str, Any]:
        """Ricostruisce il payload usato dal modello da colonne + meta JSON (sot-v2)."""
        meta = None
        if fr.features and isinstance(fr.features, dict):
            meta = fr.features.get("meta")
        if not isinstance(meta, dict):
            meta = {
                "n_team_priors": fr.previous_matches_count or 0,
                "n_opp_priors": fr.opponent_previous_matches_count or 0,
                "formula_fallback_count": 1 if fr.fallback_used else 0,
            }
        return {
            "season_avg_sot_for": _num_to_float(fr.season_avg_sot_for),
            "season_avg_sot_against": _num_to_float(fr.season_avg_sot_against),
            "home_away_avg_sot_for": _num_to_float(fr.home_away_avg_sot_for),
            "home_away_avg_sot_against": _num_to_float(fr.home_away_avg_sot_against),
            "last5_avg_sot_for": _num_to_float(fr.last5_avg_sot_for),
            "last5_avg_sot_against": _num_to_float(fr.last5_avg_sot_against),
            "last10_avg_sot_for": _num_to_float(fr.last10_avg_sot_for),
            "last10_avg_sot_against": _num_to_float(fr.last10_avg_sot_against),
            "opponent_season_avg_sot_conceded": _num_to_float(fr.opponent_season_avg_sot_conceded),
            "opponent_home_away_avg_sot_conceded": _num_to_float(fr.opponent_home_away_avg_sot_conceded),
            "opponent_last5_avg_sot_conceded": _num_to_float(fr.opponent_last5_avg_sot_conceded),
            "rest_days": fr.rest_days,
            "actual_sot": fr.actual_sot,
            "meta": meta,
        }

    def expected_sot_from_features(self, features: dict[str, Any]) -> float:
        total = 0.0
        for key, w in WEIGHTS_BASELINE_V0_1.items():
            v = float(features.get(key) or 0.0)
            total += w * v
        return round(total, 4)

    def confidence_score(self, features: dict[str, Any]) -> int:
        meta = features.get("meta")
        if not isinstance(meta, dict):
            return 50
        n_team = int(meta.get("n_team_priors") or 0)
        n_opp = int(meta.get("n_opp_priors") or 0)
        fb = int(meta.get("formula_fallback_count") or 0)

        team_part = min(55, int(55 * min(n_team, 8) / 8))
        opp_part = min(45, int(45 * min(n_opp, 8) / 8))
        penalty = fb * 8
        score = team_part + opp_part - penalty + 10
        return max(0, min(100, score))

    def explanation_it(
        self,
        *,
        confidence: int,
        features: dict[str, Any],
        line_value: float | None,
        expected: float,
    ) -> str:
        meta = features.get("meta") if isinstance(features.get("meta"), dict) else {}
        n_team = int(meta.get("n_team_priors") or 0)
        fb = int(meta.get("formula_fallback_count") or 0)

        if confidence >= 75:
            livello = "Alta"
        elif confidence >= 45:
            livello = "Media"
        else:
            livello = "Bassa"

        parts = [
            "Modello baseline v0.1: attacco stagionale (30%), concesso avversario (25%), "
            "split casa/trasferta (15% + 10%) e forma recente ultimi 5 (10% + 10%).",
            f"Affidabilità {livello} (confidenza {confidence}/100): {n_team} partite precedenti "
            f"in campionato per la squadra; {fb} input su media di lega per campioni insufficienti.",
        ]
        if line_value is not None:
            delta = round(expected - line_value, 3)
            parts.append(
                f"Simulazione vs linea manuale {line_value:.2f}: atteso − linea = {delta:+.3f} tiri in porta.",
            )
        return " ".join(parts)

    def build_raw_json(
        self,
        *,
        features: dict[str, Any],
        expected: float,
        confidence: int,
        explanation: str,
        line_value: float | None,
    ) -> dict[str, Any]:
        inputs = {k: features.get(k) for k in WEIGHTS_BASELINE_V0_1}
        out: dict[str, Any] = {
            "model_version": self.model_version,
            "weights": WEIGHTS_BASELINE_V0_1,
            "inputs": inputs,
            "expected_sot": expected,
            "confidence_score": confidence,
            "explanation": explanation,
        }
        if line_value is not None:
            out["line_value"] = line_value
            out["vs_line"] = round(expected - line_value, 4)
        return out

    def generate_for_season(
        self,
        db: Session,
        league_id: int,
        season_year: int,
        *,
        line_value: float | None = None,
    ) -> int:
        season = db.scalar(
            select(Season).where(Season.league_id == league_id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per league_id={league_id} year={season_year}")

        rows = db.scalars(
            select(TeamSotFeature)
            .join(Fixture, Fixture.id == TeamSotFeature.fixture_id)
            .where(Fixture.season_id == season.id),
        ).all()

        n = 0
        try:
            for fr in rows:
                feats = self.feature_dict_from_orm(fr)
                expected = self.expected_sot_from_features(feats)
                conf = self.confidence_score(feats)
                expl = self.explanation_it(
                    confidence=conf,
                    features=feats,
                    line_value=line_value,
                    expected=expected,
                )
                raw = self.build_raw_json(
                    features=feats,
                    expected=expected,
                    confidence=conf,
                    explanation=expl,
                    line_value=line_value,
                )
                self._upsert_prediction(db, fr.fixture_id, fr.team_id, expected, raw)
                n += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
        return n

    def _upsert_prediction(
        self,
        db: Session,
        fixture_id: int,
        team_id: int,
        predicted: float,
        raw_json: dict[str, Any],
    ) -> None:
        row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == fixture_id,
                TeamSotPrediction.team_id == team_id,
                TeamSotPrediction.model_version == self.model_version,
            ),
        )
        if row is None:
            row = TeamSotPrediction(
                fixture_id=fixture_id,
                team_id=team_id,
                model_version=self.model_version,
                predicted_sot=predicted,
                raw_json=raw_json,
            )
            db.add(row)
        else:
            row.predicted_sot = predicted
            row.raw_json = raw_json
        db.flush()

    @staticmethod
    def resolve_serie_a_league_id(db: Session) -> int:
        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            raise ValueError("Lega Serie A non trovata")
        return league.id
