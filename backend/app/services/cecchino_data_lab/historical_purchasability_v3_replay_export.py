"""Export ZIP autonomo Replay Acquistabilità V3 (STEP 3C.2) — unica sorgente ufficiale.

Read-only, streaming, nessun ricalcolo formula, nessun dump ZIP intero in RAM.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BufferedIOBase
from typing import Any, BinaryIO, Iterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
    REPLAY_NOT_COMPLETED_MSG,
    _json_safe,
    ensure_replay_ready_for_analytics,
    get_purchasability_v3_replay_analytics,
    iter_compact_export_rows,
    iter_lean_replay_result_rows,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

logger = logging.getLogger(__name__)

PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION = "cecchino_lab_purchasability_v3_export_v2"
SPOOL_MAX_SIZE = 8 * 1024 * 1024
REPORT_CHUNK_SIZE = 64 * 1024
EXPORT_MODES = frozenset({"analysis", "full_archive"})

AI_INSTRUCTIONS_MD = """# Istruzioni per ChatGPT — Report Replay Acquistabilità V3

1. Usa **esclusivamente Acquistabilità V3** (questo report). Non cercare V1.1 o V2.
2. Non confrontare con indici Acquistabilità precedenti.
3. La sorgente ufficiale è il **replay V3 persistito** (`official_source_type=historical_replay`).
4. Non ricalcolare la formula: tutti i valori sono persistiti (`formula_recomputed=false`).
5. Gate failed **non** equivale a score 0: non inserire i gate falliti nella fascia «Molto Bassa» / 0–19.
6. Analizza score e ROI **entro lo stesso mercato**; non confrontare HOME 90 con OVER_2_5 90 senza indicare il mercato.
7. ROI reale (`profit_1u_real`) e ROI sintetico (`profit_1u_synthetic`) sono **separati**; non mescolarli.
8. Le doppie chance (ONE_X / X_TWO / ONE_TWO) **non** sono quote Bet365 reali (`not_a_real_bet365_quote=true`).
9. `family_decisions` sono **diagnostiche** (`diagnostic_family_selection=true`), non una strategia operativa.
10. Non sommare mercati indipendenti come un'unica strategia.
11. Non considerare il technical aggregate una strategia (`technical_aggregate_only=true`).
12. Distingui value_score, quality_score e penalità; non affermare causalità.
13. Verifica stabilità temporale (prima/seconda metà **per campionato**) e per competition.
14. Considera numerosità e intervalli di confidenza (CI null se campione insufficiente).
15. Non cambiare soglie operative sulla base di una sola stagione.
16. La stagione 2022/2023 non è ancora stata usata per validazione.

Leggi prima `report_index.json`, `manifest.json`, `SCHEMA.md` e `ANALYSIS_CHECKLIST.md`.
"""

SCHEMA_MD = """# Schema export Replay Acquistabilità V3

- `analytics_schema_version`: cecchino_lab_purchasability_v3_analytics_v2
- `export_schema_version`: cecchino_lab_purchasability_v3_export_v2
- `official_purchasability_version`: V3
- `official_source_type`: historical_replay
- `legacy_purchasability_included`: false
- `legacy_purchasability_read`: false
- `legacy_fallback_allowed`: false
- Universi: ALL / SCORED / GATE_FAILED / UNAVAILABLE / REAL_PERFORMANCE / SYNTHETIC_PERFORMANCE
- Gate failed ≠ score 0
- ROI = profit_units / stake_count × 100; stake 0 → null
- Quote reali e derivate separate
- Family decisions diagnostiche, no cross-family winner
- Temporal split per competition (floor n/2)
- `replay_results_compact.jsonl`: 1 riga per valutazione persistita
- `replay_results_full.jsonl`: solo mode full_archive
- `formula_recomputed=false` sempre
- Nessun file V1.1/V2 / compatibility / confronto legacy
"""

README_MD = """# Report Replay Acquistabilità V3

Export ufficiale Acquistabilità V3 dal replay storico completato.
Unica sorgente ufficiale per le Run che possiedono un replay V3 compatibile.
Non include V1.1, V2, né confronti legacy.

Modalità:
- **analysis** (consigliata per ChatGPT): riepiloghi + compact JSONL + family decisions
- **full_archive**: analysis + audit verbose (`replay_results_full.jsonl`)

