"""Export batch giornaliero audit Acquistabilità V3.5 Structural V2."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_AUDIT_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_V2_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_v2_audit_export import (
    build_purchasability_v35_v2_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    SNAPSHOT_OUTPUT_KEY,
    fixture_has_v35_v2_score,
    validate_purchasability_preview_v35_v2_snapshot,
)


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
    return json.dumps(make_json_safe(payload), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


def _scored_market_count(snapshot: dict[str, Any]) -> int:
    return sum(
        1
        for item in snapshot.get("items") or []
        if isinstance(item, dict) and item.get("status") == "score"
    )


def build_daily_purchasability_v35_v2_audit_manifest_and_files(
    db: Session,
    *,
    scan_date: date,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    fixtures = _load_eligible_fixtures(db, scan_date=scan_date)
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest_fixtures: list[dict[str, Any]] = []
    file_entries: dict[str, bytes] = {}
    summary = {
        "eligible_fixtures": len(fixtures),
        "included": 0,
        "with_score": 0,
        "without_score": 0,
        "snapshot_unavailable": 0,
        "snapshot_invalid": 0,
    }

    for row in fixtures:
        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        snap = output.get(SNAPSHOT_OUTPUT_KEY)
        entry: dict[str, Any] = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "league": row.league_name,
            "country": row.country_name,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        }

        if not isinstance(snap, dict):
            summary["snapshot_unavailable"] += 1
            entry["status"] = "snapshot_unavailable"
            manifest_fixtures.append(entry)
            continue

        check = validate_purchasability_preview_v35_v2_snapshot(snap)
        if not check.get("ok"):
            summary["snapshot_invalid"] += 1
            entry["status"] = "snapshot_invalid"
            entry["validation_reason"] = check.get("reason")
            manifest_fixtures.append(entry)
            continue

        export = build_purchasability_v35_v2_audit_export(row, snap)
        has_score = fixture_has_v35_v2_score(snap)
        folder = "with-score" if has_score else "without-score"
        fname = f"purchasability-v35-v2-audit-{int(row.provider_fixture_id)}.json"
        path = f"{folder}/{fname}"
        file_entries[path] = _json_bytes(export)
        summary["included"] += 1
        if has_score:
            summary["with_score"] += 1
        else:
            summary["without_score"] += 1
        entry["status"] = "included"
        entry["path"] = path
        entry["scored_markets"] = _scored_market_count(snap)
        entry["formula_freeze_sha256"] = snap.get("formula_freeze_sha256")
        manifest_fixtures.append(entry)

    manifest = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_V2_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION,
            "audit_export_contract_version": PURCHASABILITY_V35_V2_AUDIT_EXPORT_CONTRACT_VERSION,
            "generated_at": generated_at,
            "scan_date": scan_date.isoformat(),
            "summary": summary,
            "fixtures": manifest_fixtures,
            "pre_match_only": True,
            "contains_post_match_fields": False,
        }
    )
    file_entries["manifest.json"] = _json_bytes(manifest)
    return manifest, file_entries


def build_daily_purchasability_v35_v2_audit_zip(
    db: Session,
    *,
    scan_date: date,
) -> tuple[bytes, str]:
    _manifest, files = build_daily_purchasability_v35_v2_audit_manifest_and_files(
        db, scan_date=scan_date
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, raw in sorted(files.items()):
            zf.writestr(path, raw)
    filename = f"purchasability-v35-v2-audit-daily-{scan_date.isoformat()}.zip"
    return buf.getvalue(), filename


__all__ = [
    "build_daily_purchasability_v35_v2_audit_manifest_and_files",
    "build_daily_purchasability_v35_v2_audit_zip",
]
