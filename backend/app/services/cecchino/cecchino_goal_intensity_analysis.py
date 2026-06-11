"""Intensità Goal — Cecchino Today Fase 46/47 (motore interno OVER/UNDER Q44 + v2 calibrata)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture
from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_fixture_history import build_goal_fixture_slices
from app.services.cecchino.cecchino_goal_formulas import (
    calculate_over_fulltime_excel_parity,
    calculate_under_fulltime_excel_parity,
)
from app.services.cecchino.cecchino_goal_intensity_baselines import (
    get_goal_intensity_baselines,
)

VERSION = "cecchino_goal_intensity_v2"
STATUS_INSUFFICIENT_BASELINE = "insufficient_baseline"
STATUS_AVAILABLE = "available"

_OVER_FORMULA = "(Q39+R39)/2+(Q42+R42)/2"
_UNDER_FORMULA = "(Q39+R39)/2+(Q42+R42)/2"
_NORMALIZATION_FORMULA = "(OVER_Q44 / baseline_OVER_Q44) / (UNDER_Q44 / baseline_UNDER_Q44)"
_DELTA_FORMULA = "(OVER_Q44 / baseline_OVER_Q44) - (UNDER_Q44 / baseline_UNDER_Q44)"


def _q44_from_blocks(blocks: dict[str, Any] | None) -> tuple[float | None, dict[str, float] | None]:
    if not blocks:
        return None, None
    ha = blocks.get("home_away") or {}
    tot = blocks.get("totals") or {}
    q39 = ha.get("home_component")
    r39 = ha.get("away_component")
    q42 = tot.get("home_component")
    r42 = tot.get("away_component")
    if None in (q39, r39, q42, r42):
        return None, None
    q44 = round(float(ha["block_value"]) + float(tot["block_value"]), 2)
    return q44, {
        "q39": round(float(q39), 4),
        "r39": round(float(r39), 4),
        "q42": round(float(q42), 4),
        "r42": round(float(r42), 4),
    }


def _q44_from_ft_parity(
    ft_result: dict[str, Any] | None,
    *,
    missing_warning: str,
) -> tuple[float | None, dict[str, float] | None, list[str]]:
    warnings: list[str] = []
    if not ft_result or ft_result.get("status") == STATUS_INSUFFICIENT_DATA:
        warnings.append(missing_warning)
        return None, None, warnings
    q44, sources = _q44_from_blocks(ft_result.get("blocks"))
    if q44 is None:
        warnings.append(missing_warning)
    return q44, sources, warnings


def _classify_ratio(ratio: float) -> tuple[str, str]:
    if ratio < 0.70:
        return "very_defensive", "Molto Difensiva"
    if ratio < 0.90:
        return "defensive", "Difensiva"
    if ratio <= 1.05:
        return "balanced", "Equilibrata"
    if ratio <= 1.20:
        return "offensive", "Offensiva"
    return "very_offensive", "Molto Offensiva"


def _classify_delta(delta: float) -> tuple[str, str]:
    if delta > 0.50:
        return "strong_offensive_push", "Forte Spinta Offensiva"
    if delta >= 0.20:
        return "moderate_offensive_push", "Moderata Spinta Offensiva"
    if delta > -0.20:
        return "neutral_zone", "Zona Neutra"
    if delta >= -0.50:
        return "moderate_defensive_push", "Moderata Spinta Difensiva"
    return "strong_defensive_push", "Forte Spinta Difensiva"


def _delta_confirms_ratio(ratio_class_key: str, delta_class_key: str) -> bool | None:
    offensive_ratio = ratio_class_key in ("offensive", "very_offensive")
    defensive_ratio = ratio_class_key in ("defensive", "very_defensive")
    offensive_delta = delta_class_key in ("strong_offensive_push", "moderate_offensive_push")
    defensive_delta = delta_class_key in ("strong_defensive_push", "moderate_defensive_push")
    if delta_class_key == "neutral_zone":
        return None
    if offensive_ratio and offensive_delta:
        return True
    if defensive_ratio and defensive_delta:
        return True
    if offensive_ratio and defensive_delta:
        return False
    if defensive_ratio and offensive_delta:
        return False
    return None


def _build_plain_summary_v2(
    ratio_label: str,
    delta_label: str,
    *,
    delta_confirms: bool | None,
) -> str:
    if ratio_label == "Equilibrata":
        base = (
            "Pressione offensiva e resistenza difensiva risultano vicine alle rispettive baseline: "
            "il modello legge una gara equilibrata sul piano dell'intensità goal."
        )
    elif ratio_label == "Molto Offensiva":
        base = (
            "La pressione offensiva è nettamente sopra la sua baseline storica rispetto alla "
            "resistenza difensiva: il modello legge una gara ad alta intensità goal."
        )
    elif ratio_label == "Offensiva":
        base = (
            "La pressione offensiva risulta superiore alla propria baseline rispetto alla "
            "resistenza difensiva: la gara tende verso una lettura offensiva."
        )
    elif ratio_label == "Difensiva":
        base = (
            "La resistenza difensiva pesa più della pressione offensiva rispetto alle rispettive "
            "baseline: il modello legge una gara a tendenza difensiva."
        )
    elif ratio_label == "Molto Difensiva":
        base = (
            "La resistenza difensiva domina nettamente la pressione offensiva normalizzata: "
            "il modello legge una gara molto difensiva."
        )
    else:
        base = f"Il rapporto di intensità calibrato indica una lettura {ratio_label.lower()}."

    if delta_confirms is True:
        return f"{base} Il Delta Intensità conferma la direzione della lettura."
    if delta_confirms is False:
        return (
            f"{base} Il Delta Intensità non conferma pienamente la lettura principale, "
            "quindi la classificazione va letta con cautela."
        )
    return base


def _insufficient_data_payload(warnings: list[str]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_DATA,
        "raw": None,
        "baseline": {
            "source": None,
            "sample_size": 0,
            "baseline_over_q44": None,
            "baseline_under_q44": None,
            "method": "median",
        },
        "normalized": None,
        "ratio_class_key": None,
        "ratio_label": None,
        "delta_class_key": None,
        "delta_label": None,
        "final_class_key": None,
        "final_label": "Dati insufficienti",
        "plain_summary": None,
        "sources": None,
        "debug": {
            "over_formula": _OVER_FORMULA,
            "under_formula": _UNDER_FORMULA,
            "normalization_formula": _NORMALIZATION_FORMULA,
            "delta_formula": _DELTA_FORMULA,
        },
        "warnings": warnings,
    }


def _insufficient_baseline_payload(
    *,
    raw: dict[str, Any],
    baseline: dict[str, Any],
    sources: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    warnings = list(warnings)
    if "insufficient_goal_intensity_baseline" not in warnings:
        warnings.append("insufficient_goal_intensity_baseline")
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_BASELINE,
        "raw": raw,
        "baseline": baseline,
        "normalized": None,
        "ratio_class_key": None,
        "ratio_label": None,
        "delta_class_key": None,
        "delta_label": None,
        "final_class_key": None,
        "final_label": "Baseline insufficiente",
        "plain_summary": None,
        "sources": sources,
        "debug": {
            "over_formula": _OVER_FORMULA,
            "under_formula": _UNDER_FORMULA,
            "normalization_formula": _NORMALIZATION_FORMULA,
            "delta_formula": _DELTA_FORMULA,
        },
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis_from_parity(
    *,
    over_ft: dict[str, Any] | None,
    under_ft: dict[str, Any] | None,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builder puro da risultati parità Excel OVER/UNDER FT + baseline opzionale."""
    warnings: list[str] = []
    raw_off, over_sources, over_warn = _q44_from_ft_parity(
        over_ft,
        missing_warning="missing_over_q44_sources",
    )
    raw_def, under_sources, under_warn = _q44_from_ft_parity(
        under_ft,
        missing_warning="missing_under_q44_sources",
    )
    warnings.extend(over_warn)
    warnings.extend(under_warn)

    if raw_off is None or raw_def is None:
        return _insufficient_data_payload(warnings)

    raw_ratio = round(raw_off / raw_def, 2) if raw_def != 0 else 0.0
    raw_delta = round(raw_off - raw_def, 2)
    raw = {
        "offensive_index": raw_off,
        "defensive_index": raw_def,
        "raw_ratio": raw_ratio,
        "raw_delta": raw_delta,
    }

    sources: dict[str, Any] = {}
    if over_sources:
        sources["over"] = over_sources
    if under_sources:
        sources["under"] = under_sources

    baseline_payload = baseline or {
        "source": None,
        "sample_size": 0,
        "baseline_over_q44": None,
        "baseline_under_q44": None,
        "method": "median",
    }

    b_over = baseline_payload.get("baseline_over_q44")
    b_under = baseline_payload.get("baseline_under_q44")
    if b_over is None or b_under is None or b_over <= 0 or b_under <= 0:
        return _insufficient_baseline_payload(
            raw=raw,
            baseline=baseline_payload,
            sources=sources or None,
            warnings=warnings,
        )

    over_norm = round(raw_off / float(b_over), 2)
    under_norm = round(raw_def / float(b_under), 2)
    if under_norm <= 0:
        intensity_ratio = 0.0
    else:
        intensity_ratio = round(over_norm / under_norm, 2)
    intensity_delta = round(over_norm - under_norm, 2)

    ratio_class_key, ratio_label = _classify_ratio(intensity_ratio)
    delta_class_key, delta_label = _classify_delta(intensity_delta)
    delta_confirms = _delta_confirms_ratio(ratio_class_key, delta_class_key)
    plain_summary = _build_plain_summary_v2(
        ratio_label,
        delta_label,
        delta_confirms=delta_confirms,
    )

    return {
        "version": VERSION,
        "status": STATUS_AVAILABLE,
        "raw": raw,
        "baseline": baseline_payload,
        "normalized": {
            "offensive_index": over_norm,
            "defensive_index": under_norm,
            "intensity_ratio": intensity_ratio,
            "intensity_delta": intensity_delta,
        },
        "ratio_class_key": ratio_class_key,
        "ratio_label": ratio_label,
        "delta_class_key": delta_class_key,
        "delta_label": delta_label,
        "final_class_key": ratio_class_key,
        "final_label": ratio_label,
        "plain_summary": plain_summary,
        "sources": sources or None,
        "debug": {
            "over_formula": _OVER_FORMULA,
            "under_formula": _UNDER_FORMULA,
            "normalization_formula": _NORMALIZATION_FORMULA,
            "delta_formula": _DELTA_FORMULA,
        },
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis(
    db: Session,
    target_fixture: Fixture,
    *,
    competition_id: int | None = None,
    country_name: str | None = None,
) -> dict[str, Any]:
    """Calcola Intensità Goal v2 da storico goal fixture + baseline mediana."""
    slices = build_goal_fixture_slices(db, target_fixture)
    over_ft = calculate_over_fulltime_excel_parity(slices)
    under_ft = calculate_under_fulltime_excel_parity(slices)
    baseline = get_goal_intensity_baselines(
        db,
        target_fixture,
        competition_id=competition_id,
        country_name=country_name,
    )
    return build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over_ft,
        under_ft=under_ft,
        baseline=baseline,
    )


def build_goal_intensity_for_today_row(
    db: Session,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Wrapper per dettaglio Cecchino Today."""
    if not row.local_fixture_id:
        return _insufficient_data_payload(["missing_local_fixture_id"])
    fixture = db.get(Fixture, int(row.local_fixture_id))
    if fixture is None:
        return _insufficient_data_payload(["missing_local_fixture"])
    return build_cecchino_goal_intensity_analysis(
        db,
        fixture,
        competition_id=row.competition_id,
        country_name=row.country_name,
    )
