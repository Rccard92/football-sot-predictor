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
    HISTORICAL_PILOT_STRATEGY_MODULE_READY,
    HISTORICAL_QUOTE_POLICY_VERSION,
    HISTORICAL_SCAN_VERSION,
    PARSER_VERSION,
    PILOT_SAMPLE_ROLE_ANALYSIS,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE

logger = logging.getLogger(__name__)

REPORT_SCHEMA_VERSION = "cecchino_lab_ai_report_v4"
REPORT_MODES = frozenset({"ai_summary", "competition", "module", "full_archive"})
REPORT_MODULES = frozenset({"markets", "signals", "goal_intensity", "purchasability", "balance"})
PATTERNS_TOP_CAP = 25
MIN_PATTERN_SAMPLE_FOR_REAL_ROI = 20
SPOOL_MAX_SIZE = 8 * 1024 * 1024
REPORT_CHUNK_SIZE = 64 * 1024
AI_SUMMARY_WARN_BYTES = 5 * 1024 * 1024

AI_INSTRUCTIONS_MD = """# Istruzioni per ChatGPT — Report storico Cecchino Lab (v4)

1. Leggi prima `report_index.json`, `manifest.json` e `SCHEMA.md`.
2. Usa **solo** `eligible_analysis` (o il campione `analysis` del pilota moduli maturi) per hit rate, profitto, ROI, fasce rating, pattern e analisi segnali.
3. `excluded_diagnostics` / warm-up sono diagnostica: non mescolarli con la performance.
4. Non confondere quote **reali Bet365** e quote **derivate**.
5. Non sommare ROI reale e ROI sintetico.
6. Non trattare quote derivate come offerte Bet365.
7. Non confondere `quota_cecchino` (modello) e `quota_book` (bookmaker).
8. La frequenza naturale di un mercato (`outcome_base_rate`) **non** è “performance del Cecchino”.
9. Distingui: outcome base rate; mercato con quota Cecchino; con rating; con segnale attivo; con quota Bet365 reale; con quota derivata.
10. Intensità Goal storica: usa `goal_intensity.jsonl` (pilastri). `parity_status=partial` — non è V5 live completo (no bundle Today, no xG).
11. Acquistabilità storica Bet365: usa `purchasability.jsonl` / `purchasability_compact.jsonl`. Profilo progressivo Lab; **non** equivalente al modulo Betfair operativo.
12. Modelli segnali A–F: usa `signal_models.jsonl`. Il modello F coincide con il modello corrente del Cecchino. `model_label` non deve essere null.
13. Non utilizzare risultati futuri come input: il blocco pre-match è congelato prima del risultato.
14. Riporta sempre `sample_size`. Separa risultati globali e per campionato.
15. Segnala instabilità cross-competition.
16. Non proporre modifiche automatiche a formule, pesi o soglie produttive.
17. Distingui correlazione, ipotesi e prova.
18. Se `is_partial_run=true` / `not_full_season_report=true`, non trattare il report come scansione stagione completa.
19. **Non** interpretare `technical_sum_across_all_independent_market_rows` come profitto del Cecchino o come strategia di scommessa (`not_a_betting_strategy=true`).
20. Mostra profitto/ROI separati per: mercato, segnale, modello A–F, fascia rating, fascia Acquistabilità, pattern. Nessuna somma globale come rendimento Cecchino.
21. Ordine consigliato: `ai_summary` → eventuale campionato → eventuale modulo → `full_archive` solo per audit tecnico.
22. Produci una “prima linea” con: dati sufficienti; dati mancanti; moduli analizzabili; moduli parziali; segnali promettenti/negativi; aspetti da verificare.

Cecchino Today operativo resta su **Betfair** e non è modificato da questo report.
"""

