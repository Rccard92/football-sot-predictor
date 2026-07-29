"""Export read-only Acquistabilità storica — righe compatte, decisioni, drift.

Nessuna scrittura DB. Nessun ricalcolo formula/pesi/gate.
Valori esclusivamente da snapshot e MarketResult congelati.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Iterator

from app.services.cecchino_data_lab.historical_analytics_agg import (
    as_dict,
    classify_purchasability_gate,
    purchasability_accepted_score_band_report,
    score_zero_semantics_for_row,
)
from app.services.cecchino_data_lab.historical_signal_export import (
    MARKET_JOIN_AMBIGUOUS,
    MARKET_JOIN_INVALID,
    MARKET_JOIN_MATCHED,
    MARKET_JOIN_MISSING,
    index_markets_by_snap_key,
    join_market_result,
)

PURCHASABILITY_EXPORT_SCHEMA_VERSION = "cecchino_lab_purchasability_export_v1"

# Contratto export: invalid_market_key (signal export usa invalid_market_mapping)
PURCH_JOIN_INVALID = "invalid_market_key"


def _normalize_join_status(status: str) -> str:
    if status in (MARKET_JOIN_INVALID, "invalid_market_mapping"):
        return PURCH_JOIN_INVALID
    return status

# Formula storica Lab già persistita (solo lettura per diagnostica ungated)
KNOWN_HISTORICAL_FORMULA_VERSIONS = frozenset(
    {
        "cecchino_lab_purchasability_historical_v1",
    }
)

DECISION_GROUP_ONE_X_TWO = "ONE_X_TWO_REAL"
DECISION_GROUP_GOALS_FT = "GOALS_FT_2_5_REAL"
DECISION_GROUP_DC = "DOUBLE_CHANCE_DERIVED"

DECISION_GROUPS: dict[str, tuple[str, ...]] = {
    DECISION_GROUP_ONE_X_TWO: ("HOME", "DRAW", "AWAY"),
    DECISION_GROUP_GOALS_FT: ("OVER_2_5", "UNDER_2_5"),
    DECISION_GROUP_DC: ("ONE_X", "X_TWO", "ONE_TWO"),
}

MARKET_TO_DECISION_GROUP: dict[str, str] = {
    mk: group for group, markets in DECISION_GROUPS.items() for mk in markets
}

THRESHOLD_SPECS: tuple[tuple[str, float | None], ...] = (
    ("accepted_only", None),
    ("score_ge_40", 40.0),
    ("score_ge_60", 60.0),
    ("score_ge_70", 70.0),
    ("score_ge_80", 80.0),
    ("score_ge_90", 90.0),
)

OBSERVATIONAL_WARNING = (
    "L'Acquistabilità storica è un modulo osservazionale. Il report descrive la "
    "formula congelata del Run #3 e non costituisce una strategia o una modifica "
    "della formula operativa."
)


def build_purchasability_evaluation_id(
    *,
    run_id: int,
    snapshot_id: int,
    market_key: str,
) -> str:
    return f"run:{int(run_id)}:snapshot:{int(snapshot_id)}:market:{market_key}"


def build_decision_id(
    *,
    run_id: int,
    snapshot_id: int,
    decision_group: str,
) -> str:
    return (
        f"run:{int(run_id)}:snapshot:{int(snapshot_id)}"
        f":decision_group:{decision_group}"
    )


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _phase_score(phase: Any) -> float | None:
    if not isinstance(phase, dict):
        return None
    return _safe_float(phase.get("score"))


def _iso_kickoff(kickoff: Any) -> str | None:
    if kickoff is None:
        return None
    if isinstance(kickoff, datetime):
        if kickoff.tzinfo is None:
            return kickoff.isoformat() + "Z"
        return kickoff.isoformat()
    text = str(kickoff).strip()
    return text or None


def _scores_from_result(snap: Any) -> dict[str, Any]:
    result = as_dict(getattr(snap, "result_json", None))
    ft = as_dict(result.get("fulltime"))
    ht = as_dict(result.get("halftime"))
    return {
        "home_score_ft": ft.get("home", result.get("ft_home")),
        "away_score_ft": ft.get("away", result.get("ft_away")),
        "home_score_ht": ht.get("home", result.get("ht_home")),
        "away_score_ht": ht.get("away", result.get("ht_away")),
    }


def derive_diagnostic_ungated_score(
    mk_row: dict[str, Any],
) -> tuple[float | None, str]:
    """Ricostruisce sqrt(phase_1 * phase_2) solo da valori persistiti.

    Non sostituisce final_score. Non scrive su DB.
    """
    formula = mk_row.get("formula_version")
    if formula not in KNOWN_HISTORICAL_FORMULA_VERSIONS:
        return None, "not_reconstructable"

    phase_1 = mk_row.get("phase_1") or as_dict(as_dict(mk_row.get("components")).get("phase_1"))
    phase_2 = mk_row.get("phase_2") or as_dict(as_dict(mk_row.get("components")).get("phase_2"))
    p1 = _phase_score(phase_1)
    p2 = _phase_score(phase_2)
    if p1 is None or p2 is None:
        return None, "not_reconstructable"
    if p1 < 0 or p2 < 0:
        return None, "not_reconstructable"
    return round(math.sqrt(float(p1) * float(p2)), 2), "derived_read_only_from_persisted_phase_values"


def _component_availability(mk_row: dict[str, Any]) -> str:
    comps = as_dict(mk_row.get("components"))
    p1 = mk_row.get("phase_1") or comps.get("phase_1")
    p2 = mk_row.get("phase_2") or comps.get("phase_2")
    has_p1 = isinstance(p1, dict) and p1
    has_p2 = isinstance(p2, dict) and p2
    if has_p1 and has_p2:
        # dettagli componenti oltre allo score
        detail_keys = {"components", "contributions", "weights", "items", "parts"}
        rich = any(k in p1 or k in p2 for k in detail_keys) or (
            len(p1) > 2 and len(p2) > 2
        )
        return "full" if rich else "partial"
    if has_p1 or has_p2:
        return "partial"
    return "unavailable"


def _market_fields_from_join(
    m: Any | None,
    join_status: str,
    *,
    mk_row: dict[str, Any],
) -> dict[str, Any]:
    null_market = {
        "market_label": None,
        "period": None,
        "line": None,
        "quote_quality": mk_row.get("quote_quality"),
        "is_real_book_quote": None,
        "is_derived_quote": None,
        "real_book_odds": None,
        "derived_odds": None,
        "prob_book_raw": None,
        "prob_book_fair": None,
        "prob_cecchino": None,
        "quota_cecchino": None,
        "rating": mk_row.get("rating"),
        "edge_pct": mk_row.get("edge_pct"),
        "vantaggio_prob": mk_row.get("vantaggio_prob"),
        "signal_active_current_F": None,
        "won": None,
        "evaluation_status": None,
        "result_reason": None,
        "profit_1u_real": None,
        "profit_1u_synthetic": None,
    }
    if m is None or join_status in (MARKET_JOIN_MISSING, MARKET_JOIN_INVALID, PURCH_JOIN_INVALID):
        return null_market

    real_odds = None
    derived_odds = None
    is_real = bool(getattr(m, "is_real_book_quote", False))
    is_derived = bool(getattr(m, "is_derived_quote", False))
    quota_book = getattr(m, "quota_book", None)
    if is_real and quota_book is not None and not is_derived:
        real_odds = float(quota_book)
    elif is_derived and quota_book is not None:
        derived_odds = float(quota_book)

    # Rating/edge/vantaggio: preferisci market result, fallback payload purch
    rating = int(m.rating) if getattr(m, "rating", None) is not None else mk_row.get("rating")
    edge = (
        float(m.edge_pct)
        if getattr(m, "edge_pct", None) is not None
        else _safe_float(mk_row.get("edge_pct"))
    )
    vant = (
        float(m.vantaggio_prob)
        if getattr(m, "vantaggio_prob", None) is not None
        else _safe_float(mk_row.get("vantaggio_prob"))
    )

    qq = None
    if is_real and not is_derived:
        qq = "real"
    elif is_derived:
        qq = "derived"
    elif mk_row.get("quote_quality"):
        qq = mk_row.get("quote_quality")
    else:
        qq = "unavailable"

    profit_real = float(m.profit_1u_real) if m.profit_1u_real is not None else None
    profit_syn = float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
    # Nessun profitto senza quote
    if real_odds is None and derived_odds is None and quota_book is None:
        profit_real = None
        profit_syn = None

    performance_ok = join_status == MARKET_JOIN_MATCHED
    return {
        "market_label": getattr(m, "market_label", None),
        "period": getattr(m, "period", None),
        "line": getattr(m, "line", None),
        "quote_quality": qq,
        "is_real_book_quote": is_real,
        "is_derived_quote": is_derived,
        "real_book_odds": real_odds,
        "derived_odds": derived_odds,
        "prob_book_raw": float(m.prob_book_raw) if m.prob_book_raw is not None else None,
        "prob_book_fair": float(m.prob_book_fair) if m.prob_book_fair is not None else None,
        "prob_cecchino": float(m.prob_cecchino) if m.prob_cecchino is not None else None,
        "quota_cecchino": float(m.quota_cecchino) if m.quota_cecchino is not None else None,
        "rating": rating,
        "edge_pct": edge,
        "vantaggio_prob": vant,
        "signal_active_current_F": bool(m.signal_active),
        "won": m.won if performance_ok or join_status == MARKET_JOIN_AMBIGUOUS else None,
        "evaluation_status": m.evaluation_status,
        "result_reason": m.result_reason,
        "profit_1u_real": profit_real if performance_ok else None,
        "profit_1u_synthetic": profit_syn if performance_ok else None,
    }


def build_compact_evaluation_row(
    *,
    run_id: int,
    snap: Any,
    mk_row: dict[str, Any],
    markets_index: dict[tuple[int, str], list[Any]],
) -> dict[str, Any]:
    """Una riga canonica snapshot × market (sola lettura)."""
    snapshot_id = int(snap.id)
    market_key = mk_row.get("market_key")
    mk = str(market_key) if market_key is not None else None

    if not mk:
        join_status = PURCH_JOIN_INVALID
        market_obj = None
    else:
        market_obj, join_raw = join_market_result(
            markets_index,
            snapshot_id=snapshot_id,
            market_key=mk,
            mapping_status=MARKET_JOIN_MATCHED,
        )
        join_status = _normalize_join_status(join_raw)

    gate_info = classify_purchasability_gate(mk_row, snap_payload=as_dict(snap.purchasability_compatibility_json))
    final_score = mk_row.get("score")
    gate_status = gate_info["gate_status"]
    zero_sem = score_zero_semantics_for_row(final_score, gate_status)
    diag_score, diag_source = derive_diagnostic_ungated_score(mk_row)

    accepted_band = None
    score_class_export = None
    if gate_status == "accepted" and final_score is not None:
        accepted_band = purchasability_accepted_score_band_report(final_score)
        # Classe operativa persistita solo se gate accepted
        score_class_export = mk_row.get("class")
    elif gate_status != "accepted" and gate_status != "unknown_legacy":
        accepted_band = "gate_rejected"
        score_class_export = "Bloccato dal gate"
    else:
        if final_score is None:
            accepted_band = "unavailable"
        else:
            accepted_band = purchasability_accepted_score_band_report(final_score)
            score_class_export = mk_row.get("class")

    scores = _scores_from_result(snap)
    market_fields = _market_fields_from_join(market_obj, join_status, mk_row=mk_row)
    comps = as_dict(mk_row.get("components"))
    phase_1 = mk_row.get("phase_1") if isinstance(mk_row.get("phase_1"), dict) else comps.get("phase_1")
    phase_2 = mk_row.get("phase_2") if isinstance(mk_row.get("phase_2"), dict) else comps.get("phase_2")
    gate_raw = mk_row.get("positive_value_gate")

    eval_id = build_purchasability_evaluation_id(
        run_id=run_id,
        snapshot_id=snapshot_id,
        market_key=mk or "INVALID",
    )

    # Per join non matched: niente profitto / won nelle metriche performance
    performance_eligible = join_status == MARKET_JOIN_MATCHED

    return {
        "purchasability_evaluation_id": eval_id,
        "run_id": int(run_id),
        "snapshot_id": snapshot_id,
        "match_snapshot_id": snapshot_id,
        "lab_match_id": int(snap.lab_match_id) if snap.lab_match_id is not None else None,
        "dataset_id": getattr(snap, "dataset_id", None),
        "competition_name": snap.competition_name,
        "season_label": getattr(snap, "season_label", None),
        "kickoff_at": _iso_kickoff(snap.kickoff_at),
        "chronological_order": snap.chronological_order,
        "home_team": snap.home_team,
        "away_team": snap.away_team,
        **scores,
        "eligibility_status": snap.historical_eligibility_status,
        "settlement_status": snap.settlement_status,
        "market_key": mk,
        **market_fields,
        "market_join_status": join_status,
        "performance_eligible": performance_eligible,
        "final_score": final_score,
        "persisted_score": final_score,
        "persisted_raw_score": mk_row.get("raw_score"),
        "score_class": score_class_export,
        "persisted_class_legacy": mk_row.get("class"),
        "accepted_score_band": accepted_band,
        "positive_value_gate": gate_raw if isinstance(gate_raw, dict) else None,
        "gate_status": gate_status,
        "gate_reasons": gate_info["gate_reasons"],
        "score_zero_semantics": zero_sem,
        "diagnostic_ungated_score": diag_score,
        "diagnostic_ungated_score_source": diag_source,
        "diagnostic_only": True,
        "phase_1_score": _phase_score(phase_1),
        "phase_2_score": _phase_score(phase_2),
        "components_phase_1": phase_1 if isinstance(phase_1, dict) else None,
        "components_phase_2": phase_2 if isinstance(phase_2, dict) else None,
        "component_availability": _component_availability(mk_row),
        "normalization_profile_version": mk_row.get("normalization_profile_version"),
        "normalization_profile_hash": mk_row.get("normalization_profile_hash"),
        "normalization_sample_size": mk_row.get("normalization_sample_size"),
        "normalization_cutoff": as_dict(
            as_dict(snap.purchasability_compatibility_json).get("normalization_profile")
        ).get("cutoff")
        if not mk_row.get("normalization_cutoff")
        else mk_row.get("normalization_cutoff"),
        "reason_codes": list(mk_row.get("reason_codes") or []),
        "status": mk_row.get("status"),
        "formula_version": mk_row.get("formula_version"),
        "parity_status": mk_row.get("parity_status"),
        "formula_recomputed": False,
        "source_values_from_frozen_snapshot": True,
    }


def iter_compact_evaluations(
    *,
    run_id: int,
    snaps: Iterable[Any],
    markets: Iterable[Any],
) -> Iterator[dict[str, Any]]:
    markets_index = index_markets_by_snap_key(markets)
    for snap in snaps:
        purch = as_dict(getattr(snap, "purchasability_compatibility_json", None))
        for mk_row in purch.get("markets") or []:
            if not isinstance(mk_row, dict):
                continue
            yield build_compact_evaluation_row(
                run_id=run_id,
                snap=snap,
                mk_row=mk_row,
                markets_index=markets_index,
            )


def collect_compact_evaluations(
    *,
    run_id: int,
    snaps: Iterable[Any],
    markets: Iterable[Any],
) -> list[dict[str, Any]]:
    return list(iter_compact_evaluations(run_id=run_id, snaps=snaps, markets=markets))


def build_decision_rows(
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Una decisione per snapshot × gruppo: max final_score persistito nella famiglia."""
    by_snap_group: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    snap_meta: dict[int, dict[str, Any]] = {}

    for ev in evaluations:
        mk = ev.get("market_key")
        if not mk or mk not in MARKET_TO_DECISION_GROUP:
            continue
        group = MARKET_TO_DECISION_GROUP[mk]
        sid = int(ev["snapshot_id"])
        by_snap_group[(sid, group)].append(ev)
        snap_meta.setdefault(
            sid,
            {
                "run_id": ev.get("run_id"),
                "competition_name": ev.get("competition_name"),
                "kickoff_at": ev.get("kickoff_at"),
            },
        )

    decisions: list[dict[str, Any]] = []
    for (sid, group), rows in sorted(by_snap_group.items(), key=lambda x: (x[0][0], x[0][1])):
        candidate_markets = list(DECISION_GROUPS[group])
        evaluated = [r for r in rows if r.get("market_key") in candidate_markets]
        accepted = [r for r in evaluated if r.get("gate_status") == "accepted"]
        rejected = [r for r in evaluated if r.get("gate_status") != "accepted"]

        selected = None
        selection_tied = False
        tied_keys: list[str] = []
        selection_rule = "max_persisted_final_score_within_decision_group"

        if accepted:
            scored = []
            for r in accepted:
                sc = _safe_float(r.get("final_score"))
                if sc is None:
                    continue
                scored.append((sc, str(r.get("market_key")), r))
            if scored:
                max_score = max(s[0] for s in scored)
                tied = sorted([s for s in scored if s[0] == max_score], key=lambda x: x[1])
                selection_tied = len(tied) > 1
                tied_keys = [t[1] for t in tied]
                selected = tied[0][2]  # lessicografico deterministico
                if selection_tied:
                    selection_rule = (
                        "max_persisted_final_score_within_decision_group;"
                        "tie_break_lexicographic_market_key"
                    )

        # Best diagnostic ungated tra tutti i candidati (anche rejected)
        best_diag = None
        best_diag_mk = None
        for r in evaluated:
            d = _safe_float(r.get("diagnostic_ungated_score"))
            if d is None:
                continue
            if best_diag is None or d > best_diag or (
                d == best_diag and str(r.get("market_key")) < str(best_diag_mk or "")
            ):
                best_diag = d
                best_diag_mk = r.get("market_key")

        highest = None
        scores_all = [_safe_float(r.get("final_score")) for r in evaluated]
        scores_all = [s for s in scores_all if s is not None]
        if scores_all:
            highest = max(scores_all)

        is_dc = group == DECISION_GROUP_DC
        meta = snap_meta.get(sid, {})
        run_id = int(meta.get("run_id") or (evaluated[0]["run_id"] if evaluated else 0))

        sel_qq = selected.get("quote_quality") if selected else None
        sel_odds = None
        if selected:
            if selected.get("real_book_odds") is not None:
                sel_odds = selected.get("real_book_odds")
            elif selected.get("derived_odds") is not None:
                sel_odds = selected.get("derived_odds")

        decisions.append(
            {
                "decision_id": build_decision_id(
                    run_id=run_id, snapshot_id=sid, decision_group=group
                ),
                "run_id": run_id,
                "snapshot_id": sid,
                "competition_name": meta.get("competition_name"),
                "kickoff_at": meta.get("kickoff_at"),
                "decision_group": group,
                "candidate_markets": candidate_markets,
                "evaluated_markets_count": len(evaluated),
                "accepted_markets_count": len(accepted),
                "rejected_markets_count": len(rejected),
                "highest_final_score": highest,
                "selected_market_key": selected.get("market_key") if selected else None,
                "selected_score": selected.get("final_score") if selected else None,
                "selected_gate_status": selected.get("gate_status") if selected else None,
                "selection_tied": selection_tied,
                "tied_market_keys": tied_keys if selection_tied else [],
                "selection_rule": selection_rule,
                "selected_quote_quality": sel_qq,
                "selected_odds": sel_odds,
                "selected_won": selected.get("won") if selected else None,
                "selected_profit_1u_real": (
                    selected.get("profit_1u_real") if selected else None
                ),
                "selected_profit_1u_synthetic": (
                    selected.get("profit_1u_synthetic") if selected else None
                ),
                "performance_available": bool(
                    selected and selected.get("performance_eligible")
                ),
                "best_diagnostic_ungated_score": best_diag,
                "best_diagnostic_ungated_market_key": best_diag_mk,
                "performance_type": "synthetic" if is_dc else "real",
                "not_real_bet365_strategy": is_dc,
                "diagnostic_only": True,
                "not_a_production_strategy": True,
            }
        )
    return decisions


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _drift_bucket_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    computed = sum(1 for r in rows if r.get("status") in ("ok", "available", "partial") or r.get("final_score") is not None)
    insuff = sum(1 for r in rows if r.get("gate_status") == "not_evaluated_insufficient_history")
    unsupp = sum(1 for r in rows if r.get("gate_status") == "unsupported_market")
    unavail = sum(1 for r in rows if r.get("gate_status") == "unavailable_inputs")
    accepted = [r for r in rows if r.get("gate_status") == "accepted"]
    rejected = [r for r in rows if str(r.get("gate_status", "")).startswith("rejected_")]
    zeros = [r for r in rows if _safe_float(r.get("final_score")) == 0.0]
    ge80 = [
        r
        for r in accepted
        if (_safe_float(r.get("final_score")) or -1) >= 80
    ]
    accepted_scores = sorted(
        s for s in (_safe_float(r.get("final_score")) for r in accepted) if s is not None
    )
    samples = [
        s
        for s in (_safe_int(r.get("normalization_sample_size")) for r in rows)
        if s is not None
    ]
    hashes = [r.get("normalization_profile_hash") for r in rows if r.get("normalization_profile_hash")]
    distinct = sorted({str(h) for h in hashes})

    return {
        "evaluations_count": n,
        "computed_count": computed,
        "insufficient_history_count": insuff,
        "unsupported_count": unsupp,
        "unavailable_count": unavail,
        "gate_accepted_count": len(accepted),
        "gate_rejected_count": len(rejected),
        "gate_accepted_pct": round(100.0 * len(accepted) / n, 2) if n else None,
        "score_zero_count": len(zeros),
        "score_zero_pct": round(100.0 * len(zeros) / n, 2) if n else None,
        "score_ge_80_count": len(ge80),
        "score_ge_80_pct": round(100.0 * len(ge80) / n, 2) if n else None,
        "mean_accepted_score": (
            round(statistics.mean(accepted_scores), 2) if accepted_scores else None
        ),
        "median_accepted_score": (
            round(float(statistics.median(accepted_scores)), 2) if accepted_scores else None
        ),
        "p10_accepted_score": (
            round(_percentile(accepted_scores, 10) or 0, 2) if accepted_scores else None
        ),
        "p90_accepted_score": (
            round(_percentile(accepted_scores, 90) or 0, 2) if accepted_scores else None
        ),
        "mean_normalization_sample_size": (
            round(statistics.mean(samples), 2) if samples else None
        ),
        "min_normalization_sample_size": min(samples) if samples else None,
        "max_normalization_sample_size": max(samples) if samples else None,
        "distinct_profile_hashes": len(distinct),
        "first_profile_hash": distinct[0] if distinct else None,
        "last_profile_hash": distinct[-1] if distinct else None,
        "positive_cap": None,
        "negative_cap": None,
        "clipping_count": None,
        "clipping_pct": None,
        "cap_diagnostics_available": False,
    }


