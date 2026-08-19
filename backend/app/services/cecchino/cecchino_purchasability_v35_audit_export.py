"""Export audit Acquistabilità V3.5 fixture — read-only, persisted snapshot only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    index_purchasability_v35_snapshot_by_market,
    validate_purchasability_preview_v35_snapshot,
)

_POST_MATCH_EXCLUDE_KEYS = frozenset(
    {
        "final_score",
        "result",
        "outcome",
        "goals_home",
        "goals_away",
        "score_fulltime_home",
        "score_fulltime_away",
        "score_halftime_home",
        "score_halftime_away",
        "settlement",
        "settlement_status",
        "won",
        "lost",
        "hit",
        "profit",
        "profit_1u",
        "unit_stake_profit",
        "ft_result",
        "ht_result",
    }
)


def _assert_no_post_match_leakage_v35(payload: dict[str, Any]) -> None:
    """Anti-leakage ricorsivo — fallisce se trova campi post-match."""

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in _POST_MATCH_EXCLUDE_KEYS:
                    raise ValueError(f"post_match_leakage at {path}.{k}")
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(payload)


def _fixture_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    kickoff = row.kickoff.isoformat() if row.kickoff else None
    scan_date = row.scan_date.isoformat() if row.scan_date else None
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "date": scan_date,
        "kickoff": kickoff,
        "league": row.league_name,
        "country": row.country_name,
        "season": row.provider_season,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
    }


def _snapshot_identity_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_version": snapshot.get("snapshot_version"),
        "contract_version": snapshot.get("contract_version"),
        "feature_version": snapshot.get("feature_version"),
        "formula_version": snapshot.get("formula_version"),
        "relation_registry_version": snapshot.get("relation_registry_version"),
        "candidate_registry_version": snapshot.get("candidate_registry_version"),
        "experiment_version": snapshot.get("experiment_version"),
        "source_snapshot_at": snapshot.get("source_snapshot_at"),
        "source_snapshot_verified": snapshot.get("source_snapshot_verified"),
        "source_snapshot_before_kickoff": snapshot.get("source_snapshot_before_kickoff"),
        "pre_match_verified": snapshot.get("pre_match_verified"),
        "input_fingerprint_sha256": snapshot.get("input_fingerprint_sha256"),
        "engine_payload_sha256": snapshot.get("engine_payload_sha256"),
    }


def build_purchasability_v35_audit_export(
    row: CecchinoTodayFixture,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Costruisce export audit V3.5 esclusivamente dallo snapshot frozen."""
    by_market = index_purchasability_v35_snapshot_by_market(snapshot)
    markets: dict[str, Any] = {}
    for mk in PANEL_MARKET_KEYS:
        item = by_market.get(mk)
        if isinstance(item, dict):
            markets[mk] = item

    payload = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fixture": _fixture_block(row),
            "snapshot_identity": _snapshot_identity_block(snapshot),
            "frozen_config": snapshot.get("frozen_config"),
            "candidate_registry": snapshot.get("candidate_registry"),
            "relation_registry": snapshot.get("relation_registry"),
            "market_order": list(PANEL_MARKET_KEYS),
            "markets": markets,
            "summary": snapshot.get("summary"),
            "pre_match_only": True,
            "contains_post_match_fields": False,
        }
    )
    _assert_no_post_match_leakage_v35(payload)
    return payload


class V35SnapshotUnavailableError(Exception):
    """Fixture senza snapshot V3.5 persistito."""

    code = "v35_snapshot_unavailable"


class V35SnapshotInvalidError(Exception):
    """Snapshot V3.5 presente ma non valido per audit."""

    code = "v35_snapshot_invalid"


def get_purchasability_v35_audit_export(
    db: Session,
    today_fixture_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read-only DB — ritorna (payload, filename) o solleva errori strutturati."""
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None, None

    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    snapshot = output.get("purchasability_preview_v35")
    if not isinstance(snapshot, dict):
        raise V35SnapshotUnavailableError()

    check = validate_purchasability_preview_v35_snapshot(snapshot)
    if not check.get("ok"):
        raise V35SnapshotInvalidError()

    export = build_purchasability_v35_audit_export(row, snapshot)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"purchasability-v35-audit-{int(row.provider_fixture_id)}-{ts}.json"
    return export, filename


__all__ = [
    "PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION",
    "V35SnapshotInvalidError",
    "V35SnapshotUnavailableError",
    "build_purchasability_v35_audit_export",
    "get_purchasability_v35_audit_export",
]
