"""Export canonico segnali A–F: opportunità deduplicate vs celle legacy.

Read-only. Nessuna modifica a pesi, soglie, formule o settlement persistiti.
Il join a MarketResult arricchisce probabilità/quote Cecchino in fase di export.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Iterable

from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    get_cecchino_weight_model,
    model_meta_for_key,
    model_weights_json,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_target_mapping import (
    SIGNAL_GROUP_TO_MARKET_KEY,
    map_cecchino_signal_to_target,
)
from app.services.cecchino_data_lab.historical_analytics_agg import (
    agg_bucket,
    as_dict,
    as_list,
    bump_bucket_from_market,
    finalize_bucket,
    max_losing_streak,
    purchasability_band_report,
    quote_quality_of_market,
)

SIGNAL_EXPORT_SCHEMA_VERSION = "cecchino_lab_signal_export_v1"
CURRENT_MODEL_KEY = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY  # "F"

MARKET_JOIN_MATCHED = "matched"
MARKET_JOIN_MISSING = "missing_market_result"
MARKET_JOIN_AMBIGUOUS = "ambiguous_market_result"
MARKET_JOIN_INVALID = "invalid_market_mapping"

# Alias legacy → market_key canonico (nessun mapping divergente)
_MARKET_KEY_ALIASES: dict[str, str] = {
    "HOME": SEL_HOME,
    "1": SEL_HOME,
    "DRAW": SEL_DRAW,
    "X": SEL_DRAW,
    "AWAY": SEL_AWAY,
    "2": SEL_AWAY,
    "ONE_X": SEL_ONE_X,
    "1X": SEL_ONE_X,
    "X_TWO": SEL_X_TWO,
    "X2": SEL_X_TWO,
    "ONE_TWO": SEL_ONE_TWO,
    "12": SEL_ONE_TWO,
    "OVER": SEL_OVER_2_5,
    "OVER_2_5": SEL_OVER_2_5,
    "OVER25": SEL_OVER_2_5,
    "UNDER": SEL_UNDER_2_5,
    "UNDER_2_5": SEL_UNDER_2_5,
    "UNDER25": SEL_UNDER_2_5,
    "OVER_1_5": SEL_OVER_1_5,
    "UNDER_3_5": SEL_UNDER_3_5,
    "UNDER_UNDER_PT": SEL_UNDER_2_5,
    "OVER_OVER_PT": SEL_OVER_2_5,
}

_CANONICAL_MARKET_KEYS = frozenset(_MARKET_KEY_ALIASES.values()) | frozenset(
    SIGNAL_GROUP_TO_MARKET_KEY.values()
)


def normalize_signal_market_key(raw: Any) -> str | None:
    """Normalizza target_market / alias al market_key canonico. Puro e testato."""
    if raw is None:
        return None
    text = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    if not text:
        return None
    if text in _MARKET_KEY_ALIASES:
        return _MARKET_KEY_ALIASES[text]
    if text in _CANONICAL_MARKET_KEYS:
        return text
    # signal_group diretto
    if text in SIGNAL_GROUP_TO_MARKET_KEY:
        return SIGNAL_GROUP_TO_MARKET_KEY[text]
    return None


def build_opportunity_id(
    *,
    run_id: int,
    snapshot_id: int,
    model_key: str,
    market_key: str,
) -> str:
    return (
        f"run:{int(run_id)}:snapshot:{int(snapshot_id)}"
        f":model:{str(model_key).upper()}:market:{market_key}"
    )


def build_signal_cell_id(
    opportunity_id: str,
    *,
    signal_group: str | None,
    source_column: str | None,
    cell_key: str | None = None,
) -> str:
    parts = [
        opportunity_id,
        f"group:{signal_group or 'unknown'}",
        f"col:{source_column or 'unknown'}",
    ]
    if cell_key:
        parts.append(f"cell:{cell_key}")
    return ":".join(parts)


def signal_confidence_status(sample_size: int) -> str:
    """Soglie prudenti per aggregazioni cella/combinazione (descrittive)."""
    n = int(sample_size or 0)
    if n < 30:
        return "small_sample"
    if n < 100:
        return "exploratory_only"
    if n < 200:
        return "descriptive_only"
    return "candidate_for_validation"


def canonical_model_fields(model_key: str) -> dict[str, Any]:
    key = str(model_key).upper()
    meta = model_meta_for_key(key)
    model = get_cecchino_weight_model(key)
    return {
        "model_key": key,
        "model_label": str(meta.get("model_label") or model.get("label") or key),
        "model_short_label": str(model.get("short_label") or f"Modello {key}"),
        "weights_version": str(meta.get("weights_version") or ""),
        "weights": model_weights_json(key),
        "is_current_model": key == CURRENT_MODEL_KEY,
        "current_model_key": CURRENT_MODEL_KEY,
    }


def _compact_active_cell(cell: dict[str, Any], market_key: str | None) -> dict[str, Any]:
    signal_group = cell.get("signal_group")
    source_column = cell.get("source_column")
    cell_key = cell.get("row_key") or cell.get("cell_key") or cell.get("column_key")
    return {
        "signal_group": signal_group,
        "source_column": source_column,
        "cell_key": cell_key,
        "cell_label": cell.get("signal_label") or cell.get("cell_label"),
        "signal_family": cell.get("signal_family") or signal_group,
        "target_market": market_key or cell.get("target_market") or cell.get("target_market_key"),
        "raw_value": cell.get("raw_signal_value") or cell.get("raw_value"),
        "threshold": cell.get("threshold"),  # null se non persistito
        "comparison_operator": cell.get("comparison_operator"),
        "weight": cell.get("weight"),
        "weighted_contribution": cell.get("weighted_contribution"),
        "source_version": cell.get("source_version"),
    }


def _resolve_cell_market_key(cell: dict[str, Any]) -> tuple[str | None, str]:
    """Ritorna (market_key|None, join_hint)."""
    explicit = (
        cell.get("target_market")
        or cell.get("target_market_key")
        or cell.get("market_key")
    )
    if explicit is not None:
        mk = normalize_signal_market_key(explicit)
        if mk:
            return mk, MARKET_JOIN_MATCHED
        return None, MARKET_JOIN_INVALID

    signal_group = cell.get("signal_group")
    source_column = cell.get("source_column")
    if signal_group and source_column:
        target = map_cecchino_signal_to_target(str(signal_group), str(source_column))
        mk = normalize_signal_market_key(target.get("target_market_key"))
        if mk:
            return mk, MARKET_JOIN_MATCHED
        if target.get("target_market_key"):
            return None, MARKET_JOIN_INVALID
        return None, MARKET_JOIN_INVALID

    if signal_group:
        mk = normalize_signal_market_key(signal_group)
        if mk:
            return mk, MARKET_JOIN_MATCHED

    return None, MARKET_JOIN_INVALID


def group_model_opportunities(
    *,
    model_key: str,
    model_block: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Raggruppa celle attive per market_key.

    Preferisce active_signals; se vuoto usa settlements (compat legacy).
    """
    by_market: dict[str, dict[str, Any]] = {}
    active = as_list(model_block.get("active_signals"))
    settlements = as_list(model_block.get("settlements"))

    cells_source: list[dict[str, Any]] = []
    if active:
        cells_source = [c for c in active if isinstance(c, dict)]
    elif settlements:
        # Legacy: una settlement ≈ una cella
        for sett in settlements:
            if not isinstance(sett, dict):
                continue
            cells_source.append(
                {
                    "signal_group": sett.get("signal_family") or sett.get("signal_group"),
                    "signal_family": sett.get("signal_family"),
                    "source_column": sett.get("source_column"),
                    "row_key": sett.get("row_key"),
                    "target_market": sett.get("target_market") or sett.get("market_key"),
                    "raw_signal_value": "SI",
                    "signal_label": sett.get("signal_family"),
                }
            )

    for cell in cells_source:
        mk, status = _resolve_cell_market_key(cell)
        if not mk:
            # Opportunità audit con mapping invalido: chiave speciale
            inv_key = f"__invalid__:{cell.get('signal_group')}:{cell.get('source_column')}"
            bucket = by_market.setdefault(
                inv_key,
                {
                    "market_key": None,
                    "mapping_status": MARKET_JOIN_INVALID,
                    "cells": [],
                },
            )
            bucket["cells"].append(_compact_active_cell(cell, None))
            continue

        bucket = by_market.setdefault(
            mk,
            {
                "market_key": mk,
                "mapping_status": status,
                "cells": [],
            },
        )
        bucket["cells"].append(_compact_active_cell(cell, mk))

    return by_market


