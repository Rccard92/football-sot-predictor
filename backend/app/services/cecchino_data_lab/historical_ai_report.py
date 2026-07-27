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

REPORT_SCHEMA_VERSION = "cecchino_lab_ai_report_v1"

AI_INSTRUCTIONS_MD = """# Istruzioni per ChatGPT — Report storico Cecchino Lab

1. Leggi prima `manifest.json` e `SCHEMA.md`.
2. Non confondere quote **reali Bet365** e quote **derivate**.
3. Non sommare ROI reale e ROI sintetico.
4. Non trattare quote derivate come offerte Bet365.
5. Non confondere `quota_cecchino` (modello) e `quota_book` (bookmaker).
6. Non utilizzare risultati futuri come input: il blocco pre-match è congelato prima del risultato.
7. Riporta sempre `sample_size`.
8. Separa risultati globali e per campionato.
9. Segnala instabilità cross-competition.
10. Non proporre modifiche produttive basate su una sola stagione.
11. Distingui correlazione, ipotesi e prova.
12. Produci una “prima linea” con:
    1. dati sufficienti;
    2. dati mancanti;
    3. moduli pienamente analizzabili;
    4. moduli parziali;
    5. segnali promettenti;
    6. segnali negativi;
    7. aspetti da verificare sulle stagioni successive.

Cecchino Today operativo resta su **Betfair** e non è modificato da questo report.
"""

