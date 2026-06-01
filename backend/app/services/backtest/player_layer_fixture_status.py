"""Classificazione player layer v2.1 da JSON persistiti (nessun ricalcolo)."""

from __future__ import annotations

from typing import Any, Literal

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

V21_MODEL_KEY = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

FixturePlayerLayerBucket = Literal["ok", "partial", "missing"]


def _normalize_side_status(raw: str | None) -> str:
    if not raw:
        return "missing"
    return str(raw).strip().lower() or "missing"


def _player_layer_from_side(side: Any) -> str | None:
    if not isinstance(side, dict):
        return None
    direct = side.get("player_layer")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    macros = side.get("macros")
    if isinstance(macros, list):
        for macro in macros:
            if isinstance(macro, dict) and macro.get("key") == "player_layer":
                st = macro.get("status")
                if st is not None and str(st).strip():
                    return str(st).strip()
    return None


def _side_from_v21_audit(trace: dict[str, Any], side: str) -> str | None:
    audit = trace.get("v21_audit")
    if not isinstance(audit, dict):
        return None
    return _player_layer_from_side(audit.get(side))


def extract_v21_player_layer_sides(
    *,
    models_json: dict[str, Any] | None,
    explanation_json: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Home/away player_layer status da trace v21_audit, explanation o trace legacy."""
    models_json = models_json or {}
    explanation_json = explanation_json or {}

    block = models_json.get(V21_MODEL_KEY)
    if isinstance(block, dict):
        trace = block.get("trace_summary")
        if isinstance(trace, dict):
            home = _side_from_v21_audit(trace, "home")
            away = _side_from_v21_audit(trace, "away")
            if home is not None or away is not None:
                return home, away
            home = _player_layer_from_side(trace.get("home"))
            away = _player_layer_from_side(trace.get("away"))
            if home is not None or away is not None:
                return home, away

    expl = explanation_json.get(V21_MODEL_KEY)
    if isinstance(expl, dict):
        home = _player_layer_from_side(expl.get("home"))
        away = _player_layer_from_side(expl.get("away"))
        if home is not None or away is not None:
            return home, away

    return None, None


def classify_player_layer_fixture_bucket(
    home_status: str | None,
    away_status: str | None,
) -> FixturePlayerLayerBucket:
    h = _normalize_side_status(home_status)
    a = _normalize_side_status(away_status)
    if h == "available" and a == "available":
        return "ok"
    if (h == "available") ^ (a == "available"):
        return "partial"
    return "missing"


def summarize_player_layer_from_fixture_rows(
    fixture_rows: list[dict[str, Any]],
) -> dict[str, int]:
    ok = partial = missing = 0
    sides_available = 0
    sides_total = 0

    for row in fixture_rows:
        if row.get("status") != "ok":
            continue
        home, away = extract_v21_player_layer_sides(
            models_json=row.get("models_json"),
            explanation_json=row.get("explanation_json"),
        )
        bucket = classify_player_layer_fixture_bucket(home, away)
        if bucket == "ok":
            ok += 1
        elif bucket == "partial":
            partial += 1
        else:
            missing += 1
        sides_total += 2
        if _normalize_side_status(home) == "available":
            sides_available += 1
        if _normalize_side_status(away) == "available":
            sides_available += 1

    return {
        "fixtures_player_layer_ok": ok,
        "fixtures_player_layer_partial": partial,
        "fixtures_player_layer_missing": missing,
        "player_layer_sides_available": sides_available,
        "player_layer_sides_total": sides_total,
    }


def merge_player_layer_into_data_quality_summary(
    summary: dict[str, Any],
    fixture_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Arricchisce un dump data_quality_summary con conteggi player layer."""
    counts = summarize_player_layer_from_fixture_rows(fixture_rows)
    out = dict(summary)
    out.update(counts)
    details = dict(out.get("details") or {})
    preflight = dict(details.get("preflight") or {})
    preflight["player_stats_available"] = counts["fixtures_player_layer_ok"]
    details["preflight"] = preflight
    out["details"] = details
    return out
