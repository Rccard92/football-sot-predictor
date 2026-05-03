from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import BASELINE_SOT_MODEL_VERSION
from app.models import Fixture, League, Season, Team, TeamSotFeature, TeamSotPrediction

logger = logging.getLogger(__name__)

WEIGHTS_BASELINE_V0_1 = {
    "season_avg_sot_for": 0.30,
    "opponent_season_avg_sot_conceded": 0.25,
    "home_away_avg_sot_for": 0.15,
    "opponent_home_away_avg_sot_conceded": 0.10,
    "last5_avg_sot_for": 0.10,
    "opponent_last5_avg_sot_conceded": 0.10,
}

PRUDENTIAL_FALLBACK_SOT = 3.5

EXPLANATION_BASELINE_IT = (
    "Previsione basata su media stagionale tiri in porta, rendimento casa/fuori, "
    "forma recente e tiri concessi dall'avversario."
)


def _num_to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _resolve_single_input(
    feats: dict[str, Any],
    key: str,
    league_pre_match_avg: float | None,
) -> float:
    raw = feats.get(key)
    if raw is not None:
        return float(raw)
    season_for = feats.get("season_avg_sot_for")
    if season_for is not None:
        return float(season_for)
    if league_pre_match_avg is not None:
        return float(league_pre_match_avg)
    return PRUDENTIAL_FALLBACK_SOT


def confidence_score_from_feature_row(fr: TeamSotFeature) -> int:
    score = 50
    if (fr.previous_matches_count or 0) >= 8:
        score += 20
    if (fr.opponent_previous_matches_count or 0) >= 8:
        score += 10
    if fr.fallback_used:
        score -= 15
    if fr.last5_avg_sot_for is not None:
        score += 10
    if fr.opponent_last5_avg_sot_conceded is not None:
        score += 10
    return max(0, min(100, score))


