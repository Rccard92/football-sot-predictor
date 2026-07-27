"""Export ZIP report ottimizzato per analisi ChatGPT."""

from __future__ import annotations

import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_DERIVATION_METHOD,
    HISTORICAL_KPI_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION,
    HISTORICAL_SCAN_VERSION,
    PARSER_VERSION,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE

REPORT_SCHEMA_VERSION = "cecchino_lab_ai_report_v2"

AI_INSTRUCTIONS_MD = """# Istruzioni per ChatGPT — Report storico Cecchino Lab

1. Leggi prima `manifest.json` e `SCHEMA.md`.
2. Usa **solo** `eligible_analysis` per hit rate, profitto, ROI, fasce rating, pattern e analisi segnali.
3. `excluded_diagnostics` è diagnostica separata: non mescolarla con la performance.
4. Non confondere quote **reali Bet365** e quote **derivate**.
5. Non sommare ROI reale e ROI sintetico.
6. Non trattare quote derivate come offerte Bet365.
7. Non confondere `quota_cecchino` (modello) e `quota_book` (bookmaker).
8. La frequenza naturale di un mercato (`outcome_base_rate`) **non** è “performance del Cecchino”.
9. Distingui: outcome base rate; mercato con quota Cecchino; con rating; con segnale attivo; con quota Bet365 reale; con quota derivata.
10. Intensità Goal e Acquistabilità: puoi studiare le **feature/input**, non validare i punteggi finali (`v5_score_not_executed` / `final_score_not_executed`).
11. Non utilizzare risultati futuri come input: il blocco pre-match è congelato prima del risultato.
12. Riporta sempre `sample_size`. Separa risultati globali e per campionato.
13. Segnala instabilità cross-competition.
14. Non proporre modifiche automatiche a formule, pesi o soglie produttive.
15. Distingui correlazione, ipotesi e prova.
16. Se `is_partial_run=true`, non trattare il report come scansione stagione completa.
17. Produci una “prima linea” con:
    1. dati sufficienti;
    2. dati mancanti;
    3. moduli pienamente analizzabili;
    4. moduli parziali (feature only);
    5. segnali promettenti;
    6. segnali negativi;
    7. aspetti da verificare sulle stagioni successive.

Cecchino Today operativo resta su **Betfair** e non è modificato da questo report.
"""

SCHEMA_MD = """# Schema report AI Cecchino Lab (v2)

- `manifest.json`: metadati run, policy, scope (full/pilot), versioni moduli
- `summary.json`: sezioni `eligible_analysis`, `excluded_diagnostics`, `errors`, `data_coverage`
- `data_quality.json`: qualità dati stagione (preflight)
- `eligibility.json`: conteggi eleggibilità
- `module_coverage.json`: copertura moduli + limiti Intensità/Acquistabilità
- `matches.jsonl`: una riga JSON per partita (pre-match separato dal risultato)
- `markets.jsonl`: una riga per partita×mercato **solo eligible_core** (con eligibility_status e competition_name)
- `patterns.json`: pattern combinati con soglie sample (`small_sample` / `descriptive_only` / `candidate_for_review`)
- `AI_INSTRUCTIONS.md`: istruzioni analisi
- `SCHEMA.md`: questo file

Metriche di performance (hit/ROI/profit) usano esclusivamente partite `eligible_core`.
"""


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _agg_bucket() -> dict[str, Any]:
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
    }


def _finalize_bucket(b: dict[str, Any]) -> dict[str, Any]:
    comps = b.pop("competitions", set()) or set()
    n = b["won"] + b["lost"]
    b["hit_rate"] = round(b["won"] / n, 4) if n else None
    if b["real_quote_count"]:
        b["real_roi_pct"] = round(100.0 * b["real_profit_1u"] / b["real_quote_count"], 2)
    if b["derived_quote_count"]:
        b["synthetic_roi_pct"] = round(
            100.0 * b["synthetic_profit_1u"] / b["derived_quote_count"], 2
        )
    b["competitions_count"] = len(comps)
    b["competitions"] = sorted(comps)
    if n < 30:
        b["warnings"].append("small_sample")
    b["real_profit_1u"] = round(b["real_profit_1u"], 4)
    b["synthetic_profit_1u"] = round(b["synthetic_profit_1u"], 4)
    return b


