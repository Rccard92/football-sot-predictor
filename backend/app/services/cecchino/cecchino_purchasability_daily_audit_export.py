"""Export batch giornaliero audit Acquistabilità — read-only, contract manifest v1."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_audit_export import (
    PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION,
    build_purchasability_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v31_snapshot import (
    index_purchasability_v31_snapshot_by_market,
)

DAILY_AUDIT_MANIFEST_CONTRACT_VERSION = "cecchino_purchasability_daily_audit_manifest_v1"

PURCHASABILITY_STATUS_SCORE = "score"
PURCHASABILITY_STATUS_SCORE_PROVISIONAL = "score_provisional"


def _score_or_none(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    return None if n != n else n


def is_active_v31_market(item: dict[str, Any] | None) -> bool:
    """Criterio PHASE 00 — identico al pannello Today frontend."""
    if not isinstance(item, dict):
        return False
    status = str(item.get("status") or "")
    if status not in (PURCHASABILITY_STATUS_SCORE, PURCHASABILITY_STATUS_SCORE_PROVISIONAL):
        return False
    score = item.get("score_v31")
    if score is None:
        score = item.get("score")
    return _score_or_none(score) is not None


def classify_fixture_opportunity(
    v31_snapshot: dict[str, Any] | None,
) -> tuple[bool, int, list[str]]:
    """Restituisce (has_opportunity, active_count, active_market_keys)."""
    by_market = index_purchasability_v31_snapshot_by_market(v31_snapshot)
    active_keys: list[str] = []
    for mk in PANEL_MARKET_KEYS:
        if is_active_v31_market(by_market.get(mk)):
            active_keys.append(mk)
    return bool(active_keys), len(active_keys), active_keys


def _fixture_has_audit_contract(row: CecchinoTodayFixture) -> bool:
    panel = row.kpi_panel_json
    if not isinstance(panel, dict):
        return False
    rows = panel.get("rows")
    return isinstance(rows, list) and len(rows) > 0


def _load_eligible_fixtures(db: Session, *, scan_date: date) -> list[CecchinoTodayFixture]:
    stmt = (
        select(CecchinoTodayFixture)
        .where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
        )
        .order_by(CecchinoTodayFixture.kickoff.asc())
    )
    return list(db.scalars(stmt).all())


def _json_bytes(payload: Any) -> bytes:
    safe = make_json_safe(payload)
    return json.dumps(safe, indent=2, ensure_ascii=False).encode("utf-8")


def build_daily_purchasability_audit_manifest_and_files(
    db: Session,
    *,
    scan_date: date,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Costruisce manifest + mappa path→bytes per ZIP giornaliero."""
    fixtures = _load_eligible_fixtures(db, scan_date=scan_date)
    generated_at = datetime.now(timezone.utc).isoformat()

    manifest_fixtures: list[dict[str, Any]] = []
    file_entries: dict[str, bytes] = {}
    summary = {
        "eligible_fixtures": len(fixtures),
        "with_opportunity": 0,
        "without_opportunity": 0,
        "audit_unavailable": 0,
    }

    for row in fixtures:
        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        v31_snapshot = output.get("purchasability_preview_v31")
        v31_dict = v31_snapshot if isinstance(v31_snapshot, dict) else None

        has_opp, active_count, active_keys = classify_fixture_opportunity(v31_dict)

        entry: dict[str, Any] = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "league": row.league_name,
            "country": row.country_name,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "has_opportunity": has_opp,
            "active_opportunity_count": active_count,
            "active_market_keys": active_keys,
            "purchasability_formula_version": (
                v31_dict.get("formula_version") if v31_dict else None
            ),
            "candidate_version": v31_dict.get("candidate_version") if v31_dict else None,
        }

        if not _fixture_has_audit_contract(row):
            entry["audit_status"] = "unavailable"
            summary["audit_unavailable"] += 1
            manifest_fixtures.append(entry)
            continue

        audit = build_purchasability_audit_export(db, int(row.id))
        if audit is None:
            entry["audit_status"] = "unavailable"
            summary["audit_unavailable"] += 1
            manifest_fixtures.append(entry)
            continue

        entry["audit_status"] = "included"
        folder = "with-opportunity" if has_opp else "without-opportunity"
        if has_opp:
            summary["with_opportunity"] += 1
        else:
            summary["without_opportunity"] += 1

        filename = f"purchasability-audit-{int(row.provider_fixture_id)}.json"
        file_entries[f"{folder}/{filename}"] = _json_bytes(audit)
        manifest_fixtures.append(entry)

    manifest = make_json_safe(
        {
            "contract_version": DAILY_AUDIT_MANIFEST_CONTRACT_VERSION,
            "audit_contract_version": PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION,
            "scan_date": scan_date.isoformat(),
            "generated_at": generated_at,
            "summary": summary,
            "fixtures": manifest_fixtures,
        }
    )
    return manifest, file_entries


def build_daily_purchasability_audit_zip(
    db: Session,
    *,
    scan_date: date,
) -> tuple[bytes, str]:
    """Assembla ZIP purchasability-audits-YYYY-MM-DD.zip."""
    manifest, file_entries = build_daily_purchasability_audit_manifest_and_files(
        db, scan_date=scan_date
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name in sorted(file_entries):
            archive.writestr(name, file_entries[name])
    filename = f"purchasability-audits-{scan_date.isoformat()}.zip"
    return buf.getvalue(), filename
