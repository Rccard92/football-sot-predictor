"""Quote Bet365 osservazionali (pre/closing/movimento) — separati dal pre-match payload."""

from __future__ import annotations

from typing import Any

AVAILABILITY_HORIZON = "post_closing_observation"

MOVEMENT_DIRECTION_SHORTEN = "shorten"
MOVEMENT_DIRECTION_STABLE = "stable"
MOVEMENT_DIRECTION_LENGTHEN = "lengthen"

STABLE_DELTA_PCT_THRESHOLD = 0.5


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 1.0:
        return None
    return f


def _implied(odd: float) -> float:
    return round(1.0 / odd, 6)


def _movement_direction(delta_pct: float) -> str:
    if abs(delta_pct) < STABLE_DELTA_PCT_THRESHOLD:
        return MOVEMENT_DIRECTION_STABLE
    # quota scende -> shorten (favorito)
    return MOVEMENT_DIRECTION_SHORTEN if delta_pct < 0 else MOVEMENT_DIRECTION_LENGTHEN


def _movement_intensity(delta_pct: float) -> str:
    a = abs(delta_pct)
    if a < STABLE_DELTA_PCT_THRESHOLD:
        return "none"
    if a < 3.0:
        return "low"
    if a < 8.0:
        return "medium"
    return "high"


def _pair_movement(
    *,
    market_key: str,
    quota_pre: float | None,
    quota_closing: float | None,
    pre_columns: list[str] | None = None,
    closing_columns: list[str] | None = None,
) -> dict[str, Any] | None:
    if quota_pre is None or quota_closing is None:
        return None
    delta_abs = round(quota_closing - quota_pre, 4)
    delta_pct = round(100.0 * delta_abs / quota_pre, 4) if quota_pre else None
    ip_pre = _implied(quota_pre)
    ip_cl = _implied(quota_closing)
    delta_prob = round(ip_cl - ip_pre, 6) if ip_pre is not None and ip_cl is not None else None
    direction = _movement_direction(delta_pct) if delta_pct is not None else MOVEMENT_DIRECTION_STABLE
    return {
        "market_key": market_key,
        "quota_pre": round(quota_pre, 4),
        "quota_closing": round(quota_closing, 4),
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
        "implied_probability_pre": ip_pre,
        "implied_probability_closing": ip_cl,
        "delta_probability": delta_prob,
        "direction": direction,
        "intensity": _movement_intensity(delta_pct or 0.0),
        "availability_horizon": AVAILABILITY_HORIZON,
        "pre_columns": list(pre_columns or []),
        "closing_columns": list(closing_columns or []),
    }


def build_quote_families_raw(match: Any) -> dict[str, Any]:
    """Entrambe le famiglie pre/closing side-by-side (osservazionale)."""
    pre_1x2 = {
        "HOME": _num(getattr(match, "bet365_home", None)),
        "DRAW": _num(getattr(match, "bet365_draw", None)),
        "AWAY": _num(getattr(match, "bet365_away", None)),
        "columns": ["B365H", "B365D", "B365A"],
    }
    closing_1x2 = {
        "HOME": _num(getattr(match, "bet365_closing_home", None)),
        "DRAW": _num(getattr(match, "bet365_closing_draw", None)),
        "AWAY": _num(getattr(match, "bet365_closing_away", None)),
        "columns": ["B365CH", "B365CD", "B365CA"],
    }
    pre_ou = {
        "OVER_2_5": _num(getattr(match, "bet365_over_25", None)),
        "UNDER_2_5": _num(getattr(match, "bet365_under_25", None)),
        "columns": ["B365>2.5", "B365<2.5"],
    }
    closing_ou = {
        "OVER_2_5": _num(getattr(match, "bet365_closing_over_25", None)),
        "UNDER_2_5": _num(getattr(match, "bet365_closing_under_25", None)),
        "columns": ["B365C>2.5", "B365C<2.5"],
    }
    pre_ah = {
        "line": _num(getattr(match, "asian_handicap_home_line", None)),
        "HOME": _num(getattr(match, "bet365_ah_home", None)),
        "AWAY": _num(getattr(match, "bet365_ah_away", None)),
        "columns": ["AHh", "B365AHH", "B365AHA"],
    }
    closing_ah = {
        "line": _num(getattr(match, "asian_handicap_closing_home_line", None)),
        "HOME": _num(getattr(match, "bet365_closing_ah_home", None)),
        "AWAY": _num(getattr(match, "bet365_closing_ah_away", None)),
        "columns": ["AHCh", "B365CAHH", "B365CAHA"],
    }
    return {
        "pre_closing": {
            "1x2": pre_1x2,
            "ou25": pre_ou,
            "asian_handicap": pre_ah,
        },
        "closing": {
            "1x2": closing_1x2,
            "ou25": closing_ou,
            "asian_handicap": closing_ah,
        },
    }


def build_quote_movement_features(match: Any) -> dict[str, Any]:
    """Feature movimento solo dove pre e closing coesistono."""
    movements: dict[str, Any] = {}
    pairs = [
        ("HOME", _num(getattr(match, "bet365_home", None)), _num(getattr(match, "bet365_closing_home", None)), ["B365H"], ["B365CH"]),
        ("DRAW", _num(getattr(match, "bet365_draw", None)), _num(getattr(match, "bet365_closing_draw", None)), ["B365D"], ["B365CD"]),
        ("AWAY", _num(getattr(match, "bet365_away", None)), _num(getattr(match, "bet365_closing_away", None)), ["B365A"], ["B365CA"]),
        ("OVER_2_5", _num(getattr(match, "bet365_over_25", None)), _num(getattr(match, "bet365_closing_over_25", None)), ["B365>2.5"], ["B365C>2.5"]),
        ("UNDER_2_5", _num(getattr(match, "bet365_under_25", None)), _num(getattr(match, "bet365_closing_under_25", None)), ["B365<2.5"], ["B365C<2.5"]),
    ]
    for mk, pre, closing, pc, cc in pairs:
        mv = _pair_movement(
            market_key=mk,
            quota_pre=pre,
            quota_closing=closing,
            pre_columns=pc,
            closing_columns=cc,
        )
        if mv:
            movements[mk] = mv
    return movements


def build_quote_observations(match: Any) -> dict[str, Any]:
    """Payload osservazionale completo — mai nel pre_match_payload/hash."""
    families = build_quote_families_raw(match)
    movement = build_quote_movement_features(match)
    complete_pairs = len(movement)
    status = "complete" if complete_pairs >= 3 else ("partial" if complete_pairs else "unavailable")
    return {
        "observation_status": status,
        "availability_horizon": AVAILABILITY_HORIZON,
        "quote_families_raw": families,
        "movement_features": movement,
        "movement_pairs_count": complete_pairs,
        "anti_leakage": {
            "excluded_from_pre_match_payload": True,
            "excluded_from_pre_match_hash": True,
            "excluded_from_module_inputs": True,
            "post_closing_observation_only": True,
        },
    }