def build_purchasability_drift(
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)

    timeline_keys: list[tuple[str, int, str]] = []
    for ev in evaluations:
        ko = ev.get("kickoff_at") or ""
        month = ko[:7] if len(str(ko)) >= 7 else "unknown"
        by_month[month].append(ev)
        comp = str(ev.get("competition_name") or "unknown")
        by_comp[comp].append(ev)
        timeline_keys.append((str(ko), int(ev.get("snapshot_id") or 0), str(ev.get("market_key") or "")))

    # Timeline: ordina per kickoff; stesso kickoff non implica ordine causale
    timeline_sorted = sorted(set(timeline_keys), key=lambda x: (x[0], x[1], x[2]))

    return {
        "schema_version": PURCHASABILITY_EXPORT_SCHEMA_VERSION,
        "diagnostic_only": True,
        "cap_diagnostics_available": False,
        "same_kickoff_no_invented_causal_order": True,
        "by_month": {
            m: _drift_bucket_stats(rows) for m, rows in sorted(by_month.items())
        },
        "by_competition": {
            c: _drift_bucket_stats(rows) for c, rows in sorted(by_comp.items())
        },
        "overall": _drift_bucket_stats(evaluations),
        "timeline_kickoff_order": [
            {"kickoff_at": k[0] or None, "snapshot_id": k[1], "market_key": k[2]}
            for k in timeline_sorted[:5000]  # cap diagnostico
        ],
        "timeline_truncated": len(timeline_sorted) > 5000,
    }


