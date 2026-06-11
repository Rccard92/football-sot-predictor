"""Intensità Goal — Cecchino Today Fase 48 (v3 OVER-only, percentile storico)."""

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
    get_goal_intensity_over_baseline,
    percentile_rank_percent,
)

VERSION = "cecchino_goal_intensity_v3_over_only"
METHOD = "over_percentile"
STATUS_INSUFFICIENT_BASELINE = "insufficient_baseline"
STATUS_AVAILABLE = "available"

_OVER_FORMULA = "(Q39+R39)/2+(Q42+R42)/2"
_CLASSIFICATION_METHOD = "OVER Q44 percentile rank"
_UNDER_DEPRECATED_NOTE = (
    "UNDER Q44 non determina più la classificazione finale nella versione v3."
)


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


def _classify_over_percentile(percentile: float) -> tuple[str, str]:
    if percentile < 20:
        return "very_defensive", "Molto Difensiva"
    if percentile < 40:
        return "defensive", "Difensiva"
    if percentile <= 60:
        return "balanced", "Equilibrata"
    if percentile <= 80:
        return "offensive", "Offensiva"
    return "very_offensive", "Molto Offensiva"


def _build_plain_summary_v3(final_label: str) -> str:
    if final_label == "Molto Difensiva":
        return (
            "La pressione goal della partita è molto bassa rispetto allo storico Cecchino: "
            "il modello legge una gara a tendenza difensiva."
        )
    if final_label == "Difensiva":
        return (
            "La pressione goal della partita è sotto la media storica Cecchino: "
            "il modello legge una gara con intensità goal contenuta."
        )
    if final_label == "Equilibrata":
        return (
            "La pressione goal della partita è nella media dello storico Cecchino: "
            "il modello legge una gara equilibrata sul piano dell'intensità goal."
        )
    if final_label == "Offensiva":
        return (
            "La pressione goal della partita è superiore alla maggior parte dei valori storici "
            "del Cecchino: il modello legge una gara a tendenza offensiva."
        )
    if final_label == "Molto Offensiva":
        return (
            "La pressione goal della partita è nettamente sopra lo storico Cecchino: "
            "il modello legge una gara ad alta intensità goal."
        )
    return f"Il percentile OVER Q44 indica una lettura {final_label.lower()}."


def _public_baseline(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": baseline.get("source"),
        "sample_size": baseline.get("sample_size", 0),
        "median_over_q44": baseline.get("median_over_q44"),
        "p20_over_q44": baseline.get("p20_over_q44"),
        "p40_over_q44": baseline.get("p40_over_q44"),
        "p60_over_q44": baseline.get("p60_over_q44"),
        "p80_over_q44": baseline.get("p80_over_q44"),
        "method": baseline.get("method", "percentile_distribution"),
    }


def _debug_payload() -> dict[str, str]:
    return {
        "over_formula": _OVER_FORMULA,
        "classification_method": _CLASSIFICATION_METHOD,
        "note": _UNDER_DEPRECATED_NOTE,
    }


def _insufficient_data_payload(warnings: list[str]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_DATA,
        "method": METHOD,
        "raw": None,
        "baseline": None,
        "over_analysis": None,
        "final_class_key": None,
        "final_label": "Dati insufficienti",
        "plain_summary": None,
        "sources": None,
        "debug": _debug_payload(),
        "warnings": warnings,
    }


def _insufficient_baseline_payload(
    *,
    raw: dict[str, Any],
    sources: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    warnings = list(warnings)
    if "insufficient_goal_intensity_over_baseline" not in warnings:
        warnings.append("insufficient_goal_intensity_over_baseline")
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_BASELINE,
        "method": METHOD,
        "raw": raw,
        "baseline": None,
        "over_analysis": None,
        "final_class_key": None,
        "final_label": "Baseline insufficiente",
        "plain_summary": None,
        "sources": sources,
        "debug": _debug_payload(),
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis_from_parity(
    *,
    over_ft: dict[str, Any] | None,
    under_ft: dict[str, Any] | None = None,
    over_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builder puro v3 — classificazione solo su percentile OVER Q44."""
    warnings: list[str] = []
    raw_over, over_sources, over_warn = _q44_from_ft_parity(
        over_ft,
        missing_warning="missing_over_q44_sources",
    )
    raw_under, _, under_warn = _q44_from_ft_parity(
        under_ft,
        missing_warning="missing_under_q44_sources",
    )
    warnings.extend(over_warn)
    warnings.extend(under_warn)

    if raw_over is None:
        return _insufficient_data_payload(warnings)

    raw: dict[str, Any] = {"over_q44": raw_over}
    if raw_under is not None:
        raw["under_q44_deprecated"] = raw_under

    sources: dict[str, Any] = {}
    if over_sources:
        sources["over"] = over_sources

    baseline_payload = over_baseline or {
        "source": None,
        "sample_size": 0,
        "median_over_q44": None,
        "over_values": [],
        "method": "percentile_distribution",
    }

    over_values = list(baseline_payload.get("over_values") or [])
    median = baseline_payload.get("median_over_q44")
    if (
        not over_values
        or median is None
        or float(median) <= 0
        or baseline_payload.get("source") is None
    ):
        return _insufficient_baseline_payload(
            raw=raw,
            sources=sources or None,
            warnings=warnings,
        )

    over_percentile = percentile_rank_percent(over_values, raw_over)
    over_index_vs_median = round(raw_over / float(median), 2)
    final_class_key, final_label = _classify_over_percentile(over_percentile)
    plain_summary = _build_plain_summary_v3(final_label)

    public_baseline = _public_baseline(baseline_payload)

    return {
        "version": VERSION,
        "status": STATUS_AVAILABLE,
        "method": METHOD,
        "raw": raw,
        "baseline": public_baseline,
        "over_analysis": {
            "over_percentile": over_percentile,
            "over_index_vs_median": over_index_vs_median,
        },
        "final_class_key": final_class_key,
        "final_label": final_label,
        "plain_summary": plain_summary,
        "sources": sources or None,
        "debug": _debug_payload(),
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis(
    db: Session,
    target_fixture: Fixture,
    *,
    competition_id: int | None = None,
    country_name: str | None = None,
) -> dict[str, Any]:
    """Calcola Intensità Goal v3 da OVER Q44 e distribuzione storica."""
    slices = build_goal_fixture_slices(db, target_fixture)
    over_ft = calculate_over_fulltime_excel_parity(slices)
    under_ft = calculate_under_fulltime_excel_parity(slices)
    over_baseline = get_goal_intensity_over_baseline(
        db,
        target_fixture,
        competition_id=competition_id,
        country_name=country_name,
    )
    return build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over_ft,
        under_ft=under_ft,
        over_baseline=over_baseline,
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
