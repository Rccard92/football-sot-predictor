"""Test preview batch e detect_division Cecchino Lab."""

from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import cecchino_lab
from app.core.database import get_db
from app.services.cecchino_data_lab.batch_preview_service import (
    IMPORT_STATUS_ALREADY_IMPORTED,
    IMPORT_STATUS_BLOCKED,
    IMPORT_STATUS_DATASET_ALREADY_EXISTS,
    IMPORT_STATUS_DUPLICATE_COMPETITION_IN_BATCH,
    IMPORT_STATUS_DUPLICATE_IN_BATCH,
    IMPORT_STATUS_READY,
    IMPORT_STATUS_READY_WITH_WARNINGS,
    batch_preview_csv_files,
)
from app.services.cecchino_data_lab.constants import (
    BATCH_MAX_FILES,
    IMPORT_CONFIRM_TOKEN,
    ISSUE_PARTIAL_BET365_AH,
    ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS,
    PARSER_VERSION,
    RAW_EXTRA_COLUMNS_KEY,
)
from app.services.cecchino_data_lab.division_detect import (
    MAPPING_INVALID_CSV,
    MAPPING_MAPPED,
    MAPPING_MISSING_DIVISION,
    MAPPING_MIXED_DIVISIONS,
    MAPPING_UNKNOWN_DIVISION,
    detect_division,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.import_service import import_csv_bytes
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes


def _csv(div: str, *, extra: str | None = None, ah_partial: bool = False) -> bytes:
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    vals = [div, "10/08/2024", "Home", "Away", "2", "0", "H", "1.80", "3.50", "4.20"]
    if ah_partial:
        cols.extend(["AHh", "B365AHH"])
        vals.extend(["-0.5", "1.90"])
    if extra is not None:
        vals.append(extra)
    return (",".join(cols) + "\n" + ",".join(vals) + "\n").encode("utf-8")


def test_detect_division_mapped_i1_e1_e3():
    for div, key in [("I1", "serie_a"), ("E1", "championship"), ("E3", "league_two")]:
        r = detect_division(_csv(div))
        assert r.mapping_status == MAPPING_MAPPED
        assert r.division_code == div
        assert r.competition is not None
        assert r.competition.key == key


def test_detect_unknown_missing_mixed_invalid():
    unknown = detect_division(_csv("XX"))
    assert unknown.mapping_status == MAPPING_UNKNOWN_DIVISION
    assert unknown.division_code == "XX"

    no_div = b"Date,HomeTeam,AwayTeam\n10/08/2024,A,B\n"
    missing = detect_division(no_div)
    assert missing.mapping_status == MAPPING_MISSING_DIVISION

    mixed = (
        b"Div,Date,HomeTeam,AwayTeam\n"
        b"E1,10/08/2024,A,B\n"
        b"E2,11/08/2024,C,D\n"
    )
    m = detect_division(mixed)
    assert m.mapping_status == MAPPING_MIXED_DIVISIONS
    assert m.detected_divisions == ["E1", "E2"]

    empty = detect_division(b"   \n")
    assert empty.mapping_status == MAPPING_INVALID_CSV


def test_batch_preview_three_competitions_same_season():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    files = [
        ("I1.csv", _csv("I1")),
        ("E1.csv", _csv("E1")),
        ("E3.csv", _csv("E3", extra="0.38")),
    ]
    out = batch_preview_csv_files(db, files, season_label="2024/2025")
    assert out["status"] == "ok"
    assert out["season_label"] == "2024/2025"
    assert out["files_total"] == 3
    assert out["ready_count"] == 3
    assert out["blocked_count"] == 0

    by_div = {i["division_code"]: i for i in out["items"]}
    assert by_div["I1"]["competition_key"] == "serie_a"
    assert by_div["E1"]["competition_key"] == "championship"
    assert by_div["E3"]["competition_key"] == "league_two"
    assert by_div["I1"]["import_status"] == IMPORT_STATUS_READY
    assert by_div["E3"]["info_count"] >= 1
    assert any(
        iss["issue_code"] == ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS
        for iss in by_div["E3"]["issues"]
    )
    extras = by_div["E3"]["preview_rows"][0].get(RAW_EXTRA_COLUMNS_KEY)
    # preview_rows may include __extra_columns__ from parser
    assert by_div["E3"]["rows_total"] == 1


def test_batch_duplicate_sha_and_competition():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    same = _csv("E0")
    out = batch_preview_csv_files(
        db,
        [("a.csv", same), ("b.csv", same)],
        season_label="2024/2025",
    )
    assert all(i["import_status"] == IMPORT_STATUS_DUPLICATE_IN_BATCH for i in out["items"])
    assert out["ready_count"] == 0

    out2 = batch_preview_csv_files(
        db,
        [
            ("E0.csv", _csv("E0")),
            (
                "PREMIER.csv",
                (
                    b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
                    b"E0,11/08/2024,X,Y,1,0,H,2.00,3.20,3.50\n"
                ),
            ),
        ],
        season_label="2024/2025",
    )
    assert all(
        i["import_status"] == IMPORT_STATUS_DUPLICATE_COMPETITION_IN_BATCH for i in out2["items"]
    )
    assert "Premier League 2024/2025" in (out2["items"][0]["blocking_reason"] or "")


def test_batch_already_imported_and_dataset_exists():
    db = MagicMock()

    existing_imp = MagicMock()
    existing_imp.id = 9
    existing_ds = MagicMock()
    existing_ds.id = 3

    # First call SHA check returns import; second competition's dataset check etc.
    # Use side_effect based on call pattern via filter args is hard with MagicMock;
    # patch helpers instead.
    with patch(
        "app.services.cecchino_data_lab.batch_preview_service._find_existing_import",
        return_value=existing_imp,
    ), patch(
        "app.services.cecchino_data_lab.batch_preview_service._find_existing_dataset",
        return_value=None,
    ):
        out = batch_preview_csv_files(db, [("I1.csv", _csv("I1"))], season_label="2024/2025")
    assert out["items"][0]["import_status"] == IMPORT_STATUS_ALREADY_IMPORTED
    assert out["already_imported_count"] == 1
    assert out["ready_count"] == 0

    with patch(
        "app.services.cecchino_data_lab.batch_preview_service._find_existing_import",
        return_value=None,
    ), patch(
        "app.services.cecchino_data_lab.batch_preview_service._find_existing_dataset",
        return_value=existing_ds,
    ):
        out2 = batch_preview_csv_files(db, [("I1.csv", _csv("I1"))], season_label="2025/2026")
    assert out2["items"][0]["import_status"] == IMPORT_STATUS_DATASET_ALREADY_EXISTS
    assert out2["items"][0]["dataset_id"] == 3
    assert "Sostituisci CSV" in (out2["items"][0]["blocking_reason"] or "")


def test_batch_blocked_and_ready_mix_no_db_write():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    out = batch_preview_csv_files(
        db,
        [
            ("ok.csv", _csv("I1")),
            ("bad.csv", _csv("XX")),
            ("ok2.csv", _csv("E1")),
        ],
        season_label="2023/2024",
    )
    assert out["ready_count"] == 2
    assert out["blocked_count"] == 1
    statuses = {i["filename"]: i["import_status"] for i in out["items"]}
    assert statuses["ok.csv"] == IMPORT_STATUS_READY
    assert statuses["ok2.csv"] == IMPORT_STATUS_READY
    assert statuses["bad.csv"] == IMPORT_STATUS_BLOCKED
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_batch_ah_partial_ready_with_warnings():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None
    out = batch_preview_csv_files(
        db,
        [("ah.csv", _csv("E0", ah_partial=True))],
        season_label="2024/2025",
    )
    item = out["items"][0]
    assert item["import_status"] == IMPORT_STATUS_READY_WITH_WARNINGS
    assert item["warnings_count"] >= 1
    assert any(i["issue_code"] == ISSUE_PARTIAL_BET365_AH for i in item["issues"])
    assert out["ready_count"] == 1


def test_batch_limits_and_non_csv():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as exc:
        batch_preview_csv_files(db, [], season_label="2024/2025")
    assert exc.value.code == "empty_batch"

    too_many = [(f"f{i}.csv", _csv("E0")) for i in range(BATCH_MAX_FILES + 1)]
    with pytest.raises(CecchinoLabImportError) as exc2:
        batch_preview_csv_files(db, too_many, season_label="2024/2025")
    assert exc2.value.code == "batch_too_large"

    db.query.return_value.filter.return_value.one_or_none.return_value = None
    out = batch_preview_csv_files(
        db,
        [("notes.txt", b"not a csv")],
        season_label="2024/2025",
    )
    assert out["items"][0]["import_status"] == IMPORT_STATUS_BLOCKED
    assert "csv" in (out["items"][0]["blocking_reason"] or "").lower()


def test_batch_preview_api_endpoint():
    app = FastAPI()
    app.include_router(cecchino_lab.admin_router, prefix="/api")

    def override_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.one_or_none.return_value = None
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    files = [
        ("files", ("I1.csv", BytesIO(_csv("I1")), "text/csv")),
        ("files", ("E1.csv", BytesIO(_csv("E1")), "text/csv")),
    ]
    res = client.post(
        "/api/admin/cecchino-lab/imports/batch/preview",
        files=files,
        data={"season_label": "2024/2025"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["files_total"] == 2
    assert body["ready_count"] == 2
    assert all(i["season_label"] == "2024/2025" for i in body["items"])


def test_single_import_unchanged_smoke():
    """L'import singolo continua a richiedere competition_key + token."""
    out = preview_csv_bytes(
        _csv("E0"),
        competition_key="premier_league",
        season_label="2024/2025",
    )
    assert out["summary"]["importable"] is True
    assert out["division_code"] == "E0"

    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as exc:
        import_csv_bytes(
            db,
            _csv("E0"),
            competition_key="premier_league",
            season_label="2024/2025",
            confirm="WRONG",
        )
    assert exc.value.code == "invalid_confirm_token"
    # ensure token constant still works as gate
    assert IMPORT_CONFIRM_TOKEN == "IMPORT_CECCHINO_LAB_CSV"
    assert PARSER_VERSION.startswith("football_data_uk_bet365")
