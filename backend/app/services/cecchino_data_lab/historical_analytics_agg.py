"""Funzioni pure di aggregazione condivise tra report AI e dashboard run.

Nessuna scrittura DB. Nessuna dipendenza da Cecchino Today / Betfair operativo.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult

ANALYTICS_AGGREGATION_VERSION = "cecchino_lab_analytics_agg_v2_2"

# Pilastri Balance canonici (ordine UI dashboard)
BALANCE_CANONICAL_PILLARS: tuple[str, ...] = (
    "f36",
    "dominance",
    "draw_credibility",
    "gap_coherence",
)

BALANCE_PILLAR_LABELS: dict[str, str] = {
    "f36": "Equilibrio F36",
    "dominance": "Convinzione / Dominanza",
    "draw_credibility": "Credibilità X",
    "gap_coherence": "Coerenza gap",
}

BALANCE_COMBINATIONS: tuple[tuple[str, str, str], ...] = (
    ("equilibrio_coerenza", "f36", "gap_coherence"),
    ("convinzione_credibilita_x", "dominance", "draw_credibility"),
    ("equilibrio_credibilita_x", "f36", "draw_credibility"),
    ("convinzione_coerenza", "dominance", "gap_coherence"),
)

GI_PILLARS: tuple[str, ...] = (
    "offensive_production",
    "defensive_solidity",
    "match_tempo",
    "offensive_stability",
)

GI_PILLAR_LABELS: dict[str, str] = {
    "offensive_production": "Produzione offensiva",
    "defensive_solidity": "Solidità difensiva",
    "match_tempo": "Ritmo partita",
    "offensive_stability": "Stabilità offensiva",
}

RATING_BANDS_DASHBOARD: tuple[str, ...] = (
    "lt_50",
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90-99",
    "100",
    "unavailable",
)

PURCH_BANDS_DASHBOARD: tuple[str, ...] = (
    "0-9",
    "10-19",
    "20-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90-99",
    "100",
    "unavailable",
)

MIN_PATTERN_SAMPLE_FOR_REAL_ROI = 30
PATTERNS_TOP_CAP = 25
MIN_COMBO_SAMPLE = 30

ABSENCE_CONDITION_VALUES = frozenset(
    {
        "no_rating",
        "no_purch",
        "no_gi",
        "no_signal",
        "signal_off",
        "module_unavailable",
        "missing_value",
        "unavailable",
        "unknown",
    }
)

ABSENCE_CONDITION_KEYS = frozenset(
    {
        "rating_band",
        "purchasability_band",
        "offensive_production_class",
        "signal",
        "balance_class",
    }
)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_valid_book_odds(q: Any) -> bool:
    """Quota book valida: numerica, finita, strettamente > 1.0 (0 non è una quota)."""
    if q is None:
        return False
    try:
        f = float(q)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(f):
        return False
    return f > 1.0


def confidence_status(sample_size: int) -> str:
    if sample_size < 30:
        return "small_sample"
    if sample_size < 100:
        return "descriptive_only"
    return "sufficient_sample"


def quote_quality_of_market(m: CecchinoLabHistoricalMarketResult) -> str:
    if m.is_real_book_quote:
        return "real"
    if m.is_derived_quote:
        return "derived"
    return "unavailable"


def quote_count_reconciliation(b: dict[str, Any]) -> dict[str, Any]:
    sample = int(b.get("sample_size") or 0)
    real_n = int(b.get("real_quote_count") or 0)
    der_n = int(b.get("derived_quote_count") or 0)
    unavail = int(b.get("unavailable_quote_count") or 0)
    ok = real_n + der_n + unavail == sample
    return {
        "market_rows": sample,
        "real_quote_count": real_n,
        "derived_quote_count": der_n,
        "unavailable_quote_count": unavail,
        "quote_count_reconciliation_ok": ok,
    }


def agg_bucket() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "won": 0,
        "lost": 0,
        "hit_rate": None,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "unavailable_quote_count": 0,
        "with_cecchino_probability": 0,
        "with_cecchino_fair_quote": 0,
        # Alias compat: same as with_cecchino_fair_quote (quota_cecchino), non probabilità.
        "with_cecchino_quote": 0,
        "with_rating": 0,
        "with_signal_active": 0,
        "real_profit_1u": 0.0,
        "real_roi_pct": None,
        "synthetic_profit_1u": 0.0,
        "synthetic_roi_pct": None,
        "competitions": set(),
        "warnings": [],
        "prob_sum": 0.0,
        "prob_count": 0,
        "rating_sum": 0.0,
        "rating_count": 0,
        "odds_real_sum": 0.0,
        "odds_real_n": 0,
        "odds_derived_sum": 0.0,
        "odds_derived_n": 0,
        "probs": [],
    }


def _apply_quote_and_eval_to_bucket(b: dict[str, Any], m: CecchinoLabHistoricalMarketResult) -> None:
    if m.is_real_book_quote:
        b["real_quote_count"] += 1
        if m.profit_1u_real is not None:
            b["real_profit_1u"] += float(m.profit_1u_real)
        if is_valid_book_odds(m.quota_book):
            b["odds_real_sum"] += float(m.quota_book)
            b["odds_real_n"] += 1
    elif m.is_derived_quote:
        b["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)
        if is_valid_book_odds(m.quota_book):
            b["odds_derived_sum"] += float(m.quota_book)
            b["odds_derived_n"] += 1
    else:
        b["unavailable_quote_count"] += 1

    if m.quota_cecchino is not None:
        b["with_cecchino_fair_quote"] += 1
        b["with_cecchino_quote"] += 1  # alias
    if m.prob_cecchino is not None:
        p = float(m.prob_cecchino)
        b["with_cecchino_probability"] += 1
        b["prob_sum"] += p
        b["prob_count"] += 1
        b["probs"].append(p)
    if m.rating is not None:
        b["with_rating"] += 1
        b["rating_sum"] += float(m.rating)
        b["rating_count"] += 1
    if m.signal_active:
        b["with_signal_active"] += 1


def finalize_bucket(b: dict[str, Any]) -> dict[str, Any]:
    # Copia shallow per non corrompere bucket riusati (doppia finalize)
    b = dict(b)
    comps = b.pop("competitions", set()) or set()
    if isinstance(comps, list):
        comps = set(comps)
    n = int(b.get("won") or 0) + int(b.get("lost") or 0)
    b["hit_rate"] = round(b["won"] / n, 4) if n else None
    real_n = int(b.get("real_quote_count") or 0)
    der_n = int(b.get("derived_quote_count") or 0)
    if real_n:
        b["real_roi_pct"] = round(100.0 * float(b.get("real_profit_1u") or 0) / real_n, 2)
    else:
        b["real_roi_pct"] = None
    if der_n:
        b["synthetic_roi_pct"] = round(
            100.0 * float(b.get("synthetic_profit_1u") or 0) / der_n, 2
        )
    else:
        b["synthetic_roi_pct"] = None
    b["competitions_count"] = len(comps) if not isinstance(comps, int) else comps
    if isinstance(comps, set):
        b["competitions"] = sorted(comps)
    elif isinstance(comps, list):
        b["competitions"] = comps
    else:
        b["competitions"] = b.get("competitions") or []
    warnings = list(b.get("warnings") or [])
    if n < 30 and "small_sample" not in warnings:
        warnings.append("small_sample")
    b["warnings"] = warnings
    if real_n:
        b["real_profit_1u"] = round(float(b.get("real_profit_1u") or 0), 4)
    else:
        b["real_profit_1u"] = None
    if der_n:
        b["synthetic_profit_1u"] = round(float(b.get("synthetic_profit_1u") or 0), 4)
    else:
        b["synthetic_profit_1u"] = None
    b["confidence_status"] = confidence_status(int(b.get("sample_size") or 0))
    if b.get("prob_count"):
        b["average_cecchino_probability"] = round(
            float(b.get("prob_sum") or 0) / b["prob_count"], 6
        )
    else:
        b["average_cecchino_probability"] = None
    probs = b.pop("probs", None) or []
    if probs:
        sp = sorted(probs)
        mid = len(sp) // 2
        b["median_cecchino_probability"] = (
            sp[mid] if len(sp) % 2 else round((sp[mid - 1] + sp[mid]) / 2, 6)
        )
    else:
        b["median_cecchino_probability"] = None
    if b.get("rating_count"):
        b["average_rating"] = round(float(b.get("rating_sum") or 0) / b["rating_count"], 2)
    else:
        b["average_rating"] = None
    odds_real_n = int(b.get("odds_real_n") or 0)
    odds_der_n = int(b.get("odds_derived_n") or 0)
    if odds_real_n > 0:
        b["average_real_odds"] = round(float(b.get("odds_real_sum") or 0) / odds_real_n, 3)
    else:
        b["average_real_odds"] = None
    if odds_der_n > 0:
        b["average_derived_odds"] = round(float(b.get("odds_derived_sum") or 0) / odds_der_n, 3)
    else:
        b["average_derived_odds"] = None
    recon = quote_count_reconciliation(b)
    b["quote_count_reconciliation_ok"] = recon["quote_count_reconciliation_ok"]
    for k in (
        "prob_sum",
        "prob_count",
        "rating_sum",
        "rating_count",
        "odds_real_sum",
        "odds_real_n",
        "odds_derived_sum",
        "odds_derived_n",
    ):
        b.pop(k, None)
    hit = b["hit_rate"]
    avg_p = b.get("average_cecchino_probability")
    if hit is not None and avg_p is not None:
        b["calibration_gap"] = round(float(avg_p) - float(hit), 4)
    else:
        b["calibration_gap"] = None
    b["analytics_aggregation_version"] = ANALYTICS_AGGREGATION_VERSION
    return b


def rating_band(rating: Any) -> str | None:
    """Fascia a decade stile report: 0-9 … 90-99, poi 100 esclusivo (mai 100-109)."""
    if rating is None:
        return None
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(r):
        return None
    if r >= 100:
        return "100"
    if r < 0:
        return None
    base = int(r // 10) * 10
    return f"{base}-{base + 9}"


def rating_band_dashboard(rating: Any) -> str:
    """Fasce dashboard: lt_50, 50-59 … 90-99, 100, unavailable."""
    if rating is None:
        return "unavailable"
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return "unavailable"
    if not math.isfinite(r):
        return "unavailable"
    if r < 50:
        return "lt_50"
    if r < 60:
        return "50-59"
    if r < 70:
        return "60-69"
    if r < 80:
        return "70-79"
    if r < 90:
        return "80-89"
    if r < 100:
        return "90-99"
    return "100"


def purchasability_band_dashboard(score: Any) -> str:
    """Fasce granulari 0-9 … 90-99, 100, unavailable."""
    if score is None:
        return "unavailable"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "unavailable"
    if s >= 100:
        return "100"
    if s < 0:
        return "unavailable"
    base = int(s // 10) * 10
    return f"{base}-{base + 9}"


def purchasability_band_report(score: Any) -> str:
    """Fasce grosse usate nei pattern del report AI."""
    if score is None:
        return "no_purch"
    try:
        ps = float(score)
    except (TypeError, ValueError):
        return "no_purch"
    if ps < 20:
        return "0-19"
    if ps < 40:
        return "20-39"
    if ps < 60:
        return "40-59"
    if ps < 80:
        return "60-79"
    return "80-100"


def edge_band(edge_pct: Any) -> str | None:
    if edge_pct is None:
        return None
    try:
        e = float(edge_pct)
    except (TypeError, ValueError):
        return None
    if e < 0:
        return "neg"
    if e < 5:
        return "0-5"
    if e < 10:
        return "5-10"
    return "10+"


def signal_meta(sources_json: Any) -> dict[str, Any]:
    if isinstance(sources_json, dict):
        families = sources_json.get("signal_families")
        sources = sources_json.get("sources")
        return {
            "signal_family": sources_json.get("signal_family"),
            "signal_families": as_list(families),
            "active_signal_count": int(sources_json.get("active_signal_count") or 0),
            "sources": as_list(sources),
        }
    if isinstance(sources_json, list):
        return {
            "signal_family": None,
            "signal_families": [],
            "active_signal_count": len(sources_json),
            "sources": sources_json,
        }
    return {
        "signal_family": None,
        "signal_families": [],
        "active_signal_count": 0,
        "sources": [],
    }


def structural_class(structural: Any) -> tuple[str, str | None]:
    if isinstance(structural, dict):
        raw = structural.get("class")
        if raw is None or raw == "":
            raw = structural.get("class_key")
        if raw is None or raw == "":
            return "unknown", None
        return str(raw), None
    if isinstance(structural, str):
        text = structural.strip()
        if text:
            return text, None
        return "unknown", "empty_structural_summary_string"
    if structural is None:
        return "unknown", None
    return "unknown", f"unexpected_structural_summary_type:{type(structural).__name__}"


def balance_pillars(balance: Any) -> dict[str, Any]:
    bal = as_dict(balance)
    if not bal:
        return {}
    pillars: dict[str, Any] = {}
    nested = as_dict(bal.get("pillars"))
    for key in BALANCE_CANONICAL_PILLARS:
        block = nested.get(key) if nested else None
        if not isinstance(block, dict):
            block = bal.get(key)
        if isinstance(block, dict):
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label") or BALANCE_PILLAR_LABELS.get(key),
                "value": block.get("value")
                or block.get("score")
                or block.get("f36_abs")
                or block.get("raw_value"),
                "score": block.get("score") or block.get("value"),
            }
    for key in (
        "f36",
        "side_probability_gap",
        "draw",
        "operational",
        "structural_summary",
        "dominance",
        "draw_credibility",
        "gap_coherence",
    ):
        if key in pillars:
            continue
        block = bal.get(key)
        if isinstance(block, dict):
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label"),
                "value": block.get("value") or block.get("score") or block.get("f36_abs"),
                "score": block.get("score") or block.get("value"),
            }
        elif isinstance(block, str) and block.strip() and key == "structural_summary":
            pillars[key] = {
                "class_key": block.strip(),
                "label": None,
                "value": None,
                "score": None,
            }
    for key, block in bal.items():
        if key in pillars or not isinstance(block, dict):
            continue
        if "class_key" in block or "class" in block:
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label"),
                "value": block.get("value") or block.get("score"),
                "score": block.get("score") or block.get("value"),
            }
    return pillars


def conditions_are_absence_only(conditions: dict[str, Any]) -> bool:
    """True se le condizioni informative sono assenze dati (no_rating, no_purch, …)."""
    informative = {
        k: v
        for k, v in conditions.items()
        if k not in ("market_key", "model_key", "competition_name", "signal_family")
        and v is not None
    }
    if not informative:
        return True
    for k, v in informative.items():
        sv = str(v)
        if k in ABSENCE_CONDITION_KEYS and sv in ABSENCE_CONDITION_VALUES:
            continue
        if sv in ABSENCE_CONDITION_VALUES:
            continue
        return False
    return True


def is_signal_off_control(conditions: dict[str, Any]) -> bool:
    """signal_off come controllo esplicito sullo stesso market_key."""
    return (
        conditions.get("signal") == "signal_off"
        and conditions.get("market_key") is not None
        and "rating_band" not in conditions
        and "purchasability_band" not in conditions
    )


def pattern_status(
    *,
    real_quote_count: int,
    competitions_count: int,
    competition_shares: dict[str, int],
    market_key: str | None = None,
    is_diagnostic: bool = False,
    main_competition_share: float | None = None,
    temporal_concentrated: bool = False,
    conditions_informative: bool = True,
    sample_size: int | None = None,  # compat: ignorato se real_quote_count passato
) -> str:
    """Classificazione campione pattern basata su quote reali."""
    del sample_size  # non usare sample_size grezzo per candidatura
    if is_diagnostic or not conditions_informative:
        return "coverage_diagnostic"
    if market_key is None:
        return "descriptive_only"
    if real_quote_count < 30:
        return "small_sample"
    if real_quote_count < 100:
        return "exploratory_only"
    if real_quote_count < 200:
        return "descriptive_only"

    share = main_competition_share
    if share is None and competition_shares and real_quote_count:
        top = max(competition_shares.values())
        share = top / max(sum(competition_shares.values()), 1)

    if competitions_count < 3:
        return "descriptive_only"
    if share is not None and share > 0.60:
        return "descriptive_only"
    if temporal_concentrated:
        return "descriptive_only"
    return "candidate_for_validation"


def add_market_row(
    buckets: dict[str, dict[str, dict[str, Any]]],
    dim: str,
    key: str,
    m: CecchinoLabHistoricalMarketResult,
    competition_name: str | None,
) -> None:
    b = buckets[dim][key]
    b["sample_size"] += 1
    if competition_name:
        b["competitions"].add(competition_name)
    if m.won is True:
        b["won"] += 1
    elif m.won is False:
        b["lost"] += 1
    _apply_quote_and_eval_to_bucket(b, m)


def bump_bucket_from_market(
    b: dict[str, Any],
    m: CecchinoLabHistoricalMarketResult,
    competition_name: str | None = None,
) -> None:
    """Incrementa un singolo bucket (senza dict dimensionale)."""
    b["sample_size"] += 1
    if competition_name:
        b["competitions"].add(competition_name)
    if m.won is True:
        b["won"] += 1
    elif m.won is False:
        b["lost"] += 1
    _apply_quote_and_eval_to_bucket(b, m)


def pattern_accumulator() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "wins": 0,
        "losses": 0,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "unavailable_quote_count": 0,
        "real_profit": 0.0,
        "synthetic_profit": 0.0,
        "competitions": defaultdict(int),
        "competition_real_n": defaultdict(int),
        "competition_real_profit": defaultdict(float),
        "temporal_points": [],  # (kickoff iso or None, profit)
    }


def bump_pattern(
    acc: dict[str, Any],
    m: CecchinoLabHistoricalMarketResult,
    comp: str | None,
    *,
    kickoff_at: Any = None,
) -> None:
    acc["sample_size"] += 1
    if comp:
        acc["competitions"][comp] += 1
    if m.won is True:
        acc["wins"] += 1
    elif m.won is False:
        acc["losses"] += 1
    if m.is_real_book_quote:
        acc["real_quote_count"] += 1
        profit = float(m.profit_1u_real) if m.profit_1u_real is not None else 0.0
        if m.profit_1u_real is not None:
            acc["real_profit"] += profit
        if comp:
            acc["competition_real_n"][comp] += 1
            if m.profit_1u_real is not None:
                acc["competition_real_profit"][comp] += profit
        acc["temporal_points"].append((kickoff_at, profit if m.profit_1u_real is not None else None))
    elif m.is_derived_quote:
        acc["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            acc["synthetic_profit"] += float(m.profit_1u_synthetic)
    else:
        acc["unavailable_quote_count"] += 1


def _roi_sign(roi: float | None, eps: float = 0.5) -> str:
    if roi is None:
        return "neutral"
    if roi > eps:
        return "positive"
    if roi < -eps:
        return "negative"
    return "neutral"


def _compute_temporal_halves(
    points: list[tuple[Any, float | None]],
) -> tuple[float | None, float | None, bool, bool]:
    """Ritorna (first_half_roi, second_half_roi, sign_consistent, concentrated)."""
    dated = []
    for ko, profit in points:
        if profit is None:
            continue
        if isinstance(ko, datetime):
            dated.append((ko, float(profit)))
        elif ko is not None:
            try:
                # string iso
                dated.append((datetime.fromisoformat(str(ko).replace("Z", "+00:00")), float(profit)))
            except (TypeError, ValueError):
                continue
    if len(dated) < 4:
        return None, None, False, False
    dated.sort(key=lambda x: x[0])
    mid = len(dated) // 2
    first = dated[:mid]
    second = dated[mid:]
    if not first or not second:
        return None, None, False, False

    def _half_roi(rows: list[tuple[Any, float]]) -> float | None:
        if not rows:
            return None
        return round(100.0 * sum(p for _, p in rows) / len(rows), 2)

    r1 = _half_roi(first)
    r2 = _half_roi(second)
    s1 = _roi_sign(r1)
    s2 = _roi_sign(r2)
    sign_ok = s1 == s2 and s1 != "neutral"

    total_abs = sum(abs(p) for _, p in dated) or 1.0
    # finestre ~25% della timeline: se una finestra ha >60% del |profit| → concentrato
    window = max(1, len(dated) // 4)
    concentrated = False
    for i in range(0, len(dated) - window + 1):
        w_abs = sum(abs(p) for _, p in dated[i : i + window])
        if w_abs / total_abs > 0.60:
            concentrated = True
            break
    return r1, r2, sign_ok, concentrated


def compute_cross_competition_stability(
    *,
    real_quote_count: int,
    competitions: dict[str, int],
    competition_real_n: dict[str, int],
    competition_real_profit: dict[str, float],
    temporal_points: list[tuple[Any, float | None]],
    overall_real_roi: float | None,
) -> dict[str, Any]:
    comps_count = len(competitions)
    sample_for_share = sum(competitions.values()) or 1
    shares = {k: round(v / sample_for_share, 4) for k, v in sorted(competitions.items())}
    main_share = max(shares.values()) if shares else 0.0

    pos = neg = neu = 0
    rois: list[tuple[int, float]] = []
    for c, n in competition_real_n.items():
        if n <= 0:
            continue
        profit = float(competition_real_profit.get(c) or 0)
        roi = 100.0 * profit / n
        rois.append((n, roi))
        sign = _roi_sign(roi)
        if sign == "positive":
            pos += 1
        elif sign == "negative":
            neg += 1
        else:
            neu += 1

    scored = pos + neg + neu
    positive_share = round(pos / scored, 4) if scored else None
    # direzione dominante rispetto all'overall
    overall_sign = _roi_sign(overall_real_roi)
    same_dir = 0
    if scored and overall_sign != "neutral":
        for n, roi in rois:
            if _roi_sign(roi) == overall_sign:
                same_dir += 1
        direction_share = same_dir / scored
    else:
        direction_share = 0.0

    # dispersione ROI pesata
    if rois:
        total_n = sum(n for n, _ in rois) or 1
        mean = sum(n * r for n, r in rois) / total_n
        var = sum(n * (r - mean) ** 2 for n, r in rois) / total_n
        dispersion = round(math.sqrt(var), 4)
    else:
        dispersion = None

    t1, t2, t_sign_ok, t_concentrated = _compute_temporal_halves(temporal_points)

    category = "insufficient_evidence"
    if real_quote_count < 30 or comps_count < 2:
        category = "insufficient_evidence"
    elif main_share > 0.60:
        category = "concentrated"
    elif scored >= 2 and direction_share < 0.5:
        category = "inconsistent"
    elif t1 is not None and t2 is not None and _roi_sign(t1) != _roi_sign(t2) and _roi_sign(t1) != "neutral":
        category = "inconsistent"
    elif (
        real_quote_count >= 200
        and comps_count >= 5
        and main_share <= 0.40
        and direction_share >= 0.65
        and t_sign_ok
        and not t_concentrated
    ):
        category = "stable_candidate"
    elif scored >= 2 and direction_share >= 0.65 and (t_sign_ok or t1 is None):
        category = "directionally_consistent"
    elif main_share > 0.40 and comps_count >= 2:
        category = "concentrated"
    else:
        category = "insufficient_evidence"

    return {
        "competitions_count": comps_count,
        "main_competition_share": main_share,
        "competition_shares": shares,
        "top_competition_share": main_share,
        "competitions_positive": pos,
        "competitions_negative": neg,
        "competitions_neutral": neu,
        "weighted_roi_dispersion": dispersion,
        "positive_competition_share": positive_share,
        "same_direction_competition_share": round(direction_share, 4) if scored else None,
        "temporal_first_half_roi": t1,
        "temporal_second_half_roi": t2,
        "temporal_sign_consistency": t_sign_ok,
        "temporal_profit_concentrated": t_concentrated,
        "cross_competition_stability": category,
        # legacy bool: True solo per stable_candidate (non chiamare "stabile" altrimenti)
        "stable_cross_competition": category == "stable_candidate",
    }


def finalize_pattern(
    pattern_id: str,
    conditions: dict[str, Any],
    acc: dict[str, Any],
    *,
    title: str | None = None,
    is_diagnostic: bool = False,
) -> dict[str, Any]:
    comps = dict(acc["competitions"])
    n = int(acc["wins"]) + int(acc["losses"])
    sample = int(acc["sample_size"])
    real_n = int(acc["real_quote_count"])
    derived_n = int(acc["derived_quote_count"])
    unavail_n = int(acc.get("unavailable_quote_count") or 0)
    real_profit = round(float(acc["real_profit"]), 4) if real_n else None
    synth_profit = round(float(acc["synthetic_profit"]), 4) if derived_n else None
    competitions_count = len(comps)
    real_roi = round(100.0 * float(real_profit) / real_n, 2) if real_n and real_profit is not None else None

    main_competition = None
    main_share = None
    if comps and sample:
        shares = {k: round(v / sample, 4) for k, v in sorted(comps.items())}
        top_key = max(comps.items(), key=lambda kv: kv[1])[0]
        main_competition = top_key
        main_share = shares.get(top_key)

    stability = compute_cross_competition_stability(
        real_quote_count=real_n,
        competitions=comps,
        competition_real_n=dict(acc.get("competition_real_n") or {}),
        competition_real_profit=dict(acc.get("competition_real_profit") or {}),
        temporal_points=list(acc.get("temporal_points") or []),
        overall_real_roi=real_roi,
    )
    temporal_concentrated = bool(stability.get("temporal_profit_concentrated"))
    informative = not conditions_are_absence_only(conditions)
    # signal_off control: diagnostica / controllo, non candidato
    diagnostic = is_diagnostic or conditions_are_absence_only(conditions)
    if is_signal_off_control(conditions):
        diagnostic = True

    status = pattern_status(
        real_quote_count=real_n,
        competitions_count=competitions_count,
        competition_shares=comps,
        market_key=conditions.get("market_key"),
        is_diagnostic=diagnostic,
        main_competition_share=main_share,
        temporal_concentrated=temporal_concentrated,
        conditions_informative=informative and not diagnostic,
    )

    limitations = [
        "Una sola stagione; pattern descrittivo non prescrittivo",
        "Non proporre modifiche automatiche a formule",
        "Pattern market-specific: non mescolare mercati indipendenti",
    ]
    if real_n < 30:
        limitations.append("Campione di quote reali insufficiente (<30)")
    elif real_n < 100:
        limitations.append("Solo esplorativo (30–99 quote reali)")
    elif real_n < 200:
        limitations.append("Solo descrittivo (100–199 quote reali)")
    if diagnostic:
        limitations.append("Condizione di assenza dati / diagnostica — non candidabile")
    if stability.get("cross_competition_stability") != "stable_candidate":
        limitations.append(
            f"Stabilità: {stability.get('cross_competition_stability')} (non usare il termine stabile)"
        )

    mk = conditions.get("market_key")
    auto_title = title
    if not auto_title:
        parts = [str(mk)] if mk else []
        for k, v in conditions.items():
            if k == "market_key":
                continue
            parts.append(f"{k}={v}")
        auto_title = " · ".join(parts) if parts else pattern_id.replace("__", " · ")

    return {
        "pattern_id": pattern_id,
        "title": auto_title,
        "conditions": conditions,
        "market_key": mk,
        "sample_size": sample,
        "wins": int(acc["wins"]),
        "losses": int(acc["losses"]),
        "hit_rate": round(acc["wins"] / n, 4) if n else None,
        "real_quote_count": real_n,
        "derived_quote_count": derived_n,
        "unavailable_quote_count": unavail_n,
        "real_profit": real_profit,
        "real_roi": real_roi,
        "synthetic_profit": synth_profit,
        "synthetic_roi": (
            round(100.0 * float(synth_profit) / derived_n, 2)
            if derived_n and synth_profit is not None
            else None
        ),
        "competitions_count": competitions_count,
        "main_competition": main_competition,
        "main_competition_share": main_share,
        "stability": stability,
        "stability_by_competition": stability,
        "cross_competition_stability": stability.get("cross_competition_stability"),
        "status": status,
        "is_diagnostic": diagnostic,
        "limitations": limitations,
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
    }


def _model_has_market_settlement(snap: Any, model_key: str, market_key: str) -> bool:
    if snap is None:
        return False
    sigs = as_dict(getattr(snap, "signals_json", None))
    models = as_dict(sigs.get("models"))
    mblock = as_dict(models.get(model_key))
    for sett in as_list(mblock.get("settlements")):
        if isinstance(sett, dict) and sett.get("target_market") == market_key:
            return True
    # fallback: sources on market row may list model
    return False


def build_combined_patterns(
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    snap_by_id: dict[int, Any],
    *,
    shape_warnings: list[str] | None = None,
    shape_warning_seen: set[str] | None = None,
) -> dict[str, Any]:
    """Logica deterministica pattern (identica al report AI). Sempre market-specific."""
    groups: dict[str, dict[str, Any]] = {}
    diag_groups: dict[str, dict[str, Any]] = {}
    warnings = shape_warnings if shape_warnings is not None else []
    seen = shape_warning_seen if shape_warning_seen is not None else set()

    def key_id(prefix: str, parts: list[str]) -> str:
        return prefix + "__" + "__".join(parts)

    def note_shape_warning(code: str | None) -> None:
        if not code:
            return
        if code in seen:
            return
        seen.add(code)
        warnings.append(code)

    def register(
        target: dict[str, dict[str, Any]],
        prefix: str,
        conditions: dict[str, Any],
        parts: list[Any],
        m: CecchinoLabHistoricalMarketResult,
        comp: str | None,
        kickoff: Any,
    ) -> None:
        assert "market_key" in conditions
        pid = key_id(prefix, [str(p) for p in parts])
        if pid not in target:
            target[pid] = {"conditions": conditions, "acc": pattern_accumulator()}
        bump_pattern(target[pid]["acc"], m, comp, kickoff_at=kickoff)

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        comp = s.competition_name if s else "unknown"
        kickoff = getattr(s, "kickoff_at", None) if s else None
        rb = rating_band(m.rating) or "no_rating"
        sig = signal_meta(m.signal_sources_json)
        fam = str(sig.get("signal_family") or ("active" if m.signal_active else "no_signal"))
        signal_flag = "signal_on" if m.signal_active else "signal_off"
        bal = as_dict(s.balance_v5_json) if s else {}
        bal_class, warn = structural_class(bal.get("structural_summary") if bal else None)
        note_shape_warning(warn)

        purch = as_dict(s.purchasability_compatibility_json) if s else {}
        purch_score = None
        for mk_row in purch.get("markets") or []:
            if isinstance(mk_row, dict) and mk_row.get("market_key") == m.market_key:
                purch_score = mk_row.get("score")
                break
        purch_band = purchasability_band_report(purch_score)

        gi = as_dict(s.goal_intensity_compatibility_json) if s else {}
        gi_pillars = as_dict(gi.get("pillars"))
        op_class = as_dict(gi_pillars.get("offensive_production")).get("class_key") or "no_gi"

        mk = m.market_key

        # --- performance patterns (informative) ---
        perf_combos: list[tuple[str, dict[str, Any], list[Any]]] = []
        if rb != "no_rating":
            perf_combos.append(
                ("market_rating", {"market_key": mk, "rating_band": rb}, [mk, rb])
            )
        if signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_signal",
                    {"market_key": mk, "signal": signal_flag, "signal_family": fam},
                    [mk, signal_flag, fam],
                )
            )
        if rb != "no_rating" and signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_rating_signal",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "signal": signal_flag,
                        "signal_family": fam,
                    },
                    [mk, rb, signal_flag, fam],
                )
            )
        perf_combos.append(
            (
                "market_balance",
                {"market_key": mk, "balance_class": bal_class},
                [mk, bal_class],
            )
        )
        if rb != "no_rating":
            perf_combos.append(
                (
                    "market_rating_balance",
                    {"market_key": mk, "rating_band": rb, "balance_class": bal_class},
                    [mk, rb, bal_class],
                )
            )
        if rb != "no_rating":
            perf_combos.append(
                (
                    "competition_market_rating",
                    {
                        "competition_name": comp,
                        "market_key": mk,
                        "rating_band": rb,
                    },
                    [comp or "unknown", mk, rb],
                )
            )
        if signal_flag == "signal_on":
            perf_combos.append(
                (
                    "competition_market_signal",
                    {
                        "competition_name": comp,
                        "market_key": mk,
                        "signal": signal_flag,
                    },
                    [comp or "unknown", mk, signal_flag],
                )
            )

        if purch_band != "no_purch" and rb != "no_rating":
            perf_combos.append(
                (
                    "market_rating_purchasability",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "purchasability_band": purch_band,
                    },
                    [mk, rb, purch_band],
                )
            )
        if rb != "no_rating" and op_class != "no_gi":
            perf_combos.append(
                (
                    "market_rating_intensity_op",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "offensive_production_class": str(op_class),
                    },
                    [mk, rb, str(op_class)],
                )
            )
        if purch_band != "no_purch":
            perf_combos.append(
                (
                    "market_purchasability_balance",
                    {
                        "market_key": mk,
                        "purchasability_band": purch_band,
                        "balance_class": bal_class,
                    },
                    [mk, purch_band, bal_class],
                )
            )
        if purch_band != "no_purch" and signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_purchasability_signal",
                    {
                        "market_key": mk,
                        "purchasability_band": purch_band,
                        "signal": signal_flag,
                    },
                    [mk, purch_band, signal_flag],
                )
            )
        if op_class != "no_gi" and signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_intensity_signal",
                    {
                        "market_key": mk,
                        "offensive_production_class": str(op_class),
                        "signal": signal_flag,
                    },
                    [mk, str(op_class), signal_flag],
                )
            )
        if op_class != "no_gi" and purch_band != "no_purch":
            perf_combos.append(
                (
                    "market_intensity_purchasability",
                    {
                        "market_key": mk,
                        "offensive_production_class": str(op_class),
                        "purchasability_band": purch_band,
                    },
                    [mk, str(op_class), purch_band],
                )
            )
        if rb != "no_rating" and purch_band != "no_purch" and signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_rating_purchasability_signal",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "purchasability_band": purch_band,
                        "signal": signal_flag,
                    },
                    [mk, rb, purch_band, signal_flag],
                )
            )
        if rb != "no_rating" and purch_band != "no_purch":
            perf_combos.append(
                (
                    "market_rating_purchasability_balance",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "purchasability_band": purch_band,
                        "balance_class": bal_class,
                    },
                    [mk, rb, purch_band, bal_class],
                )
            )
        if rb != "no_rating" and op_class != "no_gi" and signal_flag == "signal_on":
            perf_combos.append(
                (
                    "market_rating_intensity_signal",
                    {
                        "market_key": mk,
                        "rating_band": rb,
                        "offensive_production_class": str(op_class),
                        "signal": signal_flag,
                    },
                    [mk, rb, str(op_class), signal_flag],
                )
            )

        for model_key in ("A", "B", "C", "D", "E", "F"):
            if not _model_has_market_settlement(s, model_key, mk):
                # anche senza settlements_json: conta solo se signal sources citano il modello
                sources = sig.get("sources") or []
                cited = False
                for src in sources:
                    if not isinstance(src, dict):
                        continue
                    col = str(src.get("column_key") or src.get("source_column") or "")
                    if col == model_key or col.endswith(f"_{model_key}") or model_key in col:
                        cited = True
                        break
                if not cited:
                    continue
            perf_combos.append(
                (
                    "model_market",
                    {"model_key": model_key, "market_key": mk},
                    [model_key, mk],
                )
            )
            if rb != "no_rating":
                perf_combos.append(
                    (
                        "model_market_rating",
                        {"model_key": model_key, "market_key": mk, "rating_band": rb},
                        [model_key, mk, rb],
                    )
                )
            perf_combos.append(
                (
                    "model_market_balance",
                    {
                        "model_key": model_key,
                        "market_key": mk,
                        "balance_class": bal_class,
                    },
                    [model_key, mk, bal_class],
                )
            )

        for prefix, conditions, parts in perf_combos:
            register(groups, prefix, conditions, parts, m, comp, kickoff)

        # --- diagnostica / coverage ---
        if rb == "no_rating":
            register(
                diag_groups,
                "diag_no_rating",
                {"market_key": mk, "rating_band": "no_rating"},
                [mk, "no_rating"],
                m,
                comp,
                kickoff,
            )
        if purch_band == "no_purch":
            register(
                diag_groups,
                "diag_no_purch",
                {"market_key": mk, "purchasability_band": "no_purch"},
                [mk, "no_purch"],
                m,
                comp,
                kickoff,
            )
        if signal_flag == "signal_off":
            register(
                diag_groups,
                "diag_signal_off_control",
                {"market_key": mk, "signal": "signal_off", "control_vs": "signal_on"},
                [mk, "signal_off"],
                m,
                comp,
                kickoff,
            )
        if op_class == "no_gi":
            register(
                diag_groups,
                "diag_module_unavailable_gi",
                {"market_key": mk, "offensive_production_class": "no_gi"},
                [mk, "no_gi"],
                m,
                comp,
                kickoff,
            )

    patterns = [
        finalize_pattern(pid, g["conditions"], g["acc"], is_diagnostic=False)
        for pid, g in sorted(groups.items())
    ]
    diagnostic_patterns = [
        finalize_pattern(pid, g["conditions"], g["acc"], is_diagnostic=True)
        for pid, g in sorted(diag_groups.items())
    ]

    # verifica: nessun pattern performance senza market_key / multi-market
    for p in patterns:
        assert p.get("market_key") or (p.get("conditions") or {}).get("market_key")

    return {
        "patterns": patterns,
        "diagnostic_patterns": diagnostic_patterns,
        "coverage_diagnostics": diagnostic_patterns,
        "note": (
            "Descriptive only — no operational threshold or formula changes. "
            "Performance universe = eligible_core only. "
            "All performance patterns are market-specific. "
            "Absence conditions live under diagnostic_patterns."
        ),
        "status_thresholds": {
            "small_sample": "<30 real quotes",
            "exploratory_only": "30-99 real quotes",
            "descriptive_only": "100-199 real quotes or failed candidacy gates",
            "candidate_for_validation": (
                ">=200 real quotes, market_key, >=3 competitions, "
                "main_competition_share<=60%, not temporally concentrated, informative conditions"
            ),
        },
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
    }


def build_patterns_top(patterns: dict[str, Any]) -> dict[str, Any]:
    items = [
        p
        for p in (patterns.get("patterns") or [])
        if isinstance(p, dict) and not p.get("is_diagnostic")
    ]
    diagnostics = list(patterns.get("diagnostic_patterns") or patterns.get("coverage_diagnostics") or [])

    def _dedupe(seq: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for p in seq:
            pid = str(p.get("pattern_id"))
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            out.append(p)
            if len(out) >= PATTERNS_TOP_CAP:
                break
        return out

    largest = _dedupe(sorted(items, key=lambda p: int(p.get("real_quote_count") or 0), reverse=True))
    real_eligible = [
        p
        for p in items
        if int(p.get("real_quote_count") or 0) >= MIN_PATTERN_SAMPLE_FOR_REAL_ROI
        and p.get("real_roi") is not None
        and p.get("status") != "coverage_diagnostic"
    ]
    best_positive = _dedupe(
        sorted(real_eligible, key=lambda p: float(p.get("real_roi") or -1e9), reverse=True)
    )
    worst_negative = _dedupe(
        sorted(real_eligible, key=lambda p: float(p.get("real_roi") or 1e9))
    )
    unstable = _dedupe(
        [
            p
            for p in sorted(items, key=lambda x: int(x.get("real_quote_count") or 0), reverse=True)
            if as_dict(p.get("stability_by_competition") or p.get("stability")).get(
                "cross_competition_stability"
            )
            in ("inconsistent", "concentrated", "insufficient_evidence")
            and int(p.get("competitions_count") or 0) >= 2
        ]
    )
    return {
        "cap_per_category": PATTERNS_TOP_CAP,
        "min_sample_for_real_roi": MIN_PATTERN_SAMPLE_FOR_REAL_ROI,
        "largest_sample": largest,
        "best_positive_real_roi": best_positive,
        "worst_negative_real_roi": worst_negative,
        "unstable_cross_competition": unstable,
        "coverage_diagnostics": _dedupe(
            sorted(diagnostics, key=lambda x: int(x.get("sample_size") or 0), reverse=True)
        ),
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
        "note": (
            "Selezione deterministica non duplicata. "
            "ROI reale solo con campione e quote reali sufficienti. "
            "Diagnostiche assenze dati escluse da candidati."
        ),
    }


def group_patterns_for_dashboard(patterns: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Raggruppa pattern in positive / negative / watchlist / unstable / diagnostics."""
    items = [
        p
        for p in (patterns.get("patterns") or [])
        if isinstance(p, dict) and not p.get("is_diagnostic")
    ]
    diagnostics = [
        p
        for p in (patterns.get("diagnostic_patterns") or patterns.get("coverage_diagnostics") or [])
        if isinstance(p, dict)
    ]
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    watchlist: list[dict[str, Any]] = []
    unstable: list[dict[str, Any]] = []

    for p in items:
        stab = as_dict(p.get("stability") or p.get("stability_by_competition"))
        cat = stab.get("cross_competition_stability") or p.get("cross_competition_stability")
        roi = p.get("real_roi")
        real_n = int(p.get("real_quote_count") or 0)
        status = p.get("status")
        if cat in ("inconsistent", "concentrated") and int(p.get("competitions_count") or 0) >= 2:
            unstable.append(p)
            continue
        if status in ("small_sample", "exploratory_only", "coverage_diagnostic") or real_n < 30:
            watchlist.append(p)
            continue
        if roi is not None and float(roi) > 0 and real_n >= 30:
            positive.append(p)
        elif roi is not None and float(roi) < 0 and real_n >= 30:
            negative.append(p)
        else:
            watchlist.append(p)

    def _sort_roi(seq: list[dict[str, Any]], reverse: bool) -> list[dict[str, Any]]:
        return sorted(seq, key=lambda x: float(x.get("real_roi") or 0), reverse=reverse)[
            :PATTERNS_TOP_CAP
        ]

    return {
        "positive": _sort_roi(positive, True),
        "negative": _sort_roi(negative, False),
        "watchlist": sorted(
            watchlist, key=lambda x: int(x.get("real_quote_count") or 0), reverse=True
        )[:PATTERNS_TOP_CAP],
        "unstable": sorted(
            unstable, key=lambda x: int(x.get("real_quote_count") or 0), reverse=True
        )[:PATTERNS_TOP_CAP],
        "diagnostics": sorted(
            diagnostics, key=lambda x: int(x.get("sample_size") or 0), reverse=True
        )[:PATTERNS_TOP_CAP],
    }


