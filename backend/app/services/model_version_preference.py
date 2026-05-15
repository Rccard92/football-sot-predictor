"""
Ordine di preferenza modelli SOT e risoluzione modello raccomandato/attivo.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
)
from app.models import TeamSotPrediction

MODEL_VERSION_PREFERENCE_ORDER: tuple[str, ...] = (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION,
)


def preferred_model_versions() -> list[str]:
    return list(MODEL_VERSION_PREFERENCE_ORDER)


def v11_meets_recommend_criteria(
    db: Session,
    *,
    upcoming_fixture_ids: list[int],
    by_version: dict[str, dict[str, Any]],
    upcoming_fixtures_total: int,
) -> bool:
    row = by_version.get(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    if not row or not row.get("is_available_for_upcoming"):
        return False
    up = int(row.get("upcoming_predictions") or 0)
    if upcoming_fixtures_total <= 0 or up != 2 * upcoming_fixtures_total:
        return False
    incomplete = int(row.get("incomplete_predictions") or 0)
    if incomplete > 0:
        return False
    if int(row.get("missing_required_data_count") or 0) > 0:
        return False
    if not upcoming_fixture_ids:
        return False
    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids),
            TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT,
        ),
    ).all()
    if len(preds) != up:
        return False
    for p in preds:
        if p.predicted_sot is None:
            return False
        raw = p.raw_json if isinstance(p.raw_json, dict) else {}
        if raw.get("prediction_valid") is False:
            return False
        if str(raw.get("formula_quality_status") or "") != "ok":
            return False
    return True


def v10_meets_recommend_criteria(
    db: Session,
    *,
    upcoming_fixture_ids: list[int],
    by_version: dict[str, dict[str, Any]],
    upcoming_fixtures_total: int,
) -> bool:
    row = by_version.get(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    if not row or not row.get("is_available_for_upcoming"):
        return False
    up = int(row.get("upcoming_predictions") or 0)
    if upcoming_fixtures_total <= 0 or up != 2 * upcoming_fixtures_total:
        return False
    if not upcoming_fixture_ids:
        return False
    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids),
            TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT,
            TeamSotPrediction.predicted_sot.isnot(None),
        ),
    ).all()
    if len(preds) != up:
        return False
    for p in preds:
        raw = p.raw_json if isinstance(p.raw_json, dict) else {}
        va = raw.get("v04_alignment")
        if not isinstance(va, dict):
            return False
        st = va.get("status")
        if st == "needs_review":
            return False
        if st not in ("aligned_with_v04", "minor_rounding_difference"):
            return False
    return True


def resolve_recommended_model_version(
    db: Session,
    *,
    upcoming_fixture_ids: list[int],
    by_version: dict[str, dict[str, Any]],
    upcoming_fixtures_total: int,
) -> str | None:
    if v11_meets_recommend_criteria(
        db,
        upcoming_fixture_ids=upcoming_fixture_ids,
        by_version=by_version,
        upcoming_fixtures_total=upcoming_fixtures_total,
    ):
        return BASELINE_SOT_MODEL_VERSION_V11_SOT
    if v10_meets_recommend_criteria(
        db,
        upcoming_fixture_ids=upcoming_fixture_ids,
        by_version=by_version,
        upcoming_fixtures_total=upcoming_fixtures_total,
    ):
        return BASELINE_SOT_MODEL_VERSION_V10_SOT
    for mv in MODEL_VERSION_PREFERENCE_ORDER:
        if mv in (BASELINE_SOT_MODEL_VERSION_V11_SOT, BASELINE_SOT_MODEL_VERSION_V10_SOT):
            continue
        row = by_version.get(mv)
        if row and row.get("is_available_for_upcoming"):
            return mv
    return None


def resolve_active_model_for_fixture_preds(
    preds: dict[str, dict[str, float | None]],
) -> str | None:
    for mv in MODEL_VERSION_PREFERENCE_ORDER:
        row = preds.get(mv) or {}
        if row.get("home") is not None and row.get("away") is not None:
            return mv
    for mv, row in preds.items():
        if row.get("home") is not None or row.get("away") is not None:
            return mv
    return None


def enrich_v10_model_status_row(
    db: Session,
    row: dict[str, Any],
    *,
    upcoming_fixture_ids: list[int],
) -> None:
    if not upcoming_fixture_ids:
        row["xg_applied_count"] = 0
        row["xg_fallback_count"] = 0
        return
    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids),
            TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT,
        ),
    ).all()
    applied = 0
    fallback = 0
    for p in preds:
        raw = p.raw_json if isinstance(p.raw_json, dict) else {}
        xc = raw.get("xg_component") if isinstance(raw.get("xg_component"), dict) else {}
        if xc.get("xg_adjustment_applied"):
            applied += 1
        else:
            fallback += 1
    row["xg_applied_count"] = int(applied)
    row["xg_fallback_count"] = int(fallback)


def build_v10_coherence_warnings(
    db: Session,
    *,
    upcoming_fixture_ids: list[int],
    upcoming_fixtures_total: int,
    by_version: dict[str, dict[str, Any]],
    recommended: str | None,
) -> list[str]:
    warnings: list[str] = []
    v10_row = by_version.get(BASELINE_SOT_MODEL_VERSION_V10_SOT)
    if not v10_row:
        warnings.append("baseline_v1_0_sot assente in DB: generare con POST generate-v10-sot.")
        return warnings

    if recommended != BASELINE_SOT_MODEL_VERSION_V10_SOT:
        if v10_meets_recommend_criteria(
            db,
            upcoming_fixture_ids=upcoming_fixture_ids,
            by_version=by_version,
            upcoming_fixtures_total=upcoming_fixtures_total,
        ):
            warnings.append("v1.0 completa ma non raccomandata: verificare logica model-status.")
        return warnings

    if not v10_row.get("is_available_for_upcoming"):
        warnings.append("v1.0 raccomandata ma senza coverage upcoming completa.")

    if not upcoming_fixture_ids:
        return warnings

    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids),
            TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V10_SOT,
        ),
    ).all()
    for p in preds:
        raw = p.raw_json if isinstance(p.raw_json, dict) else {}
        formula = raw.get("formula") if isinstance(raw.get("formula"), dict) else {}
        terms = formula.get("terms") if isinstance(formula.get("terms"), list) else []
        has_xg = any(isinstance(t, dict) and t.get("key") == "expected_goals" for t in terms)
        trace = raw.get("applied_variable_trace") if isinstance(raw.get("applied_variable_trace"), list) else []
        has_trace = any(isinstance(r, dict) and r.get("key") == "expected_goals" for r in trace)
        if not has_xg:
            warnings.append(f"Fixture {p.fixture_id} team {p.team_id}: formula.terms senza expected_goals.")
        if not has_trace:
            warnings.append(f"Fixture {p.fixture_id} team {p.team_id}: trace senza expected_goals.")

    if preds and int(v10_row.get("xg_fallback_count") or 0) == len(preds):
        warnings.append("xG sempre in fallback sulle righe v1.0 upcoming: verificare ingestion team-stats.")

    return warnings


def enrich_v11_model_status_row(
    db: Session,
    row: dict[str, Any],
    *,
    upcoming_fixture_ids: list[int],
) -> None:
    if not upcoming_fixture_ids:
        row["valid_predictions"] = 0
        row["incomplete_predictions"] = 0
        row["missing_required_data_count"] = 0
        return
    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids),
            TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT,
        ),
    ).all()
    valid = 0
    incomplete = 0
    missing_count = 0
    for p in preds:
        raw = p.raw_json if isinstance(p.raw_json, dict) else {}
        if (
            p.predicted_sot is not None
            and raw.get("prediction_valid") is not False
            and str(raw.get("formula_quality_status") or "") == "ok"
        ):
            valid += 1
        else:
            incomplete += 1
            miss = raw.get("missing_required_fields")
            if isinstance(miss, list) and miss:
                missing_count += 1
    row["valid_predictions"] = int(valid)
    row["incomplete_predictions"] = int(incomplete)
    row["missing_required_data_count"] = int(missing_count)
    row["model_stage"] = "offensive_plus_opponent_defense"


def build_v11_coherence_warnings(
    *,
    by_version: dict[str, dict[str, Any]],
    recommended: str | None,
) -> list[str]:
    warnings: list[str] = []
    v11_row = by_version.get(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    if not v11_row:
        warnings.append("baseline_v1_1_sot assente in DB: generare con POST generate-v11-sot.")
        return warnings
    if recommended != BASELINE_SOT_MODEL_VERSION_V11_SOT:
        inc = int(v11_row.get("incomplete_predictions") or 0)
        if inc > 0:
            warnings.append(
                f"v1.1 presente ma non raccomandata: {inc} predizioni incomplete (dati obbligatori mancanti).",
            )
        return warnings
    if int(v11_row.get("incomplete_predictions") or 0) > 0:
        warnings.append("v1.1 raccomandata ma con predizioni incomplete: verificare ingestion team-stats.")
    return warnings
