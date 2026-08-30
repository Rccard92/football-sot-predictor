"""AI Summary v5 — sintesi Compact per ChatGPT basata su Pattern Lab + V3.6.

Schema dedicato: AI_SUMMARY_SCHEMA_VERSION (non confondere con legacy v4).
Nessun ricalcolo engine: solo projection/filtri/aggregazioni Pattern Lab + registry preset.
"""

from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.models import CecchinoLabHistoricalScanRun
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_DERIVATION_METHOD,
    HISTORICAL_KPI_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION,
    HISTORICAL_SCAN_VERSION,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.pattern_lab_aggregations import _purch_band, _rating_band
from app.services.cecchino_data_lab.pattern_lab_constants import PATTERN_LAB_VERSION
from app.services.cecchino_data_lab.pattern_lab_filters import (
    GOAL_PILLAR_KEYS,
    market_informative_reasons,
    parse_pattern_lab_filters,
    row_passes_filters,
    v36_informative,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PATTERN_LAB_PRESETS,
    PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    PRESET_REGISTRY_VERSION,
    preset_scientific_filters,
)
from app.services.cecchino_data_lab.pattern_lab_preset_metrics import (
    _bump_pattern,
    _bump_real,
    _empty_econ,
    _finalize_econ,
    _month_key,
    _preset_meta_export,
    _quarter_key,
)
from app.services.cecchino_data_lab.pattern_lab_service import (
    count_eligible_market_rows,
    iter_pattern_lab_rows,
)
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision
from app.services.cecchino_data_lab.errors import CecchinoLabImportError

AI_SUMMARY_SCHEMA_VERSION = "cecchino_lab_ai_report_v5"

BALANCE_PILLAR_KEYS = ("f36", "dominance", "draw_credibility", "gap_coherence")

README_FOR_AI_MD = """# README per AI — Cecchino Lab AI Summary v5

## Principi scientifici

1. **Separa discovery da validation.** Non dichiarare un pattern definitivo su una sola stagione.
2. **P01–P05** sono preset precedenti con risultati OOS già osservati (vedi `status` + `validation_history`). Non chiamarli semplicemente «confermati» senza contesto.
3. **P06–P12** sono pattern scoperti usando 2021/22–2023/24. **NON sono validati.** La prima vera OOS sarà 2024/25 (`candidate_oos_2024_25`). Registry congelato: `pattern_lab_presets_v3` (P01–P12).
4. **È vietato modificare P06–P12** dopo aver osservato 2024/25. Una variante futura deve ottenere un nuovo ID/versione. Verifica `scientific_filters_sha256`.
5. **P12** è un *low-sample refinement candidate — first OOS 2024/25*: refinement di P03 (`flags.derived_from=P03`) con `match_tempo=high`. **NON sostituisce né modifica P03.** Sample piccolo (`flags.low_sample`); non presentarlo come primario rispetto a P03.
6. **Non ottimizzare nuove soglie** usando la stagione di validazione/OOS.
7. **Quote derivate** non devono essere usate per dichiarazioni di ROI reale. Usa `real_quote_count`, `profit_1u`, `roi` solo dove `performance_quote_policy=real_only`.
8. **Balance V5** e **Goal V4-compat** nel report storico sono snapshot V4-compatible, **non** l'engine live futuro.
9. **V3.6** (`purchasability_v36_summary.json`) è l'indice di acquistabilità **canonico corrente** nel Pattern Lab / Historical Scan V4.
10. Il download `module=purchasability` resta lo ZIP **V3 replay legacy** (diagnostico/compatibilità); non confonderlo con V3.6.
11. I `filters` dei preset sono la formula scientifica; `performance_quote_policy=real_only` è solo per le metriche economiche (`selections` ≠ `real_quote_count`).
12. I preset falliti OOS restano nel registro scientifico: non nasconderli.
13. P10 è longshot/high_variance: non presentarlo come «migliore» solo per ROI elevato.
14. Non inventare capture fisica delle quote: vedi provenance in `purchasability_v36_summary.json` (`synthetic_timestamp=true`, `does_not_claim_physical_capture=true`).
"""