def index_markets_by_snap_key(
    markets: Iterable[Any],
) -> dict[tuple[int, str], list[Any]]:
    """Indice (snapshot_id, market_key) → lista market rows."""
    out: dict[tuple[int, str], list[Any]] = defaultdict(list)
    for m in markets:
        sid = int(getattr(m, "match_snapshot_id"))
        mk = str(getattr(m, "market_key"))
        out[(sid, mk)].append(m)
    return out


def join_market_result(
    markets_index: dict[tuple[int, str], list[Any]],
    *,
    snapshot_id: int,
    market_key: str | None,
    mapping_status: str,
) -> tuple[Any | None, str]:
    if mapping_status == MARKET_JOIN_INVALID or not market_key:
        return None, MARKET_JOIN_INVALID
    rows = markets_index.get((int(snapshot_id), str(market_key))) or []
    if not rows:
        return None, MARKET_JOIN_MISSING
    if len(rows) > 1:
        return rows[0], MARKET_JOIN_AMBIGUOUS
    return rows[0], MARKET_JOIN_MATCHED


def purchasability_for_market(snap: Any, market_key: str | None) -> dict[str, Any]:
    purch = as_dict(getattr(snap, "purchasability_compatibility_json", None))
    status = purch.get("historical_purchasability_status") or purch.get("execution_status")
    if not market_key:
        return {
            "purchasability_score": None,
            "purchasability_band": None,
            "purchasability_status": status,
        }
    for mk_row in purch.get("markets") or []:
        if isinstance(mk_row, dict) and mk_row.get("market_key") == market_key:
            score = mk_row.get("score")
            return {
                "purchasability_score": score,
                "purchasability_band": purchasability_band_report(score)
                if score is not None
                else None,
                "purchasability_status": mk_row.get("status") or status,
            }
    return {
        "purchasability_score": None,
        "purchasability_band": None,
        "purchasability_status": status,
    }


def _scores_from_result(snap: Any) -> dict[str, Any]:
    result = as_dict(getattr(snap, "result_json", None))
    ft = as_dict(result.get("fulltime"))
    ht = as_dict(result.get("halftime"))
    return {
        "home_score_ft": ft.get("home"),
        "away_score_ft": ft.get("away"),
        "home_score_ht": ht.get("home"),
        "away_score_ht": ht.get("away"),
    }


def _market_enrichment(m: Any | None, join_status: str) -> dict[str, Any]:
    if m is None or join_status in (MARKET_JOIN_MISSING, MARKET_JOIN_INVALID):
        return {
            "prob_cecchino": None,
            "quota_cecchino": None,
            "rating": None,
            "edge": None,
            "vantaggio_probabilistico": None,
            "quote_quality": None,
            "is_real_book_quote": None,
            "is_derived_quote": None,
            "real_book_odds": None,
            "derived_odds": None,
            "odds": None,
            "won": None,
            "evaluation_status": None,
            "result_reason": None,
            "profit_1u_real": None,
            "profit_1u_synthetic": None,
            "signal_active_current_F": None,
            "market_label": None,
            "period": None,
            "line": None,
        }

    real_odds = None
    derived_odds = None
    if getattr(m, "is_real_book_quote", False) and getattr(m, "quota_book", None) is not None:
        real_odds = float(m.quota_book)
    elif getattr(m, "is_derived_quote", False) and getattr(m, "quota_book", None) is not None:
        derived_odds = float(m.quota_book)

    return {
        "prob_cecchino": float(m.prob_cecchino) if m.prob_cecchino is not None else None,
        "quota_cecchino": float(m.quota_cecchino) if m.quota_cecchino is not None else None,
        "rating": int(m.rating) if m.rating is not None else None,
        "edge": float(m.edge_pct) if getattr(m, "edge_pct", None) is not None else None,
        "vantaggio_probabilistico": (
            float(m.vantaggio_prob) if getattr(m, "vantaggio_prob", None) is not None else None
        ),
        "quote_quality": quote_quality_of_market(m),
        "is_real_book_quote": bool(m.is_real_book_quote),
        "is_derived_quote": bool(m.is_derived_quote),
        "real_book_odds": real_odds,
        "derived_odds": derived_odds,
        "odds": float(m.quota_book) if m.quota_book is not None else None,
        "won": m.won,
        "evaluation_status": m.evaluation_status,
        "result_reason": m.result_reason,
        "profit_1u_real": float(m.profit_1u_real) if m.profit_1u_real is not None else None,
        "profit_1u_synthetic": (
            float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
        ),
        "signal_active_current_F": bool(m.signal_active),
        "market_label": m.market_label,
        "period": m.period,
        "line": m.line,
    }


