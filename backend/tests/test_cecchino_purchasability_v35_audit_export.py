"""Test export audit Acquistabilità V3.5 — persisted snapshot only."""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.routes.cecchino_today import router
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_audit_export import (
    V35SnapshotInvalidError,
    V35SnapshotUnavailableError,
    build_purchasability_v35_audit_export,
    get_purchasability_v35_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v35_daily_audit_export import (
    build_daily_purchasability_v35_audit_zip,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
)
from app.services.cecchino.cecchino_selection_keys import SEL_HOME

SNAP_AT = "2026-08-19T10:00:00+00:00"
KICKOFF = "2026-08-19T15:00:00+00:00"


def _row(mk: str, *, quota: float = 2.2, rating: float = 60, prob: float = 0.55) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _build_v35_snapshot(*, quota: float = 2.2) -> dict:
    rows = [_row(mk, quota=quota) for mk in PANEL_MARKET_KEYS]
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel={"rows": rows},
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 555,
            "snapshot_at": SNAP_AT,
            "kickoff": KICKOFF,
        },
        snapshot_info={
            "snapshot_at": SNAP_AT,
            "snapshot_timestamp_verified": True,
        },
    )
    return output["purchasability_preview_v35"]


def _fixture_row(
    *,
    fid: int = 7,
    provider_id: int = 555,
    v35_snapshot: dict | None = None,
    kpi_quota: float = 2.2,
) -> SimpleNamespace:
    snap = v35_snapshot if v35_snapshot is not None else _build_v35_snapshot(quota=kpi_quota)
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=provider_id,
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc),
        scan_date=date(2026, 8, 19),
        provider_season=2026,
        country_name="Italy",
        league_name="Serie A",
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        goals_home=2,
        goals_away=1,
        kpi_panel_json={
            "rows": [_row(mk, quota=kpi_quota) for mk in PANEL_MARKET_KEYS],
        },
        cecchino_output_json={"purchasability_preview_v35": snap},
    )


def _client_with_db(row: SimpleNamespace | None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override_db():
        db = MagicMock()
        db.get.return_value = row
        yield db

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_audit_uses_persisted_v35_only():
    row = _fixture_row()
    snap = row.cecchino_output_json["purchasability_preview_v35"]
    export = build_purchasability_v35_audit_export(row, snap)
    assert export["contract_version"] == PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION
    assert export["markets"][SEL_HOME]["candidates"]["A"] == snap["items"][0]["candidates"]["A"]


def test_no_calculate_v35_batch_in_get():
    row = _fixture_row()
    db = MagicMock()
    db.get.return_value = row
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_audit_export.calculate_purchasability_v35_batch",
        side_effect=AssertionError("must not recompute"),
        create=True,
    ):
        payload, _fn = get_purchasability_v35_audit_export(db, 7)
    assert payload is not None


def test_kpi_change_after_snapshot_audit_unchanged():
    row = _fixture_row(kpi_quota=9.9)
    snap = _build_v35_snapshot(quota=2.2)
    row.cecchino_output_json = {"purchasability_preview_v35": snap}
    export = build_purchasability_v35_audit_export(row, snap)
    home_item = export["markets"][SEL_HOME]
    snap_home = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    assert home_item["input"] == snap_home["input"]


def test_no_snapshot_returns_unavailable():
    row = _fixture_row(v35_snapshot=None)
    row.cecchino_output_json = {}
    db = MagicMock()
    db.get.return_value = row
    with pytest.raises(V35SnapshotUnavailableError):
        get_purchasability_v35_audit_export(db, 7)


def test_invalid_snapshot_returns_invalid():
    row = _fixture_row(v35_snapshot={"snapshot_version": "wrong", "items": []})
    db = MagicMock()
    db.get.return_value = row
    with pytest.raises(V35SnapshotInvalidError):
        get_purchasability_v35_audit_export(db, 7)


def test_api_no_snapshot_409():
    row = _fixture_row()
    row.cecchino_output_json = {}
    client = _client_with_db(row)
    resp = client.get("/api/cecchino/today/7/purchasability-v35-audit-export")
    assert resp.status_code == 409
    assert resp.json()["error"] == "v35_snapshot_unavailable"


def test_api_invalid_snapshot_409():
    row = _fixture_row(v35_snapshot={"snapshot_version": "bad", "items": []})
    client = _client_with_db(row)
    resp = client.get("/api/cecchino/today/7/purchasability-v35-audit-export")
    assert resp.status_code == 409
    assert resp.json()["error"] == "v35_snapshot_invalid"


def test_api_fixture_not_found_404():
    client = _client_with_db(None)
    resp = client.get("/api/cecchino/today/999/purchasability-v35-audit-export")
    assert resp.status_code == 404