AI_INSTRUCTIONS_V5_MD = """# Istruzioni per ChatGPT — Report storico Cecchino Lab (AI Summary v5)

1. Leggi `README_FOR_AI.md`, `manifest.json` e `SCHEMA.md` prima di analizzare i JSON.
2. Distingui `scan_source_git_commit_recorded` / `scan_source_git_commit` (snapshot congelati immutabili) da `report_generator_git_commit` (codice che genera il report). Se `report_generator_revision_conflict=true`, le fonti env discordanti sono in `report_generator_revision_conflict_sources`.
3. Universo performance: `eligible_core`. Non mescolare excluded/errors con la performance.
4. **Pattern Lab**: usa `pattern_lab_summary.json` per mercati storici vs `market_informative` e i motivi (KPI / Signals / V3.6).
5. **Acquistabilità corrente = V3.6** in `purchasability_v36_summary.json` (stessa projection del Pattern Lab). Non trattare il replay V3 come indice corrente.
6. Il menu/download `module=purchasability` è **legacy V3 replay** (diagnostico). Non usarlo come sostituto di V3.6.
7. **Preset P01–P12** in `preset_patterns_summary.json`: filtri scientifici congelati (`pattern_lab_presets_v3`); ROI/profit/avg odds **solo** su `real_quote_count` (`performance_quote_policy=real_only`). Controlla `scientific_filters_sha256`.
8. P01–P05 = OOS già osservati (`validation_history`). P06–P12 = candidati 2024/25, **non validati**. Non dichiarare P06–P12 validati.
9. **P12** = low-sample refinement candidate — first OOS 2024/25 (`derived_from=P03`). Non sostituisce P03; non presentarlo come primario.
10. Non ottimizzare soglie sulla stagione di validation/OOS. Vietato ritoccare P06–P12 dopo 2024/25 (nuovo ID).
11. Quote **reali Bet365**, **derivate** e **unavailable** restano separate. Mai mescolare derivate nei KPI economici reali.
12. Balance/Goal: campi storici V4-compatible; non sono l'engine live.
13. Provenance quote V3.6: epoch sintetico di riferimento pre-closing — **non** claim di capture fisica a kickoff-24h.
14. Report compatto: niente dataset Pattern Discovery completo / JSONL partita-per-partita.
15. Confronta fasce e mercati in modo market-specific.
16. Non modificare pesi o formule basandoti su una sola stagione.
"""

SCHEMA_V5_MD = """# Schema AI Summary Cecchino Lab (v5)

- `report_schema_version` = `cecchino_lab_ai_report_v5` (solo mode=`ai_summary`)
- Altri mode report (`competition` / `module` / `full_archive`) usano ancora `cecchino_lab_ai_report_v4` (legacy)
- File primari: `manifest.json`, `run_summary.json`, `pattern_lab_summary.json`, `kpi_summary.json`, `signals_summary.json`, `balance_v5_summary.json`, `goal_v4_compat_summary.json`, `purchasability_v36_summary.json`, `preset_patterns_summary.json`, `README_FOR_AI.md`, `AI_INSTRUCTIONS.md`, `SCHEMA.md`
- Acquistabilità **canonica corrente**: V3.6 (Pattern Lab projection). V3 replay = legacy diagnostic via endpoint dedicato
- Preset P01–P12 (`pattern_lab_presets_v3`): `filters` = pattern; `scientific_filters_sha256` = fingerprint; `validation_history` = storico OOS; `performance_quote_policy=real_only` = metriche economiche
- P12 = low-sample refinement candidate — first OOS 2024/25 (`flags.derived_from=P03`; non sostituisce P03)
- `status_group` è derivato da `status` (non canonico nel registry)
- Provenance: `scan_source_git_commit_recorded` (immutabile) vs `report_generator_git_commit*` (+ eventuale `revision_conflict`)
- `market_informative` = KPI (≥30 + value) OR Signals OR V3.6 score
"""


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _is_real(row: dict[str, Any]) -> bool:
    return row.get("pre_quote_type") == "real" or row.get("pre_is_real_book_quote") is True