Nessun ricalcolo formula. Nessuna modifica a Run storico / Replay / MarketResult.
Nessun fallback verso indici Acquistabilità legacy.
"""

ANALYSIS_CHECKLIST_MD = """# Checklist analisi V3

- [ ] Usare esclusivamente Acquistabilità V3 (nessun V1.1/V2)
- [ ] Riconciliazione (all = scored + gate_failed + unavailable + …)
- [ ] Distribuzione gate e reason codes
- [ ] Score per mercato
- [ ] ROI per score band (solo scored)
- [ ] ROI per threshold (≥20…≥90) per mercato
- [ ] Penalità (application rate, mean/median, bande)
- [ ] Matrice Value/Quality
- [ ] Family decisions (diagnostiche)
- [ ] Prima / seconda metà per campionato
- [ ] Stabilità per campionato e sample flags
- [ ] Quote reali
- [ ] Quote derivate (sintetiche)
- [ ] Concentrazione del profitto
- [ ] Manifest: official_purchasability_version=V3, legacy_*=false, formula_recomputed=false
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _put_json(zf: zipfile.ZipFile, name: str, obj: Any) -> None:
    zf.writestr(name, _json_bytes(obj))


def _put_text(zf: zipfile.ZipFile, name: str, text: str) -> None:
    zf.writestr(name, text.encode("utf-8"))


def _write_jsonl_once(
    zf: zipfile.ZipFile, name: str, rows: Iterator[dict[str, Any]] | list
) -> int:
    lines: list[str] = []
    count = 0
    for row in rows:
        lines.append(json.dumps(_json_safe(row), ensure_ascii=False, default=str))
        count += 1
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    zf.writestr(name, payload)
    return count


def _full_row(r: dict[str, Any]) -> dict[str, Any]:
    compact = next(iter_compact_export_rows([r]))
    compact.update(
        {
            "gate_reason_codes_json": r.get("gate_reason_codes_json"),
            "reason_codes_json": r.get("reason_codes_json"),
            "warnings_json": r.get("warnings_json"),
            "source_pre_match_payload_sha256": r.get("source_pre_match_payload_sha256"),
            "source_pre_match_locked_at": r.get("source_pre_match_locked_at"),
            "formula_payload_sha256": r.get("formula_payload_sha256"),
            "formula_payload_fields_json": r.get("formula_payload_fields_json"),
            "pre_match_only": r.get("pre_match_only"),
            "post_match_fields_excluded": r.get("post_match_fields_excluded"),
            "derivation_method": r.get("derivation_method"),
            "result_reason": r.get("result_reason"),
            "raw_score": r.get("raw_score"),
        }
    )
    return compact


def _by_market_jsonl_rows(analytics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"market_key": mk, **payload}
        for mk, payload in (analytics.get("by_market") or {}).items()
    ]


def _by_score_band_jsonl(analytics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"score_band": b, **payload}
        for b, payload in (analytics.get("by_score_band") or {}).items()
    ]


