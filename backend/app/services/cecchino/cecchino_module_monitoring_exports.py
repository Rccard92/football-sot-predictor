"""Overview + analysis-pack ZIP — Monitoraggio Moduli Cecchino Fase 1/3.

Assembla export esistenti senza modificare formule/candidate/gate.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_validation import (
    PURCHASABILITY_VALIDATION_VERSION,
    build_purchasability_validation_health,
    build_purchasability_validation_rows,
    export_purchasability_validation_csv,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    PURCHASABILITY_PROMOTION_POLICY_VERSION,
    build_purchasability_promotion_readiness,
    build_purchasability_validation_summary,
)

ModuleKey = Literal[
    "purchasability",
    "balance-v5",
    "goal-intensity-v5",
    "signals",
]

VALID_MODULE_KEYS: frozenset[str] = frozenset(
    {"purchasability", "balance-v5", "goal-intensity-v5", "signals"}
)

MONITORING_EXPORT_VERSION = "cecchino_module_monitoring_exports_v1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(payload: Any) -> bytes:
    safe = make_json_safe(payload)
    return json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False).encode(
        "utf-8"
    )


def _csv_bom(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fieldnames})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def build_purchasability_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    health = build_purchasability_validation_health(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    readiness = build_purchasability_promotion_readiness(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        bootstrap_iterations=50,
    )
    warnings: list[str] = []
    coverage = health.get("snapshot_persistence_coverage")
    if coverage is None and int(health.get("fixtures_with_kpi_panel") or 0) == 0:
        warnings.append("Nessuna fixture eleggibile con KPI panel nel periodo")
    elif int(health.get("result_settled_count") or 0) == 0:
        warnings.append("Coorte settled ancora vuota")
    return make_json_safe(
        {
            "module_key": "purchasability",
            "status": readiness.get("status") or "collecting_data",
            "version": PURCHASABILITY_CANDIDATE_VERSION,
            "coverage": coverage,
            "fixtures": health.get("fixtures_with_verified_pre_match_preview"),
            "settled": health.get("result_settled_count"),
            "last_snapshot_at": None,
            "next_review_at": readiness.get("prima_data_teorica_promozione"),
            "warnings": warnings,
        }
    )


def build_balance_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == int(competition_id))
    rows = list(db.scalars(q).all())
    with_balance = 0
    settled = 0
    for row in rows:
        out = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        if out.get("balance_v5") or out.get("balance_analysis"):
            with_balance += 1
        if row.score_fulltime_home is not None and row.score_fulltime_away is not None:
            settled += 1
    denom = len(rows)
    coverage = (with_balance / denom) if denom else None
    warnings = []
    if denom == 0:
        warnings.append("Nessuna fixture eleggibile nel periodo")
    warnings.append(
        "Monitoraggio descrittivo — validazione empirica avanzata in preparazione"
    )
    return make_json_safe(
        {
            "module_key": "balance-v5",
            "status": "official_monitored",
            "version": "cecchino_balance_v5_v2",
            "coverage": coverage,
            "fixtures": with_balance if denom else None,
            "settled": settled if denom else None,
            "last_snapshot_at": None,
            "next_review_at": None,
            "warnings": warnings,
        }
    )


def build_goal_intensity_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    # Soft overview: count fixtures; detailed preview via existing APIs in pack
    q = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        q = q.where(CecchinoTodayFixture.competition_id == int(competition_id))
    rows = list(db.scalars(q).all())
    settled = sum(
        1
        for r in rows
        if r.score_fulltime_home is not None and r.score_fulltime_away is not None
    )
    warnings = [
        "Preview research: metriche candidate/calibrazione nel pacchetto export",
    ]
    if not rows:
        warnings.insert(0, "Nessuna fixture eleggibile nel periodo")
    return make_json_safe(
        {
            "module_key": "goal-intensity-v5",
            "status": "preview_research",
            "version": "goal_intensity_v5_preview",
            "coverage": None,
            "fixtures": len(rows) if rows else None,
            "settled": settled if rows else None,
            "last_snapshot_at": None,
            "next_review_at": None,
            "warnings": warnings,
        }
    )


def build_signals_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    try:
        from app.services.cecchino.cecchino_signal_aggregation import (
            build_signals_summary,
        )

        summary = build_signals_summary(
            db,
            date_from=date_from,
            date_to=date_to,
        )
        overall = summary.get("overall") if isinstance(summary, dict) else {}
        overall = overall or {}
        settled = int(overall.get("won") or 0) + int(overall.get("lost") or 0)
        return make_json_safe(
            {
                "module_key": "signals",
                "status": "operational",
                "version": "signals_lab",
                "coverage": None,
                "fixtures": overall.get("fixtures"),
                "settled": settled or overall.get("activations"),
                "last_snapshot_at": None,
                "next_review_at": None,
                "warnings": [],
            }
        )
    except Exception as exc:
        return make_json_safe(
            {
                "module_key": "signals",
                "status": "operational",
                "version": "signals_lab",
                "coverage": None,
                "fixtures": None,
                "settled": None,
                "last_snapshot_at": None,
                "next_review_at": None,
                "warnings": [f"summary_unavailable:{type(exc).__name__}"],
            }
        )


def build_module_monitoring_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    modules = [
        build_purchasability_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_balance_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_goal_intensity_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_signals_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
    ]
    return make_json_safe(
        {
            "generated_at": _utcnow(),
            "version": MONITORING_EXPORT_VERSION,
            "modules": modules,
        }
    )


def _handoff_md(
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    status: str,
    metrics: dict[str, Any],
    warnings: list[str],
) -> str:
    questions = {
        "purchasability": [
            "Lo score ordina il residuale rispetto al Book?",
            "Phase 2 aggiunge valore rispetto a Phase 1?",
            "Quali score band sono problematiche?",
            "La persistenza degli snapshot è affidabile?",
        ],
        "balance-v5": [
            "I pilastri mostrano monotonicità empirica?",
            "Credibilità X distingue realmente le classi?",
            "Esistono drift o classi sovrarappresentate?",
            "Gap e Dominanza sono coerenti?",
        ],
        "goal-intensity-v5": [
            "Quale candidato è più stabile?",
            "La calibrazione è coerente?",
            "Quali target mostrano maggiore utilità?",
            "Il campione prospettico è sufficiente?",
        ],
        "signals": [
            "Quali segnali sono stabili?",
            "Quali modelli producono rendimento?",
            "Esistono drift temporali?",
            "Quali segnali dipendono da campioni piccoli?",
        ],
    }.get(module_key, [])
    lines = [
        f"# Modulo\n{module_key}",
        "\n# Obiettivo\nAudit approfondito del monitoraggio modulo Cecchino.",
        f"\n# Versione export\n{MONITORING_EXPORT_VERSION}",
        f"\n# Periodo\n{date_from.isoformat()} → {date_to.isoformat()}",
        f"\n# Competizione\n{competition_id if competition_id is not None else 'tutte'}",
        "\n# Dati inclusi\nhealth, summary, versions, filters, handoff; rows se richiesti.",
        "\n# Dati esclusi\ntoken, secret, header admin, payload sensibili.",
        f"\n# Stato monitoraggio\n{status}",
        "\n# Metriche principali\n```json\n"
        + json.dumps(make_json_safe(metrics), ensure_ascii=False, indent=2)
        + "\n```",
        "\n# Warning\n" + ("\n".join(f"- {w}" for w in warnings) or "- nessuno"),
        "\n# Domande consigliate per ChatGPT\n"
        + "\n".join(f"- {q}" for q in questions),
    ]
    return "\n".join(lines) + "\n"


def _readme_md(module_key: str) -> str:
    return (
        f"# SOT Monitor — {module_key}\n\n"
        "Pacchetto generato da Monitoraggio Moduli Cecchino (Fase 1/3).\n"
        "Apri `CHATGPT_HANDOFF.md` per il contesto e le domande di audit.\n"
        "I JSON sono strict (no NaN/Infinity). I CSV usano BOM UTF-8.\n"
    )


def analysis_pack_filename(
    module_key: str, date_from: date, date_to: date
) -> str:
    return f"SOT_MONITOR_{module_key}_{date_from.isoformat()}_{date_to.isoformat()}.zip"


def build_module_analysis_pack_zip(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    include_rows: bool = True,
    include_debug: bool = False,
) -> tuple[bytes, str]:
    if module_key not in VALID_MODULE_KEYS:
        raise ValueError("invalid_module_key")

    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "competition_id": competition_id,
        "market_key": market_key,
        "include_rows": include_rows,
        "include_debug": include_debug,
    }

    if module_key == "purchasability":
        health = build_purchasability_validation_health(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        summary = build_purchasability_validation_summary(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            bootstrap_iterations=50,
        )
        readiness = build_purchasability_promotion_readiness(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            bootstrap_iterations=50,
        )
        versions = {
            "validation": PURCHASABILITY_VALIDATION_VERSION,
            "policy": PURCHASABILITY_PROMOTION_POLICY_VERSION,
            "candidate": PURCHASABILITY_CANDIDATE_VERSION,
        }
        status = str(readiness.get("status") or "collecting_data")
        warnings = list(readiness.get("warnings") or [])
        metrics = summary.get("metrics") or {}
        gates = readiness.get("data_gates")
        files: dict[str, bytes] = {
            "health.json": _json_bytes(health),
            "summary.json": _json_bytes(summary),
            "gates.json": _json_bytes(gates),
            "readiness.json": _json_bytes(readiness),
            "warnings.json": _json_bytes({"warnings": warnings}),
            "distributions.csv": _csv_bom(
                list(summary.get("by_score_band") or []),
                [
                    "score_band",
                    "rows",
                    "fixtures",
                    "win_rate",
                    "roi_pct",
                    "realized_margin",
                    "average_phase_1",
                    "average_phase_2",
                ],
            ),
        }
        if include_rows:
            csv_text = export_purchasability_validation_csv(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                market_key=market_key,
            )
            files["rows.csv"] = ("\ufeff" + csv_text).encode("utf-8")
    elif module_key == "balance-v5":
        overview = build_balance_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        health = {"overview": overview, "note": "descriptive_monitoring_only"}
        summary = {
            "module": "balance-v5",
            "disclaimer": "Monitoraggio descrittivo — validazione empirica avanzata in preparazione",
            "overview": overview,
        }
        versions = {"balance": "cecchino_balance_v5_v2"}
        status = "official_monitored"
        warnings = list(overview.get("warnings") or [])
        metrics = {
            "fixtures": overview.get("fixtures"),
            "settled": overview.get("settled"),
            "coverage": overview.get("coverage"),
        }
        files = {
            "health.json": _json_bytes(health),
            "summary.json": _json_bytes(summary),
            "warnings.json": _json_bytes({"warnings": warnings}),
        }
    elif module_key == "goal-intensity-v5":
        overview = build_goal_intensity_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        summary = {
            "module": "goal-intensity-v5",
            "overview": overview,
            "export_kinds_available": [
                "preview_summary",
                "preview_snapshots",
                "preview_completed_results",
                "preview_candidate_monitoring",
                "preview_calibration",
                "preview_bundle_definition",
            ],
        }
        versions = {"goal_intensity": "goal_intensity_v5_preview"}
        status = "preview_research"
        warnings = list(overview.get("warnings") or [])
        metrics = {
            "fixtures": overview.get("fixtures"),
            "settled": overview.get("settled"),
        }
        files = {
            "health.json": _json_bytes({"overview": overview}),
            "summary.json": _json_bytes(summary),
            "warnings.json": _json_bytes({"warnings": warnings}),
        }
    else:
        overview = build_signals_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        try:
            from app.services.cecchino.cecchino_signal_aggregation import (
                build_signals_summary,
            )

            sig_summary = build_signals_summary(
                db,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception:
            sig_summary = {"status": "unavailable"}
        summary = {"module": "signals", "overview": overview, "signals": sig_summary}
        versions = {"signals": "signals_lab"}
        status = "operational"
        warnings = list(overview.get("warnings") or [])
        metrics = {
            "fixtures": overview.get("fixtures"),
            "settled": overview.get("settled"),
        }
        files = {
            "health.json": _json_bytes({"overview": overview}),
            "summary.json": _json_bytes(summary),
            "warnings.json": _json_bytes({"warnings": warnings}),
        }

    manifest = {
        "module_key": module_key,
        "generated_at": _utcnow(),
        "export_version": MONITORING_EXPORT_VERSION,
        "files": sorted(
            [
                "README_ANALISI.md",
                "CHATGPT_HANDOFF.md",
                "manifest.json",
                "versions.json",
                "filters.json",
                "data_dictionary.md",
                *files.keys(),
            ]
        ),
        "include_rows": include_rows,
        "include_debug": include_debug,
    }
    dictionary = (
        "# Data dictionary\n\n"
        "- health.json: indicatori di copertura/qualità\n"
        "- summary.json: metriche aggregate del modulo\n"
        "- readiness.json / gates.json: solo Acquistabilità\n"
        "- rows.csv: righe detail se include_rows=true\n"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README_ANALISI.md", _readme_md(module_key))
        zf.writestr(
            "CHATGPT_HANDOFF.md",
            _handoff_md(
                module_key=module_key,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                status=status,
                metrics=metrics,
                warnings=warnings,
            ),
        )
        zf.writestr("manifest.json", _json_bytes(manifest).decode("utf-8"))
        zf.writestr("versions.json", _json_bytes(versions).decode("utf-8"))
        zf.writestr("filters.json", _json_bytes(filters).decode("utf-8"))
        zf.writestr("data_dictionary.md", dictionary)
        for name, content in files.items():
            zf.writestr(name, content)

    return buf.getvalue(), analysis_pack_filename(module_key, date_from, date_to)


def build_module_summary_payload(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
) -> dict[str, Any]:
    if module_key not in VALID_MODULE_KEYS:
        raise ValueError("invalid_module_key")
    if module_key == "purchasability":
        return build_purchasability_validation_summary(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            bootstrap_iterations=50,
        )
    if module_key == "balance-v5":
        return {
            "overview": build_balance_module_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
        }
    if module_key == "goal-intensity-v5":
        return {
            "overview": build_goal_intensity_module_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
        }
    return {
        "overview": build_signals_module_overview(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
        )
    }
