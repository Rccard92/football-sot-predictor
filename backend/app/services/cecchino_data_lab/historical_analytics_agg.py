"""Funzioni pure di aggregazione condivise tra report AI e dashboard run.

Nessuna scrittura DB. Nessuna dipendenza da Cecchino Today / Betfair operativo.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult

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

MIN_PATTERN_SAMPLE_FOR_REAL_ROI = 20
PATTERNS_TOP_CAP = 25
MIN_COMBO_SAMPLE = 30


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def confidence_status(sample_size: int) -> str:
    if sample_size < 30:
        return "small_sample"
    if sample_size < 100:
        return "descriptive_only"
    return "sufficient_sample"


def agg_bucket() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "won": 0,
        "lost": 0,
        "hit_rate": None,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "unavailable_quote_count": 0,
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
        "odds_derived_sum": 0.0,
        "probs": [],
    }


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
        b["real_roi_pct"] = b.get("real_roi_pct")
    if der_n:
        b["synthetic_roi_pct"] = round(
            100.0 * float(b.get("synthetic_profit_1u") or 0) / der_n, 2
        )
    else:
        b["synthetic_roi_pct"] = b.get("synthetic_roi_pct")
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
    b["real_profit_1u"] = round(float(b.get("real_profit_1u") or 0), 4)
    b["synthetic_profit_1u"] = round(float(b.get("synthetic_profit_1u") or 0), 4)
    b["confidence_status"] = confidence_status(int(b.get("sample_size") or 0))
    if b.get("prob_count"):
        b["average_cecchino_probability"] = round(
            float(b.get("prob_sum") or 0) / b["prob_count"], 6
        )
    else:
        b["average_cecchino_probability"] = b.get("average_cecchino_probability")
    probs = b.pop("probs", None) or []
    if probs:
        sp = sorted(probs)
        mid = len(sp) // 2
        b["median_cecchino_probability"] = (
            sp[mid] if len(sp) % 2 else round((sp[mid - 1] + sp[mid]) / 2, 6)
        )
    else:
        b["median_cecchino_probability"] = b.get("median_cecchino_probability")
    if b.get("rating_count"):
        b["average_rating"] = round(float(b.get("rating_sum") or 0) / b["rating_count"], 2)
    else:
        b["average_rating"] = b.get("average_rating")
    if real_n and "odds_real_sum" in b:
        b["average_real_odds"] = round(float(b["odds_real_sum"]) / real_n, 3)
    else:
        b["average_real_odds"] = b.get("average_real_odds")
    if der_n and "odds_derived_sum" in b:
        b["average_derived_odds"] = round(float(b["odds_derived_sum"]) / der_n, 3)
    else:
        b["average_derived_odds"] = b.get("average_derived_odds")
    for k in (
        "prob_sum",
        "prob_count",
        "rating_sum",
        "rating_count",
        "odds_real_sum",
        "odds_derived_sum",
    ):
        b.pop(k, None)
    hit = b["hit_rate"]
    avg_p = b.get("average_cecchino_probability")
    if hit is not None and avg_p is not None:
        b["calibration_gap"] = round(float(avg_p) - float(hit), 4)
    else:
        b["calibration_gap"] = b.get("calibration_gap")
    return b


def rating_band(rating: Any) -> str | None:
    """Fascia a decade stile report (0-9, 10-19, …)."""
    if rating is None:
        return None
    try:
        r = int(rating)
    except (TypeError, ValueError):
        return None
    base = (r // 10) * 10
    return f"{base}-{base + 9}"


def rating_band_dashboard(rating: Any) -> str:
    """Fasce dashboard: lt_50, 50-59 … 90-99, 100, unavailable."""
    if rating is None:
        return "unavailable"
    try:
        r = float(rating)
    except (TypeError, ValueError):
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
    # Legacy / extra keys
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


def pattern_status(
    *,
    sample_size: int,
    competitions_count: int,
    competition_shares: dict[str, int],
) -> str:
    if sample_size < 30:
        return "small_sample"
    if sample_size < 100:
        return "descriptive_only"
    if competitions_count <= 1:
        return "descriptive_only"
    if competition_shares:
        top = max(competition_shares.values())
        if top / max(sample_size, 1) >= 0.85:
            return "descriptive_only"
        if top < 15:
            return "descriptive_only"
    return "candidate_for_review"


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
    if m.is_real_book_quote:
        b["real_quote_count"] += 1
        if m.profit_1u_real is not None:
            b["real_profit_1u"] += float(m.profit_1u_real)
        if m.quota_book is not None:
            b["odds_real_sum"] += float(m.quota_book)
    elif m.is_derived_quote:
        b["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)
        if m.quota_book is not None:
            b["odds_derived_sum"] += float(m.quota_book)
    else:
        b["unavailable_quote_count"] += 1
    if m.quota_cecchino is not None:
        b["with_cecchino_quote"] += 1
    if m.prob_cecchino is not None:
        p = float(m.prob_cecchino)
        b["prob_sum"] += p
        b["prob_count"] += 1
        b["probs"].append(p)
    if m.rating is not None:
        b["with_rating"] += 1
        b["rating_sum"] += float(m.rating)
        b["rating_count"] += 1
    if m.signal_active:
        b["with_signal_active"] += 1


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
    if m.is_real_book_quote:
        b["real_quote_count"] += 1
        if m.profit_1u_real is not None:
            b["real_profit_1u"] += float(m.profit_1u_real)
        if m.quota_book is not None:
            b["odds_real_sum"] += float(m.quota_book)
    elif m.is_derived_quote:
        b["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)
        if m.quota_book is not None:
            b["odds_derived_sum"] += float(m.quota_book)
    else:
        b["unavailable_quote_count"] += 1
    if m.quota_cecchino is not None:
        b["with_cecchino_quote"] += 1
    if m.prob_cecchino is not None:
        p = float(m.prob_cecchino)
        b["prob_sum"] += p
        b["prob_count"] += 1
        b["probs"].append(p)
    if m.rating is not None:
        b["with_rating"] += 1
        b["rating_sum"] += float(m.rating)
        b["rating_count"] += 1
    if m.signal_active:
        b["with_signal_active"] += 1


def pattern_accumulator() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "wins": 0,
        "losses": 0,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "real_profit": 0.0,
        "synthetic_profit": 0.0,
        "competitions": defaultdict(int),
    }


def bump_pattern(
    acc: dict[str, Any], m: CecchinoLabHistoricalMarketResult, comp: str | None
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
        if m.profit_1u_real is not None:
            acc["real_profit"] += float(m.profit_1u_real)
    elif m.is_derived_quote:
        acc["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            acc["synthetic_profit"] += float(m.profit_1u_synthetic)


def finalize_pattern(
    pattern_id: str,
    conditions: dict[str, Any],
    acc: dict[str, Any],
    *,
    title: str | None = None,
) -> dict[str, Any]:
    comps = dict(acc["competitions"])
    n = int(acc["wins"]) + int(acc["losses"])
    sample = int(acc["sample_size"])
    real_n = int(acc["real_quote_count"])
    derived_n = int(acc["derived_quote_count"])
    real_profit = round(float(acc["real_profit"]), 4)
    synth_profit = round(float(acc["synthetic_profit"]), 4)
    competitions_count = len(comps)
    status = pattern_status(
        sample_size=sample,
        competitions_count=competitions_count,
        competition_shares=comps,
    )
    main_competition = None
    main_share = None
    stability = None
    if comps and sample:
        shares = {k: round(v / sample, 4) for k, v in sorted(comps.items())}
        top_key = max(comps.items(), key=lambda kv: kv[1])[0]
        main_competition = top_key
        main_share = shares.get(top_key)
        top_share = max(shares.values()) if shares else 0
        stability = {
            "competition_shares": shares,
            "top_competition_share": top_share,
            "stable_cross_competition": competitions_count >= 2 and top_share < 0.7,
        }
    return {
        "pattern_id": pattern_id,
        "title": title or pattern_id.replace("__", " · "),
        "conditions": conditions,
        "sample_size": sample,
        "wins": int(acc["wins"]),
        "losses": int(acc["losses"]),
        "hit_rate": round(acc["wins"] / n, 4) if n else None,
        "real_quote_count": real_n,
        "derived_quote_count": derived_n,
        "real_profit": real_profit,
        "real_roi": round(100.0 * real_profit / real_n, 2) if real_n else None,
        "synthetic_profit": synth_profit,
        "synthetic_roi": round(100.0 * synth_profit / derived_n, 2) if derived_n else None,
        "competitions_count": competitions_count,
        "main_competition": main_competition,
        "main_competition_share": main_share,
        "stability": stability,
        "stability_by_competition": stability,
        "status": status,
        "limitations": [
            "Una sola stagione; pattern descrittivo non prescrittivo",
            "Non proporre modifiche automatiche a formule",
        ],
    }


def build_combined_patterns(
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    snap_by_id: dict[int, Any],
    *,
    shape_warnings: list[str] | None = None,
    shape_warning_seen: set[str] | None = None,
) -> dict[str, Any]:
    """Logica deterministica pattern (identica al report AI)."""
    groups: dict[str, dict[str, Any]] = {}
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

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        comp = s.competition_name if s else "unknown"
        rb = rating_band(m.rating) or "no_rating"
        sig = signal_meta(m.signal_sources_json)
        fam = str(sig.get("signal_family") or ("active" if m.signal_active else "no_signal"))
        signal_flag = "signal_on" if m.signal_active else "signal_off"
        bal = as_dict(s.balance_v5_json) if s else {}
        bal_class, warn = structural_class(bal.get("structural_summary") if bal else None)
        note_shape_warning(warn)

        combos: list[tuple[str, dict[str, Any], list[Any]]] = [
            ("market_rating", {"market_key": m.market_key, "rating_band": rb}, [m.market_key, rb]),
            (
                "market_signal",
                {"market_key": m.market_key, "signal": signal_flag, "signal_family": fam},
                [m.market_key, signal_flag, fam],
            ),
            (
                "market_rating_signal",
                {
                    "market_key": m.market_key,
                    "rating_band": rb,
                    "signal": signal_flag,
                    "signal_family": fam,
                },
                [m.market_key, rb, signal_flag, fam],
            ),
            (
                "market_balance",
                {"market_key": m.market_key, "balance_class": bal_class},
                [m.market_key, bal_class],
            ),
            (
                "market_rating_balance",
                {"market_key": m.market_key, "rating_band": rb, "balance_class": bal_class},
                [m.market_key, rb, bal_class],
            ),
            (
                "competition_market_rating",
                {
                    "competition_name": comp,
                    "market_key": m.market_key,
                    "rating_band": rb,
                },
                [comp or "unknown", m.market_key, rb],
            ),
            (
                "competition_market_signal",
                {
                    "competition_name": comp,
                    "market_key": m.market_key,
                    "signal": signal_flag,
                },
                [comp or "unknown", m.market_key, signal_flag],
            ),
        ]

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

        combos.extend(
            [
                (
                    "rating_purchasability",
                    {"rating_band": rb, "purchasability_band": purch_band},
                    [rb, purch_band],
                ),
                (
                    "rating_intensity_op",
                    {"rating_band": rb, "offensive_production_class": str(op_class)},
                    [rb, str(op_class)],
                ),
                (
                    "purchasability_balance",
                    {"purchasability_band": purch_band, "balance_class": bal_class},
                    [purch_band, bal_class],
                ),
                (
                    "purchasability_signal",
                    {"purchasability_band": purch_band, "signal": signal_flag},
                    [purch_band, signal_flag],
                ),
                (
                    "intensity_signal",
                    {"offensive_production_class": str(op_class), "signal": signal_flag},
                    [str(op_class), signal_flag],
                ),
                (
                    "intensity_purchasability",
                    {
                        "offensive_production_class": str(op_class),
                        "purchasability_band": purch_band,
                    },
                    [str(op_class), purch_band],
                ),
                (
                    "rating_purchasability_signal",
                    {
                        "rating_band": rb,
                        "purchasability_band": purch_band,
                        "signal": signal_flag,
                    },
                    [rb, purch_band, signal_flag],
                ),
                (
                    "rating_purchasability_balance",
                    {
                        "rating_band": rb,
                        "purchasability_band": purch_band,
                        "balance_class": bal_class,
                    },
                    [rb, purch_band, bal_class],
                ),
                (
                    "rating_intensity_signal",
                    {
                        "rating_band": rb,
                        "offensive_production_class": str(op_class),
                        "signal": signal_flag,
                    },
                    [rb, str(op_class), signal_flag],
                ),
            ]
        )

        for model_key in ("A", "B", "C", "D", "E", "F"):
            combos.append(
                (
                    "model_market",
                    {"model_key": model_key, "market_key": m.market_key},
                    [model_key, m.market_key],
                )
            )
            combos.append(
                (
                    "model_rating",
                    {"model_key": model_key, "rating_band": rb},
                    [model_key, rb],
                )
            )
            combos.append(
                (
                    "model_balance",
                    {"model_key": model_key, "balance_class": bal_class},
                    [model_key, bal_class],
                )
            )
        for prefix, conditions, parts in combos:
            pid = key_id(prefix, [str(p) for p in parts])
            if pid not in groups:
                groups[pid] = {"conditions": conditions, "acc": pattern_accumulator()}
            bump_pattern(groups[pid]["acc"], m, comp)

    patterns = [
        finalize_pattern(pid, g["conditions"], g["acc"])
        for pid, g in sorted(groups.items())
    ]
    return {
        "patterns": patterns,
        "note": (
            "Descriptive only — no operational threshold or formula changes. "
            "Performance universe = eligible_core only."
        ),
        "status_thresholds": {
            "small_sample": "<30",
            "descriptive_only": "30-99 or unstable cross-competition",
            "candidate_for_review": ">=100 and not dominated by one competition",
        },
    }


def build_patterns_top(patterns: dict[str, Any]) -> dict[str, Any]:
    items = list(patterns.get("patterns") or [])

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

    largest = _dedupe(sorted(items, key=lambda p: int(p.get("sample_size") or 0), reverse=True))
    real_eligible = [
        p
        for p in items
        if int(p.get("sample_size") or 0) >= MIN_PATTERN_SAMPLE_FOR_REAL_ROI
        and int(p.get("real_quote_count") or 0) >= MIN_PATTERN_SAMPLE_FOR_REAL_ROI
        and p.get("real_roi") is not None
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
            for p in sorted(items, key=lambda x: int(x.get("sample_size") or 0), reverse=True)
            if as_dict(p.get("stability_by_competition") or p.get("stability")).get(
                "stable_cross_competition"
            )
            is False
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
        "note": (
            "Selezione deterministica non duplicata. "
            "ROI reale solo con campione e quote reali sufficienti."
        ),
    }


def group_patterns_for_dashboard(patterns: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Raggruppa pattern in positive / negative / watchlist / unstable."""
    items = [p for p in (patterns.get("patterns") or []) if isinstance(p, dict)]
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    watchlist: list[dict[str, Any]] = []
    unstable: list[dict[str, Any]] = []

    for p in items:
        stab = as_dict(p.get("stability") or p.get("stability_by_competition"))
        roi = p.get("real_roi")
        sample = int(p.get("sample_size") or 0)
        status = p.get("status")
        if stab.get("stable_cross_competition") is False and int(p.get("competitions_count") or 0) >= 2:
            unstable.append(p)
            continue
        if sample < 30 or status == "small_sample":
            watchlist.append(p)
            continue
        if roi is not None and float(roi) > 0 and int(p.get("real_quote_count") or 0) >= 20:
            positive.append(p)
        elif roi is not None and float(roi) < 0 and int(p.get("real_quote_count") or 0) >= 20:
            negative.append(p)
        else:
            watchlist.append(p)

    def _sort_roi(seq: list[dict[str, Any]], reverse: bool) -> list[dict[str, Any]]:
        return sorted(seq, key=lambda x: float(x.get("real_roi") or 0), reverse=reverse)[:PATTERNS_TOP_CAP]

    return {
        "positive": _sort_roi(positive, True),
        "negative": _sort_roi(negative, False),
        "watchlist": sorted(watchlist, key=lambda x: int(x.get("sample_size") or 0), reverse=True)[
            :PATTERNS_TOP_CAP
        ],
        "unstable": sorted(unstable, key=lambda x: int(x.get("sample_size") or 0), reverse=True)[
            :PATTERNS_TOP_CAP
        ],
    }


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


def quote_quality_of_market(m: CecchinoLabHistoricalMarketResult) -> str:
    if m.is_real_book_quote:
        return "real"
    if m.is_derived_quote:
        return "derived"
    return "unavailable"