SCHEMA_MD = """# Schema report AI Cecchino Lab (v4)

- `report_index.json`: indice pacchetti, conteggi, ordine analisi consigliato
- `manifest.json`: metadati run, policy, scope, revision git, versioni moduli
- `summary.json`: `eligible_analysis`, `excluded_diagnostics`, `errors`, `data_coverage`
- `data_quality.json`: qualità dati stagione (preflight)
- `eligibility.json`: conteggi eleggibilità
- `module_coverage.json`: copertura moduli + parità Intensità/Acquistabilità
- `patterns_top.json`: sottoinsieme deterministico di pattern (ai_summary)
- `patterns.json`: pattern completi (full_archive / competition)
- `matches.jsonl` / `matches_compact.jsonl`: partite (completo vs compatto AI)
- `markets.jsonl`: partita×mercato eligible/analysis
- `signal_models.jsonl`: partita × modello × segnale attivo (etichette canoniche A–F)
- `goal_intensity.jsonl`: pilastri Intensità
- `purchasability.jsonl` / `purchasability_compact.jsonl`: Acquistabilità
- `AI_INSTRUCTIONS.md` / `SCHEMA.md`

Modalità export: `ai_summary` | `competition` | `module` | `full_archive`.
`full_archive` = archivio tecnico completo — non necessario per la prima analisi ChatGPT.
Metriche di performance usano `eligible_core` (o `pilot_sample_role=analysis` nei piloti moduli maturi).
`technical_sum_across_all_independent_market_rows` è diagnostica tecnica, non una strategia.
"""


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    """Normalizza JSON opzionale a dict; altrimenti {}."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Normalizza JSON opzionale a list; altrimenti []."""
    return value if isinstance(value, list) else []


def _pilot_sample_role(snap: CecchinoLabHistoricalMatchSnapshot) -> str | None:
    ma = _as_dict(snap.module_availability_json)
    role = ma.get("pilot_sample_role")
    return str(role) if role else None


def _is_analysis_snap(
    snap: CecchinoLabHistoricalMatchSnapshot,
    *,
    is_module_ready_pilot: bool,
) -> bool:
    if is_module_ready_pilot:
        return _pilot_sample_role(snap) == PILOT_SAMPLE_ROLE_ANALYSIS
    return snap.historical_eligibility_status == ELIGIBLE_CORE


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
    purch = _as_dict(s.purchasability_compatibility_json)
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
        "pilot_sample_role": _pilot_sample_role(s),
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
        "purchasability_execution": purch.get("execution_status"),
        "signal_active_counts_A_F": af_counts,
        "result_after_lock": s.result_json,
        "pre_match_payload_sha256": s.pre_match_payload_sha256,
    }


def _purchasability_compact_rows(
    s: CecchinoLabHistoricalMatchSnapshot,
    markets_by_snap: dict[int, list[CecchinoLabHistoricalMarketResult]],
) -> list[dict[str, Any]]:
    purch = _as_dict(s.purchasability_compatibility_json)
    bal = _as_dict(s.balance_v5_json)
    bal_class, _ = _structural_class(bal.get("structural_summary") if bal else None)
    gi = _as_dict(s.goal_intensity_compatibility_json)
    m_by_key = {m.market_key: m for m in markets_by_snap.get(int(s.id), [])}
    rows: list[dict[str, Any]] = []
    for mk_row in purch.get("markets") or []:
        if not isinstance(mk_row, dict):
            continue
        mk = mk_row.get("market_key")
        m = m_by_key.get(mk)
        rows.append(
            {
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "market_key": mk,
                "score": mk_row.get("score"),
                "class": mk_row.get("class"),
                "rating": mk_row.get("rating"),
                "edge_pct": mk_row.get("edge_pct"),
                "vantaggio_prob": mk_row.get("vantaggio_prob"),
                "quote_quality": mk_row.get("quote_quality"),
                "signal_active": bool(m.signal_active) if m else None,
                "balance_class": bal_class,
                "goal_intensity_execution": gi.get("execution_status"),
                "won": m.won if m else None,
                "real_profit_1u": (
                    float(m.profit_1u_real) if m and m.profit_1u_real is not None else None
                ),
                "synthetic_profit_1u": (
                    float(m.profit_1u_synthetic)
                    if m and m.profit_1u_synthetic is not None
                    else None
                ),
            }
        )
    return rows


