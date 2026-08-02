"""Export ZIP report ottimizzato per analisi ChatGPT (report frammentati + streaming)."""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, BinaryIO, Iterator

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    get_cecchino_weight_model,
    model_meta_for_key,
    model_weights_json,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_DERIVATION_METHOD,
    HISTORICAL_KPI_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION,
    HISTORICAL_SCAN_VERSION,
    PARSER_VERSION,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_analytics_agg import (
    ANALYTICS_AGGREGATION_VERSION,
    MIN_PATTERN_SAMPLE_FOR_REAL_ROI,
    PATTERNS_TOP_CAP,
    add_market_row as _add_market_row,
    agg_bucket as _agg_bucket,
    as_dict as _as_dict,
    as_list as _as_list,
    balance_pillars as _balance_pillars,
    build_combined_patterns as _build_combined_patterns,
    build_patterns_top as _build_patterns_top,
    build_rating_by_market as _build_rating_by_market,
    bump_bucket_from_market as _bump_bucket_from_market,
    bump_pattern as _bump_pattern,
    edge_band as _edge_band,
    finalize_bucket as _finalize_bucket,
    finalize_pattern as _finalize_pattern,
    pattern_accumulator as _pattern_accumulator,
    pattern_status as _pattern_status,
    quote_count_reconciliation as _quote_count_reconciliation,
    quote_quality_of_market as _quote_quality_of_market,
    rating_band as _rating_band,
    signal_meta as _signal_meta,
    structural_class as _structural_class,
)
from app.services.cecchino_data_lab.historical_signal_export import (
    SIGNAL_EXPORT_SCHEMA_VERSION,
    CURRENT_MODEL_KEY as SIGNAL_CURRENT_MODEL_KEY,
    build_cell_rows_from_opportunity,
    build_signal_models_summary,
    collect_all_opportunities,
    public_opportunity_row,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_official import (
    build_official_purchasability_section,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_export import (
    PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
    write_purchasability_v3_replay_report_zip,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver import (
    LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
    resolve_official_purchasability_v3_replay,
    try_resolve_official_purchasability_v3_replay,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE

logger = logging.getLogger(__name__)

REPORT_SCHEMA_VERSION = "cecchino_lab_ai_report_v4"
REPORT_MODES = frozenset({"ai_summary", "competition", "module", "full_archive"})
REPORT_MODULES = frozenset({"markets", "signals", "goal_intensity", "purchasability", "balance"})
SPOOL_MAX_SIZE = 8 * 1024 * 1024
REPORT_CHUNK_SIZE = 64 * 1024
AI_SUMMARY_WARN_BYTES = 5 * 1024 * 1024

AI_INSTRUCTIONS_MD = """# Istruzioni per ChatGPT — Report storico Cecchino Lab (v4)

1. Leggi prima `report_index.json`, `manifest.json` e `SCHEMA.md`.
2. Distingui `scan_source_git_commit` (snapshot congelati) da `report_generator_git_commit` (codice che genera il report). Alias legacy `source_git_commit*` = scan.
3. Usa **solo** `eligible_analysis` (`eligible_core`) per hit rate, profitto, ROI, fasce rating, pattern e analisi segnali.
4. `excluded_diagnostics` e `diagnostic_patterns` / `coverage_diagnostics` sono diagnostica: non mescolarle con la performance.
5. Non confondere quote **reali Bet365**, quote **derivate** e quote **non disponibili** (`unavailable`).
6. Deve sempre valere: `real_quote_count + derived_quote_count + unavailable_quote_count = market_rows` (`quote_count_reconciliation_ok`).
7. Se `real_quote_count=0` allora `real_profit_1u`/`real_roi_pct`/`average_real_odds` sono **null** (non zero). Stesso per derived/synthetic.
8. Distingui zero economico reale (quote presenti, profitto = 0) da dato assente (null).
9. Rating e Acquistabilità: usa `rating_by_market` e `purchasability_by_market`. Le strutture `*_global_distribution_diagnostic` non sono performance.
10. Confronta fasce Rating/Acquistabilità **entro lo stesso mercato**. Non confrontare HOME 90 con OVER_2_5 90 senza indicare il mercato.
11. Fascia Rating `100` è esclusiva (mai `100-109`).
12. Pattern sempre market-specific. Stabilità: insufficient_evidence|concentrated|inconsistent|directionally_consistent|stable_candidate.
13. Condizioni `no_rating`/`no_purch`/`signal_off` → solo diagnostica.
14. **Non** interpretare `technical_sum_across_all_independent_market_rows` come strategia.
15. Report e dashboard condividono `analytics_aggregation_version`.
16. `ai_summary` resta compatto: niente markets.jsonl completo / dettaglio partita-per-partita.
17. Segnali A–F: usa `signal_opportunities.jsonl` per performance e ROI (una riga = run+snapshot+modello+mercato).
18. `signal_models.jsonl` è **legacy cell-level** (`row_granularity=signal_cell`): celle sovrapposte sulla stessa opportunità; **non** sommare profitto/stake delle righe cella.
19. `with_signal_active` nei riepiloghi modello è alias **deprecato** di `model_active_opportunity_count` (conteggio opportunità attive del modello), non overlap con F.
20. Per sovrapposizione con F usa `overlap_with_current_model_F_*` e `model_overlap_matrix`.
21. Più celle attive sulla stessa opportunità **non** sono più scommesse.
22. Confronta i modelli sullo **stesso mercato**; non mescolare HOME/DRAW/AWAY/Over/Under in un unico ROI.
23. F è il modello **corrente**, non automaticamente il migliore.
24. Non modificare pesi o formule basandosi su una sola stagione.
25. Acquistabilità ufficiale = **solo V3** dal replay storico (`official_purchasability_source=replay_v3`). Non usare V1.1/V2 né `purchasability_compatibility_json`.
26. Gate failed ≠ score 0. `formula_recomputed=false`. Quote reali e sintetiche restano separate.
27. Se `purchasability.status=unavailable` → replay V3 assente; non inventare score legacy.
28. `module=purchasability` scarica l'export V3 ufficiale (`cecchino-run-{id}-purchasability-v3.zip`).

Cecchino Today operativo resta su **Betfair** e non è modificato da questo report.
"""

SCHEMA_MD = """# Schema report AI Cecchino Lab (v4)

- `manifest.json`: `scan_source_git_commit*` vs `report_generator_git_commit*`; alias legacy `source_git_commit*` = scan; `analytics_aggregation_version`; `signal_export_schema_version`; `purchasability_v3_*_schema_version`; `legacy_purchasability_excluded=true`; `performance_granularity=signal_opportunity`; `legacy_cell_file=signal_models.jsonl`
- `summary.json` / `eligible_analysis`: `rating_by_market` primaria; Acquistabilità in `purchasability` (solo V3 replay); `quote_reconciliation`
- Segnali: `signal_opportunities.jsonl` (canonico, 1 riga/opportunità); `signal_models.jsonl` (legacy, 1 riga/cella, `do_not_sum_as_independent_opportunities=true`)
- Acquistabilità ufficiale: sezione `purchasability` V3; `module=purchasability` = ZIP export V3; archivio esclude campi compatibility legacy
- Gate V3: gate failed ≠ score 0; nessun confronto V1.1/V2
- `signal_export_reconciliation`, `market_join_diagnostics`, `model_overlap_matrix`, `consensus_distribution`, `current_model_F_diagnostics`
- Profit/ROI/medie odds = `null` se quote_count della tipologia = 0
- Fascia Rating `100` esclusiva
- `markets.jsonl` (competition/module/full_archive): riga compatta con identity + kickoff + scores; non in `ai_summary`
- Pattern market-specific + `diagnostic_patterns`
"""


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _canonical_signal_model_fields(model_key: str) -> dict[str, Any]:
    key = str(model_key).upper()
    meta = model_meta_for_key(key)
    model = get_cecchino_weight_model(key)
    return {
        "model_key": key,
        "model_label": str(meta.get("model_label") or model.get("label") or key),
        "model_short_label": str(model.get("short_label") or f"Modello {key}"),
        "weights_version": str(meta.get("weights_version") or ""),
        "weights": model_weights_json(key),
    }


def _match_compact_row(s: CecchinoLabHistoricalMatchSnapshot) -> dict[str, Any]:
    input_snap = _as_dict(s.input_snapshot_json)
    cecchino_out = _as_dict(s.cecchino_output_json)
    final = _as_dict(cecchino_out.get("final"))
    bal = _as_dict(s.balance_v5_json)
    bal_class, _ = _structural_class(bal.get("structural_summary") if bal else None)
    gi = _as_dict(s.goal_intensity_compatibility_json)
    pillars = _as_dict(gi.get("pillars"))
    sigs = _as_dict(s.signals_json)
    models = _as_dict(sigs.get("models"))
    af_counts = {
        k: len(_as_list(_as_dict(models.get(k)).get("active_signals")))
        for k in CECCHINO_WEIGHT_MODEL_KEYS
        if k in models
    }
    samples = {
        k: v.get("sample")
        for k, v in input_snap.items()
        if isinstance(v, dict) and "sample" in v
    }
    return {
        "snapshot_id": int(s.id),
        "lab_match_id": int(s.lab_match_id),
        "competition_name": s.competition_name,
        "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
        "home_team": s.home_team,
        "away_team": s.away_team,
        "eligibility_status": s.historical_eligibility_status,
        "context_samples": samples,
        "quota_cecchino_final": {
            "quota_1": final.get("quota_1"),
            "quota_x": final.get("quota_x"),
            "quota_2": final.get("quota_2"),
            "status": final.get("status"),
        },
        "balance_class": bal_class,
        "goal_intensity_pillars": {
            k: _as_dict(v).get("class") or _as_dict(v).get("class_key")
            for k, v in pillars.items()
        },
        "goal_intensity_execution": gi.get("execution_status"),
        "signal_active_counts_A_F": af_counts,
        "result_after_lock": s.result_json,
        "pre_match_payload_sha256": s.pre_match_payload_sha256,
    }


def _scope_tag(run_scope: str, is_partial: bool) -> str:
    if run_scope == "balanced_pilot":
        return "balanced_pilot"
    if is_partial:
        return "pilot"
    return "full"


def _write_jsonl_to_zip(zf: zipfile.ZipFile, arcname: str, lines: Iterator[str]) -> int:
    """Scrive JSONL riga per riga nello ZIP; restituisce conteggio righe."""
    count = 0
    with zf.open(arcname, "w") as dest:
        for line in lines:
            if not line.endswith("\n"):
                line = line + "\n"
            dest.write(line.encode("utf-8"))
            count += 1
    return count


def _note_shape_warning(
    warnings: list[str],
    code: str | None,
    *,
    seen: set[str] | None = None,
) -> None:
    if not code:
        return
    if seen is not None:
        if code in seen:
            return
        seen.add(code)
    warnings.append(code)


def _compat_flag(compat_json: Any, key: str) -> bool:
    return bool(_as_dict(compat_json).get(key))


def build_ai_report_zip_bytes(
    db: Session,
    run_id: int,
    *,
    mode: str = "full_archive",
    competition: str | None = None,
    module: str | None = None,
) -> tuple[str, bytes]:
    """Compat: costruisce ZIP in bytes (ok per test / ai_summary piccoli)."""
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
    try:
        filename, size = write_historical_report_zip(
            db,
            run_id,
            spool,
            mode=mode,
            competition=competition,
            module=module,
        )
        spool.seek(0)
        data = spool.read()
        logger.info(
            "historical report zip built run_id=%s mode=%s bytes=%s",
            run_id,
            mode,
            size,
        )
        return filename, data
    finally:
        spool.close()


def build_historical_report_response(
    db: Session,
    run_id: int,
    *,
    mode: str = "ai_summary",
    competition: str | None = None,
    module: str | None = None,
) -> StreamingResponse:
    mode_norm = (mode or "ai_summary").strip().lower()
    if mode_norm not in REPORT_MODES:
        raise CecchinoLabImportError(
            "invalid_report_mode",
            f"mode non supportata: {mode}",
            status_code=400,
        )
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
    try:
        filename, size = write_historical_report_zip(
            db,
            run_id,
            spool,
            mode=mode_norm,
            competition=competition,
            module=module,
        )
    except Exception:
        spool.close()
        raise
    spool.seek(0)
    logger.info(
        "historical report streaming run_id=%s mode=%s bytes=%s",
        run_id,
        mode_norm,
        size,
    )

    def _iter() -> Iterator[bytes]:
        try:
            while True:
                chunk = spool.read(REPORT_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            spool.close()

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Report-Mode": mode_norm,
        "X-Report-Bytes": str(size),
    }
    if mode_norm == "full_archive":
        headers["X-Report-Warning"] = (
            "Archivio tecnico completo — non necessario per la prima analisi ChatGPT"
        )
    return StreamingResponse(_iter(), media_type="application/zip", headers=headers)


def write_historical_report_zip(
    db: Session,
    run_id: int,
    dest: BinaryIO,
    *,
    mode: str = "full_archive",
    competition: str | None = None,
    module: str | None = None,
) -> tuple[str, int]:
    mode_norm = (mode or "full_archive").strip().lower()
    if mode_norm not in REPORT_MODES:
        raise CecchinoLabImportError(
            "invalid_report_mode",
            f"mode non supportata: {mode}",
            status_code=400,
        )
    if mode_norm == "competition" and not (competition or "").strip():
        raise CecchinoLabImportError(
            "competition_required",
            "Parametro competition richiesto per mode=competition",
            status_code=400,
        )
    module_norm = (module or "").strip().lower() or None
    if mode_norm == "module":
        if module_norm not in REPORT_MODULES:
            raise CecchinoLabImportError(
                "invalid_report_module",
                f"module non supportato: {module}",
                status_code=400,
            )
        if module_norm == "purchasability":
            run = db.get(CecchinoLabHistoricalScanRun, run_id)
            if not run:
                raise CecchinoLabImportError(
                    "run_not_found", "Run non trovato", status_code=404
                )
            replay = resolve_official_purchasability_v3_replay(db, int(run_id))
            return write_purchasability_v3_replay_report_zip(
                db,
                int(replay.id),
                dest,
                mode="analysis",
                filename_override=f"cecchino-run-{int(run_id)}-purchasability-v3.zip",
            )

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

    policy = _as_dict(run.module_policy_json)
    is_partial = bool(policy.get("is_partial_run"))
    run_scope = policy.get("run_scope") or ("pilot" if is_partial else "full")

    season_slug = run.season_label.replace("/", "_")
    scope_tag = _scope_tag(str(run_scope), is_partial)
    filename = f"cecchino_lab_{season_slug}_{scope_tag}_{mode_norm}_run_{run_id}.zip"

    all_competitions = sorted({s.competition_name for s in snaps})
    competition_filter = (competition or "").strip() or None
    if competition_filter and competition_filter not in all_competitions:
        raise CecchinoLabImportError(
            "competition_not_found",
            f"Campionato non presente nel run: {competition_filter}",
            status_code=404,
        )

    if mode_norm == "competition" and competition_filter:
        snaps = [s for s in snaps if s.competition_name == competition_filter]

    competitions = sorted({s.competition_name for s in snaps})
    datasets = sorted({int(s.dataset_id) for s in snaps})

    # Universo performance: solo eligible_core
    analysis_snaps = [s for s in snaps if s.historical_eligibility_status == ELIGIBLE_CORE]
    eligible_snaps = analysis_snaps
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

    gi_computed = sum(
        1
        for s in eligible_snaps
        if _as_dict(s.goal_intensity_compatibility_json).get("execution_status") == "computed"
    )
    # Acquistabilità ufficiale = replay V3 (nessuna lettura compatibility JSON)
    purch_computed = 0

    generator_rev = resolve_code_revision()
    manifest = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_mode": mode_norm,
        "report_module": module_norm,
        "report_competition": competition_filter,
        "run_id": int(run.id),
        "season_label": run.season_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "Rccard92/football-sot-predictor",
        # Commit scansione (congelato sul run) — non sovrascrivere in DB
        "scan_source_git_commit": run.source_git_commit,
        "scan_source_git_commit_source": getattr(run, "source_git_commit_source", None),
        "scan_source_revision_status": getattr(run, "source_revision_status", None),
        # Alias legacy = scan commit
        "source_git_commit": run.source_git_commit,
        "source_git_commit_source": getattr(run, "source_git_commit_source", None),
        "source_revision_status": getattr(run, "source_revision_status", None),
        # Commit generatore report (runtime download)
        "report_generator_git_commit": generator_rev.get("git_commit"),
        "report_generator_git_commit_source": generator_rev.get("git_commit_source"),
        "report_generator_revision_status": generator_rev.get("revision_status"),
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
        "signal_export_schema_version": SIGNAL_EXPORT_SCHEMA_VERSION,
        "purchasability_v3_analytics_schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
        "purchasability_v3_export_schema_version": PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
        "official_purchasability_version": "V3",
        "official_purchasability_source": "replay_v3",
        "legacy_purchasability_excluded": True,
        "legacy_purchasability_read": False,
        "legacy_fallback_allowed": LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
        "current_model_key": SIGNAL_CURRENT_MODEL_KEY,
        "performance_granularity": "signal_opportunity",
        "legacy_cell_file": "signal_models.jsonl",
        "scan_version": run.scan_version or HISTORICAL_SCAN_VERSION,
        "parser_version": PARSER_VERSION,
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "max_matches": policy.get("max_matches"),
        "pilot_strategy": policy.get("pilot_strategy"),
        "eligible_per_competition": policy.get("eligible_per_competition"),
        "not_full_season_report": bool(policy.get("not_full_season_report") or is_partial),
        "default_weight_model_key": CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
        "full_archive_warning": (
            "Archivio tecnico completo — non necessario per la prima analisi ChatGPT"
            if mode_norm == "full_archive"
            else None
        ),
        "modules": {
            "cecchino_engine": "imported_pure",
            "kpi": HISTORICAL_KPI_VERSION,
            "source_builder_version": "cecchino_kpi_v2_betfair",
            "balance_v5": "imported_pure",
            "signals_matrix": "imported_pure_models_A_F",
            "goal_intensity": "historical_partial_v1",
            "purchasability": "replay_v3_official",
        },
        "competitions_included": competitions,
        "datasets_included": datasets,
        "quote_policy": HISTORICAL_QUOTE_POLICY_VERSION,
        "derivation_policy": HISTORICAL_DERIVATION_METHOD,
        "anti_leakage_policy": "strict_prior_kickoff_same_competition_only",
        "performance_universe": "eligible_core",
        "profit_policy": {
            "real": "profit_1u_real from real Bet365 quotes only",
            "synthetic": "profit_1u_synthetic from derived quotes only",
            "do_not_sum_real_and_synthetic": True,
            "null_when_no_quotes": True,
            "technical_sum_across_all_independent_market_rows": {
                "not_a_betting_strategy": True,
                "note": (
                    "Somma tecnica di righe mercato indipendenti (HOME+DRAW+AWAY+OU…); "
                    "non è profitto del Cecchino né una strategia giocabile"
                ),
            },
        },
        "actual_vs_derived_definitions": {
            "actual_bet365": "complete closing or complete pre family",
            "synthetic_derived": "DC fair from normalized 1X2",
            "no_book_quote": "market without book quote",
        },
        "limitations": [
            "Prima stagione nella nuova pipeline: nessun prior da stagioni precedenti",
            "Prime giornate con campione insufficiente escluse dalle metriche di performance",
            "Intensità Goal: parity_status=partial (ECDF progressivo Lab; no bundle Today; no xG)",
            "Acquistabilità: storica Bet365 progressiva; non equivalente al profilo Betfair operativo",
            "source_git_commit* è alias legacy di scan_source_git_commit*",
            "report_generator_git_commit ≠ ricalcolo del run; solo codice che legge gli snapshot",
            *(
                ["Run parziale: non confrontare come report stagione completa"]
                if is_partial
                else []
            ),
            *(
                list(policy.get("revision_warnings") or [])
                if policy.get("revision_warnings")
                else []
            ),
        ],
        "modules_parity": {
            "goal_intensity": "partial",
            "purchasability": "replay_v3_official",
            "signal_models": "F_equals_current",
        },
        "operational_today_bookmaker": "Betfair",
        "historical_replay_bookmaker": "Bet365",
        "operational_today_modified": False,
        "do_not_propose_formula_changes": True,
    }

    # --- reuse aggregation body via internal call ---
    return _finalize_report_zip(
        db=db,
        dest=dest,
        filename=filename,
        mode_norm=mode_norm,
        module_norm=module_norm,
        run=run,
        snaps=snaps,
        markets=markets,
        markets_by_snap=markets_by_snap,
        policy=policy,
        is_partial=is_partial,
        run_scope=str(run_scope),
        competitions=competitions,
        all_competitions=all_competitions,
        eligible_snaps=eligible_snaps,
        excluded_snaps=excluded_snaps,
        error_snaps=error_snaps,
        eligible_markets=eligible_markets,
        gi_computed=gi_computed,
        purch_computed=purch_computed,
        manifest=manifest,
    )


def _finalize_report_zip(
    *,
    db: Session,
    dest: BinaryIO,
    filename: str,
    mode_norm: str,
    module_norm: str | None,
    run: CecchinoLabHistoricalScanRun,
    snaps: list[CecchinoLabHistoricalMatchSnapshot],
    markets: list[CecchinoLabHistoricalMarketResult],
    markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]],
    policy: dict[str, Any],
    is_partial: bool,
    run_scope: str,
    competitions: list[str],
    all_competitions: list[str],
    eligible_snaps: list[CecchinoLabHistoricalMatchSnapshot],
    excluded_snaps: list[CecchinoLabHistoricalMatchSnapshot],
    error_snaps: list[CecchinoLabHistoricalMatchSnapshot],
    eligible_markets: list[CecchinoLabHistoricalMarketResult],
    gi_computed: int,
    purch_computed: int,
    manifest: dict[str, Any],
) -> tuple[str, int]:
    # Opportunità segnali A–F (deduplicate) — read-only join a MarketResult
    signal_opportunities = collect_all_opportunities(
        run_id=int(run.id),
        snapshots=eligible_snaps,
        markets=eligible_markets,
    )
    signal_models_summary = build_signal_models_summary(signal_opportunities)

    # Acquistabilità ufficiale V3 (nessun fallback legacy)
    purch_official = build_official_purchasability_section(db, int(run.id))
    purch_replay = try_resolve_official_purchasability_v3_replay(db, int(run.id))

    eligibility: dict[str, int] = defaultdict(int)
    for s in snaps:
        eligibility[s.historical_eligibility_status] += 1

    data_quality = _as_dict(run.preflight_json)
    shape_warnings: list[str] = []
    shape_warning_seen: set[str] = set()
    module_coverage = {
        "eligible_core": eligibility.get(ELIGIBLE_CORE, 0),
        "analysis_sample": len(eligible_snaps),
        "excluded": len(excluded_snaps),
        "errors": len(error_snaps),
        "with_kpi": sum(1 for s in eligible_snaps if s.historical_kpi_json),
        "with_signals": sum(1 for s in eligible_snaps if s.signals_json),
        "with_balance": sum(1 for s in eligible_snaps if s.balance_v5_json),
        "goal_intensity": {
            "raw_features_available": sum(
                1
                for s in eligible_snaps
                if _compat_flag(s.goal_intensity_compatibility_json, "raw_features_available")
            ),
            "pillars_computed": gi_computed,
            "parity_status": "partial",
            "v5_live_bundle_not_used": True,
            "note": "Pilastri storici con ECDF progressivo Lab; non dichiarare V5 completo",
        },
        "purchasability": {
            "official_version": "V3",
            "source_type": "historical_replay",
            "status": purch_official.get("status"),
            "replay_id": purch_official.get("replay_id"),
            "results_persisted": purch_official.get("results_persisted"),
            "scored": purch_official.get("scored"),
            "gate_failed": purch_official.get("gate_failed"),
            "unavailable": purch_official.get("unavailable"),
            "parity_status": "replay_v3_official",
            "legacy_purchasability_read": False,
            "note": "Acquistabilità ufficiale = replay V3; nessun fallback V1.1/V2",
        },
        "signal_models": {
            "models": list(CECCHINO_WEIGHT_MODEL_KEYS),
            "default_model_key": CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
            "f_equals_current": True,
        },
    }

    snap_by_id = {int(s.id): s for s in snaps}
    buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(_agg_bucket))

    # Coverage / base-rate style counters (eligible only) — not labeled as Cecchino performance
    coverage_counters = {
        "outcome_base_rate": _agg_bucket(),
        "with_cecchino_probability": _agg_bucket(),
        "with_cecchino_fair_quote": _agg_bucket(),
        "with_cecchino_quote": _agg_bucket(),  # alias fair quote (compat)
        "with_rating": _agg_bucket(),
        "with_signal_active": _agg_bucket(),
        "with_real_bet365_quote": _agg_bucket(),
        "with_derived_quote": _agg_bucket(),
        "with_unavailable_quote": _agg_bucket(),
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
            quote_sources = _as_dict(s.quote_sources_json)
            qs = _as_dict(quote_sources.get("family_1x2"))
            snap_type = qs.get("family_snapshot_type") or "none"
            _add_market_row(buckets, "closing_or_pre", str(snap_type), m, comp)
            bal = _as_dict(s.balance_v5_json)
            cls, warn = _structural_class(bal.get("structural_summary") if bal else None)
            _note_shape_warning(shape_warnings, warn, seen=shape_warning_seen)
            _add_market_row(buckets, "balance_class", str(cls), m, comp)
            pillars = _balance_pillars(bal)
            for pname, pblock in pillars.items():
                ck = _as_dict(pblock).get("class_key")
                if ck:
                    _add_market_row(buckets, f"balance_pillar_{pname}", str(ck), m, comp)
            # historical sample size band from input snapshot
            input_snap = _as_dict(s.input_snapshot_json)
            prior = input_snap.get("prior_count")
            if prior is not None:
                try:
                    p = int(prior)
                except (TypeError, ValueError):
                    p = None
                if p is not None:
                    band = (
                        "0-9"
                        if p < 10
                        else ("10-29" if p < 30 else ("30-99" if p < 100 else "100+"))
                    )
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
            for src in _as_list(sig.get("sources")):
                if isinstance(src, dict):
                    model = src.get("column_key") or src.get("source_column") or "unknown"
                    _add_market_row(buckets, "signal_model", str(model), m, comp)
                    cell = f"{src.get('signal_group')}:{src.get('source_column')}"
                    _add_market_row(buckets, "signal_cell", cell, m, comp)

        # Distinctions — full bump so unavailable/odds/cecchino counts are correct
        _bump_bucket_from_market(coverage_counters["outcome_base_rate"], m, comp)
        if m.prob_cecchino is not None:
            _bump_bucket_from_market(coverage_counters["with_cecchino_probability"], m, comp)
        if m.quota_cecchino is not None:
            _bump_bucket_from_market(coverage_counters["with_cecchino_fair_quote"], m, comp)
            _bump_bucket_from_market(coverage_counters["with_cecchino_quote"], m, comp)
        if m.rating is not None:
            _bump_bucket_from_market(coverage_counters["with_rating"], m, comp)
        if m.signal_active:
            _bump_bucket_from_market(coverage_counters["with_signal_active"], m, comp)
        if m.is_real_book_quote:
            _bump_bucket_from_market(coverage_counters["with_real_bet365_quote"], m, comp)
        elif m.is_derived_quote:
            _bump_bucket_from_market(coverage_counters["with_derived_quote"], m, comp)
        else:
            _bump_bucket_from_market(coverage_counters["with_unavailable_quote"], m, comp)

    # Intensità / modelli A–F (Acquistabilità ufficiale è separata via replay V3)
    gi_class_buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(_agg_bucket)
    )

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        if not s:
            continue
        comp = s.competition_name
        gi = _as_dict(s.goal_intensity_compatibility_json)
        for pillar_name, pblock in _as_dict(gi.get("pillars")).items():
            ck = _as_dict(pblock).get("class") or _as_dict(pblock).get("class_key")
            if not ck:
                continue
            _bump_bucket_from_market(gi_class_buckets[str(pillar_name)][str(ck)], m, comp)

    technical_sum = {
        "technical_sum_across_all_independent_market_rows": {
            "not_a_betting_strategy": True,
            "real_profit_1u": round(
                sum(float(m.profit_1u_real or 0) for m in eligible_markets if m.profit_1u_real is not None),
                4,
            ),
            "synthetic_profit_1u": round(
                sum(
                    float(m.profit_1u_synthetic or 0)
                    for m in eligible_markets
                    if m.profit_1u_synthetic is not None
                ),
                4,
            ),
            "market_rows": len(eligible_markets),
            "note": "Somma tecnica di tutte le righe mercato indipendenti; non è una strategia",
        }
    }

    # Riconciliazione quote sull'universo eligible (outcome_base_rate = tutte le righe)
    universe_recon = _quote_count_reconciliation(
        {
            "sample_size": len(eligible_markets),
            "real_quote_count": sum(1 for m in eligible_markets if m.is_real_book_quote),
            "derived_quote_count": sum(1 for m in eligible_markets if m.is_derived_quote),
            "unavailable_quote_count": sum(
                1
                for m in eligible_markets
                if not m.is_real_book_quote and not m.is_derived_quote
            ),
        }
    )

    rating_by_market = _build_rating_by_market(eligible_markets, snap_by_id)

    eligible_analysis = {
        "note": (
            "Aggregazioni di performance solo su eligible_core / analysis. "
            "outcome_base_rate non è performance del Cecchino. "
            "Rating/Acquistabilità primarie sono per mercato; "
            "le aggregazioni globali sono diagnostiche. "
            "Pattern market-specific; profit/medie quote null se quote_count=0; "
            "technical_sum non è una strategia. "
            f"analytics_aggregation_version={ANALYTICS_AGGREGATION_VERSION}."
        ),
        "analytics_aggregation_version": ANALYTICS_AGGREGATION_VERSION,
        "quote_reconciliation": universe_recon,
        "rating_by_market": rating_by_market,
        "aggregations": {
            dim: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
            for dim, inner in buckets.items()
        },
        "rating_global_distribution_diagnostic": {
            k: _finalize_bucket(v)
            for k, v in sorted((buckets.get("rating_band") or {}).items())
        },
        "goal_intensity_pillar_classes": {
            pillar: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
            for pillar, inner in gi_class_buckets.items()
        },
        "signal_models_A_F": {
            m["model_key"]: {
                **{k: v for k, v in m.items() if k != "weights"},
                "weights": m.get("weights"),
                "with_signal_active": m.get("model_active_opportunity_count"),
            }
            for m in signal_models_summary.get("models") or []
        },
        "signal_export_reconciliation": signal_models_summary.get(
            "signal_export_reconciliation"
        ),
        "market_join_diagnostics": signal_models_summary.get("market_join_diagnostics"),
        "model_overlap_matrix": signal_models_summary.get("model_overlap_matrix"),
        "consensus_distribution": signal_models_summary.get("consensus_distribution"),
        "current_model_F_diagnostics": signal_models_summary.get(
            "current_model_F_diagnostics"
        ),
        "signal_cell_attribution": signal_models_summary.get("cell_attribution"),
        "signal_export_schema_version": SIGNAL_EXPORT_SCHEMA_VERSION,
        "coverage_distinctions": {
            k: _finalize_bucket(v) for k, v in coverage_counters.items()
        },
        **technical_sum,
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
        "eligible_core": sum(
            1 for s in snaps if s.historical_eligibility_status == ELIGIBLE_CORE
        ),
        "analysis_sample": len(eligible_snaps),
        "excluded": len(excluded_snaps),
        "errors": len(error_snaps),
        "eligible_market_rows": len(eligible_markets),
        "competitions": competitions,
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "preflight": data_quality,
        "warnings": shape_warnings,
    }

    summary = {
        "eligible_analysis": eligible_analysis,
        "excluded_diagnostics": excluded_diagnostics,
        "errors": errors_section,
        "data_coverage": data_coverage,
        "purchasability": purch_official,
    }

    patterns = _build_combined_patterns(
        eligible_markets, snap_by_id, shape_warnings=shape_warnings, shape_warning_seen=shape_warning_seen
    )
    patterns_top = _build_patterns_top(patterns)

    line_counts: dict[str, int] = {}
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        def _put_json(name: str, obj: Any) -> None:
            zf.writestr(name, _json_bytes(obj))

        zf.writestr("AI_INSTRUCTIONS.md", AI_INSTRUCTIONS_MD.encode("utf-8"))
        zf.writestr("SCHEMA.md", SCHEMA_MD.encode("utf-8"))

        if mode_norm in ("ai_summary", "competition", "full_archive"):
            _put_json("summary.json", summary)
            _put_json("data_quality.json", data_quality)
            _put_json("eligibility.json", dict(eligibility))
            _put_json("module_coverage.json", module_coverage)

        if mode_norm == "ai_summary":
            _put_json("patterns_top.json", patterns_top)
        if mode_norm in ("competition", "full_archive"):
            _put_json("patterns.json", patterns)
        if mode_norm == "competition":
            _put_json("patterns_top.json", patterns_top)

        if mode_norm == "module":
            _put_json("summary.json", summary)
            _put_json("module_coverage.json", module_coverage)

        # JSONL writers
        def _iter_matches_full() -> Iterator[str]:
            for s in snaps:
                input_snap = _as_dict(s.input_snapshot_json)
                cecchino_out = _as_dict(s.cecchino_output_json)
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
                        k: v.get("sample")
                        for k, v in input_snap.items()
                        if isinstance(v, dict) and "sample" in v
                    },
                    "input_snapshot": s.input_snapshot_json,
                    "cecchino": {
                        "picchetti": cecchino_out.get("picchetti"),
                        "final": cecchino_out.get("final"),
                        "status": cecchino_out.get("status"),
                    },
                    "signals": s.signals_json,
                    "balance_v5": s.balance_v5_json,
                    "goal_intensity_compatibility": s.goal_intensity_compatibility_json,
                    "purchasability": {
                        "official_version": "V3",
                        "source_type": "historical_replay",
                        "replay_id": purch_official.get("replay_id"),
                        "status": purch_official.get("status"),
                        "legacy_purchasability_excluded": True,
                    },
                    "quote_availability": _as_dict(s.module_availability_json),
                    "pre_match_payload_sha256": s.pre_match_payload_sha256,
                    "pre_match_locked_at": (
                        s.pre_match_locked_at.isoformat() if s.pre_match_locked_at else None
                    ),
                    "result_after_lock": s.result_json,
                    "settlement_status": s.settlement_status,
                    "settlement_summary": s.settlement_summary_json,
                }
                yield json.dumps(row, ensure_ascii=False, default=str)

        def _iter_matches_compact() -> Iterator[str]:
            for s in snaps:
                yield json.dumps(_match_compact_row(s), ensure_ascii=False, default=str)

        def _iter_markets() -> Iterator[str]:
            for m in eligible_markets:
                s = snap_by_id.get(int(m.match_snapshot_id))
                result = _as_dict(s.result_json) if s else {}
                ft = _as_dict(result.get("fulltime") or result.get("ft"))
                ht = _as_dict(result.get("halftime") or result.get("ht"))
                q_quality = _quote_quality_of_market(m)
                sig = _signal_meta(m.signal_sources_json)
                real_odds = (
                    float(m.quota_book)
                    if m.is_real_book_quote and m.quota_book is not None
                    else None
                )
                derived_odds = (
                    float(m.quota_book)
                    if m.is_derived_quote and m.quota_book is not None
                    else None
                )
                row = {
                    "run_id": int(m.run_id),
                    "snapshot_id": int(m.match_snapshot_id),
                    "match_snapshot_id": int(m.match_snapshot_id),
                    "lab_match_id": int(m.lab_match_id),
                    "dataset_id": int(s.dataset_id) if s and s.dataset_id is not None else None,
                    "eligibility_status": (
                        s.historical_eligibility_status if s else ELIGIBLE_CORE
                    ),
                    "competition_name": s.competition_name if s else None,
                    "kickoff_at": s.kickoff_at.isoformat() if s and s.kickoff_at else None,
                    "chronological_order": s.chronological_order if s else None,
                    "home_team": s.home_team if s else None,
                    "away_team": s.away_team if s else None,
                    "home_score_ft": ft.get("home", result.get("ft_home")),
                    "away_score_ft": ft.get("away", result.get("ft_away")),
                    "home_score_ht": ht.get("home", result.get("ht_home")),
                    "away_score_ht": ht.get("away", result.get("ht_away")),
                    "market_key": m.market_key,
                    "market_label": m.market_label,
                    "period": m.period,
                    "line": m.line,
                    "quote_quality": q_quality,
                    "prob_cecchino": float(m.prob_cecchino) if m.prob_cecchino is not None else None,
                    "quota_cecchino": float(m.quota_cecchino) if m.quota_cecchino is not None else None,
                    "quota_book": float(m.quota_book) if m.quota_book is not None else None,
                    "rating": m.rating,
                    "signal_active": m.signal_active,
                    "signal_family": sig.get("signal_family"),
                    "active_signal_count": sig.get("active_signal_count"),
                    "is_real_book_quote": m.is_real_book_quote,
                    "is_derived_quote": m.is_derived_quote,
                    "real_book_odds": real_odds,
                    "derived_odds": derived_odds,
                    "won": m.won,
                    "evaluation_status": m.evaluation_status,
                    "settlement_status": s.settlement_status if s else None,
                    "profit_1u_real": float(m.profit_1u_real) if m.profit_1u_real is not None else None,
                    "profit_1u_synthetic": (
                        float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
                    ),
                    "profit_category": m.profit_category,
                    "result_reason": m.result_reason,
                }
                yield json.dumps(row, ensure_ascii=False, default=str)

        def _iter_signal_opportunities() -> Iterator[str]:
            for opp in signal_opportunities:
                yield json.dumps(
                    public_opportunity_row(opp), ensure_ascii=False, default=str
                )

        def _iter_signal_models() -> Iterator[str]:
            for opp in signal_opportunities:
                for cell_row in build_cell_rows_from_opportunity(opp):
                    yield json.dumps(cell_row, ensure_ascii=False, default=str)

        def _write_signal_export_files() -> None:
            line_counts["signal_opportunities.jsonl"] = _write_jsonl_to_zip(
                zf, "signal_opportunities.jsonl", _iter_signal_opportunities()
            )
            line_counts["signal_models.jsonl"] = _write_jsonl_to_zip(
                zf, "signal_models.jsonl", _iter_signal_models()
            )
            _put_json("model_overlap.json", {
                "model_overlap_matrix": signal_models_summary.get("model_overlap_matrix"),
                "consensus_distribution": signal_models_summary.get(
                    "consensus_distribution"
                ),
                "signal_export_reconciliation": signal_models_summary.get(
                    "signal_export_reconciliation"
                ),
                "market_join_diagnostics": signal_models_summary.get(
                    "market_join_diagnostics"
                ),
                "current_model_F_diagnostics": signal_models_summary.get(
                    "current_model_F_diagnostics"
                ),
                "signal_export_schema_version": SIGNAL_EXPORT_SCHEMA_VERSION,
            })

        def _iter_goal_intensity() -> Iterator[str]:
            for s in eligible_snaps:
                gi = _as_dict(s.goal_intensity_compatibility_json)
                result = _as_dict(s.result_json)
                market_outcomes = {}
                for m in markets_by_snap.get(int(s.id), []):
                    if m.market_key in ("OVER_2_5", "UNDER_2_5", "OVER_1_5", "UNDER_3_5"):
                        market_outcomes[m.market_key] = {
                            "won": m.won,
                            "evaluation_status": m.evaluation_status,
                        }
                yield json.dumps(
                    {
                        "run_id": int(run.id),
                        "lab_match_id": int(s.lab_match_id),
                        "competition_name": s.competition_name,
                        "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                        "pillars": gi.get("pillars"),
                        "final_class": gi.get("final_class"),
                        "sample_size": (_as_dict(gi.get("inputs"))).get("sample_size"),
                        "inputs": gi.get("inputs"),
                        "missing_inputs": gi.get("missing_inputs"),
                        "parity_status": gi.get("parity_status"),
                        "execution_status": gi.get("execution_status"),
                        "module_version": gi.get("module_version"),
                        "result_after_lock": result,
                        "goal_market_outcomes": market_outcomes,
                    },
                    ensure_ascii=False,
                    default=str,
                )

        def _write_official_purchasability_files() -> None:
            _put_json("purchasability_v3_summary.json", purch_official)
            manifest["purchasability_v3_replay_id"] = purch_official.get("replay_id")
            manifest["legacy_purchasability_excluded"] = True
            manifest["legacy_purchasability_read"] = False
            manifest["legacy_fallback_allowed"] = LEGACY_PURCHASABILITY_FALLBACK_ALLOWED
            manifest["official_purchasability_version"] = "V3"
            manifest["official_source_type"] = "historical_replay"
            if purch_replay is not None:
                line_counts["purchasability_v3_summary.json"] = 1

        def _iter_balance() -> Iterator[str]:
            for s in eligible_snaps:
                yield json.dumps(
                    {
                        "lab_match_id": int(s.lab_match_id),
                        "competition_name": s.competition_name,
                        "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                        "balance_v5": s.balance_v5_json,
                    },
                    ensure_ascii=False,
                    default=str,
                )

        if mode_norm == "full_archive":
            line_counts["matches.jsonl"] = _write_jsonl_to_zip(zf, "matches.jsonl", _iter_matches_full())
            line_counts["markets.jsonl"] = _write_jsonl_to_zip(zf, "markets.jsonl", _iter_markets())
            _write_signal_export_files()
            line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                zf, "goal_intensity.jsonl", _iter_goal_intensity()
            )
            _write_official_purchasability_files()
            line_counts["balance.jsonl"] = _write_jsonl_to_zip(zf, "balance.jsonl", _iter_balance())
        elif mode_norm == "competition":
            line_counts["matches_compact.jsonl"] = _write_jsonl_to_zip(
                zf, "matches_compact.jsonl", _iter_matches_compact()
            )
            line_counts["markets.jsonl"] = _write_jsonl_to_zip(zf, "markets.jsonl", _iter_markets())
            _write_signal_export_files()
            line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                zf, "goal_intensity.jsonl", _iter_goal_intensity()
            )
            _write_official_purchasability_files()
        elif mode_norm == "module":
            if module_norm == "markets":
                line_counts["markets.jsonl"] = _write_jsonl_to_zip(
                    zf, "markets.jsonl", _iter_markets()
                )
            elif module_norm == "signals":
                _write_signal_export_files()
            elif module_norm == "goal_intensity":
                line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                    zf, "goal_intensity.jsonl", _iter_goal_intensity()
                )
            elif module_norm == "purchasability":
                _write_official_purchasability_files()
            elif module_norm == "balance":
                line_counts["balance.jsonl"] = _write_jsonl_to_zip(
                    zf, "balance.jsonl", _iter_balance()
                )

        # report_index + manifest aggiornato (conteggi finali / campi purchasability)
        report_index = {
            "run_id": int(run.id),
            "schema_version": REPORT_SCHEMA_VERSION,
            "scope": run_scope,
            "season": run.season_label,
            "source_git_commit": run.source_git_commit,
            "report_mode": mode_norm,
            "available_packages": [
                {
                    "mode": "ai_summary",
                    "description": "Sintesi piccola per ChatGPT (consigliata)",
                    "recommended_first": True,
                },
                {
                    "mode": "competition",
                    "description": "Dettaglio per singolo campionato",
                    "competitions": all_competitions,
                },
                {
                    "mode": "module",
                    "description": "Dettaglio per modulo",
                    "modules": sorted(REPORT_MODULES),
                },
                {
                    "mode": "full_archive",
                    "description": (
                        "Archivio tecnico completo — non necessario per la prima analisi ChatGPT"
                    ),
                    "technical_only": True,
                },
            ],
            "competitions_available": all_competitions,
            "modules_available": sorted(REPORT_MODULES),
            "recommended_analysis_order": [
                "ai_summary",
                "competition",
                "module",
                "full_archive",
            ],
            "line_counts": dict(line_counts),
            "analysis_instruction": (
                "1) ai_summary; 2) eventuale campionato; 3) eventuale modulo; "
                "4) full_archive solo per audit tecnico."
            ),
        }
        _put_json("report_index.json", report_index)
        # Riscrivi manifest con campi purchasability e line_counts consolidati
        manifest["line_counts"] = dict(line_counts)
        manifest["uncompressed_size_hint_bytes"] = None
        _put_json("manifest.json", manifest)

    dest.seek(0, os.SEEK_END)
    size = int(dest.tell())
    if mode_norm == "ai_summary" and size > AI_SUMMARY_WARN_BYTES:
        logger.warning(
            "ai_summary report larger than expected run_id=%s bytes=%s",
            run.id,
            size,
        )
    return filename, size


def iter_report_chunks(data: bytes, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
