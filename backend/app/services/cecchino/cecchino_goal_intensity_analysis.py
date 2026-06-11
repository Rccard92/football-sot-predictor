"""Intensità Goal — Cecchino Today Fase 49 (v4 Goal Attesi + soglie Over)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture
from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_fixture_history import build_goal_market_contexts
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    poisson_cumulative,
    poisson_pmf,
    weighted_lambda,
)
from app.services.cecchino.cecchino_selection_keys import SEL_OVER_1_5, SEL_OVER_2_5

VERSION = "cecchino_goal_intensity_v4_expected_goals"
METHOD = "expected_goals_thresholds"
STATUS_AVAILABLE = "available"

_DEBUG_SOURCE = "internal_cecchino_goal_engine"
_CLASSIFICATION_METHOD = "expected_goals_total thresholds"
_DEBUG_NOTE = (
    "La classificazione usa i Goal Attesi Cecchino interni, non xG esterni e non risultato reale."
)

_THRESHOLD_LINES: tuple[tuple[str, float, str], ...] = (
    ("over_0_5", 0.5, "Over 0.5"),
    ("over_1_5", 1.5, "Over 1.5"),
    ("over_2_5", 2.5, "Over 2.5"),
    ("over_3_5", 3.5, "Over 3.5"),
)

_FT_MARKET_KEYS = (SEL_OVER_1_5, SEL_OVER_2_5)


def _poisson_prob_over_line(lambda_value: float, line: float) -> float:
    if line <= 0.5:
        return 1.0 - poisson_pmf(0, lambda_value)
    if line <= 1.5:
        return 1.0 - poisson_cumulative(lambda_value, 1)
    if line <= 2.5:
        return 1.0 - poisson_cumulative(lambda_value, 2)
    return 1.0 - poisson_cumulative(lambda_value, 3)


def _classify_expected_goals(expected_goals_total: float) -> tuple[str, str]:
    if expected_goals_total < 0.5:
        return "very_defensive", "Molto Difensiva"
    if expected_goals_total < 1.5:
        return "defensive", "Difensiva"
    if expected_goals_total < 2.5:
        return "balanced", "Equilibrata"
    if expected_goals_total < 3.5:
        return "offensive", "Offensiva"
    return "very_offensive", "Molto Offensiva"


def _active_threshold_labels(thresholds: dict[str, Any]) -> list[str]:
    return [
        str(entry["label"])
        for entry in thresholds.values()
        if isinstance(entry, dict) and entry.get("active")
    ]


def _build_plain_summary(expected_goals_total: float, final_label: str) -> str:
    eg = f"{expected_goals_total:.2f}"
    active = _active_threshold_labels(_build_thresholds(expected_goals_total, expected_goals_total))
    active_text = ", ".join(active) if active else "nessuna soglia Over principale"

    if final_label == "Molto Difensiva":
        return (
            f"Il modello stima meno di 0.5 goal attesi interni: {active_text} si accende. "
            "La partita viene letta come molto difensiva."
        )
    if final_label == "Difensiva":
        return (
            f"Il modello stima un'intensità goal bassa: si accende solo Over 0.5. "
            "La partita viene letta come difensiva."
        )
    if final_label == "Equilibrata":
        return (
            f"Il modello stima {eg} goal attesi interni: si accendono Over 0.5 e Over 1.5, "
            "ma non Over 2.5. La partita viene letta come equilibrata."
        )
    if final_label == "Offensiva":
        return (
            f"Il modello stima {eg} goal attesi interni: si accendono Over 0.5, Over 1.5 e Over 2.5. "
            "La partita viene letta come offensiva."
        )
    if final_label == "Molto Offensiva":
        return (
            f"Il modello stima un'intensità goal molto alta: si accendono tutte le soglie principali "
            f"fino a Over 3.5 ({eg} goal attesi). La partita viene letta come molto offensiva."
        )
    return f"Il modello stima {eg} goal attesi interni ({final_label.lower()})."


def _build_thresholds(
    expected_goals_total: float,
    lambda_value: float,
) -> dict[str, dict[str, Any]]:
    thresholds: dict[str, dict[str, Any]] = {}
    for key, line, label in _THRESHOLD_LINES:
        active = expected_goals_total >= line
        thresholds[key] = {
            "line": line,
            "active": active,
            "label": label,
            "probability": round(_poisson_prob_over_line(lambda_value, line), 2),
        }
    return thresholds


def _debug_payload() -> dict[str, str]:
    return {
        "source": _DEBUG_SOURCE,
        "classification_method": _CLASSIFICATION_METHOD,
        "note": _DEBUG_NOTE,
    }


def _insufficient_data_payload(warnings: list[str]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": STATUS_INSUFFICIENT_DATA,
        "method": METHOD,
        "expected_goals_total": None,
        "thresholds": None,
        "active_thresholds_count": None,
        "final_class_key": None,
        "final_label": "Dati insufficienti",
        "plain_summary": None,
        "debug": _debug_payload(),
        "warnings": warnings,
    }


def _lambda_from_goal_markets(goal_markets: dict[str, Any] | None) -> float | None:
    if not goal_markets or not isinstance(goal_markets, dict):
        return None
    for mk in _FT_MARKET_KEYS:
        block = goal_markets.get(mk)
        if not isinstance(block, dict):
            continue
        summary = block.get("summary")
        if not isinstance(summary, dict):
            continue
        lam = summary.get("lambda")
        if lam is not None and float(lam) > 0:
            return float(lam)
    return None


def _resolve_internal_expected_goals_total(
    db: Session,
    fixture: Fixture,
    goal_markets: dict[str, Any] | None = None,
) -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    lam = _lambda_from_goal_markets(goal_markets)
    if lam is not None and lam > 0:
        return round(lam, 2), warnings

    contexts = build_goal_market_contexts(db, fixture)
    computed, _, _, lam_warnings = weighted_lambda(contexts.ft_slices())
    warnings.extend(lam_warnings)
    if computed is None or computed <= 0:
        return None, warnings
    return round(float(computed), 2), warnings


def build_cecchino_goal_intensity_analysis_from_expected_goals(
    expected_goals_total: float | None,
) -> dict[str, Any]:
    """Builder puro v4 — classificazione su Goal Attesi Cecchino e soglie Over."""
    if expected_goals_total is None or expected_goals_total <= 0:
        return _insufficient_data_payload(["missing_internal_expected_goals_total"])

    eg = float(expected_goals_total)
    thresholds = _build_thresholds(eg, eg)
    active_count = sum(1 for t in thresholds.values() if t["active"])
    final_class_key, final_label = _classify_expected_goals(eg)
    plain_summary = _build_plain_summary(eg, final_label)

    return {
        "version": VERSION,
        "status": STATUS_AVAILABLE,
        "method": METHOD,
        "expected_goals_total": eg,
        "thresholds": thresholds,
        "active_thresholds_count": active_count,
        "final_class_key": final_class_key,
        "final_label": final_label,
        "plain_summary": plain_summary,
        "debug": _debug_payload(),
        "warnings": [],
    }


def build_cecchino_goal_intensity_analysis(
    db: Session,
    target_fixture: Fixture,
    *,
    goal_markets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcola Intensità Goal v4 da lambda interna del motore goal Cecchino."""
    expected, warnings = _resolve_internal_expected_goals_total(
        db,
        target_fixture,
        goal_markets=goal_markets,
    )
    if expected is None:
        payload = _insufficient_data_payload(warnings)
        if "missing_internal_expected_goals_total" not in payload["warnings"]:
            payload["warnings"].append("missing_internal_expected_goals_total")
        return payload
    result = build_cecchino_goal_intensity_analysis_from_expected_goals(expected)
    if warnings:
        result["warnings"] = list(warnings)
    return result


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

    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    goal_markets = output.get("goal_markets") if isinstance(output, dict) else None

    return build_cecchino_goal_intensity_analysis(
        db,
        fixture,
        goal_markets=goal_markets if isinstance(goal_markets, dict) else None,
    )
