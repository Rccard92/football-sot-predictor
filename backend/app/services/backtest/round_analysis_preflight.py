"""Preflight storico e blocchi no_prediction per analisi giornata (Step I UX)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.models import Fixture
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.round_analysis_data_prep_service import FixturePreflight, RoundAnalysisPrepResult
from app.services.predictions_v10.v10_prior_context import build_prior_context

REASON_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
MIN_PRIOR_FOR_RECOMMENDED_ROUND = 3
FIRST_RECOMMENDED_ROUND_FALLBACK = 3


def season_label_from_year(year: int) -> str:
    return f"{int(year)}/{int(year) + 1}"


def _model_identity_fields(
    model_key: str,
    *,
    model_version_requested: str | None = None,
    model_version_used: str | None = None,
    model_engine_name: str | None = None,
    model_status: str,
) -> dict[str, Any]:
    requested = model_version_requested or model_key
    used = model_version_used or model_key
    return {
        "model_version": used,
        "model_version_requested": requested,
        "model_version_used": used,
        "model_engine_name": model_engine_name,
        "model_status": model_status,
        "label": MODEL_LABELS.get(model_key, model_key),
    }


def build_error_block(
    model_key: str,
    *,
    error_code: str,
    error_message: str,
    model_version_requested: str | None = None,
    model_version_used: str | None = None,
    model_engine_name: str | None = None,
    data_quality: dict[str, str] | None = None,
    trace_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_model_identity_fields(
            model_key,
            model_version_requested=model_version_requested,
            model_version_used=model_version_used,
            model_engine_name=model_engine_name,
            model_status="error",
        ),
        "status": "error",
        "error_code": error_code,
        "error_message": error_message,
        "reason": error_code,
        "message": error_message,
        "predicted_home_sot": None,
        "predicted_away_sot": None,
        "predicted_total_sot": None,
        "aggressive_line": None,
        "aggressive_edge": None,
        "aggressive_outcome": None,
        "aggressive_advice": None,
        "aggressive_reason": None,
        "cautious_line": None,
        "cautious_edge": None,
        "cautious_outcome": None,
        "cautious_advice": None,
        "cautious_reason": None,
        "confidence": None,
        "sample_bucket": None,
        "warnings": [error_code.lower()],
        "data_quality": dict(data_quality or {}),
        "trace_summary": trace_summary,
    }


def build_no_prediction_block(
    model_key: str,
    *,
    reason: str = REASON_INSUFFICIENT_HISTORY,
    message: str | None = None,
    prior_home: int | None = None,
    prior_away: int | None = None,
    data_quality: dict[str, str] | None = None,
    error_code: str | None = None,
    model_version_requested: str | None = None,
    model_version_used: str | None = None,
    model_engine_name: str | None = None,
    trace_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    min_prior = None
    if prior_home is not None and prior_away is not None:
        min_prior = min(int(prior_home), int(prior_away))
    if message is None:
        if min_prior is not None:
            message = f"Storico insufficiente prima della partita: prior matches = {min_prior}"
        else:
            message = "Storico insufficiente prima della partita."

    code = error_code or reason
    return {
        **_model_identity_fields(
            model_key,
            model_version_requested=model_version_requested,
            model_version_used=model_version_used,
            model_engine_name=model_engine_name,
            model_status="no_prediction",
        ),
        "status": "no_prediction",
        "error_code": code,
        "reason": reason,
        "message": message,
        "error_message": message,
        "predicted_home_sot": None,
        "predicted_away_sot": None,
        "predicted_total_sot": None,
        "aggressive_line": None,
        "aggressive_edge": None,
        "aggressive_outcome": None,
        "aggressive_advice": None,
        "aggressive_reason": None,
        "cautious_line": None,
        "cautious_edge": None,
        "cautious_outcome": None,
        "cautious_advice": None,
        "cautious_reason": None,
        "confidence": None,
        "sample_bucket": "early_low_sample" if (min_prior or 0) < 5 else None,
        "warnings": [code.lower()],
        "data_quality": dict(data_quality or {}),
        "trace_summary": trace_summary,
    }


def insufficient_history_message(min_prior: int, *, prior_home: int, prior_away: int) -> str:
    return (
        f"Storico insufficiente prima della partita: prior matches = {min_prior} "
        f"(casa {prior_home}, trasferta {prior_away})"
    )


@dataclass(frozen=True)
class RoundHistoryPreflight:
    fixtures_count: int
    min_prior_matches_home: int
    min_prior_matches_away: int
    avg_prior_matches: float
    team_stats_available: int
    lineups_available: int
    unavailable_available: int
    player_stats_available: int
    insufficient_history: bool
    data_quality_status: str
    reason: str | None
    message: str | None
    first_recommended_round: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures_count": self.fixtures_count,
            "min_prior_matches_home": self.min_prior_matches_home,
            "min_prior_matches_away": self.min_prior_matches_away,
            "avg_prior_matches": self.avg_prior_matches,
            "team_stats_available": self.team_stats_available,
            "lineups_available": self.lineups_available,
            "unavailable_available": self.unavailable_available,
            "player_stats_available": self.player_stats_available,
            "insufficient_history": self.insufficient_history,
            "data_quality_status": self.data_quality_status,
            "reason": self.reason,
            "message": self.message,
            "first_recommended_round": self.first_recommended_round,
        }


def _prior_counts_for_fixture(
    db: Session,
    fx: Fixture,
    *,
    competition_id: int,
) -> tuple[int, int]:
    home_ctx = build_prior_context(
        db,
        fx,
        team_id=int(fx.home_team_id),
        opponent_id=int(fx.away_team_id),
        competition_id=competition_id,
    )
    away_ctx = build_prior_context(
        db,
        fx,
        team_id=int(fx.away_team_id),
        opponent_id=int(fx.home_team_id),
        competition_id=competition_id,
    )
    return int(home_ctx.team_prior_count), int(away_ctx.team_prior_count)


def compute_first_recommended_round(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    max_round: int = 38,
) -> int:
    for round_num in range(1, max_round + 1):
        selection = BacktestFixtureDebugService().select_fixtures_for_mini_run(
            db,
            competition_id=competition_id,
            round_number=round_num,
            limit=5,
        )
        for cand in selection.items:
            fx = db.get(Fixture, int(cand.fixture_id))
            if fx is None:
                continue
            home_prior, away_prior = _prior_counts_for_fixture(db, fx, competition_id=competition_id)
            if min(home_prior, away_prior) >= MIN_PRIOR_FOR_RECOMMENDED_ROUND:
                return round_num
    return FIRST_RECOMMENDED_ROUND_FALLBACK


def preflight_round_history(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    fixtures: list[BacktestFixtureCandidate],
    prep: RoundAnalysisPrepResult | None = None,
) -> RoundHistoryPreflight:
    home_priors: list[int] = []
    away_priors: list[int] = []
    team_stats_n = 0
    lineups_n = 0
    unavailable_n = 0

    preflights: dict[int, FixturePreflight] = prep.fixture_preflights if prep else {}

    for cand in fixtures:
        if cand.has_team_stats:
            team_stats_n += 1
        pf = preflights.get(int(cand.fixture_id))
        if pf:
            if pf.has_lineup:
                lineups_n += 1
            if pf.unavailable_count > 0:
                unavailable_n += 1

        fx = db.get(Fixture, int(cand.fixture_id))
        if fx is None:
            continue
        try:
            h, a = _prior_counts_for_fixture(db, fx, competition_id=competition_id)
            home_priors.append(h)
            away_priors.append(a)
        except Exception:  # noqa: BLE001
            home_priors.append(0)
            away_priors.append(0)

    min_home = min(home_priors) if home_priors else 0
    min_away = min(away_priors) if away_priors else 0
    all_priors = home_priors + away_priors
    avg_prior = sum(all_priors) / len(all_priors) if all_priors else 0.0
    min_overall = min(min_home, min_away)

    insufficient = min_overall == 0 or avg_prior < 1.0
    reason = REASON_INSUFFICIENT_HISTORY if insufficient else None
    message = None
    if insufficient:
        message = (
            f"Storico campionato insufficiente per questa giornata "
            f"(min prior casa={min_home}, trasferta={min_away}, media={avg_prior:.1f})."
        )

    dq_status = "critical" if insufficient else "ok"
    first_round = compute_first_recommended_round(
        db,
        competition_id=competition_id,
        season_year=season_year,
    )

    return RoundHistoryPreflight(
        fixtures_count=len(fixtures),
        min_prior_matches_home=min_home,
        min_prior_matches_away=min_away,
        avg_prior_matches=round(avg_prior, 2),
        team_stats_available=team_stats_n,
        lineups_available=lineups_n,
        unavailable_available=unavailable_n,
        player_stats_available=0,
        insufficient_history=insufficient,
        data_quality_status=dq_status,
        reason=reason,
        message=message,
        first_recommended_round=first_round,
    )


def model_block_is_no_prediction(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return True
    return str(block.get("status") or "") == "no_prediction"


def model_block_is_error(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return False
    return str(block.get("status") or "") == "error"


def accordion_summary_from_models(
    model_summary: dict[str, Any] | None,
    *,
    insufficient_history: bool,
) -> dict[str, str]:
    labels = {
        BASELINE_SOT_MODEL_VERSION_V11_SOT: "v1.1",
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: "v2.0",
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: "v2.1",
        BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR: "v3.0",
    }
    out: dict[str, str] = {}
    any_predictions = False
    for key, short in labels.items():
        m = (model_summary or {}).get(key) if isinstance(model_summary, dict) else None
        if isinstance(m, dict):
            display = str(m.get("display") or "ND")
            if int(m.get("predictions_available") or 0) > 0:
                any_predictions = True
            out[short] = display if display in ("OK", "ND", "ERROR", "WARNINGS") else (
                "OK" if int(m.get("predictions_available") or 0) > 0 else "ND"
            )
        else:
            out[short] = "ND"

    if insufficient_history and not any_predictions:
        out["motive"] = "storico insufficiente (preflight giornata)"
    elif isinstance(model_summary, dict):
        codes: list[str] = []
        for m in model_summary.values():
            if isinstance(m, dict) and m.get("prevalent_error_code"):
                codes.append(str(m["prevalent_error_code"]))
        if codes and not any_predictions:
            from collections import Counter

            out["motive"] = Counter(codes).most_common(1)[0][0]
    return out
