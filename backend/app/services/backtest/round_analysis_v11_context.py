"""Contesto e diagnostica v1.1 per Round Analysis (backtest-only)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, League, Season
from app.services.predictions_v11.v11_side_result import V11SideResult
from app.services.sot_feature_math import fixture_key_before

logger = logging.getLogger(__name__)

WARN_HOME_AWAY_SPLIT_MISSING = "V11_HOME_AWAY_SPLIT_MISSING"


def resolve_season_id_for_round_analysis(
    db: Session,
    fixture: Fixture,
    competition_id: int,
) -> tuple[int, dict[str, Any]]:
    """Risolve season_id coerente con competition/stagione (tracciato, no UPDATE)."""
    trace: dict[str, Any] = {
        "fixture_season_id": int(fixture.season_id) if fixture.season_id is not None else None,
        "resolution_source": None,
        "season_id_fallback_used": False,
    }
    comp = db.get(Competition, int(competition_id))
    season_year = int(comp.season) if comp is not None else None
    trace["competition_season_year"] = season_year

    if fixture.season_id is not None and comp is not None:
        if comp.season_id is not None and int(fixture.season_id) == int(comp.season_id):
            trace["resolution_source"] = "fixture.season_id"
            return int(fixture.season_id), trace
        if comp.season_id is None:
            trace["resolution_source"] = "fixture.season_id"
            return int(fixture.season_id), trace

    if comp is not None and comp.season_id is not None:
        trace["resolution_source"] = "competition.season_id"
        if fixture.season_id is not None and int(fixture.season_id) != int(comp.season_id):
            trace["season_id_fallback_used"] = True
        return int(comp.season_id), trace

    league_id = comp.league_id if comp is not None else None
    if league_id is None and comp is not None and comp.provider_league_id is not None:
        league = db.scalar(select(League).where(League.api_league_id == int(comp.provider_league_id)))
        if league is not None:
            league_id = int(league.id)

    if league_id is not None and season_year is not None:
        season = db.scalar(
            select(Season).where(Season.league_id == int(league_id), Season.year == int(season_year)),
        )
        if season is not None:
            trace["resolution_source"] = "season.league_year"
            trace["season_id_fallback_used"] = fixture.season_id is not None
            return int(season.id), trace

    from app.services.predictions_v10.v10_prior_context import _resolve_fixture_season_id

    sid = _resolve_fixture_season_id(db, fixture)
    trace["resolution_source"] = "v10_prior_context_fallback"
    trace["season_id_fallback_used"] = True
    return sid, trace


def count_league_baseline_eligible_fixtures(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> int:
    """Conteggio fixture usate da compute_league_v11_baselines_strict (solo lettura)."""
    fixtures = db.scalars(
        select(Fixture).where(
            Fixture.season_id == int(season_id),
            Fixture.status.in_(FINISHED_STATUSES),
        ),
    ).all()
    return sum(
        1
        for f in fixtures
        if fixture_key_before(f.kickoff_at, int(f.id), cutoff_kickoff, cutoff_fixture_id)
    )


_FQ_TO_ERROR: dict[str, str] = {
    "missing_required_xg_league_baseline": "V11_MISSING_XG_LEAGUE_BASELINE",
    "missing_required_player_league_baseline": "V11_MISSING_PLAYER_LEAGUE_BASELINE",
    "missing_required_league_split_baseline": "V11_MISSING_LEAGUE_SPLIT_BASELINE",
    "missing_required_recent_league_baseline": "V11_MISSING_RECENT_LEAGUE_BASELINE",
    "insufficient_player_profile_sample": "V11_INSUFFICIENT_PLAYER_PROFILE",
    "insufficient_sample": "V11_INSUFFICIENT_SAMPLE",
    "insufficient_split_sample": "V11_INSUFFICIENT_SPLIT_SAMPLE",
    "insufficient_recent_sample": "V11_INSUFFICIENT_RECENT_SAMPLE",
    "insufficient_xg_sample": "V11_INSUFFICIENT_XG_SAMPLE",
    "missing_required_data": "V11_MISSING_TEAM_STATS",
}


def _failed_components(res: V11SideResult) -> list[str]:
    comps = (res.raw_json or {}).get("components") if isinstance(res.raw_json, dict) else {}
    failed: list[str] = []
    if isinstance(comps, dict):
        for key, val in comps.items():
            if isinstance(val, dict) and str(val.get("status") or "") not in ("available", "ok", ""):
                failed.append(f"{key}:{val.get('status')}")
    return failed


def _side_formula_output(res: V11SideResult) -> dict[str, Any]:
    return {
        "valid": bool(res.valid),
        "expected_sot": res.expected_sot,
        "formula_quality_status": res.formula_quality_status,
        "failed_components": _failed_components(res),
    }


def infer_v11_failure_code(
    home_res: V11SideResult,
    away_res: V11SideResult,
    total_pred: float | None,
    *,
    league_baseline_eligible: int,
) -> str | None:
    if total_pred is not None:
        return None
    if league_baseline_eligible == 0:
        return "V11_LEAGUE_BASELINE_EMPTY"
    for res in (home_res, away_res):
        fq = str(res.formula_quality_status or "")
        if fq in _FQ_TO_ERROR:
            return _FQ_TO_ERROR[fq]
    if not home_res.valid and not away_res.valid:
        home_fq = str(home_res.formula_quality_status or "")
        away_fq = str(away_res.formula_quality_status or "")
        if home_fq == away_fq and home_fq in _FQ_TO_ERROR:
            return _FQ_TO_ERROR[home_fq]
    return "V11_PREDICTION_INCOMPLETE"


def _side_trace_summary(side: str, res: V11SideResult) -> dict[str, Any]:
    comps = (res.raw_json or {}).get("components") if isinstance(res.raw_json, dict) else {}
    component_status: dict[str, str] = {}
    if isinstance(comps, dict):
        for key, val in list(comps.items())[:12]:
            if isinstance(val, dict):
                component_status[str(key)] = str(val.get("status") or "")
    return {
        "side": side,
        "valid": bool(res.valid),
        "expected_sot": res.expected_sot,
        "formula_quality_status": res.formula_quality_status,
        "component_status_keys": list(component_status.keys()),
        "component_status": component_status,
    }


def build_v11_fixture_trace(
    *,
    fixture: Fixture,
    competition_id: int,
    season_id_used: int,
    season_resolution: dict[str, Any],
    home_prior_count: int,
    away_prior_count: int,
    league_baseline_eligible: int,
    home_res: V11SideResult,
    away_res: V11SideResult,
    home_pred: float | None,
    away_pred: float | None,
    total_pred: float | None,
    context_mode: str = "production_v11",
    inferred_error_code: str | None = None,
) -> dict[str, Any]:
    missing_fields: list[str] = []
    if home_pred is None:
        missing_fields.append("home_predicted_sot")
    if away_pred is None:
        missing_fields.append("away_predicted_sot")
    if total_pred is None:
        missing_fields.append("predicted_total_sot")
    if league_baseline_eligible == 0:
        missing_fields.append("league_baseline_eligible_fixtures")

    trace: dict[str, Any] = {
        "fixture_id": int(fixture.id),
        "model": "baseline_v1_1_sot",
        "service": "V11RoundAnalysisPreviewService",
        "competition_id": int(competition_id),
        "season_year": season_resolution.get("competition_season_year"),
        "season_id_used": int(season_id_used),
        "season_id_fallback_used": bool(season_resolution.get("season_id_fallback_used")),
        "season_resolution_source": season_resolution.get("resolution_source"),
        "home_team_id": int(fixture.home_team_id),
        "away_team_id": int(fixture.away_team_id),
        "cutoff_time": fixture.kickoff_at.isoformat() if fixture.kickoff_at else None,
        "formula_inputs": {
            "context_mode": context_mode,
            "prior_home": home_prior_count,
            "prior_away": away_prior_count,
            "league_baseline_eligible_fixtures": league_baseline_eligible,
            "season_id_used": int(season_id_used),
        },
        "formula_outputs": {
            "home": _side_formula_output(home_res),
            "away": _side_formula_output(away_res),
        },
        "prior_context": {
            "home_prior_matches": home_prior_count,
            "away_prior_matches": away_prior_count,
            "league_baseline_eligible_fixtures": league_baseline_eligible,
            "context_mode": context_mode,
        },
        "home_side": _side_trace_summary("home", home_res),
        "away_side": _side_trace_summary("away", away_res),
        "inferred_error_code": inferred_error_code,
        "extracted_fields": {
            "home_predicted_sot": home_pred,
            "away_predicted_sot": away_pred,
            "total_predicted_sot": total_pred,
        },
        "missing_fields": missing_fields,
    }
    home_fq = trace["formula_outputs"]["home"].get("formula_quality_status")
    away_fq = trace["formula_outputs"]["away"].get("formula_quality_status")
    failed = (
        trace["formula_outputs"]["home"].get("failed_components", [])
        + trace["formula_outputs"]["away"].get("failed_components", [])
    )
    logger.info(
        "V11_ROUND_ANALYSIS_TRACE fixture_id=%s season_id=%s home_prior=%s away_prior=%s "
        "league_baseline_eligible=%s formula_quality_home=%s formula_quality_away=%s "
        "total_pred=%s error_code=%s failed_components=%s missing=%s",
        trace["fixture_id"],
        trace["season_id_used"],
        home_prior_count,
        away_prior_count,
        league_baseline_eligible,
        home_fq,
        away_fq,
        total_pred,
        inferred_error_code or "-",
        ",".join(failed) if failed else "-",
        ",".join(missing_fields) if missing_fields else "-",
    )
    return trace


def extract_v11_predictions(raw: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Estrae home/away/total da output preview con alias minimi."""
    home = raw.get("predicted_home_sot")
    away = raw.get("predicted_away_sot")
    total = raw.get("predicted_total_sot")

    for key in ("home_expected_sot", "expected_sot_home", "home_sot_prediction"):
        if home is None and raw.get(key) is not None:
            home = raw.get(key)
    for key in ("away_expected_sot", "expected_sot_away", "away_sot_prediction"):
        if away is None and raw.get(key) is not None:
            away = raw.get(key)
    for key in ("total_expected_sot", "expected_total_sot"):
        if total is None and raw.get(key) is not None:
            total = raw.get(key)

    pred = raw.get("prediction")
    if isinstance(pred, dict):
        if home is None and pred.get("home") is not None:
            home = pred.get("home")
        if away is None and pred.get("away") is not None:
            away = pred.get("away")
        if total is None and pred.get("total") is not None:
            total = pred.get("total")

    if home is not None and away is not None and total is None:
        total = round(float(home) + float(away), 4)
    return (
        round(float(home), 4) if home is not None else None,
        round(float(away), 4) if away is not None else None,
        round(float(total), 4) if total is not None else None,
    )