def build_opportunity_row(
    *,
    run_id: int,
    snap: Any,
    model_key: str,
    market_bucket: dict[str, Any],
    markets_index: dict[tuple[int, str], list[Any]],
    model_opportunity_sets: dict[str, set[tuple[int, str]]],
) -> dict[str, Any]:
    """Costruisce una riga opportunità canonica."""
    mk = market_bucket.get("market_key")
    mapping_status = market_bucket.get("mapping_status") or MARKET_JOIN_MATCHED
    cells = list(market_bucket.get("cells") or [])
    snapshot_id = int(snap.id)
    opp_id = build_opportunity_id(
        run_id=run_id,
        snapshot_id=snapshot_id,
        model_key=model_key,
        market_key=mk or "INVALID",
    )

    market_obj, join_status = join_market_result(
        markets_index,
        snapshot_id=snapshot_id,
        market_key=mk,
        mapping_status=mapping_status,
    )
    enrich = _market_enrichment(market_obj, join_status)
    purch = purchasability_for_market(snap, mk)
    scores = _scores_from_result(snap)
    canon = canonical_model_fields(model_key)

    # Consensus: quanti modelli A–F hanno la stessa opportunità (snapshot, market)
    consensus_models: list[str] = []
    if mk:
        key = (snapshot_id, mk)
        for mk_model in CECCHINO_WEIGHT_MODEL_KEYS:
            if key in model_opportunity_sets.get(mk_model, set()):
                consensus_models.append(mk_model)
    consensus_models = sorted(set(consensus_models))

    active_in_f = False
    if mk:
        active_in_f = (snapshot_id, mk) in model_opportunity_sets.get(CURRENT_MODEL_KEY, set())

    # Escludi performance se join non matched
    performance_eligible = join_status == MARKET_JOIN_MATCHED and market_obj is not None
    if not performance_eligible:
        enrich = {
            **enrich,
            "won": None,
            "profit_1u_real": None,
            "profit_1u_synthetic": None,
            "prob_cecchino": enrich.get("prob_cecchino"),
            "quota_cecchino": enrich.get("quota_cecchino"),
        }
        # Se missing: metriche mercato null (già così). Se matched ambiguous: usa primo row.

    signal_family = None
    families = sorted(
        {str(c.get("signal_family")) for c in cells if c.get("signal_family")}
    )
    if len(families) == 1:
        signal_family = families[0]
    elif families:
        signal_family = "|".join(families)

    result_missing = enrich.get("won") is None and performance_eligible

    return {
        "row_granularity": "signal_opportunity",
        "opportunity_id": opp_id,
        "run_id": int(run_id),
        "snapshot_id": snapshot_id,
        "match_snapshot_id": snapshot_id,
        "lab_match_id": int(snap.lab_match_id),
        "dataset_id": int(snap.dataset_id) if getattr(snap, "dataset_id", None) is not None else None,
        "competition_name": snap.competition_name,
        "kickoff_at": snap.kickoff_at.isoformat() if getattr(snap, "kickoff_at", None) else None,
        "chronological_order": getattr(snap, "chronological_order", None),
        "home_team": snap.home_team,
        "away_team": snap.away_team,
        **scores,
        **canon,
        "market_key": mk,
        "target_market": mk,
        "market_label": enrich.get("market_label"),
        "signal_family": signal_family,
        "period": enrich.get("period"),
        "line": enrich.get("line"),
        "model_active": True,
        "active_cell_count": len(cells),
        "active_cells": cells,
        "active_signal_groups": sorted(
            {str(c.get("signal_group")) for c in cells if c.get("signal_group")}
        ),
        "active_source_columns": sorted(
            {str(c.get("source_column")) for c in cells if c.get("source_column")}
        ),
        "active_cell_labels": [
            c.get("cell_label") for c in cells if c.get("cell_label")
        ],
        "consensus_model_count": len(consensus_models),
        "consensus_models": consensus_models,
        "active_in_current_model_F": active_in_f,
        "overlap_with_current_model_F": bool(active_in_f),
        "prob_cecchino": enrich.get("prob_cecchino"),
        "quota_cecchino": enrich.get("quota_cecchino"),
        "rating": enrich.get("rating"),
        "edge": enrich.get("edge"),
        "vantaggio_probabilistico": enrich.get("vantaggio_probabilistico"),
        **purch,
        "quote_quality": enrich.get("quote_quality"),
        "is_real_book_quote": enrich.get("is_real_book_quote"),
        "is_derived_quote": enrich.get("is_derived_quote"),
        "real_book_odds": enrich.get("real_book_odds"),
        "derived_odds": enrich.get("derived_odds"),
        "won": enrich.get("won") if performance_eligible or join_status == MARKET_JOIN_AMBIGUOUS else None,
        "evaluation_status": enrich.get("evaluation_status"),
        "settlement_status": getattr(snap, "settlement_status", None),
        "result_reason": enrich.get("result_reason"),
        "profit_1u_real": enrich.get("profit_1u_real")
        if (performance_eligible or join_status == MARKET_JOIN_AMBIGUOUS)
        and enrich.get("is_real_book_quote")
        else None,
        "profit_1u_synthetic": enrich.get("profit_1u_synthetic")
        if (performance_eligible or join_status == MARKET_JOIN_AMBIGUOUS)
        and enrich.get("is_derived_quote")
        else None,
        "result_missing": bool(result_missing),
        "market_join_status": join_status,
        "performance_eligible": performance_eligible or join_status == MARKET_JOIN_AMBIGUOUS,
        "pre_match_hash": None,
        "locked_at": None,
        "result_attached_after_lock": True,
        "_market_obj": market_obj if (performance_eligible or join_status == MARKET_JOIN_AMBIGUOUS) else None,
    }