class SotPredictionService:
    model_version = BASELINE_SOT_MODEL_VERSION

    @staticmethod
    def feature_dict_from_orm(fr: TeamSotFeature) -> dict[str, Any]:
        """Payload feature da colonne + meta JSON (sot-v2)."""
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

    def expected_sot_resolved(self, feats: dict[str, Any], league_pre_match_avg: float | None) -> float:
        resolved = self._resolved_inputs_dict(feats, league_pre_match_avg)
        total = sum(WEIGHTS_BASELINE_V0_1[k] * resolved[k] for k in WEIGHTS_BASELINE_V0_1)
        return round(max(0.0, float(total)), 2)

    def build_raw_json(
        self,
        *,
        features: dict[str, Any],
        resolved_inputs: dict[str, float],
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
            "resolved_inputs": resolved_inputs,
            "expected_sot": expected,
            "confidence_score": confidence,
            "explanation": explanation,
        }
        if line_value is not None:
            out["line_value"] = line_value
            out["vs_line"] = round(expected - line_value, 4)
        return out

    def _resolved_inputs_dict(
        self,
        feats: dict[str, Any],
        league_pre_match_avg: float | None,
    ) -> dict[str, float]:
        return {k: _resolve_single_input(feats, k, league_pre_match_avg) for k in WEIGHTS_BASELINE_V0_1}

    def _season_row(self, db: Session, season_year: int) -> tuple[League, Season]:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError(f"Lega con api_league_id={settings.default_league_id} non trovata")
        season = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per year={season_year}")
        return league, season

    def _feature_rows_for_season(self, db: Session, season_id: int) -> list[TeamSotFeature]:
        return list(
            db.scalars(
                select(TeamSotFeature)
                .join(Fixture, Fixture.id == TeamSotFeature.fixture_id)
                .where(Fixture.season_id == season_id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc(), TeamSotFeature.team_id.asc()),
            ).all(),
        )

    def generate_for_season_admin(self, db: Session, season_year: int) -> dict[str, Any]:
        from app.services.ingestion_service import IngestionService

        summary: dict[str, Any] = {
            "status": "pending",
            "season": season_year,
            "model_version": self.model_version,
            "feature_rows_total": 0,
            "predictions_created_or_updated": 0,
            "errors": [],
        }

        ing = IngestionService()
        run = ing._begin_run(
            db,
            "generate_sot_predictions",
            meta={"season": season_year, "model_version": self.model_version},
        )

        try:
            _league, season = self._season_row(db, season_year)
        except ValueError as exc:
            logger.warning("generate_sot_predictions: %s", exc)
            summary["status"] = "error"
            summary["message"] = str(exc)
            ing._finish_run(
                db,
                run,
                success=False,
                records_processed=0,
                error=str(exc),
                meta_merge={"summary": summary},
            )
            summary["ingestion_run_id"] = run.id
            return summary

        rows = self._feature_rows_for_season(db, season.id)
        summary["feature_rows_total"] = len(rows)

        if not rows:
            summary["status"] = "success"
            ing._finish_run(db, run, success=True, records_processed=0, meta_merge={"summary": summary})
            summary["ingestion_run_id"] = run.id
            return summary

        prior_season_avgs: list[float] = []
        n_ok = 0

        for fr in rows:
            try:
                league_pre = (
                    sum(prior_season_avgs) / len(prior_season_avgs) if prior_season_avgs else None
                )
                feats = self.feature_dict_from_orm(fr)
                resolved = self._resolved_inputs_dict(feats, league_pre)
                expected = self.expected_sot_resolved(feats, league_pre)
                conf = confidence_score_from_feature_row(fr)
                raw = self.build_raw_json(
                    features=feats,
                    resolved_inputs=resolved,
                    expected=expected,
                    confidence=conf,
                    explanation=EXPLANATION_BASELINE_IT,
                    line_value=None,
                )
                self._upsert_prediction(
                    db,
                    fixture_id=fr.fixture_id,
                    team_id=fr.team_id,
                    predicted=expected,
                    raw_json=raw,
                    actual_sot=fr.actual_sot,
                    confidence_score=conf,
                    explanation=EXPLANATION_BASELINE_IT,
                    line_value=None,
                    over_probability=None,
                    under_probability=None,
                    recommendation="not_evaluated",
                )
                n_ok += 1
                s_avg = _num_to_float(fr.season_avg_sot_for)
                if s_avg is not None:
                    prior_season_avgs.append(s_avg)
            except Exception as exc:
                logger.exception(
                    "generate_sot_predictions: errore feature_id=%s fixture_id=%s team_id=%s",
                    fr.id,
                    fr.fixture_id,
                    fr.team_id,
                )
                summary["errors"].append(
                    {
                        "feature_id": fr.id,
                        "fixture_id": fr.fixture_id,
                        "team_id": fr.team_id,
                        "message": str(exc),
                    },
                )

        try:
            db.commit()
            summary["status"] = "success"
            summary["predictions_created_or_updated"] = n_ok
            ing._finish_run(
                db,
                run,
                success=True,
                records_processed=n_ok,
                meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
            )
        except Exception as exc:
            logger.exception("generate_sot_predictions: commit fallito")
            db.rollback()
            summary["status"] = "error"
            summary["message"] = str(exc)
            try:
                ing._finish_run(
                    db,
                    run,
                    success=False,
                    records_processed=n_ok,
                    error=str(exc),
                    meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
                )
            except Exception:
                logger.exception("generate_sot_predictions: impossibile finalizzare ingestion_run")

        summary["ingestion_run_id"] = run.id
        return summary

    def get_season_predictions_summary(self, db: Session, season_year: int) -> dict[str, Any]:
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return {
                "season": season_year,
                "model_version": self.model_version,
                "feature_rows_total": 0,
                "predictions_total": 0,
                "coverage_pct": 0.0,
                "avg_expected_sot": 0.0,
                "min_expected_sot": 0.0,
                "max_expected_sot": 0.0,
                "avg_confidence_score": 0.0,
            }

        feature_rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotFeature)
                .join(Fixture, Fixture.id == TeamSotFeature.fixture_id)
                .where(Fixture.season_id == season.id),
            )
            or 0,
        )

        predictions_total = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(
                    Fixture.season_id == season.id,
                    TeamSotPrediction.model_version == self.model_version,
                ),
            )
            or 0,
        )

        stats = db.execute(
            select(
                func.avg(TeamSotPrediction.predicted_sot),
                func.min(TeamSotPrediction.predicted_sot),
                func.max(TeamSotPrediction.predicted_sot),
                func.avg(TeamSotPrediction.confidence_score),
            )
            .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
            .where(
                Fixture.season_id == season.id,
                TeamSotPrediction.model_version == self.model_version,
            ),
        ).one()

        avg_exp = float(stats[0] or 0.0)
        min_exp = float(stats[1] or 0.0)
        max_exp = float(stats[2] or 0.0)
        avg_conf = float(stats[3] or 0.0)

        coverage = (
            round(100.0 * predictions_total / feature_rows_total, 2) if feature_rows_total else 0.0
        )

        return {
            "season": season_year,
            "model_version": self.model_version,
            "feature_rows_total": feature_rows_total,
            "predictions_total": predictions_total,
            "coverage_pct": coverage,
            "avg_expected_sot": round(avg_exp, 4),
            "min_expected_sot": round(min_exp, 4),
            "max_expected_sot": round(max_exp, 4),
            "avg_confidence_score": round(avg_conf, 4),
        }

    def get_fixture_predictions_enriched(
        self,
        db: Session,
        fixture_id: int,
        model_version: str | None = None,
    ) -> list[dict[str, Any]]:
        fixture = db.get(Fixture, fixture_id)
        if fixture is None:
            return []

        mv = model_version or self.model_version
        preds = db.scalars(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == fixture_id,
                TeamSotPrediction.model_version == mv,
            ),
        ).all()

        team_ids = {p.team_id for p in preds}
        teams = {
            t.id: t
            for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
        } if team_ids else {}

        out: list[dict[str, Any]] = []
        for p in preds:
            team = teams.get(p.team_id)
            team_name = team.name if team else ""
            if p.team_id == fixture.home_team_id:
                side = "home"
                opp_id = fixture.away_team_id
            else:
                side = "away"
                opp_id = fixture.home_team_id
            opp = db.get(Team, opp_id)
            opponent_name = opp.name if opp else ""

            out.append(
                {
                    "team_id": p.team_id,
                    "team_name": team_name,
                    "opponent_team_id": opp_id,
                    "opponent_name": opponent_name,
                    "side": side,
                    "expected_sot": p.predicted_sot,
                    "actual_sot": p.actual_sot,
                    "confidence_score": p.confidence_score,
                    "explanation": p.explanation or EXPLANATION_BASELINE_IT,
                },
            )

        out.sort(key=lambda x: (0 if x["side"] == "home" else 1, x["team_id"]))
        return out

    def _upsert_prediction(
        self,
        db: Session,
        *,
        fixture_id: int,
        team_id: int,
        predicted: float,
        raw_json: dict[str, Any],
        actual_sot: int | None,
        confidence_score: int,
        explanation: str,
        line_value: float | None,
        over_probability: float | None,
        under_probability: float | None,
        recommendation: str | None,
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
                actual_sot=actual_sot,
                confidence_score=confidence_score,
                explanation=explanation,
                line_value=line_value,
                over_probability=over_probability,
                under_probability=under_probability,
                recommendation=recommendation,
                raw_json=raw_json,
            )
            db.add(row)
        else:
            row.predicted_sot = predicted
            row.actual_sot = actual_sot
            row.confidence_score = confidence_score
            row.explanation = explanation
            row.line_value = line_value
            row.over_probability = over_probability
            row.under_probability = under_probability
            row.recommendation = recommendation
            row.raw_json = raw_json
        db.flush()

    def generate_for_season(
        self,
        db: Session,
        league_id: int,
        season_year: int,
        *,
        line_value: float | None = None,
    ) -> int:
        """Compatibilità: genera senza ingestion run (deprecato per POST admin)."""
        season = db.scalar(
            select(Season).where(Season.league_id == league_id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per league_id={league_id} year={season_year}")

        rows = self._feature_rows_for_season(db, season.id)
        prior_season_avgs: list[float] = []
        n = 0
        try:
            for fr in rows:
                league_pre = (
                    sum(prior_season_avgs) / len(prior_season_avgs) if prior_season_avgs else None
                )
                feats = self.feature_dict_from_orm(fr)
                resolved = self._resolved_inputs_dict(feats, league_pre)
                expected = self.expected_sot_resolved(feats, league_pre)
                conf = confidence_score_from_feature_row(fr)
                raw = self.build_raw_json(
                    features=feats,
                    resolved_inputs=resolved,
                    expected=expected,
                    confidence=conf,
                    explanation=EXPLANATION_BASELINE_IT,
                    line_value=line_value,
                )
                self._upsert_prediction(
                    db,
                    fixture_id=fr.fixture_id,
                    team_id=fr.team_id,
                    predicted=expected,
                    raw_json=raw,
                    actual_sot=fr.actual_sot,
                    confidence_score=conf,
                    explanation=EXPLANATION_BASELINE_IT,
                    line_value=line_value,
                    over_probability=None,
                    under_probability=None,
                    recommendation="not_evaluated",
                )
                n += 1
                s_avg = _num_to_float(fr.season_avg_sot_for)
                if s_avg is not None:
                    prior_season_avgs.append(s_avg)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return n