def _build_patterns_top(patterns: dict[str, Any]) -> dict[str, Any]:
    items = list(patterns.get("patterns") or [])
    by_id: dict[str, dict[str, Any]] = {}
    for p in items:
        if isinstance(p, dict) and p.get("pattern_id"):
            by_id[str(p["pattern_id"])] = p

    def _dedupe(seq: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in seq:
            pid = str(p.get("pattern_id"))
            if pid in seen:
                continue
            seen.add(pid)
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
            if _as_dict(p.get("stability_by_competition")).get("stable_cross_competition") is False
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


def _scope_tag(run_scope: str, is_partial: bool) -> str:
    if run_scope == "balanced_pilot":
        return "balanced_pilot"
    if run_scope == "module_ready_pilot":
        return "module_ready_pilot"
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


def _structural_class(structural: Any) -> tuple[str, str | None]:
    """
    Estrae la classe Balance da structural_summary.

    - dict → class, poi class_key, poi unknown
    - stringa non vuota → la stringa
    - null / list / number / altro → unknown (+ warning diagnostico)
    """
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
        families = sources_json.get("signal_families")
        sources = sources_json.get("sources")
        return {
            "signal_family": sources_json.get("signal_family"),
            "signal_families": _as_list(families),
            "active_signal_count": int(sources_json.get("active_signal_count") or 0),
            "sources": _as_list(sources),
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


def _balance_pillars(balance: Any) -> dict[str, Any]:
    bal = _as_dict(balance)
    if not bal:
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
        block = bal.get(key)
        if isinstance(block, dict):
            pillars[key] = {
                "class_key": block.get("class_key") or block.get("class"),
                "label": block.get("label"),
                "value": block.get("value") or block.get("score") or block.get("f36_abs"),
            }
        elif isinstance(block, str) and block.strip() and key == "structural_summary":
            pillars[key] = {
                "class_key": block.strip(),
                "label": None,
                "value": None,
            }
    for key, block in bal.items():
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
    is_module_ready_pilot = policy.get("pilot_strategy") == HISTORICAL_PILOT_STRATEGY_MODULE_READY

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

    # Universo performance: analysis per module_ready, altrimenti eligible_core
    analysis_snaps = [
        s for s in snaps if _is_analysis_snap(s, is_module_ready_pilot=is_module_ready_pilot)
    ]
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
    purch_computed = sum(
        1
        for s in eligible_snaps
        if _as_dict(s.purchasability_compatibility_json).get("execution_status") == "computed"
    )

    manifest = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_mode": mode_norm,
        "report_module": module_norm,
        "report_competition": competition_filter,
        "run_id": int(run.id),
        "season_label": run.season_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": "Rccard92/football-sot-predictor",
        "source_git_commit": run.source_git_commit,
        "source_git_commit_source": getattr(run, "source_git_commit_source", None),
        "source_revision_status": getattr(run, "source_revision_status", None),
        "scan_version": run.scan_version or HISTORICAL_SCAN_VERSION,
        "parser_version": PARSER_VERSION,
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "max_matches": policy.get("max_matches"),
        "pilot_strategy": policy.get("pilot_strategy"),
        "eligible_per_competition": policy.get("eligible_per_competition"),
        "module_ready_per_competition": policy.get("module_ready_per_competition"),
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
            "purchasability": "historical_bet365_progressive_v1",
        },
        "competitions_included": competitions,
        "datasets_included": datasets,
        "quote_policy": HISTORICAL_QUOTE_POLICY_VERSION,
        "derivation_policy": HISTORICAL_DERIVATION_METHOD,
        "anti_leakage_policy": "strict_prior_kickoff_same_competition_only",
        "performance_universe": (
            "pilot_sample_role_analysis"
            if is_module_ready_pilot
            else "eligible_core_only"
        ),
        "profit_policy": {
            "real": "profit_1u_real from real Bet365 quotes only",
            "synthetic": "profit_1u_synthetic from derived quotes only",
            "do_not_sum_real_and_synthetic": True,
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
            "purchasability": "historical_bet365_v2",
            "signal_models": "F_equals_current",
        },
        "operational_today_bookmaker": "Betfair",
        "historical_replay_bookmaker": "Bet365",
        "operational_today_modified": False,
        "do_not_propose_formula_changes": True,
    }

    # --- reuse aggregation body via internal call ---
    return _finalize_report_zip(
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
        is_module_ready_pilot=is_module_ready_pilot,
    )


