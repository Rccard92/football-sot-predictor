"""Filtri multidimensionali Pattern Lab — tutti opzionali e combinabili."""

from __future__ import annotations

from typing import Any


def parse_pattern_lab_filters(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}

    def _list(key: str) -> list[str] | None:
        val = raw.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            parts = [p.strip() for p in val.split(",") if p.strip()]
            return parts or None
        if isinstance(val, (list, tuple)):
            out = [str(x) for x in val if x is not None and str(x).strip()]
            return out or None
        return [str(val)]

    def _float(key: str) -> float | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _int(key: str) -> int | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _bool(key: str) -> bool | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ("1", "true", "yes", "on", "si", "sì"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
        return None

    signal_columns = raw.get("signal_columns")
    if not isinstance(signal_columns, dict):
        signal_columns = None

    return {
        "competitions": _list("competitions") or _list("competition"),
        "market_keys": _list("market_keys") or _list("market_key"),
        "quote_min": _float("quote_min"),
        "quote_max": _float("quote_max"),
        "rating_min": _int("rating_min"),
        "rating_max": _int("rating_max"),
        "value": _bool("value"),
        "edge_min": _float("edge_min"),
        "edge_max": _float("edge_max"),
        "signals_count_min": _int("signals_count_min"),
        "signals_count_max": _int("signals_count_max"),
        "signal_columns": signal_columns,
        "balance_class": raw.get("balance_class") or None,
        "gap_coherence_score_min": _float("gap_coherence_score_min")
        or _float("geometry_min")
        or _float("balance_geometry_min"),
        "gap_coherence_score_max": _float("gap_coherence_score_max")
        or _float("geometry_max")
        or _float("balance_geometry_max"),
        "goal_final_class": raw.get("goal_final_class") or raw.get("goal_direction") or None,
        "goal_composite_min": _float("goal_composite_min") or _float("goal_intensity_min"),
        "goal_composite_max": _float("goal_composite_max") or _float("goal_intensity_max"),
        "purchasability_v36_min": _float("purchasability_v36_min"),
        "purchasability_v36_max": _float("purchasability_v36_max"),
        "purchasability_v36_class": raw.get("purchasability_v36_class") or None,
        "bet_builder_active": _bool("bet_builder_active"),
        "outcome": (str(raw["outcome"]).lower() if raw.get("outcome") else None),
        "quote_type": (str(raw["quote_type"]).lower() if raw.get("quote_type") else None),
        "eligibility": raw.get("eligibility") or "eligible_core",
    }


def _signal_column_match(row: dict[str, Any], columns: dict[str, Any]) -> bool:
    for key, mode in columns.items():
        text = str(key).upper().replace("EXCEL_", "")
        field = f"pre_signal_excel_{text.lower()}"
        want_on = str(mode).lower() in ("on", "1", "true", "yes", "si", "sì")
        want_off = str(mode).lower() in ("off", "0", "false", "no")
        val = row.get(field)
        if want_on and val is not True:
            return False
        if want_off and val is True:
            return False
    return True


def row_passes_filters(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True

    comps = filters.get("competitions")
    if comps and row.get("competition") not in comps:
        return False

    markets = filters.get("market_keys")
    if markets and row.get("market_key") not in markets:
        return False

    quota = row.get("pre_quota_bet365")
    if filters.get("quote_min") is not None:
        if quota is None or float(quota) < float(filters["quote_min"]):
            return False
    if filters.get("quote_max") is not None:
        if quota is None or float(quota) > float(filters["quote_max"]):
            return False

    rating = row.get("pre_rating")
    if filters.get("rating_min") is not None:
        if rating is None or int(rating) < int(filters["rating_min"]):
            return False
    if filters.get("rating_max") is not None:
        if rating is None or int(rating) > int(filters["rating_max"]):
            return False

    if filters.get("value") is not None:
        if bool(row.get("pre_value_positive")) != bool(filters["value"]):
            return False

    edge = row.get("pre_edge_pct")
    if filters.get("edge_min") is not None:
        if edge is None or float(edge) < float(filters["edge_min"]):
            return False
    if filters.get("edge_max") is not None:
        if edge is None or float(edge) > float(filters["edge_max"]):
            return False

    sig_count = int(row.get("pre_signal_count") or 0)
    if filters.get("signals_count_min") is not None:
        if sig_count < int(filters["signals_count_min"]):
            return False
    if filters.get("signals_count_max") is not None:
        if sig_count > int(filters["signals_count_max"]):
            return False

    if filters.get("signal_columns") and not _signal_column_match(row, filters["signal_columns"]):
        return False

    if filters.get("balance_class"):
        if row.get("pre_balance_structural_class") != filters["balance_class"]:
            return False

    geom = row.get("pre_balance_geometry")
    if filters.get("gap_coherence_score_min") is not None:
        if geom is None or float(geom) < float(filters["gap_coherence_score_min"]):
            return False
    if filters.get("gap_coherence_score_max") is not None:
        if geom is None or float(geom) > float(filters["gap_coherence_score_max"]):
            return False

    if filters.get("goal_final_class"):
        if row.get("pre_goal_v4_compat_final_class") != filters["goal_final_class"]:
            return False

    gcomp = row.get("pre_goal_v4_compat_composite")
    if filters.get("goal_composite_min") is not None:
        if gcomp is None or float(gcomp) < float(filters["goal_composite_min"]):
            return False
    if filters.get("goal_composite_max") is not None:
        if gcomp is None or float(gcomp) > float(filters["goal_composite_max"]):
            return False

    pscore = row.get("pre_purch_v36_score")
    if filters.get("purchasability_v36_min") is not None:
        if pscore is None or float(pscore) < float(filters["purchasability_v36_min"]):
            return False
    if filters.get("purchasability_v36_max") is not None:
        if pscore is None or float(pscore) > float(filters["purchasability_v36_max"]):
            return False
    if filters.get("purchasability_v36_class"):
        if row.get("pre_purch_v36_class") != filters["purchasability_v36_class"]:
            return False

    if filters.get("bet_builder_active") is not None:
        if bool(row.get("pre_pattern_lab_bet_builder_active")) != bool(
            filters["bet_builder_active"]
        ):
            return False

    qtype = filters.get("quote_type")
    if qtype and qtype != "all":
        if row.get("pre_quote_type") != qtype:
            return False

    outcome = filters.get("outcome")
    if outcome:
        if outcome == "won" and row.get("target_won") is not True:
            return False
        if outcome == "lost" and row.get("target_lost") is not True:
            return False
        if outcome == "void" and row.get("target_void") is not True:
            return False

    return True