def _by_threshold_jsonl(analytics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for mk, thr_map in (analytics.get("by_threshold") or {}).items():
        for thr_key, payload in thr_map.items():
            rows.append({"market_key": mk, "threshold": thr_key, **payload})
    return rows


def _by_competition_market_jsonl(analytics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for mk, comps in (analytics.get("competition_stability") or {}).items():
        if not isinstance(comps, dict):
            continue
        for comp, payload in comps.items():
            if not isinstance(payload, dict):
                continue
            rows.append({"market_key": mk, "competition_name": comp, **payload})
    return rows


def write_purchasability_v3_replay_report_zip(
    db: Session,
    replay_id: int,
    dest: BinaryIO | BufferedIOBase,
    *,
    mode: str = "analysis",
    analytics: dict[str, Any] | None = None,
    lean_rows: list[dict[str, Any]] | None = None,
    filename_override: str | None = None,
) -> tuple[str, int]:
    mode_norm = (mode or "analysis").strip().lower()
    if mode_norm not in EXPORT_MODES:
        raise CecchinoLabImportError(
            "invalid_report_mode",
            f"mode non supportata: {mode}",
            status_code=400,
        )

    replay = ensure_replay_ready_for_analytics(db, replay_id)
    if analytics is None:
        analytics = get_purchasability_v3_replay_analytics(db, replay_id)

    if lean_rows is None:
        lean_rows = list(iter_lean_replay_result_rows(db, int(replay_id)))

    recon_status = (analytics.get("reconciliation") or {}).get("status")
    analytics_status = analytics.get("status")
    diagnostic_failed = analytics_status == "blocked" or recon_status == "failed"

    generator_rev = resolve_code_revision()
    filename = filename_override or (
        f"cecchino-purchasability-v3-replay-{int(replay_id)}-"
        f"{'full' if mode_norm == 'full_archive' else 'analysis'}.zip"
    )

    family_rows = analytics.get("family_decisions_rows") or []
    summary = {k: v for k, v in analytics.items() if k != "family_decisions_rows"}
    summary["export_validity"] = "diagnostic_failed" if diagnostic_failed else "valid"
    summary["report_valid"] = not diagnostic_failed

    file_row_counts: dict[str, int] = {}

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _put_text(zf, "AI_INSTRUCTIONS.md", AI_INSTRUCTIONS_MD)
        _put_text(zf, "SCHEMA.md", SCHEMA_MD)
        _put_text(zf, "README.md", README_MD)
        _put_text(zf, "ANALYSIS_CHECKLIST.md", ANALYSIS_CHECKLIST_MD)

        report_index: dict[str, Any] = {
            "title": "Cecchino Lab — Replay Acquistabilità V3",
            "mode": mode_norm,
            "replay_id": int(replay_id),
            "source_scan_run_id": int(replay.source_scan_run_id),
            "analytics_status": analytics_status,
            "reconciliation_status": recon_status,
            "formula_recomputed": False,
            "recommended_for_chatgpt": mode_norm == "analysis",
            "files": [],
        }

        universes = analytics.get("universes") or {}
        manifest: dict[str, Any] = {
            "analytics_schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
            "export_schema_version": PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
            "replay_id": int(replay_id),
            "source_scan_run_id": int(replay.source_scan_run_id),
            "replay_status": str(replay.status),
            "replay_schema_version": replay.replay_schema_version,
            "replay_engine_version": replay.replay_engine_version,
            "candidate_version": replay.candidate_version,
            "formula_version": replay.formula_version,
            "audit_version": replay.audit_version,
            "preflight_schema_version": replay.preflight_schema_version,
            "integrity_policy_version": replay.integrity_policy_version,
            "scan_source_git_commit": replay.source_scan_git_commit,
            "replay_runtime_git_commit": replay.runtime_git_commit,
            "report_generator_git_commit": generator_rev.get("git_commit"),
            "report_generator_git_commit_source": generator_rev.get("git_commit_source"),
            "rows": universes.get("ALL_EVALUATIONS"),
            "scored": universes.get("SCORED_EVALUATIONS"),
            "gate_failed": universes.get("GATE_FAILED_EVALUATIONS"),
            "unavailable": universes.get("UNAVAILABLE_EVALUATIONS"),
            "real_quotes": (analytics.get("reconciliation") or {})
            .get("quote_buckets", {})
            .get("real"),
            "derived_quotes": (analytics.get("reconciliation") or {})
            .get("quote_buckets", {})
            .get("derived"),
            "formula_recomputed": False,
            "performance_real_and_synthetic_separated": True,
            "generated_at": _utcnow().isoformat(),
            "reconciliation_status": recon_status,
            "analytics_status": analytics_status,
            "export_validity": "diagnostic_failed" if diagnostic_failed else "valid",
            "warnings": analytics.get("warnings") or [],
            "blockers": analytics.get("blockers") or [],
            "files": [],
            "file_row_counts": file_row_counts,
            "official_purchasability_version": "V3",
            "official_source_type": "historical_replay",
            "source_replay_id": int(replay_id),
            "legacy_purchasability_included": False,
            "legacy_purchasability_read": False,
            "legacy_fallback_allowed": False,
            "no_old_v2_primary_file": True,
        }

        def _add(name: str, obj: Any) -> None:
            _put_json(zf, name, obj)
            report_index["files"].append(name)
            manifest["files"].append(name)

        def _add_jsonl(name: str, rows: Any) -> None:
            n = _write_jsonl_once(zf, name, rows)
            file_row_counts[name] = n
            report_index["files"].append(name)
            manifest["files"].append(name)

        _add("summary.json", summary)
        _add("reconciliation.json", analytics.get("reconciliation") or {})
        _add("score_distribution.json", analytics.get("score_distribution") or {})
        _add("gate_analysis.json", analytics.get("gate_analysis") or {})
        _add("performance_real.json", analytics.get("performance_real") or {})
        _add("performance_synthetic.json", analytics.get("performance_synthetic") or {})
        _add("penalties.json", analytics.get("penalties") or {})
        _add("value_quality_matrix.json", analytics.get("value_quality_matrix") or {})
        _add("family_decisions_summary.json", analytics.get("family_decisions") or {})
        _add("temporal_stability.json", analytics.get("temporal_stability") or {})
        _add(
            "competition_stability_summary.json",
            {
                "note": "Dettaglio riga-per-riga in by_competition_market.jsonl",
                "markets": list((analytics.get("competition_stability") or {}).keys()),
            },
        )
        _add_jsonl("by_market.jsonl", _by_market_jsonl_rows(analytics))
        _add_jsonl("by_score_band.jsonl", _by_score_band_jsonl(analytics))
        _add_jsonl("by_threshold.jsonl", _by_threshold_jsonl(analytics))
        _add_jsonl(
            "by_competition_market.jsonl", _by_competition_market_jsonl(analytics)
        )
        _add_jsonl("family_decisions.jsonl", family_rows)
        _add_jsonl(
            "replay_results_compact.jsonl", iter_compact_export_rows(lean_rows)
        )

        if mode_norm == "full_archive":
            _add_jsonl(
                "replay_results_full.jsonl", (_full_row(r) for r in lean_rows)
            )

        for name in (
            "manifest.json",
            "report_index.json",
            "README.md",
            "SCHEMA.md",
            "AI_INSTRUCTIONS.md",
            "ANALYSIS_CHECKLIST.md",
        ):
            if name not in report_index["files"]:
                report_index["files"].append(name)
            if name not in manifest["files"]:
                manifest["files"].append(name)

        manifest["file_row_counts"] = file_row_counts
        _put_json(zf, "manifest.json", manifest)
        _put_json(zf, "report_index.json", report_index)

    dest.seek(0, 2)
    size = int(dest.tell())
    dest.seek(0)
    return filename, size


def build_purchasability_v3_replay_report_zip_bytes(
    db: Session,
    replay_id: int,
    *,
    mode: str = "analysis",
    analytics: dict[str, Any] | None = None,
    lean_rows: list[dict[str, Any]] | None = None,
    filename_override: str | None = None,
) -> tuple[str, bytes]:
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
    try:
        filename, size = write_purchasability_v3_replay_report_zip(
            db,
            replay_id,
            spool,
            mode=mode,
            analytics=analytics,
            lean_rows=lean_rows,
            filename_override=filename_override,
        )
        spool.seek(0)
        data = spool.read()
        logger.info(
            "v3 replay report zip built replay_id=%s mode=%s bytes=%s",
            replay_id,
            mode,
            size,
        )
        return filename, data
    finally:
        spool.close()


def build_purchasability_v3_replay_report_response(
    db: Session,
    replay_id: int,
    *,
    mode: str = "analysis",
    filename_override: str | None = None,
) -> StreamingResponse:
    mode_norm = (mode or "analysis").strip().lower()
    if mode_norm not in EXPORT_MODES:
        raise CecchinoLabImportError(
            "invalid_report_mode",
            f"mode non supportata: {mode}",
            status_code=400,
        )

    ensure_replay_ready_for_analytics(db, replay_id)

    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_SIZE)
    try:
        filename, size = write_purchasability_v3_replay_report_zip(
            db,
            replay_id,
            spool,
            mode=mode_norm,
            filename_override=filename_override,
        )
    except Exception:
        spool.close()
        raise

    spool.seek(0)
    logger.info(
        "v3 replay report streaming replay_id=%s mode=%s bytes=%s",
        replay_id,
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
        "X-Export-Schema-Version": PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
    }
    if mode_norm == "full_archive":
        headers["X-Report-Warning"] = (
            "Archivio tecnico completo - per ChatGPT preferire mode=analysis"
        )
    return StreamingResponse(_iter(), media_type="application/zip", headers=headers)


__all__ = [
    "PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION",
    "REPLAY_NOT_COMPLETED_MSG",
    "build_purchasability_v3_replay_report_response",
    "build_purchasability_v3_replay_report_zip_bytes",
    "write_purchasability_v3_replay_report_zip",
]