def _finalize_report_zip(
    *,
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
    is_module_ready_pilot: bool,
) -> tuple[str, int]:
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
            "inputs_available": sum(
                1
                for s in eligible_snaps
                if _compat_flag(s.purchasability_compatibility_json, "inputs_available")
            ),
            "scores_computed": purch_computed,
            "parity_status": "historical_bet365_v2",
            "betfair_operational_profile_applied": False,
            "note": "Indice storico Bet365 progressivo; osservazionale",
        },
        "signal_models": {
            "models": list(CECCHINO_WEIGHT_MODEL_KEYS),
            "default_model_key": CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
            "f_equals_current": True,
        },
        "pilot_sample_roles": {
            "analysis": sum(1 for s in snaps if _pilot_sample_role(s) == PILOT_SAMPLE_ROLE_ANALYSIS),
            "warmup": sum(
                1
                for s in snaps
                if _pilot_sample_role(s) == "warmup"
            ),
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

    # Aggregazioni Acquistabilità / Intensità / modelli A–F
    purch_band_buckets: dict[str, dict[str, Any]] = defaultdict(_agg_bucket)
    purch_decile_buckets: dict[str, dict[str, Any]] = defaultdict(_agg_bucket)
    gi_class_buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(_agg_bucket)
    )
    model_buckets: dict[str, dict[str, Any]] = defaultdict(_agg_bucket)

    def _purch_band(score: Any) -> str | None:
        if score is None:
            return None
        try:
            s = float(score)
        except (TypeError, ValueError):
            return None
        if s < 20:
            return "0-19"
        if s < 40:
            return "20-39"
        if s < 60:
            return "40-59"
        if s < 80:
            return "60-79"
        return "80-100"

    def _purch_decile(score: Any) -> str | None:
        if score is None:
            return None
        try:
            s = float(score)
        except (TypeError, ValueError):
            return None
        if s >= 100:
            return "100"
        bucket = int(s // 10) * 10
        return f"{bucket}-{bucket + 9}"

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        if not s:
            continue
        purch = _as_dict(s.purchasability_compatibility_json)
        for mk_row in purch.get("markets") or []:
            if not isinstance(mk_row, dict):
                continue
            if mk_row.get("market_key") != m.market_key:
                continue
            band = _purch_band(mk_row.get("score"))
            dec = _purch_decile(mk_row.get("score"))
            if band:
                b = purch_band_buckets[band]
                b["sample_size"] += 1
                if s.competition_name:
                    b["competitions"].add(s.competition_name)
                if m.won is True:
                    b["won"] += 1
                elif m.won is False:
                    b["lost"] += 1
                if m.is_real_book_quote and m.profit_1u_real is not None:
                    b["real_quote_count"] += 1
                    b["real_profit_1u"] += float(m.profit_1u_real)
                elif m.is_derived_quote and m.profit_1u_synthetic is not None:
                    b["derived_quote_count"] += 1
                    b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)
            if dec:
                b = purch_decile_buckets[dec]
                b["sample_size"] += 1
                if s.competition_name:
                    b["competitions"].add(s.competition_name)
                if m.won is True:
                    b["won"] += 1
                elif m.won is False:
                    b["lost"] += 1
                if m.is_real_book_quote and m.profit_1u_real is not None:
                    b["real_quote_count"] += 1
                    b["real_profit_1u"] += float(m.profit_1u_real)
                elif m.is_derived_quote and m.profit_1u_synthetic is not None:
                    b["derived_quote_count"] += 1
                    b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)

        gi = _as_dict(s.goal_intensity_compatibility_json)
        for pillar_name, pblock in _as_dict(gi.get("pillars")).items():
            ck = _as_dict(pblock).get("class") or _as_dict(pblock).get("class_key")
            if not ck:
                continue
            b = gi_class_buckets[str(pillar_name)][str(ck)]
            b["sample_size"] += 1
            if s.competition_name:
                b["competitions"].add(s.competition_name)
            if m.won is True:
                b["won"] += 1
            elif m.won is False:
                b["lost"] += 1
            if m.is_real_book_quote and m.profit_1u_real is not None:
                b["real_quote_count"] += 1
                b["real_profit_1u"] += float(m.profit_1u_real)
            elif m.is_derived_quote and m.profit_1u_synthetic is not None:
                b["derived_quote_count"] += 1
                b["synthetic_profit_1u"] += float(m.profit_1u_synthetic)

        sigs = _as_dict(s.signals_json)
        for model_key, mblock in (_as_dict(sigs.get("models"))).items():
            for sett in _as_list(_as_dict(mblock).get("settlements")):
                if not isinstance(sett, dict):
                    continue
                if sett.get("target_market") != m.market_key:
                    continue
                b = model_buckets[str(model_key)]
                b["sample_size"] += 1
                if s.competition_name:
                    b["competitions"].add(s.competition_name)
                if sett.get("won") is True:
                    b["won"] += 1
                elif sett.get("won") is False:
                    b["lost"] += 1
                if sett.get("real_profit_1u") is not None:
                    b["real_quote_count"] += 1
                    b["real_profit_1u"] += float(sett["real_profit_1u"])
                if sett.get("synthetic_profit_1u") is not None:
                    b["derived_quote_count"] += 1
                    b["synthetic_profit_1u"] += float(sett["synthetic_profit_1u"])

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

    eligible_analysis = {
        "note": (
            "Aggregazioni di performance solo su eligible_core / analysis. "
            "outcome_base_rate non è performance del Cecchino. "
            "Profitto principale per mercato/segnale/modello/fascia/pattern — "
            "non usare technical_sum come profitto Cecchino."
        ),
        "aggregations": {
            dim: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
            for dim, inner in buckets.items()
        },
        "purchasability_bands": {
            k: _finalize_bucket(v) for k, v in sorted(purch_band_buckets.items())
        },
        "purchasability_deciles": {
            k: _finalize_bucket(v) for k, v in sorted(purch_decile_buckets.items())
        },
        "goal_intensity_pillar_classes": {
            pillar: {k: _finalize_bucket(v) for k, v in sorted(inner.items())}
            for pillar, inner in gi_class_buckets.items()
        },
        "signal_models_A_F": {
            k: _finalize_bucket(v) for k, v in sorted(model_buckets.items())
        },
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
        "is_module_ready_pilot": is_module_ready_pilot,
        "preflight": data_quality,
        "warnings": shape_warnings,
    }

    summary = {
        "eligible_analysis": eligible_analysis,
        "excluded_diagnostics": excluded_diagnostics,
        "errors": errors_section,
        "data_coverage": data_coverage,
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
        _put_json("manifest.json", manifest)

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
                    "pilot_sample_role": _pilot_sample_role(s),
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
                    "purchasability_compatibility": s.purchasability_compatibility_json,
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
                yield json.dumps(row, ensure_ascii=False, default=str)

        def _iter_signal_models() -> Iterator[str]:
            for s in eligible_snaps:
                sigs = _as_dict(s.signals_json)
                for model_key, mblock in (_as_dict(sigs.get("models"))).items():
                    mb = _as_dict(mblock)
                    canon = _canonical_signal_model_fields(str(model_key))
                    for sett in _as_list(mb.get("settlements")):
                        if not isinstance(sett, dict):
                            continue
                        yield json.dumps(
                            {
                                "run_id": int(run.id),
                                "lab_match_id": int(s.lab_match_id),
                                "competition_name": s.competition_name,
                                "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                                **canon,
                                "signal_family": sett.get("signal_family"),
                                "source_column": sett.get("source_column"),
                                "target_market": sett.get("target_market"),
                                "quota_cecchino": sett.get("quota_cecchino"),
                                "probabilita_cecchino": sett.get("probabilita_cecchino"),
                                "quota_bet365": sett.get("quota_bet365"),
                                "quote_quality": sett.get("quote_quality"),
                                "won": sett.get("won"),
                                "real_profit_1u": sett.get("real_profit_1u"),
                                "synthetic_profit_1u": sett.get("synthetic_profit_1u"),
                            },
                            ensure_ascii=False,
                            default=str,
                        )

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

        def _iter_purch_full() -> Iterator[str]:
            for s in eligible_snaps:
                purch = _as_dict(s.purchasability_compatibility_json)
                bal = _as_dict(s.balance_v5_json)
                bal_class, _ = _structural_class(bal.get("structural_summary") if bal else None)
                m_by_key = {m.market_key: m for m in markets_by_snap.get(int(s.id), [])}
                for mk_row in purch.get("markets") or []:
                    if not isinstance(mk_row, dict):
                        continue
                    mk = mk_row.get("market_key")
                    m = m_by_key.get(mk)
                    yield json.dumps(
                        {
                            "run_id": int(run.id),
                            "lab_match_id": int(s.lab_match_id),
                            "competition_name": s.competition_name,
                            "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                            "market_key": mk,
                            "score": mk_row.get("score"),
                            "class": mk_row.get("class"),
                            "status": mk_row.get("status"),
                            "phase_1": mk_row.get("phase_1"),
                            "phase_2": mk_row.get("phase_2"),
                            "components": mk_row.get("components"),
                            "quote_quality": mk_row.get("quote_quality"),
                            "normalization_profile_version": mk_row.get(
                                "normalization_profile_version"
                            ),
                            "normalization_profile_hash": mk_row.get(
                                "normalization_profile_hash"
                            ),
                            "normalization_sample_size": mk_row.get(
                                "normalization_sample_size"
                            ),
                            "rating": mk_row.get("rating"),
                            "edge_pct": mk_row.get("edge_pct"),
                            "vantaggio_prob": mk_row.get("vantaggio_prob"),
                            "signal_active": bool(m.signal_active) if m else None,
                            "balance_class": bal_class,
                            "won": m.won if m else None,
                            "real_profit_1u": (
                                float(m.profit_1u_real)
                                if m and m.profit_1u_real is not None
                                else None
                            ),
                            "synthetic_profit_1u": (
                                float(m.profit_1u_synthetic)
                                if m and m.profit_1u_synthetic is not None
                                else None
                            ),
                            "parity_status": mk_row.get("parity_status"),
                            "formula_version": mk_row.get("formula_version"),
                        },
                        ensure_ascii=False,
                        default=str,
                    )

        def _iter_purch_compact() -> Iterator[str]:
            for s in eligible_snaps:
                for row in _purchasability_compact_rows(s, markets_by_snap):
                    yield json.dumps(row, ensure_ascii=False, default=str)

        def _iter_balance() -> Iterator[str]:
            for s in eligible_snaps:
                yield json.dumps(
                    {
                        "lab_match_id": int(s.lab_match_id),
                        "competition_name": s.competition_name,
                        "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                        "balance_v5": s.balance_v5_json,
                        "pilot_sample_role": _pilot_sample_role(s),
                    },
                    ensure_ascii=False,
                    default=str,
                )

        if mode_norm == "full_archive":
            line_counts["matches.jsonl"] = _write_jsonl_to_zip(zf, "matches.jsonl", _iter_matches_full())
            line_counts["markets.jsonl"] = _write_jsonl_to_zip(zf, "markets.jsonl", _iter_markets())
            line_counts["signal_models.jsonl"] = _write_jsonl_to_zip(
                zf, "signal_models.jsonl", _iter_signal_models()
            )
            line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                zf, "goal_intensity.jsonl", _iter_goal_intensity()
            )
            line_counts["purchasability.jsonl"] = _write_jsonl_to_zip(
                zf, "purchasability.jsonl", _iter_purch_full()
            )
        elif mode_norm == "competition":
            line_counts["matches_compact.jsonl"] = _write_jsonl_to_zip(
                zf, "matches_compact.jsonl", _iter_matches_compact()
            )
            line_counts["markets.jsonl"] = _write_jsonl_to_zip(zf, "markets.jsonl", _iter_markets())
            line_counts["signal_models.jsonl"] = _write_jsonl_to_zip(
                zf, "signal_models.jsonl", _iter_signal_models()
            )
            line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                zf, "goal_intensity.jsonl", _iter_goal_intensity()
            )
            line_counts["purchasability_compact.jsonl"] = _write_jsonl_to_zip(
                zf, "purchasability_compact.jsonl", _iter_purch_compact()
            )
        elif mode_norm == "module":
            if module_norm == "markets":
                line_counts["markets.jsonl"] = _write_jsonl_to_zip(
                    zf, "markets.jsonl", _iter_markets()
                )
            elif module_norm == "signals":
                line_counts["signal_models.jsonl"] = _write_jsonl_to_zip(
                    zf, "signal_models.jsonl", _iter_signal_models()
                )
            elif module_norm == "goal_intensity":
                line_counts["goal_intensity.jsonl"] = _write_jsonl_to_zip(
                    zf, "goal_intensity.jsonl", _iter_goal_intensity()
                )
            elif module_norm == "purchasability":
                line_counts["purchasability.jsonl"] = _write_jsonl_to_zip(
                    zf, "purchasability.jsonl", _iter_purch_full()
                )
                line_counts["purchasability_compact.jsonl"] = _write_jsonl_to_zip(
                    zf, "purchasability_compact.jsonl", _iter_purch_compact()
                )
            elif module_norm == "balance":
                line_counts["balance.jsonl"] = _write_jsonl_to_zip(
                    zf, "balance.jsonl", _iter_balance()
                )

        # report_index con conteggi finali (scritto una sola volta)
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

    dest.seek(0, os.SEEK_END)
    size = int(dest.tell())
    if mode_norm == "ai_summary" and size > AI_SUMMARY_WARN_BYTES:
        logger.warning(
            "ai_summary report larger than expected run_id=%s bytes=%s",
            run.id,
            size,
        )
    return filename, size


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
    *,
    shape_warnings: list[str] | None = None,
    shape_warning_seen: set[str] | None = None,
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    warnings = shape_warnings if shape_warnings is not None else []
    seen = shape_warning_seen if shape_warning_seen is not None else set()

    def key_id(prefix: str, parts: list[str]) -> str:
        return prefix + "__" + "__".join(parts)

    for m in eligible_markets:
        s = snap_by_id.get(int(m.match_snapshot_id))
        comp = s.competition_name if s else "unknown"
        rb = _rating_band(m.rating) or "no_rating"
        sig = _signal_meta(m.signal_sources_json)
        fam = str(sig.get("signal_family") or ("active" if m.signal_active else "no_signal"))
        signal_flag = "signal_on" if m.signal_active else "signal_off"
        bal = _as_dict(s.balance_v5_json) if s else {}
        bal_class, warn = _structural_class(bal.get("structural_summary") if bal else None)
        _note_shape_warning(warnings, warn, seen=seen)

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
                },
                [comp or "unknown", m.market_key, signal_flag],
            ),
        ]

        purch = _as_dict(s.purchasability_compatibility_json) if s else {}
        purch_score = None
        for mk_row in purch.get("markets") or []:
            if isinstance(mk_row, dict) and mk_row.get("market_key") == m.market_key:
                purch_score = mk_row.get("score")
                break
        purch_band = "no_purch"
        if purch_score is not None:
            try:
                ps = float(purch_score)
                purch_band = (
                    "0-19"
                    if ps < 20
                    else (
                        "20-39"
                        if ps < 40
                        else ("40-59" if ps < 60 else ("60-79" if ps < 80 else "80-100"))
                    )
                )
            except (TypeError, ValueError):
                purch_band = "no_purch"

        gi = _as_dict(s.goal_intensity_compatibility_json) if s else {}
        gi_pillars = _as_dict(gi.get("pillars"))
        op_class = _as_dict(gi_pillars.get("offensive_production")).get("class_key") or "no_gi"

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