def build_cell_rows_from_opportunity(opp: dict[str, Any]) -> list[dict[str, Any]]:
    """Righe legacy cell-level arricchite."""
    rows: list[dict[str, Any]] = []
    cells = list(opp.get("active_cells") or [])
    for cell in cells:
        cell_id = build_signal_cell_id(
            opp["opportunity_id"],
            signal_group=cell.get("signal_group"),
            source_column=cell.get("source_column"),
            cell_key=str(cell.get("cell_key")) if cell.get("cell_key") else None,
        )
        rows.append(
            {
                "row_granularity": "signal_cell",
                "opportunity_id": opp["opportunity_id"],
                "signal_cell_id": cell_id,
                "do_not_sum_as_independent_opportunities": True,
                "do_not_sum_cell_profit": True,
                "profit_attribution": "shared_opportunity_result",
                "run_id": opp["run_id"],
                "snapshot_id": opp["snapshot_id"],
                "match_snapshot_id": opp["match_snapshot_id"],
                "lab_match_id": opp["lab_match_id"],
                "dataset_id": opp.get("dataset_id"),
                "competition_name": opp.get("competition_name"),
                "kickoff_at": opp.get("kickoff_at"),
                "home_team": opp.get("home_team"),
                "away_team": opp.get("away_team"),
                "model_key": opp["model_key"],
                "model_label": opp.get("model_label"),
                "model_short_label": opp.get("model_short_label"),
                "weights_version": opp.get("weights_version"),
                "weights": opp.get("weights"),
                "is_current_model": opp.get("is_current_model"),
                "market_key": opp.get("market_key"),
                "target_market": opp.get("target_market"),
                "signal_family": cell.get("signal_family") or opp.get("signal_family"),
                "source_column": cell.get("source_column"),
                "cell_key": cell.get("cell_key"),
                "cell_label": cell.get("cell_label"),
                "active_cell_count": opp.get("active_cell_count"),
                "consensus_model_count": opp.get("consensus_model_count"),
                "consensus_models": opp.get("consensus_models"),
                "active_in_current_model_F": opp.get("active_in_current_model_F"),
                "overlap_with_current_model_F": opp.get("overlap_with_current_model_F"),
                "prob_cecchino": opp.get("prob_cecchino"),
                "quota_cecchino": opp.get("quota_cecchino"),
                "probabilita_cecchino": opp.get("prob_cecchino"),  # alias legacy
                "rating": opp.get("rating"),
                "purchasability_score": opp.get("purchasability_score"),
                "purchasability_band": opp.get("purchasability_band"),
                "purchasability_status": opp.get("purchasability_status"),
                "quote_quality": opp.get("quote_quality"),
                "odds": opp.get("real_book_odds") or opp.get("derived_odds") or opp.get("odds"),
                "quota_bet365": opp.get("real_book_odds") or opp.get("derived_odds"),
                "won": opp.get("won"),
                "settlement": {
                    "evaluation_status": opp.get("evaluation_status"),
                    "settlement_status": opp.get("settlement_status"),
                    "result_reason": opp.get("result_reason"),
                },
                "real_profit_1u": opp.get("profit_1u_real"),
                "synthetic_profit_1u": opp.get("profit_1u_synthetic"),
                "market_join_status": opp.get("market_join_status"),
            }
        )
    return rows


def collect_all_opportunities(
    *,
    run_id: int,
    snapshots: Iterable[Any],
    markets: Iterable[Any],
) -> list[dict[str, Any]]:
    """Raccoglie tutte le opportunità per run (in memoria, per summary/export)."""
    snaps = list(snapshots)
    markets_index = index_markets_by_snap_key(markets)

    # Pass 1: set opportunità per modello (per consensus/overlap)
    model_sets: dict[str, set[tuple[int, str]]] = {k: set() for k in CECCHINO_WEIGHT_MODEL_KEYS}
    grouped_by_snap: dict[int, dict[str, dict[str, dict[str, Any]]]] = {}

    for snap in snaps:
        sid = int(snap.id)
        sigs = as_dict(getattr(snap, "signals_json", None))
        models = as_dict(sigs.get("models"))
        grouped_by_snap[sid] = {}
        for model_key in CECCHINO_WEIGHT_MODEL_KEYS:
            block = as_dict(models.get(model_key))
            grouped = group_model_opportunities(model_key=model_key, model_block=block)
            grouped_by_snap[sid][model_key] = grouped
            for mk, bucket in grouped.items():
                if bucket.get("market_key"):
                    model_sets[model_key].add((sid, str(bucket["market_key"])))

    # Pass 2: build rows
    opportunities: list[dict[str, Any]] = []
    for snap in snaps:
        sid = int(snap.id)
        for model_key in CECCHINO_WEIGHT_MODEL_KEYS:
            for _mk, bucket in (grouped_by_snap.get(sid, {}).get(model_key) or {}).items():
                opp = build_opportunity_row(
                    run_id=run_id,
                    snap=snap,
                    model_key=model_key,
                    market_bucket=bucket,
                    markets_index=markets_index,
                    model_opportunity_sets=model_sets,
                )
                opportunities.append(opp)
    return opportunities


def public_opportunity_row(opp: dict[str, Any]) -> dict[str, Any]:
    """Rimuove campi interni (_market_obj) prima della serializzazione."""
    return {k: v for k, v in opp.items() if not str(k).startswith("_")}


def opportunity_sets_by_model(
    opportunities: list[dict[str, Any]],
) -> dict[str, set[tuple[int, str]]]:
    sets: dict[str, set[tuple[int, str]]] = {k: set() for k in CECCHINO_WEIGHT_MODEL_KEYS}
    for opp in opportunities:
        mk = opp.get("market_key")
        if not mk:
            continue
        model = str(opp.get("model_key") or "").upper()
        if model in sets:
            sets[model].add((int(opp["snapshot_id"]), str(mk)))
    return sets