def _econ_from_row(row: dict[str, Any]) -> dict[str, float | int | None]:
    """Metriche economiche real-only per una riga (0 se non real)."""
    if not _is_real(row):
        return {"real_n": 0, "wins": 0, "losses": 0, "void": 0, "profit": 0.0, "quota": None}
    profit = row.get("target_profit_1u_real")
    if profit is None:
        profit = row.get("target_profit_1u")
    return {
        "real_n": 1,
        "wins": 1 if row.get("target_won") is True else 0,
        "losses": 1 if row.get("target_lost") is True else 0,
        "void": 1 if row.get("target_void") is True else 0,
        "profit": float(profit) if profit is not None else 0.0,
        "quota": float(row["pre_quota_bet365"]) if row.get("pre_quota_bet365") is not None else None,
    }


def _finalize_market_bucket(b: dict[str, Any]) -> dict[str, Any]:
    real_n = int(b["real_n"])
    decided = int(b["wins"]) + int(b["losses"])
    return {
        "selections": int(b["n"]),
        "real_quote_count": real_n,
        "sample": int(b["n"]),
        "wins": int(b["wins"]),
        "losses": int(b["losses"]),
        "void": int(b["void"]),
        "win_rate": (float(b["wins"]) / decided) if decided else None,
        "avg_real_odds": (b["quota_sum"] / b["quota_n"]) if b["quota_n"] else None,
        "profit_1u_real": float(b["profit"]),
        "roi_real": (float(b["profit"]) / real_n) if real_n else None,
        "avg_rating": (b["rating_sum"] / b["rating_n"]) if b["rating_n"] else None,
        "avg_edge_pct": (b["edge_sum"] / b["edge_n"]) if b["edge_n"] else None,
        "avg_score_acquisto": (b["acq_sum"] / b["acq_n"]) if b["acq_n"] else None,
        "value_positive_count": int(b["value_true"]),
        "value_negative_count": int(b["value_false"]),
        "rating_coverage": int(b["rating_n"]),
        "rating_bands": dict(b["rating_bands"]),
    }


def _empty_mkt() -> dict[str, Any]:
    return {
        "n": 0,
        "real_n": 0,
        "wins": 0,
        "losses": 0,
        "void": 0,
        "profit": 0.0,
        "quota_sum": 0.0,
        "quota_n": 0,
        "rating_sum": 0.0,
        "rating_n": 0,
        "edge_sum": 0.0,
        "edge_n": 0,
        "acq_sum": 0.0,
        "acq_n": 0,
        "value_true": 0,
        "value_false": 0,
        "rating_bands": defaultdict(int),
    }


def _bump_mkt(b: dict[str, Any], row: dict[str, Any]) -> None:
    b["n"] += 1
    econ = _econ_from_row(row)
    b["real_n"] += int(econ["real_n"])
    b["wins"] += int(econ["wins"])
    b["losses"] += int(econ["losses"])
    b["void"] += int(econ["void"])
    b["profit"] += float(econ["profit"] or 0)
    if econ["quota"] is not None:
        b["quota_sum"] += float(econ["quota"])
        b["quota_n"] += 1
    if row.get("pre_rating") is not None:
        b["rating_sum"] += float(row["pre_rating"])
        b["rating_n"] += 1
    if row.get("pre_edge_pct") is not None:
        b["edge_sum"] += float(row["pre_edge_pct"])
        b["edge_n"] += 1
    if row.get("pre_score_acquisto") is not None:
        b["acq_sum"] += float(row["pre_score_acquisto"])
        b["acq_n"] += 1
    if row.get("pre_value_positive") is True:
        b["value_true"] += 1
    elif row.get("pre_value_positive") is False:
        b["value_false"] += 1
    b["rating_bands"][_rating_band(row.get("pre_rating"))] += 1


