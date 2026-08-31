"""Registry scientifico League Pattern Analysis — LN01–LN10, ipotesi, lessico umano.

Separato da P01–P12. Non modifica Pattern Lab operativo.
Hash LN congelati: qualsiasi modifica ai filtri deve fallire i test.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.cecchino_data_lab.pattern_lab_presets import (
    PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    scientific_filters_sha256,
)

ANALYSIS_VERSION = "league_pattern_analysis_v1"
ANALYSIS_REVISION = 1
MARKET_UNIVERSE_VERSION = "base_v1"

LOCKED_SOURCE_RUN_IDS: list[int] = [17, 19, 20, 21]
LOCKED_SEASONS: list[str] = [
    "2021/2022",
    "2022/2023",
    "2023/2024",
    "2024/2025",
]
SEASON_BY_RUN: dict[int, str] = {
    17: "2021/2022",
    19: "2022/2023",
    20: "2023/2024",
    21: "2024/2025",
}
FUTURE_OOS_SEASON = "2025/2026"
MIN_SAMPLE_TOP_INSIGHTS = 20
LOW_SAMPLE_N = 15

_BASE_OPS: dict[str, Any] = {
    "eligibility": "eligible_core",
    "market_informative": True,
}


def _with_base(filters: dict[str, Any]) -> dict[str, Any]:
    out = dict(_BASE_OPS)
    out.update(filters)
    return out


# Hash congelati dei soli filters LN (JSON canonico). Non ritoccare senza nuovo ID.
FROZEN_LN_SCIENTIFIC_FILTERS_SHA256: dict[str, str] = {
    "LN01": "29b5f86524aa1f3843082a3599a639a7d512dec76b0d494863f0d3ec4f67a296",
    "LN02": "5659af30e1f29a8c45354fb02220db43ca11117ded64a0a60b9f2d3a8b6e331c",
    "LN03": "ed7727a2bc1d02e2383cdd8087c91e5b5645e256b459698e122a7d2c37c85da6",
    "LN04": "45a872278d606d34f3e7c67240701126d5cb1e70ad0536f1b121bd00a4f63387",
    "LN05": "fc635ae5fbb9b9a56e1ec3f4eb2af609ce50378cc4a9f34683dc72085cf7dcaf",
    "LN06": "816d2e7c18b553ff5e0865af650a9231ccf671d87fd4640793df1ccdfa2455c1",
    "LN07": "63404fc310e29b376520a994bd520ca49918c8a0d803695cec6b503d073e97f6",
    "LN08": "013e3930fd081f778fda62b61f3c1dad62293be87ad74ed6f7d093b656948666",
    "LN09": "4799ca8e3de921ba5d6e35aa157070cf4bf93dbcad0ec81a22fd076a98779248",
    "LN10": "4ab1c769e7d1b0810dc1895473c9edc09425248b684131debdf06646a1f86e00",
}

LEAGUE_NATIVE_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "LN01",
        "human_title": "Vittoria ospite in partite a ritmo medio",
        "competition": "Championship",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Championship"],
                "market_keys": ["AWAY"],
                "goal_pillar_filters": {"match_tempo": {"class": "medium"}},
            }
        ),
    },
    {
        "id": "LN02",
        "human_title": "Vittoria ospite con solidità difensiva media",
        "competition": "Ligue 2",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Ligue 2"],
                "market_keys": ["AWAY"],
                "goal_pillar_filters": {"defensive_solidity": {"class": "medium"}},
            }
        ),
    },
    {
        "id": "LN03",
        "human_title": "Over 2.5 con produzione offensiva alta",
        "competition": "League One",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["League One"],
                "market_keys": ["OVER_2_5"],
                "goal_pillar_filters": {"offensive_production": {"class": "high"}},
            }
        ),
    },
    {
        "id": "LN04",
        "human_title": "Pareggio con acquistabilità medio-bassa",
        "competition": "Serie A",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Serie A"],
                "market_keys": ["DRAW"],
                "purchasability_v36_status": "score",
                "purchasability_v36_min": 30.0,
                "purchasability_v36_max": 40.0,
                "purchasability_v36_max_exclusive": True,
            }
        ),
    },
    {
        "id": "LN05",
        "human_title": "Pareggio in partite ad alto ritmo",
        "competition": "Serie A",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Serie A"],
                "market_keys": ["DRAW"],
                "goal_pillar_filters": {"match_tempo": {"class": "high"}},
            }
        ),
    },
    {
        "id": "LN06",
        "human_title": "Under 2.5 con stabilità offensiva molto bassa",
        "competition": "La Liga",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["La Liga"],
                "market_keys": ["UNDER_2_5"],
                "goal_pillar_filters": {"offensive_stability": {"class": "very_low"}},
            }
        ),
    },
    {
        "id": "LN07",
        "human_title": "Vittoria casa con stabilità offensiva media",
        "competition": "La Liga 2",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["La Liga 2"],
                "market_keys": ["HOME"],
                "goal_pillar_filters": {"offensive_stability": {"class": "medium"}},
            }
        ),
    },
    {
        "id": "LN08",
        "human_title": "Pareggio in partita lenta con bassa produzione offensiva",
        "competition": "Serie B",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Serie B"],
                "market_keys": ["DRAW"],
                "goal_pillar_filters": {
                    "offensive_production": {"class": "low"},
                    "match_tempo": {"class": "very_low"},
                },
            }
        ),
    },
    {
        "id": "LN09",
        "human_title": "Pareggio con profilo Goal basso e struttura di transizione",
        "competition": "Serie B",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Serie B"],
                "market_keys": ["DRAW"],
                "goal_final_class": "low",
                "balance_pillar_filters": {"f36": {"class": "transition"}},
            }
        ),
    },
    {
        "id": "LN10",
        "human_title": "Vittoria casa con acquistabilità bassa ma strutturalmente coerente",
        "competition": "Championship",
        "status": "candidate_oos_2025_26",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "internal_validation_seasons": ["2024/2025"],
        "first_true_oos_season": FUTURE_OOS_SEASON,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "competitions": ["Championship"],
                "market_keys": ["HOME"],
                "purchasability_v36_status": "score",
                "purchasability_v36_min": 20.0,
                "purchasability_v36_max": 30.0,
                "purchasability_v36_max_exclusive": True,
            }
        ),
    },
]

SPECIALIZATION_HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "SPEC_P01_CHAMPIONSHIP",
        "pattern_id": "P01",
        "competition": "Championship",
        "status": "league_specialization_candidate",
        "label": "Specializzazione da validare",
    },
    {
        "id": "SPEC_P09_SERIE_B",
        "pattern_id": "P09",
        "competition": "Serie B",
        "status": "league_specialization_candidate",
        "label": "Specializzazione da validare",
    },
    {
        "id": "SPEC_P09_LEAGUE_TWO",
        "pattern_id": "P09",
        "competition": "League Two",
        "status": "league_specialization_candidate",
        "label": "Specializzazione da validare",
    },
    {
        "id": "SPEC_P04_LEAGUE_TWO",
        "pattern_id": "P04",
        "competition": "League Two",
        "status": "league_specialization_candidate",
        "label": "Specializzazione da validare",
    },
]

INCOMPATIBILITY_HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "EXCL_P08_SERIE_A",
        "pattern_id": "P08",
        "competition": "Serie A",
        "status": "exclusion_hypothesis",
        "label": "Ipotesi di esclusione",
    },
    {
        "id": "EXCL_P06_SERIE_B",
        "pattern_id": "P06",
        "competition": "Serie B",
        "status": "exclusion_hypothesis",
        "label": "Ipotesi di esclusione",
    },
    {
        "id": "EXCL_P07_LA_LIGA_2",
        "pattern_id": "P07",
        "competition": "La Liga 2",
        "status": "exclusion_hypothesis",
        "label": "Ipotesi di esclusione",
    },
    {
        "id": "EXCL_P09_CHAMPIONSHIP",
        "pattern_id": "P09",
        "competition": "Championship",
        "status": "exclusion_hypothesis",
        "label": "Ipotesi di esclusione",
    },
]

# Lessico umano per spiegare formule tecniche (non altera i filtri).
HUMAN_TERM_LEXICON: dict[str, str] = {
    "offensive_production": "Produzione offensiva",
    "defensive_solidity": "Solidità difensiva",
    "match_tempo": "Ritmo della partita",
    "offensive_stability": "Stabilità offensiva",
    "goal_final_class": "Classe complessiva Goal",
    "f36": "Struttura Balance F36",
    "signal_active": "Segnale Cecchino attivo",
    "purchasability_v36": "Indice di Acquistabilità",
    "HOME": "Vittoria casa",
    "DRAW": "Pareggio",
    "AWAY": "Vittoria ospite",
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
    "very_low": "molto basso",
    "low": "basso",
    "medium": "medio",
    "high": "alto",
    "very_high": "molto alto",
    "transition": "transizione",
}


def ln_scientific_filters(pattern: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(pattern.get("filters") or {})


def list_league_native_patterns() -> list[dict[str, Any]]:
    out = []
    for p in LEAGUE_NATIVE_PATTERNS:
        item = deepcopy(p)
        filters = ln_scientific_filters(item)
        item["scientific_filters_sha256"] = scientific_filters_sha256(filters)
        out.append(item)
    return out


def get_league_native_pattern(pattern_id: str) -> dict[str, Any] | None:
    for p in list_league_native_patterns():
        if p["id"] == pattern_id:
            return p
    return None


def _class_it(value: str) -> str:
    return HUMAN_TERM_LEXICON.get(value, value.replace("_", " "))


def _market_it(key: str) -> str:
    return HUMAN_TERM_LEXICON.get(key, key)


def technical_formula_from_filters(filters: dict[str, Any]) -> str:
    """Formula tecnica compatta per audit (non inventata: deriva dai filtri)."""
    parts: list[str] = []
    markets = filters.get("market_keys") or []
    if markets:
        parts.append("+".join(str(m) for m in markets))
    if filters.get("goal_final_class"):
        parts.append(f"Goal Final={filters['goal_final_class']}")
    gp = filters.get("goal_pillar_filters") or {}
    if isinstance(gp, dict):
        for pillar, cfg in sorted(gp.items()):
            if isinstance(cfg, dict) and cfg.get("class"):
                short = {
                    "offensive_production": "OP",
                    "defensive_solidity": "DS",
                    "match_tempo": "Tempo",
                    "offensive_stability": "OS",
                }.get(pillar, pillar)
                parts.append(f"{short} {str(cfg['class']).upper()}")
    bp = filters.get("balance_pillar_filters") or {}
    if isinstance(bp, dict):
        f36 = bp.get("f36")
        if isinstance(f36, dict) and f36.get("class"):
            parts.append(f"F36 {f36['class']}")
    if filters.get("signal_active") is True:
        parts.append("signal_active")
    if filters.get("purchasability_v36_min") is not None:
        lo = filters.get("purchasability_v36_min")
        hi = filters.get("purchasability_v36_max")
        excl = filters.get("purchasability_v36_max_exclusive")
        bracket = f"[{lo},{hi})" if excl else f"[{lo},{hi}]"
        parts.append(f"V3.6 {bracket}")
    return " + ".join(parts) if parts else "—"


def humanize_filters(
    filters: dict[str, Any],
    *,
    pattern_id: str | None = None,
    human_title: str | None = None,
) -> dict[str, Any]:
    """Spiegazione umana da filtri registry (P* o LN*)."""
    conditions: list[dict[str, str]] = []
    markets = filters.get("market_keys") or []
    if markets:
        conditions.append(
            {
                "key": "market",
                "label": "Mercato",
                "value": ", ".join(_market_it(str(m)) for m in markets),
            }
        )
    comps = filters.get("competitions") or []
    if comps:
        conditions.append(
            {
                "key": "competition",
                "label": "Campionato",
                "value": ", ".join(str(c) for c in comps),
            }
        )
    if filters.get("goal_final_class"):
        conditions.append(
            {
                "key": "goal_final_class",
                "label": HUMAN_TERM_LEXICON["goal_final_class"],
                "value": _class_it(str(filters["goal_final_class"])),
            }
        )
    gp = filters.get("goal_pillar_filters") or {}
    if isinstance(gp, dict):
        for pillar, cfg in sorted(gp.items()):
            if isinstance(cfg, dict) and cfg.get("class"):
                conditions.append(
                    {
                        "key": pillar,
                        "label": HUMAN_TERM_LEXICON.get(pillar, pillar),
                        "value": _class_it(str(cfg["class"])),
                    }
                )
    bp = filters.get("balance_pillar_filters") or {}
    if isinstance(bp, dict):
        f36 = bp.get("f36")
        if isinstance(f36, dict) and f36.get("class"):
            conditions.append(
                {
                    "key": "f36",
                    "label": HUMAN_TERM_LEXICON["f36"],
                    "value": _class_it(str(f36["class"])),
                }
            )
    if filters.get("signal_active") is True:
        conditions.append(
            {
                "key": "signal_active",
                "label": HUMAN_TERM_LEXICON["signal_active"],
                "value": "attivo",
            }
        )
    if filters.get("purchasability_v36_min") is not None:
        lo = filters.get("purchasability_v36_min")
        hi = filters.get("purchasability_v36_max")
        excl = filters.get("purchasability_v36_max_exclusive")
        bracket = f"[{lo}, {hi})" if excl else f"[{lo}, {hi}]"
        conditions.append(
            {
                "key": "purchasability_v36",
                "label": HUMAN_TERM_LEXICON["purchasability_v36"],
                "value": bracket,
            }
        )

    title = human_title
    if not title:
        bits = [c["value"] for c in conditions if c["key"] != "competition"]
        title = (
            f"{pattern_id}: " + ", ".join(bits)
            if pattern_id and bits
            else (pattern_id or "Pattern")
        )

    market_label = _market_it(str(markets[0])) if markets else "mercato selezionato"
    pillar_bits = [
        f"{c['label'].lower()} {_class_it(c['value']) if c['key'] not in ('market', 'competition') else c['value']}"
        for c in conditions
        if c["key"] not in ("market", "competition")
    ]
    if pillar_bits:
        short = (
            f"Seleziona il mercato {market_label} quando "
            + " e ".join(pillar_bits)
            + "."
        )
    else:
        short = f"Seleziona il mercato {market_label} secondo i filtri del pattern."

    explanation = (
        "Cosa identifica: partite nelle quali i moduli Goal / Balance / Acquistabilità "
        f"soddisfano le condizioni del pattern. La combinazione viene valutata storicamente "
        f"sul mercato {market_label}."
    )

    return {
        "human_title": title,
        "short_explanation": short,
        "long_explanation": explanation,
        "structured_conditions": conditions,
        "technical_formula": technical_formula_from_filters(filters),
    }
