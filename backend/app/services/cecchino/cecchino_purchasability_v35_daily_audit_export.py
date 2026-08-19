"""Export batch giornaliero audit Acquistabilità V3.5 — read-only, persisted snapshot only."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_audit_export import (
    build_purchasability_v35_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    fixture_has_v35_score,
    validate_purchasability_preview_v35_snapshot,
)

DAILY_V35_AUDIT_MANIFEST_CONTRACT_VERSION = (
    PURCHASABILITY_V35_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION
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
    safe = make_json_safe(payload)
    return json.dumps(safe, indent=2, ensure_ascii=False).encode("utf-8")


def _scored_market_count(snapshot: dict[str, Any]) -> int:
    count = 0
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("status") == "score":
            count += 1
    return count


def _candidate_summary_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    out: dict[str, Any] = {}
    for ck in ("A", "B", "C", "D"):
        cand = summary.get(ck)
        if isinstance(cand, dict):
            out[ck] = {
                "top_market_key": cand.get("top_market_key"),
                "top_score": cand.get("top_score"),
                "top_raw_score": cand.get("top_raw_score"),
                "score_band_counts": dict(cand.get("score_band_counts") or {}),
            }
        else:
            out[ck] = {
                "top_market_key": None,
                "top_score": None,
                "top_raw_score": None,
                "score_band_counts": {
                    "0_19": 0,
                    "20_39": 0,
                    "40_59": 0,
                    "60_79": 0,
                    "80_100": 0,
                },
            }
    return out


def build_daily_purchasability_v35_audit_manifest_and_files(
    db: Session,
    *,
    scan_date: date,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Costruisce manifest + mappa path→bytes per ZIP giornaliero V3.5."""
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
        v35_snapshot = output.get("purchasability_preview_v35")

        entry: dict[str, Any] = {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "league": row.league_name,
            "country": row.country_name,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        }

        if not isinstance(v35_snapshot, dict):
            entry["audit_status"] = "snapshot_unavailable"
            summary["snapshot_unavailable"] += 1
            manifest_fixtures.append(entry)
            continue

        check = validate_purchasability_preview_v35_snapshot(v35_snapshot)
        if not check.get("ok"):
            entry["audit_status"] = "snapshot_invalid"
            summary["snapshot_invalid"] += 1
            manifest_fixtures.append(entry)
            continue

        has_score = fixture_has_v35_score(v35_snapshot)
        entry.update(
            {
                "audit_status": "included",
                "source_snapshot_at": v35_snapshot.get("source_snapshot_at"),
                "pre_match_verified": v35_snapshot.get("pre_match_verified"),
                "input_fingerprint_sha256": v35_snapshot.get("input_fingerprint_sha256"),
                "engine_payload_sha256": v35_snapshot.get("engine_payload_sha256"),
                "has_v35_score": has_score,
                "scored_market_count": _scored_market_count(v35_snapshot),
                "candidate_summary": _candidate_summary_from_snapshot(v35_snapshot),
            }
        )

        summary["included"] += 1
        if has_score:
            summary["with_score"] += 1
            folder = "with-score"
        else:
            summary["without_score"] += 1
            folder = "without-score"

        audit = build_purchasability_v35_audit_export(row, v35_snapshot)
        filename = f"purchasability-v35-audit-{int(row.provider_fixture_id)}.json"
        file_entries[f"{folder}/{filename}"] = _json_bytes(audit)
        manifest_fixtures.append(entry)

    manifest = make_json_safe(
        {
            "contract_version": DAILY_V35_AUDIT_MANIFEST_CONTRACT_VERSION,
            "audit_contract_version": PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
            "scan_date": scan_date.isoformat(),
            "generated_at": generated_at,
            "summary": summary,
            "fixtures": manifest_fixtures,
        }
    )
    return manifest, file_entries


def build_daily_purchasability_v35_audit_zip(
    db: Session,
    *,
    scan_date: date,
) -> tuple[bytes, str]:
    """Assembla ZIP purchasability-v35-audits-YYYY-MM-DD.zip."""
    manifest, file_entries = build_daily_purchasability_v35_audit_manifest_and_files(
        db, scan_date=scan_date
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name in sorted(file_entries):
            archive.writestr(name, file_entries[name])
    filename = f"purchasability-v35-audits-{scan_date.isoformat()}.zip"
    return buf.getvalue(), filename


__all__ = [
    "DAILY_V35_AUDIT_MANIFEST_CONTRACT_VERSION",
    "build_daily_purchasability_v35_audit_manifest_and_files",
    "build_daily_purchasability_v35_audit_zip",
]