def test_19_markets_preserved_in_audit():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    export = build_purchasability_v35_audit_export(row, snap)
    assert len(export["markets"]) == 19
    assert export["market_order"] == list(PANEL_MARKET_KEYS)


def test_abcd_preserved_in_audit():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    export = build_purchasability_v35_audit_export(row, snap)
    home = export["markets"][SEL_HOME]
    assert set(home["candidates"].keys()) == {"A", "B", "C", "D"}


def test_frozen_config_preserved_in_audit():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    export = build_purchasability_v35_audit_export(row, snap)
    assert export["frozen_config"] == snap["frozen_config"]


def test_relation_registry_preserved_in_audit():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    export = build_purchasability_v35_audit_export(row, snap)
    assert export["relation_registry"] == snap["relation_registry"]


def test_post_match_leakage_fails_export():
    snap = _build_v35_snapshot()
    bad_snap = dict(snap)
    bad_items = list(snap["items"])
    bad_item = dict(bad_items[0])
    bad_item["result"] = "1-0"
    bad_items[0] = bad_item
    bad_snap["items"] = bad_items
    row = _fixture_row(v35_snapshot=bad_snap)
    with pytest.raises(ValueError, match="post_match_leakage"):
        build_purchasability_v35_audit_export(row, bad_snap)


def test_daily_includes_all_eligible():
    rows = [
        _fixture_row(fid=1, provider_id=101),
        _fixture_row(fid=2, provider_id=102),
    ]
    rows[1].cecchino_output_json = {}

    db = MagicMock()

    def _scalar_side_effect(stmt):
        result = MagicMock()
        result.all.return_value = rows
        return result

    db.scalars.side_effect = _scalar_side_effect

    zip_bytes, filename = build_daily_purchasability_v35_audit_zip(
        db, scan_date=date(2026, 8, 19)
    )
    assert filename == "purchasability-v35-audits-2026-08-19.zip"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["summary"]["eligible_fixtures"] == 2
    assert manifest["summary"]["snapshot_unavailable"] == 1
    assert manifest["summary"]["included"] == 1


def test_daily_scored_goes_with_score_folder():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    zip_bytes, _ = build_daily_purchasability_v35_audit_zip(
        db, scan_date=date(2026, 8, 19)
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert any(n.startswith("with-score/") for n in names)


def test_daily_without_score_folder():
    rows_data = [_row(mk, rating=10, prob=0.40, quota=1.5) for mk in PANEL_MARKET_KEYS]
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel={"rows": rows_data},
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 555,
            "snapshot_at": SNAP_AT,
            "kickoff": KICKOFF,
        },
        snapshot_info={"snapshot_at": SNAP_AT, "snapshot_timestamp_verified": True},
    )
    snap = output["purchasability_preview_v35"]
    row = _fixture_row(v35_snapshot=snap)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    zip_bytes, _ = build_daily_purchasability_v35_audit_zip(
        db, scan_date=date(2026, 8, 19)
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert any(n.startswith("without-score/") for n in names)


def test_daily_manifest_contract_version():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    zip_bytes, _ = build_daily_purchasability_v35_audit_zip(
        db, scan_date=date(2026, 8, 19)
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["contract_version"] == PURCHASABILITY_V35_DAILY_AUDIT_MANIFEST_CONTRACT_VERSION
    assert manifest["audit_contract_version"] == PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION


def test_daily_no_db_writes():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    build_daily_purchasability_v35_audit_zip(db, scan_date=date(2026, 8, 19))
    db.commit.assert_not_called()
    db.add.assert_not_called()


def test_daily_api_route_static_before_dynamic():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override_db():
        db = MagicMock()
        db.scalars.return_value.all.return_value = [row]
        yield db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    resp = client.get(
        "/api/cecchino/today/purchasability-v35-audit-export/daily",
        params={"scan_date": "2026-08-19"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith(
        'attachment; filename="purchasability-v35-audits-2026-08-19.zip"'
    )


def test_no_historical_reliability_in_audit_path():
    row = _fixture_row()
    snap = row.cecchino_output_json["purchasability_preview_v35"]
    with patch(
        "app.services.cecchino.cecchino_purchasability_v31_hr.build_hr_history_context",
        side_effect=AssertionError("HR must not run"),
    ):
        export = build_purchasability_v35_audit_export(row, snap)
    assert export["pre_match_only"] is True


def test_audit_no_recomputation_v35_batch():
    row = _fixture_row()
    db = MagicMock()
    db.get.return_value = row
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_candidate.calculate_purchasability_v35_batch",
        side_effect=AssertionError("batch must not run on audit GET"),
    ):
        payload, _ = get_purchasability_v35_audit_export(db, 7)
    assert payload is not None
