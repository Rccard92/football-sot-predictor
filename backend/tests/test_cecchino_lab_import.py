"""Test preview e import Cecchino Lab (DB mock / in-memory)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino_data_lab.constants import IMPORT_CONFIRM_TOKEN, PARSER_VERSION
from app.services.cecchino_data_lab.import_service import CecchinoLabImportError, import_csv_bytes
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes

SAMPLE = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
    "E0,10/08/2024,15:00,Arsenal,Wolves,2,0,H,1.45,4.50,7.00\n"
)


def test_preview_does_not_touch_db():
    out = preview_csv_bytes(
        SAMPLE.encode("utf-8"),
        competition_name="Premier League",
        country="England",
        season_label="2024/25",
        source_filename="E0.csv",
    )
    assert out["rows_total"] == 1
    assert out["summary"]["importable"] is True
    assert out["file_sha256"]
    assert "B365H" in out["recognized_columns"]


def test_import_requires_confirm_token():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as exc:
        import_csv_bytes(
            db,
            SAMPLE.encode("utf-8"),
            competition_name="Premier League",
            country="England",
            season_label="2024/25",
            confirm="WRONG",
        )
    assert exc.value.code == "invalid_confirm_token"
    db.commit.assert_not_called()


def test_import_duplicate_file_noop():
    db = MagicMock()
    existing = MagicMock()
    existing.id = 9
    existing.dataset_id = 3
    # First query = existing import by sha
    db.query.return_value.filter.return_value.one_or_none.return_value = existing

    with pytest.raises(CecchinoLabImportError) as exc:
        import_csv_bytes(
            db,
            SAMPLE.encode("utf-8"),
            competition_name="Premier League",
            country="England",
            season_label="2024/25",
            confirm=IMPORT_CONFIRM_TOKEN,
        )
    assert exc.value.code == "duplicate_file"
    assert exc.value.status_code == 409
    db.commit.assert_not_called()


def test_import_real_commits_and_creates_rows():
    """Import con session mock che simula flush/query count."""
    db = MagicMock()

    # Sequence of one_or_none: no duplicate import, then no existing dataset
    no_dup = None
    no_dataset = None
    call_count = {"n": 0}

    def one_or_none_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return no_dup
        return no_dataset

    filter_mock = MagicMock()
    filter_mock.one_or_none.side_effect = one_or_none_side_effect
    filter_mock.count.return_value = 1

    query_mock = MagicMock()
    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock

    # Simulate autoincrement ids on flush
    created = {"dataset_id": 1, "import_id": 10, "match_id": 100}

    def flush_side_effect():
        for obj in list(db.add.call_args_list):
            pass
        # Assign ids to objects that were added
        for call in db.add.call_args_list:
            obj = call.args[0]
            name = type(obj).__name__
            if name == "CecchinoLabDataset" and getattr(obj, "id", None) is None:
                obj.id = created["dataset_id"]
            if name == "CecchinoLabImport" and getattr(obj, "id", None) is None:
                obj.id = created["import_id"]
            if name == "CecchinoLabMatch" and getattr(obj, "id", None) is None:
                obj.id = created["match_id"]
                created["match_id"] += 1

    db.flush.side_effect = flush_side_effect

    result = import_csv_bytes(
        db,
        SAMPLE.encode("utf-8"),
        competition_name="Premier League",
        country="England",
        season_label="2024/25",
        division_code="E0",
        source_filename="E0.csv",
        confirm=IMPORT_CONFIRM_TOKEN,
    )
    assert result["status"] == "completed"
    assert result["rows_imported"] == 1
    assert result["parser_version"] == PARSER_VERSION
    db.commit.assert_called_once()


def test_import_rollback_on_unexpected_error():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    def boom_flush():
        raise RuntimeError("db down")

    db.flush.side_effect = boom_flush

    with pytest.raises(RuntimeError):
        import_csv_bytes(
            db,
            SAMPLE.encode("utf-8"),
            competition_name="Premier League",
            country="England",
            season_label="2024/25",
            confirm=IMPORT_CONFIRM_TOKEN,
        )
    db.rollback.assert_called()
    db.commit.assert_not_called()


def test_preview_flags_partial_bet365():
    csv = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D\n"
        "E0,10/08/2024,A,B,1,0,H,1.50,3.50\n"
    )
    out = preview_csv_bytes(
        csv.encode("utf-8"),
        competition_name="PL",
        country="England",
        season_label="2024/25",
    )
    assert out["warnings_count"] >= 1
    assert any(i["issue_code"] == "partial_bet365" for i in out["issues"])