def _cell_from_finalized(
    *,
    market_key: str,
    band: str,
    fb: dict[str, Any],
    result_missing: int = 0,
    average_purchasability: float | None = None,
) -> dict[str, Any]:
    return {
        "market_key": market_key,
        "band": band,
        "sample_size": fb["sample_size"],
        "wins": fb["won"],
        "losses": fb["lost"],
        "result_missing": result_missing,
        "hit_rate": fb["hit_rate"],
        "average_cecchino_probability": fb["average_cecchino_probability"],
        "average_rating": fb.get("average_rating"),
        "average_purchasability": average_purchasability,
        "real_quote_count": fb["real_quote_count"],
        "average_real_odds": fb["average_real_odds"],
        "real_profit_1u": fb["real_profit_1u"],
        "real_roi_pct": fb["real_roi_pct"],
        "derived_quote_count": fb["derived_quote_count"],
        "average_derived_odds": fb["average_derived_odds"],
        "synthetic_profit_1u": fb["synthetic_profit_1u"],
        "synthetic_roi_pct": fb["synthetic_roi_pct"],
        "unavailable_quote_count": fb["unavailable_quote_count"],
        "competitions_count": fb["competitions_count"],
        "confidence_status": fb["confidence_status"],
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
    }


def build_rating_by_market(
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    snap_by_id: dict[int, Any],
    *,
    market_order: tuple[str, ...] | list[str] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Aggregazione primaria Rating: market_key → fascia → metriche."""
    cells: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    missing: dict[tuple[str, str], int] = defaultdict(int)
    markets_seen: set[str] = set()
    for m in eligible_markets:
        band = rating_band_dashboard(m.rating)
        mk = str(m.market_key)
        markets_seen.add(mk)
        s = snap_by_id.get(int(m.match_snapshot_id))
        bump_bucket_from_market(cells[(mk, band)], m, s.competition_name if s else None)
        if m.won is None:
            missing[(mk, band)] += 1
    order = list(market_order) if market_order else sorted(markets_seen)
    for mk in markets_seen:
        if mk not in order:
            order.append(mk)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for mk in order:
        out[mk] = {}
        for band in RATING_BANDS_DASHBOARD:
            fb = finalize_bucket(cells.get((mk, band), agg_bucket()))
            out[mk][band] = _cell_from_finalized(
                market_key=mk,
                band=band,
                fb=fb,
                result_missing=int(missing.get((mk, band), 0)),
            )
    return out


def build_purchasability_by_market(
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    snap_by_id: dict[int, Any],
    *,
    market_order: tuple[str, ...] | list[str] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Aggregazione primaria Acquistabilità: market_key → fascia → metriche."""
    cells: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    missing: dict[tuple[str, str], int] = defaultdict(int)
    purch_sum: dict[tuple[str, str], float] = defaultdict(float)
    purch_n: dict[tuple[str, str], int] = defaultdict(int)
    markets_seen: set[str] = set()
    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        purch = as_dict(getattr(s, "purchasability_compatibility_json", None) if s else None)
        score = None
        for mk_row in purch.get("markets") or []:
            if isinstance(mk_row, dict) and mk_row.get("market_key") == m.market_key:
                score = mk_row.get("score")
                break
        band = purchasability_band_dashboard(score)
        mk = str(m.market_key)
        markets_seen.add(mk)
        bump_bucket_from_market(cells[(mk, band)], m, s.competition_name if s else None)
        if m.won is None:
            missing[(mk, band)] += 1
        if score is not None:
            try:
                purch_sum[(mk, band)] += float(score)
                purch_n[(mk, band)] += 1
            except (TypeError, ValueError):
                pass
    order = list(market_order) if market_order else sorted(markets_seen)
    for mk in markets_seen:
        if mk not in order:
            order.append(mk)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for mk in order:
        out[mk] = {}
        for band in PURCH_BANDS_DASHBOARD:
            fb = finalize_bucket(cells.get((mk, band), agg_bucket()))
            avg_p = None
            if purch_n.get((mk, band)):
                avg_p = round(purch_sum[(mk, band)] / purch_n[(mk, band)], 2)
            out[mk][band] = _cell_from_finalized(
                market_key=mk,
                band=band,
                fb=fb,
                result_missing=int(missing.get((mk, band), 0)),
                average_purchasability=avg_p,
            )
    return out


def max_losing_streak(won_flags: list[bool | None]) -> int:
    streak = 0
    best = 0
    for w in won_flags:
        if w is False:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def brier_score(probs: list[float], outcomes: list[int]) -> float | None:
    if not probs or len(probs) != len(outcomes):
        return None
    n = len(probs)
    if n == 0:
        return None
    return round(sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n, 6)
