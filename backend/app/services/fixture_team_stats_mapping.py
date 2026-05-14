"""Parsing statistiche squadra da payload API-Football /fixtures/statistics."""

from __future__ import annotations

import re
from typing import Any

STAT_LABEL_ALIASES: dict[str, str] = {
    "shots on goal": "shots_on_target",
    "shots off goal": "shots_off_target",
    "total shots": "total_shots",
    "shots total": "total_shots",
    "blocked shots": "blocked_shots",
    "shots insidebox": "shots_inside_box",
    "shots inside box": "shots_inside_box",
    "shots outsidebox": "shots_outside_box",
    "shots outside box": "shots_outside_box",
    "fouls": "fouls",
    "corner kicks": "corner_kicks",
    "offsides": "offsides",
    "ball possession": "ball_possession_pct",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "goalkeeper saves": "goalkeeper_saves",
    "total passes": "total_passes",
    "passes accurate": "accurate_passes",
    "passes %": "pass_accuracy_pct",
    "expected goals": "expected_goals",
    "expected_goals": "expected_goals",
}


def _norm_label(raw: str) -> str:
    return " ".join((raw or "").strip().lower().split())


def _parse_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-"):
        return None
    s = re.sub(r"[^\d\-]", "", s)
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, float):
        return val
    if isinstance(val, int):
        return float(val)
    s = str(val).strip().rstrip("%").strip()
    if not s or s.lower() in ("null", "none", "-"):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def statistics_list_to_fields(statistics: list[dict[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in statistics or []:
        label = _norm_label(str(item.get("type") or ""))
        key = STAT_LABEL_ALIASES.get(label)
        if not key:
            continue
        raw = item.get("value")
        if key in ("ball_possession_pct", "pass_accuracy_pct", "expected_goals"):
            v = _parse_float(raw)
        else:
            v = _parse_int(raw)
        if v is not None:
            out[key] = v
    return out


def apply_parsed_to_row(row: Any, parsed: dict[str, Any], *, set_legacy_shots: bool = True) -> None:
    field_names = (
        "shots_on_target",
        "shots_off_target",
        "total_shots",
        "blocked_shots",
        "shots_inside_box",
        "shots_outside_box",
        "fouls",
        "corner_kicks",
        "offsides",
        "ball_possession_pct",
        "yellow_cards",
        "red_cards",
        "goalkeeper_saves",
        "total_passes",
        "accurate_passes",
        "pass_accuracy_pct",
        "expected_goals",
    )
    for name in field_names:
        if name in parsed:
            setattr(row, name, parsed[name])
    if set_legacy_shots:
        if "total_shots" in parsed:
            row.shots = parsed["total_shots"]
        if "shots_on_target" in parsed:
            row.shots_on_target = parsed["shots_on_target"]