def write_ai_summary_v5_zip(
    db: Session,
    run_id: int,
    dest: BinaryIO,
) -> tuple[str, int]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    policy = dict(getattr(run, "module_policy_json", None) or {}) if getattr(run, "module_policy_json", None) else {}
    is_partial = bool(policy.get("is_partial_run"))
    run_scope = policy.get("run_scope") or ("pilot" if is_partial else "full")
    season_slug = str(getattr(run, "season_label", None) or "season").replace("/", "_")
    scope_tag = "pilot" if is_partial else "full"
    filename = f"cecchino_lab_{season_slug}_{scope_tag}_ai_summary_run_{run_id}.zip"

    run_ids = [int(run_id)]
    historical_total = count_eligible_market_rows(
        db, run_ids, eligibility=ELIGIBLE_CORE
    )

    # --- accumulatori ---
    informative_n = 0
    reason_counts: dict[str, int] = defaultdict(int)  # kpi, signals, v36, combinations
    combo_counts: dict[str, int] = defaultdict(int)
    match_ids: set[tuple[int, int]] = set()
    quote_cov = {"real": 0, "derived": 0, "unavailable": 0}

    kpi_by_market: dict[str, dict[str, Any]] = {}
    sig = {
        "active": 0,
        "count_hist": defaultdict(int),
        "consensus": defaultdict(int),
        "excel": {"D": 0, "E": 0, "F": 0, "G": 0},
        "by_market": {},
    }
    bal = {
        "class_hist": defaultdict(int),
        "geometry_sum": 0.0,
        "geometry_n": 0,
        "pillars": {k: defaultdict(int) for k in BALANCE_PILLAR_KEYS},
        "by_market": {},
    }
    goal = {
        "final_class": defaultdict(int),
        "direction": defaultdict(int),
        "composite_sum": 0.0,
        "composite_n": 0,
        "pillars": {k: defaultdict(int) for k in GOAL_PILLAR_KEYS},
        "by_market": {},
    }
    v36 = {
        "score_n": 0,
        "score_sum": 0.0,
        "status": defaultdict(int),
        "gate": defaultdict(int),
        "class": defaultdict(int),
        "bands": defaultdict(int),
        "value_core_sum": 0.0,
        "value_core_n": 0,
        "acq_core_sum": 0.0,
        "acq_core_n": 0,
        "struct_sum": 0.0,
        "struct_n": 0,
        "qual_sum": 0.0,
        "qual_n": 0,
        "by_market": {},
        "by_band_perf": {},
    }

    parsed_presets = [
        (p, parse_pattern_lab_filters(preset_scientific_filters(p)))
        for p in PATTERN_LAB_PRESETS
    ]
    preset_totals = {p["id"]: _empty_econ() for p, _ in parsed_presets}
    preset_by_comp: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }
    preset_by_month: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }
    preset_by_quarter: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }
    preset_by_season: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }

    base = parse_pattern_lab_filters(
        {"eligibility": ELIGIBLE_CORE, "market_informative": False}
    )

    for row in iter_pattern_lab_rows(db, run_ids, filters=base, apply_filters=True):
        qtype = row.get("pre_quote_type")
        if qtype == "real":
            quote_cov["real"] += 1
        elif qtype == "derived":
            quote_cov["derived"] += 1
        else:
            quote_cov["unavailable"] += 1

        reasons = market_informative_reasons(row)
        if reasons:
            informative_n += 1
            for r in reasons:
                reason_counts[r] += 1
            combo_key = "+".join(sorted(reasons))
            combo_counts[combo_key] += 1

        rid = row.get("run_id")
        mid = row.get("lab_match_id")
        if rid is not None and mid is not None:
            match_ids.add((int(rid), int(mid)))

        market = str(row.get("market_key") or "unknown")
        if market not in kpi_by_market:
            kpi_by_market[market] = _empty_mkt()
        _bump_mkt(kpi_by_market[market], row)

        # signals
        if row.get("pre_signal_active") is True:
            sig["active"] += 1
        sig["count_hist"][str(int(row.get("pre_signal_count") or 0))] += 1
        cs = row.get("pre_consensus_status")
        if cs:
            sig["consensus"][str(cs)] += 1
        for col in ("d", "e", "f", "g"):
            if row.get(f"pre_signal_excel_{col}") is True:
                sig["excel"][col.upper()] += 1
        if market not in sig["by_market"]:
            sig["by_market"][market] = _empty_mkt()
        if row.get("pre_signal_active") is True or int(row.get("pre_signal_count") or 0) > 0:
            _bump_mkt(sig["by_market"][market], row)

        # balance
        bc = row.get("pre_balance_structural_class")
        if bc:
            bal["class_hist"][str(bc)] += 1
        geom = row.get("pre_balance_geometry")
        if geom is not None:
            bal["geometry_sum"] += float(geom)
            bal["geometry_n"] += 1
        for pk in BALANCE_PILLAR_KEYS:
            klass = row.get(f"pre_balance_{pk}_class")
            if klass:
                bal["pillars"][pk][str(klass)] += 1
        if market not in bal["by_market"]:
            bal["by_market"][market] = _empty_mkt()
        _bump_mkt(bal["by_market"][market], row)

        # goal
        gfc = row.get("pre_goal_v4_compat_final_class")
        if gfc:
            goal["final_class"][str(gfc)] += 1
        gdir = row.get("pre_goal_v4_compat_direction")
        if gdir:
            goal["direction"][str(gdir)] += 1
        gcomp = row.get("pre_goal_v4_compat_composite")
        if gcomp is not None:
            goal["composite_sum"] += float(gcomp)
            goal["composite_n"] += 1
        for pk in GOAL_PILLAR_KEYS:
            klass = row.get(f"pre_goal_v4_compat_{pk}_class")
            if klass:
                goal["pillars"][pk][str(klass)] += 1
        if market not in goal["by_market"]:
            goal["by_market"][market] = _empty_mkt()
        _bump_mkt(goal["by_market"][market], row)

        # v36
        st = row.get("pre_purch_v36_status")
        if st:
            v36["status"][str(st)] += 1
        gt = row.get("pre_purch_v36_gate_status")
        if gt:
            v36["gate"][str(gt)] += 1
        if v36_informative(row):
            v36["score_n"] += 1
            v36["score_sum"] += float(row["pre_purch_v36_score"])
            band = _purch_band(row.get("pre_purch_v36_score"))
            v36["bands"][band] += 1
            if row.get("pre_purch_v36_class"):
                v36["class"][str(row["pre_purch_v36_class"])] += 1
            if market not in v36["by_market"]:
                v36["by_market"][market] = _empty_mkt()
            _bump_mkt(v36["by_market"][market], row)
            if band not in v36["by_band_perf"]:
                v36["by_band_perf"][band] = _empty_mkt()
            _bump_mkt(v36["by_band_perf"][band], row)
        for key, field in (
            ("value_core", "pre_purch_v36_value_core"),
            ("acq_core", "pre_purch_v36_acquisition_core"),
            ("struct", "pre_purch_v36_structural_factor"),
            ("qual", "pre_purch_v36_quality_factor"),
        ):
            val = row.get(field)
            if val is not None:
                if key == "value_core":
                    v36["value_core_sum"] += float(val)
                    v36["value_core_n"] += 1
                elif key == "acq_core":
                    v36["acq_core_sum"] += float(val)
                    v36["acq_core_n"] += 1
                elif key == "struct":
                    v36["struct_sum"] += float(val)
                    v36["struct_n"] += 1
                else:
                    v36["qual_sum"] += float(val)
                    v36["qual_n"] += 1

        # presets (solo su informative? i filtri preset includono market_informative=true)
        for preset, filt in parsed_presets:
            if not row_passes_filters(row, filt):
                continue
            pid = preset["id"]
            _bump_pattern(preset_totals[pid], row)
            _bump_real(preset_totals[pid], row)
            for store, key in (
                (preset_by_comp[pid], str(row.get("competition") or "unknown")),
                (preset_by_month[pid], _month_key(row)),
                (preset_by_quarter[pid], _quarter_key(row)),
                (preset_by_season[pid], str(row.get("season") or "unknown")),
            ):
                if key not in store:
                    store[key] = _empty_econ()
                _bump_pattern(store[key], row)
                _bump_real(store[key], row)

    reduction_pct = None
    if historical_total:
        reduction_pct = round(100.0 * (1.0 - informative_n / historical_total), 2)

    # Run-level counts from DB
    matches_total = int(getattr(run, "matches_total", 0) or 0)
    eligible_core = int(getattr(run, "matches_eligible_core", 0) or 0)
    if not matches_total:
        matches_total = len(match_ids)
    if not eligible_core:
        eligible_core = len(match_ids)

    errors_count = int(getattr(run, "matches_error", 0) or 0)
    excl_reasons: dict[str, int] = {}
    summary_json = getattr(run, "summary_json", None)
    if isinstance(summary_json, dict):
        excl = (
            summary_json.get("eligibility_by_reason")
            or summary_json.get("exclusions_by_reason")
            or summary_json.get("exclusions")
        )
        if isinstance(excl, dict):
            excl_reasons = {
                str(k): int(v) for k, v in excl.items() if isinstance(v, (int, float))
            }

    generator_rev = resolve_code_revision()
    quote_pol = dict(getattr(run, "quote_policy_json", None) or {}) if getattr(run, "quote_policy_json", None) else {}
    scan_commit = getattr(run, "source_git_commit", None)
    scan_source = getattr(run, "source_git_commit_source", None)
    scan_status = getattr(run, "source_revision_status", None)

    manifest = {
        "report_schema_version": AI_SUMMARY_SCHEMA_VERSION,
        "report_mode": "ai_summary",
        "run_id": int(run.id),
        "season": getattr(run, "season_label", None),
        "season_label": getattr(run, "season_label", None),
        "run_scope": run_scope,
        "is_partial_run": is_partial,
        "scan_version": getattr(run, "scan_version", None) or HISTORICAL_SCAN_VERSION,
        # Scan commit congelato sul run (immutabile) — alias legacy + recorded
        "scan_source_git_commit": scan_commit,
        "scan_source_git_commit_recorded": scan_commit,
        "scan_source_git_commit_source": scan_source,
        "scan_source_revision_status": scan_status,
        # Generatore report a runtime
        "report_generator_git_commit": generator_rev.get("git_commit"),
        "report_generator_git_commit_source": generator_rev.get("git_commit_source"),
        "report_generator_revision_status": generator_rev.get("revision_status"),
        "report_generator_revision_conflict": bool(
            generator_rev.get("revision_conflict")
        ),
        "report_generator_revision_conflict_sources": generator_rev.get(
            "revision_conflict_sources"
        ),
        "quote_policy": quote_pol.get("version") or HISTORICAL_QUOTE_POLICY_VERSION,
        "quote_reference_timing": quote_pol.get("reference_timing"),
        "derivation_policy": HISTORICAL_DERIVATION_METHOD,
        "feature_contract": {
            "pattern_lab_version": PATTERN_LAB_VERSION,
            "preset_registry_version": PRESET_REGISTRY_VERSION,
            "market_informative": "kpi_or_signals_or_v36",
            "performance_quote_policy_presets": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
            "purchasability_canonical": "v36_pattern_lab_projection",
            "purchasability_legacy_download": "module=purchasability → V3 replay ZIP",
        },
        "module_versions": {
            "kpi": HISTORICAL_KPI_VERSION,
            "pattern_lab": PATTERN_LAB_VERSION,
            "balance": "balance_v5_historical_snapshot",
            "goal": "goal_v4_compat_historical",
            "purchasability_canonical": "v36_from_purchasability_compatibility_json",
            "purchasability_legacy": "replay_v3",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "performance_universe": "eligible_core",
        "limitations": [
            "AI Summary v5 riusa Pattern Lab projection; non ricalcola engine",
            "Balance/Goal = V4-compatible storico, non engine live",
            "V3.6 epoch sintetico: non claim di capture fisica kickoff-24h",
            "module=purchasability resta legacy V3 replay",
        ],
    }

    run_summary = {
        "matches_total": matches_total,
        "eligible_core": eligible_core,
        "exclusions_by_reason": excl_reasons,
        "errors": errors_count,
        "market_rows_total": historical_total,
        "performance_profile": {
            "universe": "eligible_core",
            "economic_metrics": "real_bet365_only",
        },
        "quote_coverage": {
            "real": quote_cov["real"],
            "derived": quote_cov["derived"],
            "unavailable": quote_cov["unavailable"],
            "total": historical_total,
            "reconciliation_ok": (
                quote_cov["real"] + quote_cov["derived"] + quote_cov["unavailable"]
                == historical_total
            ),
        },
    }

    pattern_lab_summary = {
        "historical_market_rows": historical_total,
        "market_informative": informative_n,
        "reduction_pct": reduction_pct,
        "distinct_matches": len(match_ids),
        "informative_reason_counts": dict(reason_counts),
        "informative_reason_combinations": dict(sorted(combo_counts.items())),
        "definition": {
            "kpi": "rating>=30 AND value_positive",
            "signals": "signal_active OR signal_count>0",
            "v36": "status=score AND score present",
            "market_informative": "kpi OR signals OR v36",
        },
    }

    kpi_summary = {
        "by_market": {
            k: _finalize_market_bucket(v) for k, v in sorted(kpi_by_market.items())
        },
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "note": "ROI/profit/avg odds solo su quote Bet365 reali",
    }

    signals_summary = {
        "signal_active_count": sig["active"],
        "signal_active_rate": (sig["active"] / historical_total) if historical_total else None,
        "count_distribution": dict(sig["count_hist"]),
        "consensus_distribution": dict(sig["consensus"]),
        "excel_column_frequency": dict(sig["excel"]),
        "performance_by_market_when_signal_present": {
            k: _finalize_market_bucket(v) for k, v in sorted(sig["by_market"].items())
        },
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    }

    balance_v5_summary = {
        "structural_class_distribution": dict(bal["class_hist"]),
        "avg_geometry": (
            bal["geometry_sum"] / bal["geometry_n"] if bal["geometry_n"] else None
        ),
        "geometry_sample_n": bal["geometry_n"],
        "pillars": {k: dict(v) for k, v in bal["pillars"].items()},
        "performance_by_market": {
            k: _finalize_market_bucket(v) for k, v in sorted(bal["by_market"].items())
        },
        "note": "Balance V5 snapshot storico; non engine live",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    }

    goal_v4_compat_summary = {
        "final_class_distribution": dict(goal["final_class"]),
        "direction_distribution": dict(goal["direction"]),
        "avg_composite": (
            goal["composite_sum"] / goal["composite_n"] if goal["composite_n"] else None
        ),
        "composite_sample_n": goal["composite_n"],
        "pillars": {k: dict(v) for k, v in goal["pillars"].items()},
        "performance_by_market": {
            k: _finalize_market_bucket(v) for k, v in sorted(goal["by_market"].items())
        },
        "note": "Goal V4-compat storico; non engine live V5",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
    }

    purchasability_v36_summary = {
        "canonical": True,
        "coverage_score": v36["score_n"],
        "coverage_score_rate": (
            v36["score_n"] / historical_total if historical_total else None
        ),
        "avg_score": (
            v36["score_sum"] / v36["score_n"] if v36["score_n"] else None
        ),
        "status_distribution": dict(v36["status"]),
        "gate_status_distribution": dict(v36["gate"]),
        "class_distribution": dict(v36["class"]),
        "score_bands": dict(v36["bands"]),
        "avg_value_core": (
            v36["value_core_sum"] / v36["value_core_n"] if v36["value_core_n"] else None
        ),
        "avg_acquisition_core": (
            v36["acq_core_sum"] / v36["acq_core_n"] if v36["acq_core_n"] else None
        ),
        "avg_structural_factor": (
            v36["struct_sum"] / v36["struct_n"] if v36["struct_n"] else None
        ),
        "avg_quality_factor": (
            v36["qual_sum"] / v36["qual_n"] if v36["qual_n"] else None
        ),
        "performance_by_market": {
            k: _finalize_market_bucket(v) for k, v in sorted(v36["by_market"].items())
        },
        "performance_by_score_band": {
            k: _finalize_market_bucket(v) for k, v in sorted(v36["by_band_perf"].items())
        },
        "snapshot_provenance": {
            "synthetic_timestamp": True,
            "physical_capture_time_known": False,
            "does_not_claim_physical_capture": True,
            "quote_reference": "bet365_pre_reference_v1",
            "reference_timing": "pre_closing_reference",
            "source": "purchasability_compatibility_json via pattern_lab_projection",
        },
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "legacy_note": (
            "Il download module=purchasability resta ZIP V3 replay legacy; "
            "non è l'indice corrente."
        ),
    }

    preset_items = []
    for preset, _ in parsed_presets:
        pid = preset["id"]
        preset_items.append(
            {
                **_preset_meta_export(preset),
                **_finalize_econ(preset_totals[pid]),
                "by_competition": [
                    _finalize_econ(b, key=k)
                    for k, b in sorted(preset_by_comp[pid].items())
                ],
                "by_month": [
                    _finalize_econ(b, key=k)
                    for k, b in sorted(preset_by_month[pid].items())
                ],
                "by_quarter": [
                    _finalize_econ(b, key=k)
                    for k, b in sorted(preset_by_quarter[pid].items())
                ],
                "by_season": [
                    _finalize_econ(b, key=k)
                    for k, b in sorted(preset_by_season[pid].items())
                ],
            }
        )

    preset_patterns_summary = {
        "registry_version": PRESET_REGISTRY_VERSION,
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "note": (
            "filters = formula scientifica; selections = pattern; "
            "ROI/profit/avg_real_odds solo su real_quote_count"
        ),
        "presets": preset_items,
    }

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README_FOR_AI.md", README_FOR_AI_MD.encode("utf-8"))
        zf.writestr("AI_INSTRUCTIONS.md", AI_INSTRUCTIONS_V5_MD.encode("utf-8"))
        zf.writestr("SCHEMA.md", SCHEMA_V5_MD.encode("utf-8"))
        zf.writestr("manifest.json", _json_bytes(manifest))
        zf.writestr("run_summary.json", _json_bytes(run_summary))
        zf.writestr("pattern_lab_summary.json", _json_bytes(pattern_lab_summary))
        zf.writestr("kpi_summary.json", _json_bytes(kpi_summary))
        zf.writestr("signals_summary.json", _json_bytes(signals_summary))
        zf.writestr("balance_v5_summary.json", _json_bytes(balance_v5_summary))
        zf.writestr("goal_v4_compat_summary.json", _json_bytes(goal_v4_compat_summary))
        zf.writestr(
            "purchasability_v36_summary.json", _json_bytes(purchasability_v36_summary)
        )
        zf.writestr(
            "preset_patterns_summary.json", _json_bytes(preset_patterns_summary)
        )

    size = int(dest.tell())
    return filename, size
