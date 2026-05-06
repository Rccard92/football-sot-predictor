from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import BASELINE_SOT_MODEL_VERSION, BASELINE_SOT_MODEL_VERSION_V02, FINISHED_STATUSES
from app.core.model_limitations import default_model_limitations_dict
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


def fallback_note_for_resolved_factor(
    inputs: dict[str, Any],
    key: str,
    league_pre: float | None,
) -> str | None:
    """Nota solo se il valore grezzo del fattore era assente (stessa catena di `_resolve_single_input`)."""
    raw = inputs.get(key)
    if raw is not None:
        return None
    season_for = inputs.get("season_avg_sot_for")
    if season_for is not None:
        return (
            "Dato originale assente: è stata usata la media stagionale dei tiri in porta "
            "fatti dalla squadra come stima per questo fattore."
        )
    if league_pre is not None:
        return (
            "Dato originale assente: è stata usata la media dei tiri in porta sulle partite "
            "già disputate nel campionato (prima di questa partita)."
        )
    return "Dato originale assente: è stato usato un valore numerico prudenziale predefinito."


def upcoming_calculation_breakdown_from_raw_json(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ricostruisce il breakdown per l'API upcoming da `TeamSotPrediction.raw_json` (nessun ricalcolo formula)."""
    if not raw or not isinstance(raw, dict):
        return None
    resolved = raw.get("resolved_inputs")
    weights = raw.get("weights")
    inputs = raw.get("inputs")
    if not isinstance(resolved, dict) or not isinstance(weights, dict) or not isinstance(inputs, dict):
        return None
    league_pre = raw.get("league_pre_match_avg")
    if league_pre is not None:
        try:
            league_pre = float(league_pre)
        except (TypeError, ValueError):
            league_pre = None
    out: dict[str, Any] = {}
    try:
        for key in WEIGHTS_BASELINE_V0_1:
            if key not in resolved:
                return None
            w_default = WEIGHTS_BASELINE_V0_1[key]
            w = float(weights.get(key, w_default))
            val = float(resolved[key])
            contrib = round(val * w, 4)
            raw_in = inputs.get(key)
            fb = raw_in is None
            note = fallback_note_for_resolved_factor(inputs, key, league_pre) if fb else None
            out[key] = round(val, 4)
            out[f"{key}_weight"] = w
            out[f"{key}_contribution"] = contrib
            out[f"{key}_fallback_used"] = fb
            out[f"{key}_fallback_note"] = note
        exp_stored = raw.get("expected_sot")
        if exp_stored is not None:
            out["expected_sot_total"] = round(float(exp_stored), 2)
        else:
            mix = sum(
                float(resolved[k]) * float(weights.get(k, WEIGHTS_BASELINE_V0_1[k]))
                for k in WEIGHTS_BASELINE_V0_1
            )
            out["expected_sot_total"] = round(max(0.0, mix), 2)
    except (TypeError, ValueError, KeyError):
        return None
    return out

EXPLANATION_BASELINE_IT = (
    "Previsione basata su media stagionale tiri in porta, rendimento casa/fuori, "
    "forma recente e tiri concessi dall'avversario."
)


def production_label_from_expected(expected_sot: float) -> str:
    if expected_sot >= 5.0:
        return "Produzione alta"
    if expected_sot >= 3.5:
        return "Produzione media"
    return "Produzione bassa"


def confidence_word_from_score(score: int) -> str:
    if score >= 80:
        return "Alta"
    if score >= 60:
        return "Media"
    return "Bassa"


def prediction_affidability_from_data_quality(
    *,
    data_quality_score: int,
    model_version: str,
    backtest_mae: float | None,
    backtest_rmse: float | None,
    backtests_total: int,
    fallback_used: bool,
) -> tuple[int, str]:
    """
    Punteggio prudente mostrato come «affidabilità previsione» (non coincide con completezza dati).
    """
    s = max(0, min(100, int(data_quality_score)))
    if model_version == BASELINE_SOT_MODEL_VERSION:
        s = min(s, 85)
    has_bt = backtests_total > 0
    if has_bt and backtest_mae is not None and 1.5 <= backtest_mae <= 2.0:
        s = min(s, 80)
    if has_bt and backtest_rmse is not None and backtest_rmse > 2.0:
        s = min(s, 78)
    if fallback_used:
        s -= 10
    s = max(0, min(100, s))
    if s >= 80:
        return s, "Alta"
    if s >= 60:
        return s, "Media"
    return s, "Bassa"


def _fixture_round_display(fx: Fixture) -> str | None:
    if fx.round and str(fx.round).strip():
        return str(fx.round).strip()[:64]
    raw = fx.raw_json if isinstance(fx.raw_json, dict) else None
    if not raw:
        return None
    fr = (raw.get("fixture") or {}).get("round")
    if fr is not None and str(fr).strip():
        return str(fr).strip()[:64]
    lr = (raw.get("league") or {}).get("round")
    if lr is not None and str(lr).strip():
        return str(lr).strip()[:64]
    return None


def _breakdown_any_fallback(bd: dict[str, Any] | None) -> bool:
    if not bd:
        return False
    return any(bd.get(f"{k}_fallback_used") is True for k in WEIGHTS_BASELINE_V0_1)


def simple_explanation_for_row(fr: TeamSotFeature, expected_sot: float) -> str:
    """Testo breve comprensibile (non sostituisce il disclaimer scientifico)."""
    parts: list[str] = []
    lf = _num_to_float(fr.last5_avg_sot_for)
    sf = _num_to_float(fr.season_avg_sot_for)
    if lf is not None and sf is not None and lf > sf + 0.15:
        parts.append("Negli ultimi match la squadra ha tirato di più in porta rispetto alla media stagionale.")
    elif lf is not None and sf is not None and lf < sf - 0.15:
        parts.append("La forma recente in attacco è sotto la media stagionale.")

    oc = _num_to_float(fr.opponent_last5_avg_sot_conceded)
    ocs = _num_to_float(fr.opponent_season_avg_sot_conceded)
    if oc is not None and ocs is not None and oc > ocs + 0.15:
        parts.append("L'avversario ha concesso più tiri in porta nelle ultime uscite.")
    elif oc is not None and ocs is not None and oc < ocs - 0.15:
        parts.append("L'avversario ha difeso meglio i tiri in porta di recente.")

    if fr.fallback_used:
        parts.append("Dati parziali: alcune medie usano valori di lega prudenziali.")

    if not parts:
        parts.append(
            "Stima basata su andamento stagionale, rendimento casa/fuori e confronto con le medie concesse dall'avversario.",
        )
    parts.append(f"Attesi circa {expected_sot:.1f} tiri in porta squadra.")
    return " ".join(parts)


def technical_debug_from_feature_row(fr: TeamSotFeature) -> dict[str, Any]:
    return {
        "season_avg_sot_for": _num_to_float(fr.season_avg_sot_for),
        "home_away_avg_sot_for": _num_to_float(fr.home_away_avg_sot_for),
        "last5_avg_sot_for": _num_to_float(fr.last5_avg_sot_for),
        "opponent_season_avg_sot_conceded": _num_to_float(fr.opponent_season_avg_sot_conceded),
        "opponent_last5_avg_sot_conceded": _num_to_float(fr.opponent_last5_avg_sot_conceded),
        "previous_matches_count": fr.previous_matches_count,
        "fallback_used": bool(fr.fallback_used),
    }


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
        league_pre_match_avg: float | None = None,
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
        if league_pre_match_avg is not None:
            out["league_pre_match_avg"] = round(float(league_pre_match_avg), 6)
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
                    league_pre_match_avg=league_pre,
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

    def generate_upcoming_predictions_for_season(
        self,
        db: Session,
        season_year: int,
        model_version: str | None = None,
    ) -> dict[str, Any]:
        from app.services.ingestion_service import IngestionService
        from app.services.sot_feature_service import SotFeatureService

        mv = model_version or BASELINE_SOT_MODEL_VERSION
        summary: dict[str, Any] = {
            "status": "pending",
            "season": season_year,
            "model_version": mv,
            "upcoming_fixtures": 0,
            "predictions_created_or_updated": 0,
            "errors": [],
        }

        ing = IngestionService()
        run = ing._begin_run(
            db,
            "generate_sot_predictions_upcoming",
            meta={"season": season_year, "model_version": mv},
        )

        try:
            _league, season = self._season_row(db, season_year)
        except ValueError as exc:
            logger.warning("generate_upcoming_predictions: %s", exc)
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

        feat_svc = SotFeatureService()
        upcoming_fixtures = feat_svc.list_upcoming_fixtures_for_season(db, season.id)
        upcoming_ids = {f.id for f in upcoming_fixtures}
        summary["upcoming_fixtures"] = len(upcoming_ids)

        if not upcoming_ids:
            summary["status"] = "success"
            ing._finish_run(db, run, success=True, records_processed=0, meta_merge={"summary": summary})
            summary["ingestion_run_id"] = run.id
            return summary

        completed_features = db.scalars(
            select(TeamSotFeature)
            .join(Fixture, Fixture.id == TeamSotFeature.fixture_id)
            .where(Fixture.season_id == season.id, Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc(), TeamSotFeature.team_id.asc()),
        ).all()

        prior_season_avgs: list[float] = []
        for fr in completed_features:
            v = _num_to_float(fr.season_avg_sot_for)
            if v is not None:
                prior_season_avgs.append(v)

        upcoming_features = [
            fr for fr in self._feature_rows_for_season(db, season.id) if fr.fixture_id in upcoming_ids
        ]

        n_ok = 0
        for fr in upcoming_features:
            try:
                league_pre = (
                    sum(prior_season_avgs) / len(prior_season_avgs) if prior_season_avgs else None
                )
                feats = self.feature_dict_from_orm(fr)
                resolved = self._resolved_inputs_dict(feats, league_pre)
                expected = self.expected_sot_resolved(feats, league_pre)
                conf = confidence_score_from_feature_row(fr)
                simple = simple_explanation_for_row(fr, expected)
                raw = self.build_raw_json(
                    features=feats,
                    resolved_inputs=resolved,
                    expected=expected,
                    confidence=conf,
                    explanation=simple,
                    line_value=None,
                    league_pre_match_avg=league_pre,
                )
                self._upsert_prediction(
                    db,
                    fixture_id=fr.fixture_id,
                    team_id=fr.team_id,
                    predicted=expected,
                    raw_json=raw,
                    actual_sot=None,
                    confidence_score=conf,
                    explanation=simple,
                    line_value=None,
                    over_probability=None,
                    under_probability=None,
                    recommendation="not_evaluated",
                    model_version=mv,
                )
                n_ok += 1
                s_avg = _num_to_float(fr.season_avg_sot_for)
                if s_avg is not None:
                    prior_season_avgs.append(s_avg)
            except Exception as exc:
                logger.exception(
                    "generate_upcoming_predictions: feature_id=%s fixture_id=%s team_id=%s",
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
            logger.exception("generate_upcoming_predictions: commit fallito")
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
                logger.exception("generate_upcoming_predictions: impossibile finalizzare ingestion_run")

        summary["ingestion_run_id"] = run.id
        return summary

    def get_serie_a_upcoming_matches(
        self,
        db: Session,
        season_year: int,
        *,
        limit: int = 20,
        round_filter: str | None = None,
        only_next_round: bool = True,
        model_version: str | None = None,
    ) -> dict[str, Any]:
        from app.services.sot_feature_service import SotFeatureService

        mv = model_version or self.model_version
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return {
                "season": season_year,
                "round": None,
                "matches_count": 0,
                "matches": [],
                "model_limitations": default_model_limitations_dict(),
            }

        feat_svc = SotFeatureService()
        raw_upcoming = feat_svc.list_upcoming_fixtures_for_season(db, season.id)
        upcoming = [
            f
            for f in raw_upcoming
            if (f.status or "").upper() not in FINISHED_STATUSES
            and not (
                (f.status or "").upper() in FINISHED_STATUSES
                and (f.goals_home is not None or f.goals_away is not None)
            )
        ]
        upcoming.sort(key=lambda f: (f.kickoff_at, f.id))
        if round_filter is not None and round_filter != "":
            upcoming = [f for f in upcoming if (f.round or "") == round_filter]
        if only_next_round and upcoming:
            r0 = _fixture_round_display(upcoming[0]) or upcoming[0].round
            if r0:
                upcoming = [f for f in upcoming if (_fixture_round_display(f) or f.round) == r0]
            else:
                d0 = upcoming[0].kickoff_at.date()
                upcoming = [f for f in upcoming if f.kickoff_at.date() == d0]
        upcoming = upcoming[: max(1, min(limit, 100))]

        round_label = _fixture_round_display(upcoming[0]) if upcoming else None
        matches: list[dict[str, Any]] = []

        from app.models import FixtureLineup, PlayerAvailabilityEvent, PlayerSotProfile
        from app.services.h2h_service import build_h2h_summary_for_fixture
        from app.services.match_context_service import MatchContextService
        from app.services.player_sot_profile_service import PlayerSotProfileService
        from app.services.sot_backtest_service import SotBacktestService

        bt_block = SotBacktestService().get_dashboard_backtest_block(db, season_year, mv)
        bt_n = int(bt_block.get("sot_backtests_total") or 0)
        bt_mae = float(bt_block["sot_backtest_mae"]) if bt_n > 0 else None
        bt_rmse = float(bt_block["sot_backtest_rmse"]) if bt_n > 0 else None

        prof_svc = PlayerSotProfileService()
        ctx_svc = MatchContextService()
        profiles_n_season = int(
            db.scalar(
                select(func.count()).select_from(PlayerSotProfile).where(
                    PlayerSotProfile.season_id == season.id,
                ),
            )
            or 0,
        )
        player_profiles_sot_data_suspicious = False
        if profiles_n_season > 0:
            profiles_with_positive_sot = int(
                db.scalar(
                    select(func.count()).select_from(PlayerSotProfile).where(
                        PlayerSotProfile.season_id == season.id,
                        or_(
                            PlayerSotProfile.shots_on_target_per90 > 0,
                            PlayerSotProfile.total_shots_on_target > 0,
                        ),
                    ),
                )
                or 0,
            )
            player_profiles_sot_data_suspicious = profiles_with_positive_sot == 0

        for fx in upcoming:
            home = db.get(Team, fx.home_team_id)
            away = db.get(Team, fx.away_team_id)
            fh = db.scalar(
                select(TeamSotFeature).where(
                    TeamSotFeature.fixture_id == fx.id,
                    TeamSotFeature.team_id == fx.home_team_id,
                ),
            )
            fa = db.scalar(
                select(TeamSotFeature).where(
                    TeamSotFeature.fixture_id == fx.id,
                    TeamSotFeature.team_id == fx.away_team_id,
                ),
            )
            ph = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == fx.id,
                    TeamSotPrediction.team_id == fx.home_team_id,
                    TeamSotPrediction.model_version == mv,
                ),
            )
            pa = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == fx.id,
                    TeamSotPrediction.team_id == fx.away_team_id,
                    TeamSotPrediction.model_version == mv,
                ),
            )

            def side_pred(
                feat: TeamSotFeature | None,
                pred: TeamSotPrediction | None,
            ) -> dict[str, Any] | None:
                if pred is None or pred.predicted_sot is None:
                    return None
                exp = float(pred.predicted_sot)
                dq = int(pred.confidence_score or 0)
                dq = max(0, min(100, dq))
                dq_label = confidence_word_from_score(dq)
                expl = (
                    simple_explanation_for_row(feat, exp)
                    if feat is not None
                    else (pred.explanation or EXPLANATION_BASELINE_IT)
                )
                raw_j = pred.raw_json if isinstance(pred.raw_json, dict) else None
                bd_raw = upcoming_calculation_breakdown_from_raw_json(raw_j)
                bd = None
                if bd_raw is not None:
                    try:
                        from app.schemas.predictions import UpcomingSotCalculationBreakdown

                        bd = UpcomingSotCalculationBreakdown.model_validate(bd_raw).model_dump()
                    except Exception:
                        bd = None
                fb = bool(feat and feat.fallback_used) or _breakdown_any_fallback(bd)
                pconf, plab = prediction_affidability_from_data_quality(
                    data_quality_score=dq,
                    model_version=mv,
                    backtest_mae=bt_mae,
                    backtest_rmse=bt_rmse,
                    backtests_total=bt_n,
                    fallback_used=fb,
                )
                return {
                    "expected_sot": exp,
                    "confidence_score": dq,
                    "confidence_label": dq_label,
                    "data_quality_score": dq,
                    "data_quality_label": dq_label,
                    "prediction_confidence_score": pconf,
                    "prediction_confidence_label": plab,
                    "label": production_label_from_expected(exp),
                    "simple_explanation": expl,
                    "calculation_breakdown": bd,
                }

            hp = side_pred(fh, ph)
            ap = side_pred(fa, pa)
            total_exp = None
            if hp and ap:
                total_exp = round(float(hp["expected_sot"]) + float(ap["expected_sot"]), 2)

            lu_n = int(
                db.scalar(
                    select(func.count()).select_from(FixtureLineup).where(
                        FixtureLineup.fixture_id == fx.id,
                    ),
                )
                or 0,
            )
            av_n = int(
                db.scalar(
                    select(func.count()).select_from(PlayerAvailabilityEvent).where(
                        PlayerAvailabilityEvent.season_id == season.id,
                        PlayerAvailabilityEvent.team_id.in_((fx.home_team_id, fx.away_team_id)),
                    ),
                )
                or 0,
            )

            h2h_summary: dict[str, Any] | None = None
            try:
                h2h_raw = build_h2h_summary_for_fixture(
                    db,
                    fx.id,
                    exclude_api_fixture_id=int(fx.api_fixture_id),
                )
                if h2h_raw.get("error"):
                    h2h_summary = {
                        "h2h_fetch_ok": False,
                        "note": str(h2h_raw.get("error")),
                    }
                else:
                    h2h_summary = h2h_raw
            except Exception as exc:
                logger.warning("upcoming h2h fixture_id=%s: %s", fx.id, exc)
                h2h_summary = {
                    "h2h_fetch_ok": False,
                    "note": "Impossibile caricare gli scontri diretti in questo momento.",
                }

            player_impact_status = {
                "player_profiles_available": profiles_n_season > 0,
                "player_profiles_sot_data_suspicious": player_profiles_sot_data_suspicious,
                "baseline_includes_player_impact": False,
                "lineups_available": lu_n > 0,
                "availability_available": av_n > 0,
                "lineup_adjustment_applied": False,
                "note": (
                    "Profili impatto giocatore e top giocatori sono solo informativi (layer debug): "
                    "non modificano expected_sot né la baseline v0.1."
                ),
                "home_top_players": prof_svc.top_for_team(
                    db,
                    season_id=season.id,
                    team_id=fx.home_team_id,
                    limit=3,
                ),
                "away_top_players": prof_svc.top_for_team(
                    db,
                    season_id=season.id,
                    team_id=fx.away_team_id,
                    limit=3,
                ),
            }
            context_payload = ctx_svc.build_match_context(db, fx.id)

            matches.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "round": _fixture_round_display(fx),
                    "kickoff_at": fx.kickoff_at,
                    "status_short": fx.status,
                    "home_team": {
                        "id": fx.home_team_id,
                        "name": home.name if home else "",
                        "logo_url": home.logo_url if home else None,
                    },
                    "away_team": {
                        "id": fx.away_team_id,
                        "name": away.name if away else "",
                        "logo_url": away.logo_url if away else None,
                    },
                    "home_prediction": hp,
                    "away_prediction": ap,
                    "total_expected_sot": total_exp,
                    "h2h_summary": h2h_summary,
                    "player_impact_status": player_impact_status,
                    "context_status": context_payload.get("context_status", "not_available"),
                    "match_context": context_payload.get("match_context"),
                    "home_team_context": context_payload.get("home_team_context"),
                    "away_team_context": context_payload.get("away_team_context"),
                    "season_phase_context": context_payload.get("season_phase_context"),
                },
            )

        return {
            "season": season_year,
            "round": round_label,
            "matches_count": len(matches),
            "matches": matches,
            "model_limitations": default_model_limitations_dict(),
            "v02_available": bool(
                db.scalar(
                    select(func.count())
                    .select_from(TeamSotPrediction)
                    .where(
                        TeamSotPrediction.fixture_id.in_([m["fixture_id"] for m in matches]) if matches else False,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V02,
                    ),
                )
                or 0,
            ),
        }

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
        model_version: str | None = None,
    ) -> None:
        mv = model_version or self.model_version
        row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == fixture_id,
                TeamSotPrediction.team_id == team_id,
                TeamSotPrediction.model_version == mv,
            ),
        )
        if row is None:
            row = TeamSotPrediction(
                fixture_id=fixture_id,
                team_id=team_id,
                model_version=mv,
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
                    league_pre_match_avg=league_pre,
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