def build_purchasability_profiles(
    *,
    snaps: Iterable[Any],
    evaluations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Una riga per normalization_profile_hash — solo dati persistiti."""
    by_hash: dict[str, dict[str, Any]] = {}
    for snap in snaps:
        purch = as_dict(getattr(snap, "purchasability_compatibility_json", None))
        profile = as_dict(purch.get("normalization_profile"))
        h = profile.get("hash")
        if not h:
            # fallback da markets[]
            for mk_row in purch.get("markets") or []:
                if isinstance(mk_row, dict) and mk_row.get("normalization_profile_hash"):
                    h = mk_row.get("normalization_profile_hash")
                    if h and h not in by_hash:
                        by_hash[str(h)] = {
                            "normalization_profile_hash": str(h),
                            "normalization_profile_version": mk_row.get(
                                "normalization_profile_version"
                            ),
                            "sample_size": mk_row.get("normalization_sample_size"),
                            "cutoff": None,
                            "min_side_samples": None,
                            "source": None,
                            "persisted_profile_fields_only": True,
                        }
            continue
        h = str(h)
        if h not in by_hash:
            by_hash[h] = {
                "normalization_profile_hash": h,
                "normalization_profile_version": profile.get("version"),
                "sample_size": profile.get("sample_size"),
                "cutoff": profile.get("cutoff"),
                "min_side_samples": profile.get("min_side_samples"),
                "source": profile.get("source"),
                "persisted_profile_fields_only": True,
            }
    return [by_hash[k] for k in sorted(by_hash.keys())]


def build_market_join_diagnostics_purch(
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(evaluations)
    counts = {
        MARKET_JOIN_MATCHED: 0,
        MARKET_JOIN_MISSING: 0,
        MARKET_JOIN_AMBIGUOUS: 0,
        PURCH_JOIN_INVALID: 0,
    }
    by_market: dict[str, dict[str, int]] = defaultdict(lambda: {k: 0 for k in counts})
    by_comp: dict[str, dict[str, int]] = defaultdict(lambda: {k: 0 for k in counts})
    for ev in evaluations:
        st = _normalize_join_status(ev.get("market_join_status") or MARKET_JOIN_MISSING)
        if st not in counts:
            st = MARKET_JOIN_MISSING
        counts[st] += 1
        mk = str(ev.get("market_key") or "INVALID")
        by_market[mk][st] += 1
        comp = str(ev.get("competition_name") or "unknown")
        by_comp[comp][st] += 1
    matched = counts[MARKET_JOIN_MATCHED]
    return {
        "evaluations_total": total,
        "matched_count": matched,
        "missing_count": counts[MARKET_JOIN_MISSING],
        "ambiguous_count": counts[MARKET_JOIN_AMBIGUOUS],
        "invalid_count": counts[PURCH_JOIN_INVALID],
        "matched_pct": round(100.0 * matched / total, 2) if total else None,
        "by_market_key": dict(sorted(by_market.items())),
        "by_competition": dict(sorted(by_comp.items())),
        "matched_plus_missing_plus_ambiguous_plus_invalid_equals_total": (
            sum(counts.values()) == total
        ),
    }


def build_export_reconciliation(
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    ids = [e["purchasability_evaluation_id"] for e in evaluations]
    unique = set(ids)
    dup = len(ids) - len(unique)
    join = build_market_join_diagnostics_purch(evaluations)
    return {
        "market_evaluations": len(evaluations),
        "unique_evaluation_ids": len(unique),
        "duplicate_evaluation_ids": dup,
        "evaluation_id_unique": dup == 0,
        "matched_plus_missing_plus_ambiguous_plus_invalid_equals_total": join[
            "matched_plus_missing_plus_ambiguous_plus_invalid_equals_total"
        ],
        "source_snapshots_unchanged": True,
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[str(r.get(key) or "unknown")] += 1
    return dict(sorted(out.items()))


def _gate_status_by_market(evaluations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in evaluations:
        mk = str(ev.get("market_key") or "INVALID")
        out[mk][str(ev.get("gate_status") or "unknown")] += 1
    return {mk: dict(sorted(v.items())) for mk, v in sorted(out.items())}


def _accepted_band_by_market(evaluations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in evaluations:
        if ev.get("gate_status") != "accepted":
            continue
        mk = str(ev.get("market_key") or "INVALID")
        band = str(ev.get("accepted_score_band") or "unavailable")
        out[mk][band] += 1
    return {mk: dict(sorted(v.items())) for mk, v in sorted(out.items())}


def _rejected_reason_by_market(evaluations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in evaluations:
        st = str(ev.get("gate_status") or "")
        if not st.startswith("rejected_"):
            continue
        mk = str(ev.get("market_key") or "INVALID")
        reasons = ev.get("gate_reasons") or [st]
        for reason in reasons:
            out[mk][str(reason)] += 1
    return {mk: dict(sorted(v.items())) for mk, v in sorted(out.items())}


def _score_dist_by(
    evaluations: list[dict[str, Any]], key: str
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in evaluations:
        dim = str(ev.get(key) or "unknown")
        band = str(ev.get("accepted_score_band") or "unavailable")
        out[dim][band] += 1
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def _threshold_diagnostics(
    evaluations: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Soglie descrittive same-season — solo diagnostica."""

    def _slice_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        comps = {str(r.get("competition_name") or "unknown") for r in rows}
        # metà temporale per kickoff
        with_ko = sorted(
            [r for r in rows if r.get("kickoff_at")],
            key=lambda r: str(r.get("kickoff_at")),
        )
        mid = len(with_ko) // 2
        first_half = with_ko[:mid]
        second_half = with_ko[mid:]
        main_comp = None
        if comps:
            from collections import Counter

            c = Counter(str(r.get("competition_name") or "unknown") for r in rows)
            main_comp, main_n = c.most_common(1)[0]
            main_pct = round(100.0 * main_n / n, 2) if n else None
        else:
            main_pct = None
        return {
            "sample_size": n,
            "competitions_count": len(comps),
            "first_half_sample_size": len(first_half),
            "second_half_sample_size": len(second_half),
            "main_competition": main_comp,
            "main_competition_concentration_pct": main_pct,
        }

    by_group: dict[str, Any] = {}
    for group in DECISION_GROUPS:
        group_dec = [d for d in decisions if d.get("decision_group") == group]
        for label, thr in THRESHOLD_SPECS:
            if thr is None:
                subset = [
                    d
                    for d in group_dec
                    if d.get("selected_gate_status") == "accepted"
                ]
            else:
                subset = [
                    d
                    for d in group_dec
                    if d.get("selected_gate_status") == "accepted"
                    and (_safe_float(d.get("selected_score")) or -1) >= thr
                ]
            # Arricchisci con evaluation rows per kickoff/comp
            sel_keys = {
                (d.get("snapshot_id"), d.get("selected_market_key")) for d in subset
            }
            ev_subset = [
                e
                for e in evaluations
                if (e.get("snapshot_id"), e.get("market_key")) in sel_keys
            ]
            by_group.setdefault(group, {})[label] = {
                **_slice_stats(ev_subset),
                "decisions_count": len(subset),
                "diagnostic_only": True,
                "discovered_on_same_season": True,
                "not_validated_out_of_sample": True,
                "not_a_betting_strategy": True,
            }

    by_market: dict[str, Any] = {}
    for mk in sorted({str(e.get("market_key")) for e in evaluations if e.get("market_key")}):
        mk_rows = [e for e in evaluations if e.get("market_key") == mk]
        for label, thr in THRESHOLD_SPECS:
            if thr is None:
                subset = [e for e in mk_rows if e.get("gate_status") == "accepted"]
            else:
                subset = [
                    e
                    for e in mk_rows
                    if e.get("gate_status") == "accepted"
                    and (_safe_float(e.get("final_score")) or -1) >= thr
                ]
            real = [e for e in subset if e.get("quote_quality") == "real"]
            derived = [e for e in subset if e.get("quote_quality") == "derived"]
            by_market.setdefault(mk, {})[label] = {
                **_slice_stats(subset),
                "real_quote_count": len(real),
                "derived_quote_count": len(derived),
                "diagnostic_only": True,
                "discovered_on_same_season": True,
                "not_validated_out_of_sample": True,
                "not_a_betting_strategy": True,
            }

    return {
        "by_decision_group": by_group,
        "by_market": by_market,
        "diagnostic_only": True,
        "discovered_on_same_season": True,
        "not_validated_out_of_sample": True,
        "not_a_betting_strategy": True,
    }


def build_purchasability_export_summary(
    *,
    evaluations: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    drift: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    join = build_market_join_diagnostics_purch(evaluations)
    recon = build_export_reconciliation(evaluations)

    gate_rejected_zero = sum(
        1
        for e in evaluations
        if e.get("score_zero_semantics") == "gate_rejected"
    )
    calculated_zero = sum(
        1 for e in evaluations if e.get("score_zero_semantics") == "calculated_zero"
    )
    final_zero = sum(
        1 for e in evaluations if _safe_float(e.get("final_score")) == 0.0
    )
    diag_avail = sum(
        1 for e in evaluations if e.get("diagnostic_ungated_score") is not None
    )

    reason_counts: dict[str, int] = defaultdict(int)
    for e in evaluations:
        for r in e.get("gate_reasons") or []:
            reason_counts[str(r)] += 1

    return {
        "export_schema_version": PURCHASABILITY_EXPORT_SCHEMA_VERSION,
        "evaluations_total": len(evaluations),
        "evaluations_by_status": _count_by(evaluations, "status"),
        "gate_status_counts": _count_by(evaluations, "gate_status"),
        "gate_reason_counts": dict(sorted(reason_counts.items())),
        "final_score_zero_count": final_zero,
        "gate_rejected_zero_count": gate_rejected_zero,
        "calculated_zero_count": calculated_zero,
        "diagnostic_ungated_score_available_count": diag_avail,
        "market_join_diagnostics": join,
        "quote_quality_counts": _count_by(evaluations, "quote_quality"),
        "decision_group_counts": _count_by(decisions, "decision_group"),
        "gate_status_by_market": _gate_status_by_market(evaluations),
        "accepted_score_band_by_market": _accepted_band_by_market(evaluations),
        "rejected_gate_reason_by_market": _rejected_reason_by_market(evaluations),
        "score_distribution_by_market": _score_dist_by(evaluations, "market_key"),
        "score_distribution_by_competition": _score_dist_by(
            evaluations, "competition_name"
        ),
        "normalization_drift_summary": drift.get("overall"),
        "unique_normalization_profiles": len(profiles),
        "profile_deduplication_applied": True,
        "threshold_diagnostics": _threshold_diagnostics(evaluations, decisions),
        "compact_export_reconciliation": recon,
        "formula_recomputed": False,
        "run_snapshot_modified": False,
        "observational_warning": OBSERVATIONAL_WARNING,
        "diagnostic_only": True,
    }


def build_dashboard_purchasability_views(
    *,
    evaluations: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    drift: dict[str, Any],
) -> dict[str, Any]:
    """Payload aggiuntivo per le 4 viste dashboard."""
    scores_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in evaluations:
        mk = str(ev.get("market_key") or "INVALID")
        scores_by_market[mk].append(
            {
                "market_key": mk,
                "gate_status": ev.get("gate_status"),
                "gate_label": (
                    "Bloccato dal gate"
                    if str(ev.get("gate_status", "")).startswith("rejected_")
                    else (
                        "Accettato"
                        if ev.get("gate_status") == "accepted"
                        else str(ev.get("gate_status") or "—")
                    )
                ),
                "final_score": ev.get("final_score"),
                "diagnostic_ungated_score": ev.get("diagnostic_ungated_score"),
                "rating": ev.get("rating"),
                "edge_pct": ev.get("edge_pct"),
                "vantaggio_prob": ev.get("vantaggio_prob"),
                "quote_quality": ev.get("quote_quality"),
                "real_book_odds": ev.get("real_book_odds"),
                "derived_odds": ev.get("derived_odds"),
                "won": ev.get("won"),
                "profit_1u_real": ev.get("profit_1u_real"),
                "profit_1u_synthetic": ev.get("profit_1u_synthetic"),
                "score_class": ev.get("score_class"),
                "competition_name": ev.get("competition_name"),
                "home_team": ev.get("home_team"),
                "away_team": ev.get("away_team"),
                "kickoff_at": ev.get("kickoff_at"),
            }
        )

    gate_summary = {
        "accepted": sum(1 for e in evaluations if e.get("gate_status") == "accepted"),
        "rejected": sum(
            1
            for e in evaluations
            if str(e.get("gate_status", "")).startswith("rejected_")
        ),
        "other": sum(
            1
            for e in evaluations
            if e.get("gate_status") != "accepted"
            and not str(e.get("gate_status", "")).startswith("rejected_")
        ),
        "gate_status_counts": _count_by(evaluations, "gate_status"),
        "gate_reason_counts": {},
        "gate_status_by_market": _gate_status_by_market(evaluations),
        "gate_rejected_zero_count": sum(
            1 for e in evaluations if e.get("score_zero_semantics") == "gate_rejected"
        ),
        "blocked_label": "Bloccato dal gate",
    }
    reason_counts: dict[str, int] = defaultdict(int)
    for e in evaluations:
        for r in e.get("gate_reasons") or []:
            reason_counts[str(r)] += 1
    gate_summary["gate_reason_counts"] = dict(sorted(reason_counts.items()))

    decisions_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in decisions:
        decisions_by_group[str(d.get("decision_group"))].append(d)

    return {
        "scores_by_market": {k: v for k, v in sorted(scores_by_market.items())},
        "gate": gate_summary,
        "decisions_by_group": {
            k: v for k, v in sorted(decisions_by_group.items())
        },
        "drift": {
            "by_month": drift.get("by_month"),
            "by_competition": drift.get("by_competition"),
            "overall": drift.get("overall"),
        },
        "observational_warning": OBSERVATIONAL_WARNING,
    }


def purchasability_manifest_fields(
    *,
    include_legacy_full: bool,
    line_counts: dict[str, int],
    unique_profiles: int,
) -> dict[str, Any]:
    return {
        "purchasability_export_schema_version": PURCHASABILITY_EXPORT_SCHEMA_VERSION,
        "canonical_analysis_file": "purchasability_compact.jsonl",
        "decision_file": "purchasability_decisions.jsonl",
        "legacy_full_payload_included": include_legacy_full,
        "legacy_raw_payload_omitted_from_module_report": not include_legacy_full,
        "profile_deduplication_applied": True,
        "unique_normalization_profiles": unique_profiles,
        "formula_recomputed": False,
        "source_values_from_frozen_snapshot": True,
        "run_snapshot_modified": False,
        "purchasability_line_counts": dict(line_counts),
    }