SCHEMA_MD = """# Schema report AI Cecchino Lab

- `manifest.json`: metadati run, policy, versioni moduli
- `summary.json`: aggregazioni (non conclusioni forti su piccoli campioni)
- `data_quality.json`: qualità dati stagione
- `eligibility.json`: conteggi eleggibilità
- `module_coverage.json`: copertura moduli
- `matches.jsonl`: una riga JSON per partita (pre-match separato dal risultato)
- `markets.jsonl`: una riga per partita×mercato
- `patterns.json`: pattern descrittivi (`descriptive_only` / `small_sample` / …)
- `AI_INSTRUCTIONS.md`: istruzioni analisi
- `SCHEMA.md`: questo file
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
        "real_profit_1u": 0.0,
        "real_roi_pct": None,
        "synthetic_profit_1u": 0.0,
        "synthetic_roi_pct": None,
        "warnings": [],
    }


def _finalize_bucket(b: dict[str, Any]) -> dict[str, Any]:
    n = b["won"] + b["lost"]
    b["hit_rate"] = round(b["won"] / n, 4) if n else None
    if b["real_quote_count"]:
        b["real_roi_pct"] = round(100.0 * b["real_profit_1u"] / b["real_quote_count"], 2)
    if b["derived_quote_count"]:
        b["synthetic_roi_pct"] = round(
            100.0 * b["synthetic_profit_1u"] / b["derived_quote_count"], 2
        )
    if n < 30:
        b["warnings"].append("small_sample")
    b["real_profit_1u"] = round(b["real_profit_1u"], 4)
    b["synthetic_profit_1u"] = round(b["synthetic_profit_1u"], 4)
    return b


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

    season_slug = run.season_label.replace("/", "_")
    filename = f"cecchino_lab_{season_slug}_ai_report_run_{run_id}.zip"

    competitions = sorted({s.competition_name for s in snaps})
    datasets = sorted({int(s.dataset_id) for s in snaps})

    manifest = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": int(run.id),
        "season_label": run.season_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "Rccard92/football-sot-predictor",
        "source_git_commit": run.source_git_commit,
        "scan_version": run.scan_version or HISTORICAL_SCAN_VERSION,
        "parser_version": PARSER_VERSION,
        "modules": {
            "cecchino_engine": "imported_pure",
            "kpi": HISTORICAL_KPI_VERSION,
            "source_builder_version": "cecchino_kpi_v2_betfair",
            "balance_v5": "imported_pure",
            "signals_matrix": "imported_pure",
            "goal_intensity": "compatibility_only",
            "purchasability": "compatibility_only",
        },
        "competitions_included": competitions,
        "datasets_included": datasets,
        "quote_policy": HISTORICAL_QUOTE_POLICY_VERSION,
        "derivation_policy": HISTORICAL_DERIVATION_METHOD,
        "anti_leakage_policy": "strict_prior_kickoff_same_competition_only",
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
            "Prime giornate con campione insufficiente escluse",
            "Intensità Goal e Acquistabilità non eseguite con profilo operativo",
        ],
        "modules_not_executed": ["goal_intensity_production_bundle", "purchasability_v2_operational"],
        "operational_today_bookmaker": "Betfair",
        "historical_replay_bookmaker": "Bet365",
        "operational_today_modified": False,
    }

    eligibility: dict[str, int] = defaultdict(int)
    for s in snaps:
        eligibility[s.historical_eligibility_status] += 1

    data_quality = run.preflight_json or {}
    module_coverage = {
        "eligible_core": eligibility.get("eligible_core", 0),
        "with_kpi": sum(1 for s in snaps if s.historical_kpi_json),
        "with_signals": sum(1 for s in snaps if s.signals_json),
        "with_balance": sum(1 for s in snaps if s.balance_v5_json),
        "goal_intensity_compat": sum(
            1 for s in snaps if s.goal_intensity_compatibility_json
        ),
        "purchasability_compat": sum(
            1 for s in snaps if s.purchasability_compatibility_json
        ),
    }

    # Aggregazioni summary
    buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(_agg_bucket))

    def add_row(dim: str, key: str, m: CecchinoLabHistoricalMarketResult) -> None:
        b = buckets[dim][key]
        b["sample_size"] += 1
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

    snap_by_id = {int(s.id): s for s in snaps}
    for m in markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        add_row("market", m.market_key, m)
        add_row(
            "quote_type",
            "real" if m.is_real_book_quote else ("derived" if m.is_derived_quote else "unavailable"),
            m,
        )
        if s:
            add_row("competition", s.competition_name, m)
            add_row("eligibility", s.historical_eligibility_status, m)
            if s.historical_eligibility_reason:
                add_row("exclusion_reason", s.historical_eligibility_reason, m)
            if m.rating is not None:
                band = f"{(int(m.rating) // 10) * 10}-{(int(m.rating) // 10) * 10 + 9}"
                add_row("rating_band", band, m)
            if m.edge_pct is not None:
                e = float(m.edge_pct)
                edge_band = (
                    "neg"
                    if e < 0
                    else ("0-5" if e < 5 else ("5-10" if e < 10 else "10+"))
                )
                add_row("edge_band", edge_band, m)
            if s.kickoff_at:
                add_row("month", f"{s.kickoff_at.year}-{s.kickoff_at.month:02d}", m)
            qs = (s.quote_sources_json or {}).get("family_1x2") or {}
            snap_type = qs.get("family_snapshot_type") or "none"
            add_row("closing_or_pre", str(snap_type), m)
            bal = s.balance_v5_json or {}
            if isinstance(bal, dict) and bal.get("structural_summary"):
                cls = (bal.get("structural_summary") or {}).get("class") or "unknown"
                add_row("balance_class", str(cls), m)

    summary = {
        dim: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
        for dim, inner in buckets.items()
    }

    patterns = _build_patterns(buckets)

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

        # Stream JSONL without holding huge strings where possible
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
                "settlement_summary": s.settlement_summary_json,
            }
            matches_io.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        zf.writestr("matches.jsonl", matches_io.getvalue().encode("utf-8"))

        markets_io = io.StringIO()
        for m in markets:
            row = {
                "run_id": int(m.run_id),
                "match_snapshot_id": int(m.match_snapshot_id),
                "lab_match_id": int(m.lab_match_id),
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


def _build_patterns(
    buckets: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    patterns = []
    for market, b in (buckets.get("market") or {}).items():
        fb = _finalize_bucket(dict(b))
        n = fb["won"] + fb["lost"]
        if n == 0:
            status = "insufficient_data"
        elif n < 30:
            status = "small_sample"
        else:
            status = "descriptive_only"
        patterns.append(
            {
                "pattern_id": f"market_{market}",
                "conditions": {"market_key": market},
                "sample_size": n,
                "wins": fb["won"],
                "losses": fb["lost"],
                "hit_rate": fb["hit_rate"],
                "real_roi": fb["real_roi_pct"],
                "synthetic_roi": fb["synthetic_roi_pct"],
                "competitions_count": None,
                "stability_by_competition": None,
                "confidence_label": "low" if n < 50 else "medium",
                "limitations": ["Una sola stagione; pattern non prescrittivo"],
                "status": status,
            }
        )
    return {"patterns": patterns, "note": "Descriptive only — no operational threshold changes"}


def iter_report_chunks(data: bytes, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