def _rating_band(rating: Any) -> str | None:
    if rating is None:
        return None
    r = int(rating)
    base = (r // 10) * 10
    return f"{base}-{base + 9}"


def _edge_band(edge_pct: Any) -> str | None:
    if edge_pct is None:
        return None
    e = float(edge_pct)
    if e < 0:
        return "neg"
    if e < 5:
        return "0-5"
    if e < 10:
        return "5-10"
    return "10+"


def _signal_meta(sources_json: Any) -> dict[str, Any]:
    if isinstance(sources_json, dict):
        return {
            "signal_family": sources_json.get("signal_family"),
            "signal_families": sources_json.get("signal_families") or [],
            "active_signal_count": int(sources_json.get("active_signal_count") or 0),
            "sources": sources_json.get("sources") or [],
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


def _balance_pillars(balance: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(balance, dict):
        return {}
    pillars: dict[str, Any] = {}
    for key in (
        "f36",
        "side_probability_gap",
        "draw",
        "operational",
        "structural_summary",
        "pillars",
    ):
        block = balance.get(key)
        if isinstance(block, dict):
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label"),
                "value": block.get("value") or block.get("score") or block.get("f36_abs"),
            }
    # Heuristic: top-level class keys sometimes nested under analysis blocks
    for key, block in balance.items():
        if key in pillars or not isinstance(block, dict):
            continue
        if "class_key" in block or "class" in block:
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label"),
                "value": block.get("value") or block.get("score"),
            }
    return pillars


def _pattern_status(
    *,
    sample_size: int,
    competitions_count: int,
    competition_shares: dict[str, int],
) -> str:
    if sample_size < 30:
        return "small_sample"
    if sample_size < 100:
        return "descriptive_only"
    # >= 100: candidate solo se non monopolio di un campionato / poche partite
    if competitions_count <= 1:
        return "descriptive_only"
    if competition_shares:
        top = max(competition_shares.values())
        if top / max(sample_size, 1) >= 0.85:
            return "descriptive_only"
        if top < 15:
            return "descriptive_only"
    return "candidate_for_review"


def _add_market_row(
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
    elif m.is_derived_quote:
        b["derived_quote_count"] += 1
        if m.profit_1u_synthetic is not None:
            b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)
    else:
        b["unavailable_quote_count"] += 1
    if m.quota_cecchino is not None:
        b["with_cecchino_quote"] += 1
    if m.rating is not None:
        b["with_rating"] += 1
    if m.signal_active:
        b["with_signal_active"] += 1


def build_ai_report_zip_bytes(db: Session, run_id: int) -> tuple[str, bytes]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    snaps = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot)
            .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
            .order_by(CecchinoLabHistoricalMatchSnapshot.chronological_order.asc().nulls_last())
        ).all()
    )
    markets = list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult).where(
                CecchinoLabHistoricalMarketResult.run_id == run_id
            )
        ).all()
    )
    markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]] = defaultdict(list)
    for m in markets:
        markets_by_snap[int(m.match_snapshot_id)].append(m)

    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    is_partial = bool(policy.get("is_partial_run"))
    run_scope = policy.get("run_scope") or ("pilot" if is_partial else "full")

    season_slug = run.season_label.replace("/", "_")
    scope_tag = "pilot" if is_partial else "full"
    filename = f"cecchino_lab_{season_slug}_{scope_tag}_ai_report_run_{run_id}.zip"

    competitions = sorted({s.competition_name for s in snaps})
    datasets = sorted({int(s.dataset_id) for s in snaps})
    eligible_snaps = [s for s in snaps if s.historical_eligibility_status == ELIGIBLE_CORE]
    excluded_snaps = [
        s
        for s in snaps
        if s.historical_eligibility_status
        and s.historical_eligibility_status != ELIGIBLE_CORE
        and s.historical_eligibility_status != "error"
    ]
    error_snaps = [s for s in snaps if s.historical_eligibility_status == "error"]
    eligible_ids = {int(s.id) for s in eligible_snaps}
    eligible_markets = [m for m in markets if int(m.match_snapshot_id) in eligible_ids]

    manifest = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": int(run.id),
        "season_label": run.season_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "Rccard92/football-sot-predictor",
        "source_git_commit": run.source_git_commit,
        "scan_version": run.scan_version or HISTORICAL_SCAN_VERSION,
        "parser_version": PARSER_VERSION,
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "max_matches": policy.get("max_matches"),
        "not_full_season_report": is_partial,
        "modules": {
            "cecchino_engine": "imported_pure",
            "kpi": HISTORICAL_KPI_VERSION,
            "source_builder_version": "cecchino_kpi_v2_betfair",
            "balance_v5": "imported_pure",
            "signals_matrix": "imported_pure",
            "goal_intensity": "raw_features_export_only",
            "purchasability": "inputs_export_only",
        },
        "competitions_included": competitions,
        "datasets_included": datasets,
        "quote_policy": HISTORICAL_QUOTE_POLICY_VERSION,
        "derivation_policy": HISTORICAL_DERIVATION_METHOD,
        "anti_leakage_policy": "strict_prior_kickoff_same_competition_only",
        "performance_universe": "eligible_core_only",
        "profit_policy": {
            "real": "profit_1u_real from real Bet365 quotes only",
            "synthetic": "profit_1u_synthetic from derived quotes only",
            "do_not_sum": True,
        },
        "actual_vs_derived_definitions": {
            "actual_bet365": "complete closing or complete pre family",
            "synthetic_derived": "DC fair from normalized 1X2",
            "no_book_quote": "market without book quote",
        },
        "limitations": [
            "Prima stagione nella nuova pipeline: nessun prior da stagioni precedenti",
            "Prime giornate con campione insufficiente escluse dalle metriche di performance",
            "Intensità Goal: feature raw esportate; v5 score non eseguito",
            "Acquistabilità: input esportati; final score operativo non eseguito",
            *(
                ["Run parziale (pilot): non confrontare come report stagione completa"]
                if is_partial
                else []
            ),
        ],
        "modules_not_executed": [
            "goal_intensity_v5_score",
            "purchasability_v2_operational_final_score",
        ],
        "operational_today_bookmaker": "Betfair",
        "historical_replay_bookmaker": "Bet365",
        "operational_today_modified": False,
        "do_not_propose_formula_changes": True,
    }

    eligibility: dict[str, int] = defaultdict(int)
    for s in snaps:
        eligibility[s.historical_eligibility_status] += 1

    data_quality = run.preflight_json or {}
    module_coverage = {
        "eligible_core": eligibility.get(ELIGIBLE_CORE, 0),
        "excluded": len(excluded_snaps),
        "errors": len(error_snaps),
        "with_kpi": sum(1 for s in eligible_snaps if s.historical_kpi_json),
        "with_signals": sum(1 for s in eligible_snaps if s.signals_json),
        "with_balance": sum(1 for s in eligible_snaps if s.balance_v5_json),
        "goal_intensity": {
            "raw_features_available": sum(
                1
                for s in eligible_snaps
                if (s.goal_intensity_compatibility_json or {}).get("raw_features_available")
            ),
            "v5_score_not_executed": True,
            "note": "Prima scansione: studiare feature, non validare punteggio finale",
        },
        "purchasability": {
            "inputs_available": sum(
                1
                for s in eligible_snaps
                if (s.purchasability_compatibility_json or {}).get("inputs_available")
            ),
            "final_score_not_executed": True,
            "note": "Prima scansione: studiare input, non validare score operativo",
        },
    }

    snap_by_id = {int(s.id): s for s in snaps}
    buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(_agg_bucket))

    # Coverage / base-rate style counters (eligible only) — not labeled as Cecchino performance
    coverage_counters = {
        "outcome_base_rate": _agg_bucket(),
        "with_cecchino_quote": _agg_bucket(),
        "with_rating": _agg_bucket(),
        "with_signal_active": _agg_bucket(),
        "with_real_bet365_quote": _agg_bucket(),
        "with_derived_quote": _agg_bucket(),
    }

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        comp = s.competition_name if s else None
        _add_market_row(buckets, "market", m.market_key, m, comp)
        _add_market_row(
            buckets,
            "quote_type",
            "real" if m.is_real_book_quote else ("derived" if m.is_derived_quote else "unavailable"),
            m,
            comp,
        )
        if s:
            _add_market_row(buckets, "competition", s.competition_name, m, comp)
            rb = _rating_band(m.rating)
            if rb:
                _add_market_row(buckets, "rating_band", rb, m, comp)
            eb = _edge_band(m.edge_pct)
            if eb:
                _add_market_row(buckets, "edge_band", eb, m, comp)
            if s.kickoff_at:
                _add_market_row(
                    buckets,
                    "month",
                    f"{s.kickoff_at.year}-{s.kickoff_at.month:02d}",
                    m,
                    comp,
                )
            qs = (s.quote_sources_json or {}).get("family_1x2") or {}
            snap_type = qs.get("family_snapshot_type") or "none"
            _add_market_row(buckets, "closing_or_pre", str(snap_type), m, comp)
            bal = s.balance_v5_json or {}
            if isinstance(bal, dict):
                structural = bal.get("structural_summary") or {}
                cls = structural.get("class") or structural.get("class_key") or "unknown"
                _add_market_row(buckets, "balance_class", str(cls), m, comp)
                pillars = _balance_pillars(bal)
                for pname, pblock in pillars.items():
                    ck = pblock.get("class_key")
                    if ck:
                        _add_market_row(buckets, f"balance_pillar_{pname}", str(ck), m, comp)
            # historical sample size band from input snapshot
            prior = (s.input_snapshot_json or {}).get("prior_count")
            if prior is not None:
                p = int(prior)
                band = "0-9" if p < 10 else ("10-29" if p < 30 else ("30-99" if p < 100 else "100+"))
                _add_market_row(buckets, "historical_sample_band", band, m, comp)

        sig = _signal_meta(m.signal_sources_json)
        if m.signal_active:
            fam = sig.get("signal_family") or "unknown"
            _add_market_row(buckets, "signal_family", str(fam), m, comp)
            _add_market_row(
                buckets,
                "active_signal_count",
                str(sig.get("active_signal_count") or 0),
                m,
                comp,
            )
            for src in sig.get("sources") or []:
                if isinstance(src, dict):
                    model = src.get("column_key") or src.get("source_column") or "unknown"
                    _add_market_row(buckets, "signal_model", str(model), m, comp)
                    cell = f"{src.get('signal_group')}:{src.get('source_column')}"
                    _add_market_row(buckets, "signal_cell", cell, m, comp)

        def _cov(name: str) -> None:
            b = coverage_counters[name]
            b["sample_size"] += 1
            if comp:
                b["competitions"].add(comp)
            if m.won is True:
                b["won"] += 1
            elif m.won is False:
                b["lost"] += 1
            if m.is_real_book_quote:
                b["real_quote_count"] += 1
                if m.profit_1u_real is not None:
                    b["real_profit_1u"] += float(m.profit_1u_real)
            elif m.is_derived_quote:
                b["derived_quote_count"] += 1
                if m.profit_1u_synthetic is not None:
                    b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)

        # Distinctions — outcome_base_rate non è "performance del Cecchino"
        _cov("outcome_base_rate")
        if m.quota_cecchino is not None:
            _cov("with_cecchino_quote")
        if m.rating is not None:
            _cov("with_rating")
        if m.signal_active:
            _cov("with_signal_active")
        if m.is_real_book_quote:
            _cov("with_real_bet365_quote")
        if m.is_derived_quote:
            _cov("with_derived_quote")

    eligible_analysis = {
        "note": (
            "Aggregazioni di performance solo su eligible_core. "
            "outcome_base_rate non è performance del Cecchino."
        ),
        "aggregations": {
            dim: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
            for dim, inner in buckets.items()
        },
        "coverage_distinctions": {
            k: _finalize_bucket(v) for k, v in coverage_counters.items()
        },
    }

    excluded_by_reason: dict[str, int] = defaultdict(int)
    excluded_by_status: dict[str, int] = defaultdict(int)
    for s in excluded_snaps:
        excluded_by_status[s.historical_eligibility_status] += 1
        reason = s.historical_eligibility_reason or "unknown"
        excluded_by_reason[str(reason)] += 1

    excluded_diagnostics = {
        "count": len(excluded_snaps),
        "by_status": dict(excluded_by_status),
        "by_reason": dict(excluded_by_reason),
        "note": (
            "Partite escluse hanno snapshot + risultato, settlement_status=excluded, "
            "zero mercati in metriche di performance."
        ),
        "sample_matches": [
            {
                "snapshot_id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "eligibility_status": s.historical_eligibility_status,
                "eligibility_reason": s.historical_eligibility_reason,
                "settlement_status": s.settlement_status,
                "settlement_summary": s.settlement_summary_json,
            }
            for s in excluded_snaps[:50]
        ],
    }

    errors_section = {
        "count": len(error_snaps),
        "items": [
            {
                "snapshot_id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "error": s.error_json,
            }
            for s in error_snaps[:50]
        ],
    }

    data_coverage = {
        "matches_total_in_run": len(snaps),
        "eligible_core": len(eligible_snaps),
        "excluded": len(excluded_snaps),
        "errors": len(error_snaps),
        "eligible_market_rows": len(eligible_markets),
        "competitions": competitions,
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "preflight": data_quality,
    }

    summary = {
        "eligible_analysis": eligible_analysis,
        "excluded_diagnostics": excluded_diagnostics,
        "errors": errors_section,
        "data_coverage": data_coverage,
    }

    patterns = _build_combined_patterns(eligible_markets, snap_by_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("summary.json", _json_bytes(summary))
        zf.writestr("data_quality.json", _json_bytes(data_quality))
        zf.writestr("eligibility.json", _json_bytes(dict(eligibility)))
        zf.writestr("module_coverage.json", _json_bytes(module_coverage))
        zf.writestr("patterns.json", _json_bytes(patterns))
        zf.writestr("AI_INSTRUCTIONS.md", AI_INSTRUCTIONS_MD.encode("utf-8"))
        zf.writestr("SCHEMA.md", SCHEMA_MD.encode("utf-8"))

        matches_io = io.StringIO()
        for s in snaps:
            row = {
                "snapshot_id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "season_label": s.season_label,
                "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                "chronological_order": s.chronological_order,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "eligibility_status": s.historical_eligibility_status,
                "eligibility_reason": s.historical_eligibility_reason,
                "blockers": s.blocking_reasons_json,
                "context_samples": {
                    k: (v or {}).get("sample")
                    for k, v in (s.input_snapshot_json or {}).items()
                    if isinstance(v, dict) and "sample" in v
                },
                "input_snapshot": s.input_snapshot_json,
                "cecchino": {
                    "picchetti": (s.cecchino_output_json or {}).get("picchetti"),
                    "final": (s.cecchino_output_json or {}).get("final"),
                    "status": (s.cecchino_output_json or {}).get("status"),
                },
                "signals": s.signals_json,
                "balance_v5": s.balance_v5_json,
                "goal_intensity_compatibility": s.goal_intensity_compatibility_json,
                "purchasability_compatibility": s.purchasability_compatibility_json,
                "quote_availability": (s.module_availability_json or {}),
                "pre_match_payload_sha256": s.pre_match_payload_sha256,
                "pre_match_locked_at": (
                    s.pre_match_locked_at.isoformat() if s.pre_match_locked_at else None
                ),
                "result_after_lock": s.result_json,
                "settlement_status": s.settlement_status,
                "settlement_summary": s.settlement_summary_json,
            }
            matches_io.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        zf.writestr("matches.jsonl", matches_io.getvalue().encode("utf-8"))

        markets_io = io.StringIO()
        for m in eligible_markets:
            s = snap_by_id.get(int(m.match_snapshot_id))
            sig = _signal_meta(m.signal_sources_json)
            row = {
                "run_id": int(m.run_id),
                "match_snapshot_id": int(m.match_snapshot_id),
                "lab_match_id": int(m.lab_match_id),
                "eligibility_status": (
                    s.historical_eligibility_status if s else ELIGIBLE_CORE
                ),
                "competition_name": s.competition_name if s else None,
                "market_key": m.market_key,
                "market_label": m.market_label,
                "period": m.period,
                "line": m.line,
                "quota_cecchino": float(m.quota_cecchino) if m.quota_cecchino is not None else None,
                "prob_cecchino": float(m.prob_cecchino) if m.prob_cecchino is not None else None,
                "quota_book": float(m.quota_book) if m.quota_book is not None else None,
                "prob_book_raw": float(m.prob_book_raw) if m.prob_book_raw is not None else None,
                "prob_book_fair": float(m.prob_book_fair) if m.prob_book_fair is not None else None,
                "quote_source_type": m.quote_source_type,
                "is_real_book_quote": m.is_real_book_quote,
                "is_derived_quote": m.is_derived_quote,
                "derivation_method": m.derivation_method,
                "edge_pct": float(m.edge_pct) if m.edge_pct is not None else None,
                "vantaggio_prob": float(m.vantaggio_prob) if m.vantaggio_prob is not None else None,
                "rating": m.rating,
                "signal_active": m.signal_active,
                "signal_family": sig.get("signal_family"),
                "active_signal_count": sig.get("active_signal_count"),
                "signal_sources_json": m.signal_sources_json,
                "evaluation_status": m.evaluation_status,
                "won": m.won,
                "profit_1u_real": float(m.profit_1u_real) if m.profit_1u_real is not None else None,
                "profit_1u_synthetic": (
                    float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
                ),
                "profit_category": m.profit_category,
                "result_reason": m.result_reason,
            }
            markets_io.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        zf.writestr("markets.jsonl", markets_io.getvalue().encode("utf-8"))

    return filename, buf.getvalue()


def _pattern_accumulator() -> dict[str, Any]:
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


def _finalize_pattern(
    pattern_id: str,
    conditions: dict[str, Any],
    acc: dict[str, Any],
) -> dict[str, Any]:
    comps = dict(acc["competitions"])
    n = int(acc["wins"]) + int(acc["losses"])
    sample = int(acc["sample_size"])
    real_n = int(acc["real_quote_count"])
    derived_n = int(acc["derived_quote_count"])
    real_profit = round(float(acc["real_profit"]), 4)
    synth_profit = round(float(acc["synthetic_profit"]), 4)
    competitions_count = len(comps)
    status = _pattern_status(
        sample_size=sample,
        competitions_count=competitions_count,
        competition_shares=comps,
    )
    stability = None
    if comps and sample:
        shares = {k: round(v / sample, 4) for k, v in sorted(comps.items())}
        top_share = max(shares.values()) if shares else 0
        stability = {
            "competition_shares": shares,
            "top_competition_share": top_share,
            "stable_cross_competition": competitions_count >= 2 and top_share < 0.7,
        }
    return {
        "pattern_id": pattern_id,
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
        "stability_by_competition": stability,
        "status": status,
        "limitations": [
            "Una sola stagione; pattern descrittivo non prescrittivo",
            "Non proporre modifiche automatiche a formule",
        ],
    }


def _bump_pattern(acc: dict[str, Any], m: CecchinoLabHistoricalMarketResult, comp: str | None) -> None:
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


def _build_combined_patterns(
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    snap_by_id: dict[int, CecchinoLabHistoricalMatchSnapshot],
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}

    def key_id(prefix: str, parts: list[str]) -> str:
        return prefix + "__" + "__".join(parts)

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        comp = s.competition_name if s else "unknown"
        rb = _rating_band(m.rating) or "no_rating"
        sig = _signal_meta(m.signal_sources_json)
        fam = str(sig.get("signal_family") or ("active" if m.signal_active else "no_signal"))
        signal_flag = "signal_on" if m.signal_active else "signal_off"
        bal = (s.balance_v5_json or {}) if s else {}
        structural = bal.get("structural_summary") if isinstance(bal, dict) else {}
        bal_class = "unknown"
        if isinstance(structural, dict):
            bal_class = str(structural.get("class") or structural.get("class_key") or "unknown")

        combos = [
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
                    "signal_family": fam,
                },
                [comp or "unknown", m.market_key, signal_flag, fam],
            ),
        ]
        for prefix, conditions, parts in combos:
            pid = key_id(prefix, [str(p) for p in parts])
            if pid not in groups:
                groups[pid] = {"conditions": conditions, "acc": _pattern_accumulator()}
            _bump_pattern(groups[pid]["acc"], m, comp)

    patterns = [
        _finalize_pattern(pid, g["conditions"], g["acc"])
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


def iter_report_chunks(data: bytes, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
