"""Intensità Goal — Cecchino Today Fase 46 (motore interno OVER/UNDER Q44)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture
from app.services.cecchino.cecchino_constants import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
)
from app.services.cecchino.cecchino_fixture_history import build_goal_fixture_slices
from app.services.cecchino.cecchino_goal_formulas import (
    calculate_over_fulltime_excel_parity,
    calculate_under_fulltime_excel_parity,
)

VERSION = "cecchino_goal_intensity_v1"

_OVER_FORMULA = "(Q39+R39)/2+(Q42+R42)/2"
_UNDER_FORMULA = "(Q39+R39)/2+(Q42+R42)/2"
_RATIO_FORMULA = "OVER!Q44 / UNDER!Q44"
_DELTA_FORMULA = "OVER!Q44 - UNDER!Q44"


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


def _build_plain_summary(ratio_label: str, delta_label: str) -> str:
    if ratio_label == "Equilibrata":
        return (
            "Pressione offensiva e resistenza difensiva risultano vicine: "
            "il modello legge una gara equilibrata sul piano dell'intensità goal."
        )
    if ratio_label == "Molto Offensiva":
        if delta_label == "Forte Spinta Offensiva":
            return (
                "La pressione offensiva supera nettamente la resistenza difensiva: "
                "il modello legge una gara molto offensiva, confermata da una forte spinta offensiva."
            )
        return (
            "La pressione offensiva supera nettamente la resistenza difensiva: "
            "il modello legge una gara ad alta intensità goal."
        )
    if ratio_label == "Offensiva":
        if delta_label == "Zona Neutra":
            return (
                "Il rapporto di intensità orienta la partita verso una lettura offensiva, "
                "ma il delta resta in zona neutra: la spinta è presente ma non estrema."
            )
        return (
            "Il rapporto di intensità orienta la partita verso una lettura offensiva: "
            "la pressione offensiva prevale sulla resistenza difensiva."
        )
    if ratio_label in ("Difensiva", "Molto Difensiva"):
        if delta_label in ("Moderata Spinta Difensiva", "Forte Spinta Difensiva"):
            return (
                "La resistenza difensiva pesa più della pressione offensiva: "
                "il modello legge una gara difensiva, con conferma dal delta intensità."
            )
        return (
            "La resistenza difensiva pesa più della pressione offensiva: "
            "il modello legge una gara con intensità goal contenuta."
        )
    return (
        f"Il rapporto di intensità indica una lettura {ratio_label.lower()}; "
        f"il delta segnala {delta_label.lower()}."
    )


def _insufficient_payload(warnings: list[str]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_DATA,
        "offensive_index": None,
        "defensive_index": None,
        "intensity_ratio": None,
        "intensity_delta": None,
        "ratio_class_key": None,
        "ratio_label": None,
        "delta_class_key": None,
        "delta_label": None,
        "final_class_key": None,
        "final_label": "Dati insufficienti",
        "plain_summary": None,
        "components": {
            "over_q44": None,
            "under_q44": None,
            "ratio": None,
            "delta": None,
        },
        "debug": {
            "over_formula": _OVER_FORMULA,
            "under_formula": _UNDER_FORMULA,
            "ratio_formula": _RATIO_FORMULA,
            "delta_formula": _DELTA_FORMULA,
        },
        "sources": None,
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis_from_parity(
    *,
    over_ft: dict[str, Any] | None,
    under_ft: dict[str, Any] | None,
) -> dict[str, Any]:
    """Builder puro da risultati parità Excel OVER/UNDER FT."""
    warnings: list[str] = []
    offensive, over_sources, over_warn = _q44_from_ft_parity(
        over_ft,
        missing_warning="missing_over_q44_sources",
    )
    defensive, under_sources, under_warn = _q44_from_ft_parity(
        under_ft,
        missing_warning="missing_under_q44_sources",
    )
    warnings.extend(over_warn)
    warnings.extend(under_warn)

    if offensive is None or defensive is None:
        return _insufficient_payload(warnings)

    if defensive == 0:
        intensity_ratio = 0.0
    else:
        intensity_ratio = round(offensive / defensive, 2)

    intensity_delta = round(offensive - defensive, 2)
    ratio_class_key, ratio_label = _classify_ratio(intensity_ratio)
    delta_class_key, delta_label = _classify_delta(intensity_delta)
    plain_summary = _build_plain_summary(ratio_label, delta_label)

    sources: dict[str, Any] = {}
    if over_sources:
        sources["over"] = over_sources
    if under_sources:
        sources["under"] = under_sources

    return {
        "version": VERSION,
        "status": STATUS_AVAILABLE,
        "offensive_index": offensive,
        "defensive_index": defensive,
        "intensity_ratio": intensity_ratio,
        "intensity_delta": intensity_delta,
        "ratio_class_key": ratio_class_key,
        "ratio_label": ratio_label,
        "delta_class_key": delta_class_key,
        "delta_label": delta_label,
        "final_class_key": ratio_class_key,
        "final_label": ratio_label,
        "plain_summary": plain_summary,
        "components": {
            "over_q44": offensive,
            "under_q44": defensive,
            "ratio": intensity_ratio,
            "delta": intensity_delta,
        },
        "debug": {
            "over_formula": _OVER_FORMULA,
            "under_formula": _UNDER_FORMULA,
            "ratio_formula": _RATIO_FORMULA,
            "delta_formula": _DELTA_FORMULA,
        },
        "sources": sources or None,
        "warnings": warnings,
    }


def build_cecchino_goal_intensity_analysis(
    db: Session,
    target_fixture: Fixture,
) -> dict[str, Any]:
    """Calcola Intensità Goal da storico goal fixture (parità Excel OVER/UNDER)."""
    slices = build_goal_fixture_slices(db, target_fixture)
    over_ft = calculate_over_fulltime_excel_parity(slices)
    under_ft = calculate_under_fulltime_excel_parity(slices)
    return build_cecchino_goal_intensity_analysis_from_parity(
        over_ft=over_ft,
        under_ft=under_ft,
    )


def build_goal_intensity_for_today_row(
    db: Session,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Wrapper per dettaglio Cecchino Today."""
    if not row.local_fixture_id:
        return _insufficient_payload(["missing_local_fixture_id"])
    fixture = db.get(Fixture, int(row.local_fixture_id))
    if fixture is None:
        return _insufficient_payload(["missing_local_fixture"])
    return build_cecchino_goal_intensity_analysis(db, fixture)