def build_model_overlap_matrix(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sets = opportunity_sets_by_model(opportunities)
    matrix: list[dict[str, Any]] = []
    keys = list(CECCHINO_WEIGHT_MODEL_KEYS)
    for i, a in enumerate(keys):
        for b in keys[i:]:
            sa, sb = sets[a], sets[b]
            inter = sa & sb
            union = sa | sb
            inter_n = len(inter)
            union_n = len(union)
            a_n = len(sa)
            b_n = len(sb)
            matrix.append(
                {
                    "model_a": a,
                    "model_b": b,
                    "intersection_count": inter_n,
                    "union_count": union_n,
                    "jaccard_pct": round(100.0 * inter_n / union_n, 2) if union_n else None,
                    "overlap_a_pct": round(100.0 * inter_n / a_n, 2) if a_n else None,
                    "overlap_b_pct": round(100.0 * inter_n / b_n, 2) if b_n else None,
                }
            )
    return matrix


def build_consensus_distribution(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Consensus market-specific: non aggrega mercati diversi."""
    # Chiave logica opportunità cross-model: (snapshot_id, market_key)
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for opp in opportunities:
        mk = opp.get("market_key")
        if not mk:
            continue
        if not opp.get("performance_eligible", True) and opp.get("market_join_status") not in (
            MARKET_JOIN_MATCHED,
            MARKET_JOIN_AMBIGUOUS,
        ):
            # Escludi dalle performance ma conta comunque per consensus count
            pass
        key = (int(opp["snapshot_id"]), str(mk))
        slot = by_key.setdefault(
            key,
            {
                "market_key": mk,
                "models": set(),
                "opps_by_model": {},
            },
        )
        model = str(opp["model_key"]).upper()
        slot["models"].add(model)
        slot["opps_by_model"][model] = opp

    # Aggrega per (market_key, consensus_model_count) usando un rappresentante market row
    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    for (_sid, mk), slot in by_key.items():
        ccount = len(slot["models"])
        bkey = (mk, ccount)
        b = buckets.setdefault(
            bkey,
            {
                "market_key": mk,
                "consensus_model_count": ccount,
                "opportunity_count": 0,
                "wins": 0,
                "losses": 0,
                "real_quote_count": 0,
                "real_profit_1u": 0.0,
                "derived_quote_count": 0,
                "synthetic_profit_1u": 0.0,
                "unavailable_quote_count": 0,
            },
        )
        b["opportunity_count"] += 1
        # Usa un rappresentante (preferisci F, poi primo modello)
        rep = slot["opps_by_model"].get(CURRENT_MODEL_KEY) or next(
            iter(slot["opps_by_model"].values())
        )
        if not rep.get("performance_eligible") and rep.get("market_join_status") not in (
            MARKET_JOIN_MATCHED,
            MARKET_JOIN_AMBIGUOUS,
        ):
            continue
        if rep.get("won") is True:
            b["wins"] += 1
        elif rep.get("won") is False:
            b["losses"] += 1
        if rep.get("is_real_book_quote"):
            b["real_quote_count"] += 1
            if rep.get("profit_1u_real") is not None:
                b["real_profit_1u"] += float(rep["profit_1u_real"])
        elif rep.get("is_derived_quote"):
            b["derived_quote_count"] += 1
            if rep.get("profit_1u_synthetic") is not None:
                b["synthetic_profit_1u"] += float(rep["profit_1u_synthetic"])
        else:
            b["unavailable_quote_count"] += 1

    out: list[dict[str, Any]] = []
    for (_mk, _cc), b in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        decided = b["wins"] + b["losses"]
        real_n = b["real_quote_count"]
        der_n = b["derived_quote_count"]
        out.append(
            {
                "market_key": b["market_key"],
                "consensus_model_count": b["consensus_model_count"],
                "opportunity_count": b["opportunity_count"],
                "wins": b["wins"],
                "losses": b["losses"],
                "hit_rate": round(b["wins"] / decided, 4) if decided else None,
                "real_quote_count": real_n,
                "real_profit_1u": round(b["real_profit_1u"], 4) if real_n else None,
                "real_roi_pct": round(100.0 * b["real_profit_1u"] / real_n, 2) if real_n else None,
                "derived_quote_count": der_n,
                "synthetic_profit_1u": round(b["synthetic_profit_1u"], 4) if der_n else None,
                "synthetic_roi_pct": (
                    round(100.0 * b["synthetic_profit_1u"] / der_n, 2) if der_n else None
                ),
                "unavailable_quote_count": b["unavailable_quote_count"],
            }
        )
    return out


def build_market_join_diagnostics(
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(opportunities)
    counts = {
        MARKET_JOIN_MATCHED: 0,
        MARKET_JOIN_MISSING: 0,
        MARKET_JOIN_AMBIGUOUS: 0,
        MARKET_JOIN_INVALID: 0,
    }
    by_model: dict[str, dict[str, int]] = defaultdict(
        lambda: {k: 0 for k in counts}
    )
    by_market: dict[str, dict[str, int]] = defaultdict(
        lambda: {k: 0 for k in counts}
    )
    for opp in opportunities:
        st = opp.get("market_join_status") or MARKET_JOIN_MISSING
        if st not in counts:
            st = MARKET_JOIN_MISSING
        counts[st] += 1
        model = str(opp.get("model_key") or "?")
        by_model[model][st] += 1
        mk = str(opp.get("market_key") or "INVALID")
        by_market[mk][st] += 1

    matched = counts[MARKET_JOIN_MATCHED]
    return {
        "opportunities_total": total,
        "matched_count": matched,
        "missing_count": counts[MARKET_JOIN_MISSING],
        "ambiguous_count": counts[MARKET_JOIN_AMBIGUOUS],
        "invalid_mapping_count": counts[MARKET_JOIN_INVALID],
        "matched_pct": round(100.0 * matched / total, 2) if total else None,
        "by_model_key": dict(sorted(by_model.items())),
        "by_market_key": dict(sorted(by_market.items())),
    }


def build_signal_export_reconciliation(
    opportunities: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    opp_ids = [o["opportunity_id"] for o in opportunities]
    unique_ids = set(opp_ids)
    duplicates = len(opp_ids) - len(unique_ids)
    sum_cells = sum(int(o.get("active_cell_count") or 0) for o in opportunities)
    cell_n = len(cell_rows) if cell_rows is not None else sum_cells
    models_present = sorted(
        {str(o.get("model_key")).upper() for o in opportunities if o.get("model_key")}
    )
    return {
        "cell_rows": cell_n,
        "opportunity_rows": len(opportunities),
        "unique_opportunity_ids": len(unique_ids),
        "duplicate_opportunity_ids": duplicates,
        "sum_active_cell_count": sum_cells,
        "cell_rows_equal_sum_active_cell_count": cell_n == sum_cells,
        "opportunity_id_unique": duplicates == 0,
        "models_present": models_present or list(CECCHINO_WEIGHT_MODEL_KEYS),
        "current_model_key": CURRENT_MODEL_KEY,
        "performance_uses_opportunities_only": True,
        "cell_rows_not_independent": True,
    }


def _median(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def summarize_model_from_opportunities(
    opportunities: list[dict[str, Any]],
    *,
    model_key: str,
    model_sets: dict[str, set[tuple[int, str]]] | None = None,
) -> dict[str, Any]:
    model_key = str(model_key).upper()
    model_opps = [
        o
        for o in opportunities
        if str(o.get("model_key") or "").upper() == model_key
    ]
    perf_opps = [
        o
        for o in model_opps
        if o.get("performance_eligible")
        or o.get("market_join_status") in (MARKET_JOIN_MATCHED, MARKET_JOIN_AMBIGUOUS)
    ]
    # Performance solo da matched/ambiguous con market row
    b = agg_bucket()
    won_flags: list[bool | None] = []
    cell_counts: list[int] = []
    match_ids: set[int] = set()
    market_keys: set[str] = set()

    for o in model_opps:
        cell_counts.append(int(o.get("active_cell_count") or 0))
        match_ids.add(int(o["snapshot_id"]))
        if o.get("market_key"):
            market_keys.add(str(o["market_key"]))

    for o in perf_opps:
        m = o.get("_market_obj")
        if m is None:
            # Synthetic bump from opportunity fields without multiplying cells
            b["sample_size"] += 1
            if o.get("competition_name"):
                b["competitions"].add(o["competition_name"])
            if o.get("won") is True:
                b["won"] += 1
            elif o.get("won") is False:
                b["lost"] += 1
            if o.get("is_real_book_quote"):
                b["real_quote_count"] += 1
                if o.get("profit_1u_real") is not None:
                    b["real_profit_1u"] += float(o["profit_1u_real"])
            elif o.get("is_derived_quote"):
                b["derived_quote_count"] += 1
                if o.get("profit_1u_synthetic") is not None:
                    b["synthetic_profit_1u"] += float(o["profit_1u_synthetic"])
            else:
                b["unavailable_quote_count"] += 1
            if o.get("prob_cecchino") is not None:
                b["with_cecchino_probability"] += 1
            if o.get("quota_cecchino") is not None:
                b["with_cecchino_fair_quote"] += 1
                b["with_cecchino_quote"] += 1
            if o.get("rating") is not None:
                b["with_rating"] += 1
            won_flags.append(o.get("won"))
        else:
            bump_bucket_from_market(b, m, o.get("competition_name"))
            won_flags.append(getattr(m, "won", None))

    # with_signal_active = alias legacy di opportunity count (non overlap F)
    b["with_signal_active"] = len(model_opps)
    fb = finalize_bucket(b)

    sets = model_sets or opportunity_sets_by_model(opportunities)
    own = sets.get(model_key, set())
    f_set = sets.get(CURRENT_MODEL_KEY, set())
    overlap = own & f_set
    unique_vs_f = own - f_set
    f_only = f_set - own

    opp_count = len(model_opps)
    active_cell_row_count = sum(cell_counts)
    result_missing = sum(1 for o in perf_opps if o.get("won") is None)

    canon = canonical_model_fields(model_key)
    return {
        **canon,
        "opportunity_count": opp_count,
        "model_active_opportunity_count": opp_count,
        "sample_size": opp_count,
        "with_signal_active": opp_count,  # alias deprecato
        "with_signal_active_deprecated_alias_of": "model_active_opportunity_count",
        "model_active_match_count": len(match_ids),
        "matches_with_opportunity": len(match_ids),
        "model_active_market_count": len(market_keys),
        "markets_count": len(market_keys),
        "active_cell_row_count": active_cell_row_count,
        "average_active_cells_per_opportunity": (
            round(active_cell_row_count / opp_count, 4) if opp_count else None
        ),
        "average_active_cells": (
            round(active_cell_row_count / opp_count, 4) if opp_count else None
        ),
        "median_active_cells_per_opportunity": _median(cell_counts),
        "max_active_cells_per_opportunity": max(cell_counts) if cell_counts else 0,
        "wins": fb["won"],
        "losses": fb["lost"],
        "result_missing": result_missing,
        "hit_rate": fb["hit_rate"],
        "real_quote_count": fb["real_quote_count"],
        "real_profit_1u": fb["real_profit_1u"],
        "real_profit": fb["real_profit_1u"],
        "real_roi_pct": fb["real_roi_pct"],
        "real_roi": fb["real_roi_pct"],
        "derived_quote_count": fb["derived_quote_count"],
        "synthetic_profit_1u": fb["synthetic_profit_1u"],
        "synthetic_profit": fb["synthetic_profit_1u"],
        "synthetic_roi_pct": fb["synthetic_roi_pct"],
        "synthetic_roi": fb["synthetic_roi_pct"],
        "unavailable_quote_count": fb["unavailable_quote_count"],
        "overlap_with_current_model_F_count": len(overlap),
        "overlap_with_current_model_F_pct": (
            round(100.0 * len(overlap) / len(own), 2) if own else None
        ),
        "unique_vs_current_model_F_count": len(unique_vs_f),
        "current_model_F_only_count": len(f_only) if model_key != CURRENT_MODEL_KEY else 0,
        "max_losing_streak": max_losing_streak(won_flags),
        "competitions_count": fb.get("competitions_count"),
        "signals_activated": active_cell_row_count,  # compat dashboard legacy = celle
        "matches_with_signal": len(match_ids),
    }


def build_current_model_F_diagnostics(
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    sets = opportunity_sets_by_model(opportunities)
    f_set = sets.get(CURRENT_MODEL_KEY, set())
    other_union: set[tuple[int, str]] = set()
    for k, s in sets.items():
        if k != CURRENT_MODEL_KEY:
            other_union |= s

    all_models_intersection = set(f_set)
    for k in CECCHINO_WEIGHT_MODEL_KEYS:
        all_models_intersection &= sets.get(k, set())

    shared_all = len(all_models_intersection)
    not_shared_all = len(f_set) - shared_all
    unique_f = len(f_set - other_union)
    excluded_by_f = len(other_union - f_set)

    f_opps = [
        o
        for o in opportunities
        if str(o.get("model_key") or "").upper() == CURRENT_MODEL_KEY
    ]

    # Performance per market_key (solo F)
    by_market: dict[str, dict[str, Any]] = defaultdict(agg_bucket)
    for o in f_opps:
        mk = o.get("market_key")
        if not mk:
            continue
        if not (
            o.get("performance_eligible")
            or o.get("market_join_status") in (MARKET_JOIN_MATCHED, MARKET_JOIN_AMBIGUOUS)
        ):
            continue
        m = o.get("_market_obj")
        if m is not None:
            bump_bucket_from_market(by_market[str(mk)], m, o.get("competition_name"))

    overlap_per_model = []
    for k in CECCHINO_WEIGHT_MODEL_KEYS:
        if k == CURRENT_MODEL_KEY:
            continue
        inter = f_set & sets.get(k, set())
        own = sets.get(k, set())
        overlap_per_model.append(
            {
                "model_key": k,
                "overlap_count": len(inter),
                "overlap_pct_of_F": (
                    round(100.0 * len(inter) / len(f_set), 2) if f_set else None
                ),
                "overlap_pct_of_model": (
                    round(100.0 * len(inter) / len(own), 2) if own else None
                ),
            }
        )

    # Combinazioni celle per mercato (F)
    combo_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for o in f_opps:
        mk = o.get("market_key")
        if not mk:
            continue
        groups = tuple(
            sorted(
                f"{c.get('signal_group')}|{c.get('source_column')}"
                for c in (o.get("active_cells") or [])
            )
        )
        combo_key = "+".join(groups) if groups else "(empty)"
        bkey = (str(mk), combo_key)
        slot = combo_buckets.setdefault(
            bkey,
            {
                "market_key": mk,
                "active_cell_combination": combo_key,
                "opportunity_count": 0,
                "wins": 0,
                "losses": 0,
                "competitions": set(),
                "real_quote_count": 0,
                "real_profit_1u": 0.0,
            },
        )
        slot["opportunity_count"] += 1
        if o.get("competition_name"):
            slot["competitions"].add(o["competition_name"])
        if o.get("won") is True:
            slot["wins"] += 1
        elif o.get("won") is False:
            slot["losses"] += 1
        if o.get("is_real_book_quote"):
            slot["real_quote_count"] += 1
            if o.get("profit_1u_real") is not None:
                slot["real_profit_1u"] += float(o["profit_1u_real"])

    cell_combos = []
    for (_mk, _ck), slot in sorted(combo_buckets.items(), key=lambda x: -x[1]["opportunity_count"]):
        n = slot["opportunity_count"]
        decided = slot["wins"] + slot["losses"]
        real_n = slot["real_quote_count"]
        cell_combos.append(
            {
                "market_key": slot["market_key"],
                "active_cell_combination": slot["active_cell_combination"],
                "opportunity_count": n,
                "wins": slot["wins"],
                "losses": slot["losses"],
                "hit_rate": round(slot["wins"] / decided, 4) if decided else None,
                "real_quote_count": real_n,
                "real_profit_1u": round(slot["real_profit_1u"], 4) if real_n else None,
                "real_roi_pct": (
                    round(100.0 * slot["real_profit_1u"] / real_n, 2) if real_n else None
                ),
                "competitions_count": len(slot["competitions"]),
                "confidence_status": signal_confidence_status(n),
                "attribution_mode": "overlapping",
                "do_not_sum_across_cells": True,
            }
        )

    # Competition distribution
    comp_counts: dict[str, int] = defaultdict(int)
    for o in f_opps:
        comp_counts[str(o.get("competition_name") or "unknown")] += 1

    # Chronological halves
    dated = [o for o in f_opps if o.get("kickoff_at")]
    dated.sort(key=lambda o: o["kickoff_at"])
    mid = len(dated) // 2
    first_half = dated[:mid]
    second_half = dated[mid:]

    def _half_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        b = agg_bucket()
        for o in rows:
            m = o.get("_market_obj")
            if m is not None:
                bump_bucket_from_market(b, m, o.get("competition_name"))
        return finalize_bucket(b)

    # F selected vs excluded by F (same market universe)
    f_vs_excluded_by_market: list[dict[str, Any]] = []
    for mk in sorted({k[1] for k in (f_set | other_union)}):
        f_mk = {s for s in f_set if s[1] == mk}
        excl_mk = {s for s in (other_union - f_set) if s[1] == mk}
        f_vs_excluded_by_market.append(
            {
                "market_key": mk,
                "selected_by_F_count": len(f_mk),
                "excluded_by_F_but_selected_by_others_count": len(excl_mk),
                "same_market_universe": True,
            }
        )

    return {
        "current_model_key": CURRENT_MODEL_KEY,
        "note": (
            "Diagnostica descrittiva del modello corrente F. "
            "Non consiglia giocate. F non è automaticamente il migliore."
        ),
        "opportunities_total": len(f_set),
        "opportunities_shared_with_all_models": shared_all,
        "opportunities_not_shared_with_all_models": not_shared_all,
        "opportunities_unique_to_F": unique_f,
        "opportunities_excluded_by_F_but_selected_by_other_models": excluded_by_f,
        "performance_by_market_key": {
            mk: finalize_bucket(b) for mk, b in sorted(by_market.items())
        },
        "overlap_per_model": overlap_per_model,
        "consensus_distribution": build_consensus_distribution(opportunities),
        "active_cell_combinations_by_market": cell_combos[:200],
        "competition_distribution": [
            {"competition_name": c, "opportunity_count": n}
            for c, n in sorted(comp_counts.items(), key=lambda x: -x[1])
        ],
        "chronological_halves": {
            "first_half": _half_stats(first_half),
            "second_half": _half_stats(second_half),
            "first_half_count": len(first_half),
            "second_half_count": len(second_half),
        },
        "f_selected_vs_excluded_same_market": f_vs_excluded_by_market,
    }


def build_cell_attribution_stats(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Performance per cella con attribution overlapping (descrittiva)."""
    # (model_key, market_key, signal_group, source_column) → stats
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for o in opportunities:
        mk = o.get("market_key")
        if not mk:
            continue
        cells = o.get("active_cells") or []
        n_cells = len(cells)
        for cell in cells:
            key = (
                str(o["model_key"]).upper(),
                str(mk),
                str(cell.get("signal_group") or ""),
                str(cell.get("source_column") or ""),
            )
            slot = buckets.setdefault(
                key,
                {
                    "model_key": key[0],
                    "market_key": mk,
                    "signal_group": cell.get("signal_group"),
                    "source_column": cell.get("source_column"),
                    "cell_label": cell.get("cell_label"),
                    "opportunities_count": 0,
                    "unique_matches": set(),
                    "shared_with_other_cells_count": 0,
                    "cells_per_opp_sum": 0,
                    "wins": 0,
                    "losses": 0,
                    "real_quote_count": 0,
                    "real_profit_1u": 0.0,
                },
            )
            slot["opportunities_count"] += 1
            slot["unique_matches"].add(int(o["snapshot_id"]))
            slot["cells_per_opp_sum"] += n_cells
            if n_cells > 1:
                slot["shared_with_other_cells_count"] += 1
            if o.get("won") is True:
                slot["wins"] += 1
            elif o.get("won") is False:
                slot["losses"] += 1
            if o.get("is_real_book_quote"):
                slot["real_quote_count"] += 1
                if o.get("profit_1u_real") is not None:
                    slot["real_profit_1u"] += float(o["profit_1u_real"])

    out = []
    for _k, slot in sorted(buckets.items(), key=lambda x: -x[1]["opportunities_count"]):
        n = slot["opportunities_count"]
        decided = slot["wins"] + slot["losses"]
        real_n = slot["real_quote_count"]
        out.append(
            {
                "attribution_mode": "overlapping",
                "do_not_sum_across_cells": True,
                "model_key": slot["model_key"],
                "market_key": slot["market_key"],
                "signal_group": slot["signal_group"],
                "source_column": slot["source_column"],
                "cell_label": slot["cell_label"],
                "opportunities_count": n,
                "unique_matches_count": len(slot["unique_matches"]),
                "shared_with_other_cells_count": slot["shared_with_other_cells_count"],
                "average_cells_per_opportunity": (
                    round(slot["cells_per_opp_sum"] / n, 4) if n else None
                ),
                "wins": slot["wins"],
                "losses": slot["losses"],
                "hit_rate": round(slot["wins"] / decided, 4) if decided else None,
                "real_quote_count": real_n,
                "real_profit_1u": round(slot["real_profit_1u"], 4) if real_n else None,
                "real_roi_pct": (
                    round(100.0 * slot["real_profit_1u"] / real_n, 2) if real_n else None
                ),
                "confidence_status": signal_confidence_status(n),
                "note": "Attribuzione descrittiva overlapping; non dichiara una cella vincitrice.",
            }
        )
    return out


def build_signal_models_summary(
    opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summary completo per report/dashboard segnali."""
    model_sets = opportunity_sets_by_model(opportunities)
    cell_rows_count = sum(int(o.get("active_cell_count") or 0) for o in opportunities)
    fake_cells = [{"opportunity_id": o["opportunity_id"]} for o in opportunities for _ in range(int(o.get("active_cell_count") or 0))]

    models = [
        summarize_model_from_opportunities(
            opportunities, model_key=k, model_sets=model_sets
        )
        for k in CECCHINO_WEIGHT_MODEL_KEYS
    ]

    # Breakdown model × market
    model_x_market: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_comp: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_family: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_cell_count: dict[tuple[str, int], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_consensus: dict[tuple[str, int], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_rating: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)
    model_x_purch: dict[tuple[str, str], dict[str, Any]] = defaultdict(agg_bucket)

    for o in opportunities:
        if not (
            o.get("performance_eligible")
            or o.get("market_join_status") in (MARKET_JOIN_MATCHED, MARKET_JOIN_AMBIGUOUS)
        ):
            continue
        m = o.get("_market_obj")
        if m is None:
            continue
        model = str(o["model_key"]).upper()
        mk = str(o.get("market_key") or "")
        comp = o.get("competition_name") or "unknown"
        bump_bucket_from_market(model_x_market[(model, mk)], m, comp)
        bump_bucket_from_market(model_x_comp[(model, comp)], m, comp)
        fam = str(o.get("signal_family") or "unknown")
        bump_bucket_from_market(model_x_family[(model, fam)], m, comp)
        bump_bucket_from_market(
            model_x_cell_count[(model, int(o.get("active_cell_count") or 0))], m, comp
        )
        bump_bucket_from_market(
            model_x_consensus[(model, int(o.get("consensus_model_count") or 0))], m, comp
        )
        rating_band = "no_rating"
        if o.get("rating") is not None:
            r = int(o["rating"])
            if r >= 100:
                rating_band = "100"
            else:
                base = (r // 10) * 10
                rating_band = f"{base}-{base + 9}"
        bump_bucket_from_market(model_x_rating[(model, rating_band)], m, comp)
        purch_band = o.get("purchasability_band") or "no_purch"
        bump_bucket_from_market(model_x_purch[(model, str(purch_band))], m, comp)

    reconciliation = build_signal_export_reconciliation(opportunities, fake_cells)

    return {
        "signal_export_schema_version": SIGNAL_EXPORT_SCHEMA_VERSION,
        "current_model_key": CURRENT_MODEL_KEY,
        "performance_granularity": "signal_opportunity",
        "legacy_cell_file": "signal_models.jsonl",
        "models": models,
        "model_overlap_matrix": build_model_overlap_matrix(opportunities),
        "consensus_distribution": build_consensus_distribution(opportunities),
        "market_join_diagnostics": build_market_join_diagnostics(opportunities),
        "signal_export_reconciliation": reconciliation,
        "current_model_F_diagnostics": build_current_model_F_diagnostics(opportunities),
        "cell_attribution": build_cell_attribution_stats(opportunities),
        "model_x_market": [
            {"model_key": k, "market_key": mk, **finalize_bucket(b)}
            for (k, mk), b in sorted(model_x_market.items())
        ],
        "model_x_competition": [
            {"model_key": k, "competition": c, **finalize_bucket(b)}
            for (k, c), b in sorted(model_x_comp.items())
        ],
        "model_x_signal_family": [
            {"model_key": k, "signal_family": f, **finalize_bucket(b)}
            for (k, f), b in sorted(model_x_family.items())
        ],
        "model_x_active_cell_count": [
            {"model_key": k, "active_cell_count": n, **finalize_bucket(b)}
            for (k, n), b in sorted(model_x_cell_count.items())
        ],
        "model_x_consensus": [
            {"model_key": k, "consensus_model_count": n, **finalize_bucket(b)}
            for (k, n), b in sorted(model_x_consensus.items())
        ],
        "model_x_rating": [
            {"model_key": k, "rating_band": r, **finalize_bucket(b)}
            for (k, r), b in sorted(model_x_rating.items())
        ],
        "model_x_purchasability": [
            {"model_key": k, "purchasability_band": p, **finalize_bucket(b)}
            for (k, p), b in sorted(model_x_purch.items())
        ],
        "opportunity_rows": len(opportunities),
        "cell_rows": cell_rows_count,
        "note": (
            "Performance su opportunità uniche (run+snapshot+model+market). "
            "signal_models.jsonl è legacy cell-level: non sommare profitto celle. "
            "with_signal_active è alias deprecato di model_active_opportunity_count. "
            f"F = modello corrente ({CURRENT_MODEL_KEY}), non automaticamente il migliore."
        ),
    }
