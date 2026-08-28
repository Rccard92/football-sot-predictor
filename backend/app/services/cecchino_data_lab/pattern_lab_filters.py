"""Filtri multidimensionali Pattern Lab — tutti opzionali e combinabili."""

from __future__ import annotations

from datetime import datetime
from typing import Any, FrozenSet


BALANCE_PILLAR_KEYS = ("f36", "dominance", "draw_credibility", "gap_coherence")
GOAL_PILLAR_KEYS = (
    "offensive_production",
    "defensive_solidity",
    "match_tempo",
    "offensive_stability",
)

# Soglia Rating KPI per market_informative (non riguarda edge_pct).
KPI_INFORMATIVE_RATING_MIN = 30


def kpi_informative(row: dict[str, Any]) -> bool:
    """Rating >= 30 e value_positive=True. Value False non è evidenza."""
    rating = row.get("pre_rating")
    if rating is None:
        return False
    try:
        if int(rating) < KPI_INFORMATIVE_RATING_MIN:
            return False
    except (TypeError, ValueError):
        return False
    return row.get("pre_value_positive") is True


def signal_informative(row: dict[str, Any]) -> bool:
    """Segnale acquisito attivo oppure count > 0. Bypass soglia Rating 30."""
    if row.get("pre_signal_active") is True:
        return True
    try:
        return int(row.get("pre_signal_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def v36_informative(row: dict[str, Any]) -> bool:
    """V3.6 realmente calcolato. Bypass soglia Rating 30."""
    return (
        row.get("pre_purch_v36_status") == "score"
        and row.get("pre_purch_v36_score") is not None
    )


def market_informative_reasons(row: dict[str, Any]) -> FrozenSet[str]:
    reasons: set[str] = set()
    if kpi_informative(row):
        reasons.add("kpi")
    if signal_informative(row):
        reasons.add("signals")
    if v36_informative(row):
        reasons.add("v36")
    return frozenset(reasons)


def is_market_informative(row: dict[str, Any]) -> bool:
    """MATCH+MARKET informativo: KPI OR Signals OR V3.6. Balance/Goal esclusi."""
    return bool(market_informative_reasons(row))


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

    def _date(key: str) -> str | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        s = str(val).strip()[:10]
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
        return s

    signal_columns = raw.get("signal_columns")
    if not isinstance(signal_columns, dict):
        signal_columns = None

    balance_pillar_filters = raw.get("balance_pillar_filters")
    if not isinstance(balance_pillar_filters, dict):
        balance_pillar_filters = None

    goal_pillar_filters = raw.get("goal_pillar_filters")
    if not isinstance(goal_pillar_filters, dict):
        goal_pillar_filters = None

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
        "score_acquisto_min": _float("score_acquisto_min"),
        "score_acquisto_max": _float("score_acquisto_max"),
        "vantaggio_prob_min": _float("vantaggio_prob_min"),
        "vantaggio_prob_max": _float("vantaggio_prob_max"),
        "signals_count_min": _int("signals_count_min"),
        "signals_count_max": _int("signals_count_max"),
        "signal_columns": signal_columns,
        "consensus_status": raw.get("consensus_status") or None,
        "consensus_yes_count_min": _int("consensus_yes_count_min"),
        "consensus_yes_count_max": _int("consensus_yes_count_max"),
        "balance_class": raw.get("balance_class") or None,
        "gap_coherence_score_min": _float("gap_coherence_score_min")
        or _float("geometry_min")
        or _float("balance_geometry_min"),
        "gap_coherence_score_max": _float("gap_coherence_score_max")
        or _float("geometry_max")
        or _float("balance_geometry_max"),
        "balance_pillar_filters": balance_pillar_filters,
        "goal_final_class": raw.get("goal_final_class") or raw.get("goal_direction") or None,
        "goal_composite_min": _float("goal_composite_min") or _float("goal_intensity_min"),
        "goal_composite_max": _float("goal_composite_max") or _float("goal_intensity_max"),
        "goal_pillar_filters": goal_pillar_filters,
        "purchasability_v36_min": _float("purchasability_v36_min"),
        "purchasability_v36_max": _float("purchasability_v36_max"),
        "purchasability_v36_class": raw.get("purchasability_v36_class") or None,
        "purchasability_v36_status": raw.get("purchasability_v36_status") or None,
        "purchasability_v36_gate_status": raw.get("purchasability_v36_gate_status") or None,
        "bet_builder_active": _bool("bet_builder_active"),
        "bet_builder_rank_min": _int("bet_builder_rank_min"),
        "bet_builder_rank_max": _int("bet_builder_rank_max"),
        "outcome": (str(raw["outcome"]).lower() if raw.get("outcome") else None),
        "quote_type": (str(raw["quote_type"]).lower() if raw.get("quote_type") else None),
        "date_from": _date("date_from"),
        "date_to": _date("date_to"),
        "eligibility": raw.get("eligibility") or "eligible_core",
        # Default operativo True; False/assenza esplicita di True → nessun vincolo.
        "market_informative": (
            True
            if "market_informative" not in raw or raw.get("market_informative") == ""
            else (_bool("market_informative") is True)
        ),
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


def _pillar_filters_match(
    row: dict[str, Any],
    filters: dict[str, Any],
    *,
    prefix: str,
    allowed_keys: tuple[str, ...],
) -> bool:
    for key, spec in filters.items():
        if key not in allowed_keys or not isinstance(spec, dict):
            continue
        score = row.get(f"{prefix}_{key}_score")
        klass = row.get(f"{prefix}_{key}_class")
        if spec.get("class") and klass != spec.get("class"):
            return False
        smin = spec.get("min")
        smax = spec.get("max")
        if smin is not None:
            try:
                if score is None or float(score) < float(smin):
                    return False
            except (TypeError, ValueError):
                return False
        if smax is not None:
            try:
                if score is None or float(score) > float(smax):
                    return False
            except (TypeError, ValueError):
                return False
    return True


def row_passes_filters(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True

    # Per singolo MATCH+MARKET; Balance/Goal non entrano nella regola.
    if filters.get("market_informative") is True and not is_market_informative(row):
        return False

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

    score_acq = row.get("pre_score_acquisto")
    if filters.get("score_acquisto_min") is not None:
        if score_acq is None or float(score_acq) < float(filters["score_acquisto_min"]):
            return False
    if filters.get("score_acquisto_max") is not None:
        if score_acq is None or float(score_acq) > float(filters["score_acquisto_max"]):
            return False

    vant = row.get("pre_vantaggio_prob")
    if filters.get("vantaggio_prob_min") is not None:
        if vant is None or float(vant) < float(filters["vantaggio_prob_min"]):
            return False
    if filters.get("vantaggio_prob_max") is not None:
        if vant is None or float(vant) > float(filters["vantaggio_prob_max"]):
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

    if filters.get("consensus_status"):
        if row.get("pre_consensus_status") != filters["consensus_status"]:
            return False
    cons_n = row.get("pre_consensus_yes_count")
    if filters.get("consensus_yes_count_min") is not None:
        if cons_n is None or int(cons_n) < int(filters["consensus_yes_count_min"]):
            return False
    if filters.get("consensus_yes_count_max") is not None:
        if cons_n is None or int(cons_n) > int(filters["consensus_yes_count_max"]):
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

    if filters.get("balance_pillar_filters") and not _pillar_filters_match(
        row,
        filters["balance_pillar_filters"],
        prefix="pre_balance",
        allowed_keys=BALANCE_PILLAR_KEYS,
    ):
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

    if filters.get("goal_pillar_filters") and not _pillar_filters_match(
        row,
        filters["goal_pillar_filters"],
        prefix="pre_goal_v4_compat",
        allowed_keys=GOAL_PILLAR_KEYS,
    ):
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
    if filters.get("purchasability_v36_status"):
        if row.get("pre_purch_v36_status") != filters["purchasability_v36_status"]:
            return False
    if filters.get("purchasability_v36_gate_status"):
        if row.get("pre_purch_v36_gate_status") != filters["purchasability_v36_gate_status"]:
            return False

    if filters.get("bet_builder_active") is not None:
        if bool(row.get("pre_pattern_lab_bet_builder_active")) != bool(
            filters["bet_builder_active"]
        ):
            return False
    bb_rank = row.get("pre_pattern_lab_bet_builder_rank")
    if filters.get("bet_builder_rank_min") is not None:
        if bb_rank is None or int(bb_rank) < int(filters["bet_builder_rank_min"]):
            return False
    if filters.get("bet_builder_rank_max") is not None:
        if bb_rank is None or int(bb_rank) > int(filters["bet_builder_rank_max"]):
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

    kickoff = str(row.get("kickoff_at") or "")[:10]
    if filters.get("date_from"):
        if not kickoff or kickoff < str(filters["date_from"]):
            return False
    if filters.get("date_to"):
        if not kickoff or kickoff > str(filters["date_to"]):
            return False

    return True
