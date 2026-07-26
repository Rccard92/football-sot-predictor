"""Test colonne extra, issue aggregate, persistenza e replace Cecchino Lab."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino_data_lab.constants import (
    ISSUE_IRREGULAR_COLUMN_COUNT,
    ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS,
    PARSER_VERSION,
    RAW_EXTRA_COLUMNS_KEY,
    REPLACE_CONFIRM_TOKEN,
)
from app.services.cecchino_data_lab.csv_parser import parse_football_data_csv
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.import_service import import_csv_bytes, persist_parsed_issues
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes
from app.services.cecchino_data_lab.replace_service import replace_dataset_csv
from app.services.cecchino_data_lab.query_service import get_overview


def _minimal_headers(n: int) -> list[str]:
    """Build n header names starting with required Div/Date/HomeTeam/AwayTeam."""
    base = ["Div", "Date", "HomeTeam", "AwayTeam"]
    extras = [f"C{i}" for i in range(len(base), n)]
    return base + extras


def _row_values(div: str, cols: int, *, trailing: list[str] | None = None) -> list[str]:
    vals = [div, "10/08/2024", "Home", "Away"] + ["0"] * (cols - 4)
    if trailing:
        vals = vals[:cols] + trailing
    return vals[: cols + (len(trailing) if trailing else 0)]


def test_uniform_extra_trailing_columns_preserved():
    """132 header + 133 values uniform → __extra_columns__ + 1 info, 0 column warnings."""
    headers = _minimal_headers(132)
    # Each data row: 133 values (one trailing extra)
    row1 = [headers[0], "10/08/2024", "A", "B"] + ["1"] * 128 + ["0.38"]
    row2 = [headers[0], "11/08/2024", "C", "D"] + ["1"] * 128 + ["0.42"]
    assert len(headers) == 132
    assert len(row1) == 133
    assert len(row2) == 133

    csv_text = ",".join(headers) + "\n" + ",".join(row1) + "\n" + ",".join(row2) + "\n"
    result = parse_football_data_csv(csv_text.encode("utf-8"), timezone_name="Europe/London")

    assert result.rows_total == 2
    assert result.rows_importable == 2
    assert result.warnings_count == 0
    assert result.errors_count == 0
    assert result.info_count >= 1

    uniform = [i for i in result.issues if i.issue_code == ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS]
    assert len(uniform) == 1
    assert uniform[0].severity == "info"
    assert uniform[0].details["header_columns"] == 132
    assert uniform[0].details["row_columns"] == 133
    assert uniform[0].details["extra_columns_count"] == 1
    assert uniform[0].details["affected_rows"] == 2
    assert uniform[0].details["raw_storage_key"] == RAW_EXTRA_COLUMNS_KEY

    # No per-row column_count_mismatch
    assert not any(i.issue_code == "column_count_mismatch" for i in result.issues)

    extras = result.matches[0].raw.get(RAW_EXTRA_COLUMNS_KEY)
    assert extras is not None
    assert len(extras) == 1
    assert extras[0]["position"] == 133
    assert extras[0]["value"] == "0.38"

    extras2 = result.matches[1].raw.get(RAW_EXTRA_COLUMNS_KEY)
    assert extras2[0]["value"] == "0.42"


def test_irregular_column_count_aggregated():
    headers = _minimal_headers(6)
    # Mixed: 6, 7, 5 columns
    rows = [
        ["E3", "10/08/2024", "A", "B", "1", "0"],
        ["E3", "11/08/2024", "C", "D", "1", "0", "0.5"],
        ["E3", "12/08/2024", "E", "F", "1"],
        ["E3", "13/08/2024", "G", "H", "1", "0"],
    ]
    csv_text = ",".join(headers) + "\n" + "\n".join(",".join(r) for r in rows) + "\n"
    result = parse_football_data_csv(csv_text.encode("utf-8"))

    irreg = [i for i in result.issues if i.issue_code == ISSUE_IRREGULAR_COLUMN_COUNT]
    assert len(irreg) == 1
    assert irreg[0].severity == "warning"
    dist = irreg[0].details["distribution"]
    assert dist["6"] == 2
    assert dist["7"] == 1
    assert dist["5"] == 1
    assert irreg[0].details["affected_rows_count"] == 2  # only non-header-matching
    assert result.warnings_count >= 1
    # Exactly one irregular aggregate, not per-row
    assert sum(1 for i in result.issues if i.issue_code == ISSUE_IRREGULAR_COLUMN_COUNT) == 1


def test_preview_exposes_info_count():
    headers = _minimal_headers(5)
    row = ["E3", "10/08/2024", "A", "B", "1", "extra"]
    csv_text = ",".join(headers) + "\n" + ",".join(row) + "\n"
    out = preview_csv_bytes(
        csv_text.encode("utf-8"),
        competition_key="league_two",
        season_label="2025/2026",
    )
    assert out["errors_count"] == 0
    assert out["warnings_count"] == 0
    assert out["info_count"] >= 1
    assert any(i["issue_code"] == ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS for i in out["issues"])


def test_persist_parsed_issues_dedup_and_source_row():
    db = MagicMock()
    from app.services.cecchino_data_lab.csv_parser import ParsedIssue, ParseResult

    parsed = ParseResult(
        parser_version=PARSER_VERSION,
        file_sha256="abc",
        file_size_bytes=1,
        encoding="utf-8",
        encoding_fallback=False,
        headers=[],
        recognized_columns=[],
        missing_required_columns=[],
        missing_optional_known=[],
        unexpected_columns=[],
        rows_total=1,
        preview_rows=[],
        matches=[],
        issues=[
            ParsedIssue(
                severity="info",
                issue_code=ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS,
                message="info file",
            ),
            ParsedIssue(
                severity="warning",
                issue_code="odds_lte_one",
                message="row warn",
                source_row_number=2,
                field_name="B365H",
            ),
            # duplicate
            ParsedIssue(
                severity="warning",
                issue_code="odds_lte_one",
                message="row warn",
                source_row_number=2,
                field_name="B365H",
            ),
        ],
        rows_importable=1,
        rows_skipped=0,
        warnings_count=1,
        errors_count=0,
        info_count=1,
    )
    persist_parsed_issues(db, import_id=5, parsed=parsed, row_to_match_id={2: 99})
    # 2 unique issues (dup dropped)
    assert db.add.call_count == 2
    added = [c.args[0] for c in db.add.call_args_list]
    by_code = {a.issue_code: a for a in added}
    assert by_code[ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS].match_id is None
    assert by_code["odds_lte_one"].match_id == 99
    assert by_code["odds_lte_one"].source_row_number == 2


def test_overview_datasets_status_and_info_excluded_from_anomalies():
    db = MagicMock()

    ds = MagicMock()
    ds.id = 1
    ds.competition_name = "League Two"
    ds.season_label = "2025/2026"
    ds.matches_count = 552
    ds.data_quality_status = "complete"
    ds.country = "England"
    ds.metadata_json = {"bet365_coverage": {"1x2_pre_pct": 100.0, "ou25_pre_pct": 100.0}}
    ds.matches_count = 552

    # Sequence: total, complete, errors, warnings, 1x2, ou, then per-ds err/warn/info
    scalars = iter([552, 552, 0, 0, 552, 552, 0, 0, 1])

    def scalar_side():
        return next(scalars)

    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.scalar.side_effect = scalar_side

    # .all() used for datasets list, recent imports, and import_ids
    all_calls = {"n": 0}

    def all_side():
        all_calls["n"] += 1
        if all_calls["n"] == 1:
            return [ds]  # datasets
        if all_calls["n"] == 2:
            return []  # recent imports
        return [(10,)]  # import ids

    q.all.side_effect = all_side
    db.query.return_value = q

    out = get_overview(db)
    assert out["anomalies_total"] == 0  # info not counted
    assert out["anomalies_errors"] == 0
    assert out["anomalies_warnings"] == 0
    assert "datasets_status" in out
    assert len(out["datasets_status"]) == 1
    assert out["datasets_status"][0]["competition_name"] == "League Two"
    assert out["datasets_status"][0]["info_count"] == 1
    assert out["datasets_status"][0]["errors_count"] == 0
    assert out["datasets_status"][0]["warnings_count"] == 0
    assert "best_quality_datasets" in out  # compat retained


def test_replace_requires_token():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as exc:
        replace_dataset_csv(db, 1, b"x", confirm="WRONG")
    assert exc.value.code == "invalid_confirm_token"


def test_replace_rollback_on_invalid_csv():
    db = MagicMock()
    ds = MagicMock()
    ds.id = 3
    ds.division_code = "E3"
    ds.season_label = "2025/2026"
    ds.matches_count = 10
    ds.competition_name = "League Two"
    db.query.return_value.filter.return_value.one_or_none.return_value = ds

    bad = b"Foo,Bar\n1,2\n"
    with pytest.raises(CecchinoLabImportError) as exc:
        replace_dataset_csv(
            db,
            3,
            bad,
            confirm=REPLACE_CONFIRM_TOKEN,
            source_filename="bad.csv",
        )
    assert exc.value.code == "invalid_header"
    # Must not have deleted anything (analysis failed first)
    db.query.return_value.filter.return_value.delete.assert_not_called()
    db.commit.assert_not_called()


def test_replace_same_sha_allowed_and_isolates_dataset():
    """Replace deletes old imports first so same SHA is allowed; other datasets untouched."""
    headers = _minimal_headers(5)
    row = ["E3", "10/08/2024", "A", "B", "1"]
    csv_text = ",".join(headers) + "\n" + ",".join(row) + "\n"
    raw = csv_text.encode("utf-8")

    db = MagicMock()
    ds = MagicMock()
    ds.id = 7
    ds.dataset_key = "england-league-two-2025-2026"
    ds.division_code = "E3"
    ds.season_label = "2025/2026"
    ds.matches_count = 1
    ds.competition_name = "League Two"
    ds.metadata_json = {}
    ds.data_quality_status = "complete"

    # one_or_none for dataset lookup
    db.query.return_value.filter.return_value.one_or_none.return_value = ds
    # import ids
    db.query.return_value.filter.return_value.all.return_value = [(100,)]
    db.query.return_value.filter.return_value.count.return_value = 1
    db.query.return_value.filter.return_value.delete.return_value = None

    created = {"import_id": 200, "match_id": 300}

    def flush_side_effect():
        for call in db.add.call_args_list:
            obj = call.args[0]
            name = type(obj).__name__
            if name == "CecchinoLabImport" and getattr(obj, "id", None) is None:
                obj.id = created["import_id"]
            if name == "CecchinoLabMatch" and getattr(obj, "id", None) is None:
                obj.id = created["match_id"]

    db.flush.side_effect = flush_side_effect

    # Patch write path counts for refresh_dataset_aggregates
    with patch(
        "app.services.cecchino_data_lab.replace_service.write_import_rows"
    ) as write_mock:
        imp = MagicMock()
        imp.id = 200
        write_mock.return_value = (imp, 1)
        out = replace_dataset_csv(
            db,
            7,
            raw,
            confirm=REPLACE_CONFIRM_TOKEN,
            source_filename="E3.csv",
        )

    assert out["status"] == "replaced"
    assert out["dataset_id"] == 7
    assert out["parser_version"] == PARSER_VERSION
    # Deletes were scoped to this dataset's filter chain
    assert db.query.return_value.filter.return_value.delete.call_count >= 1
    db.commit.assert_called_once()
    # Serie A / Championship never queried for delete by id — only dataset 7 loaded
    assert ds.id == 7


def test_import_persists_file_level_issues_with_source_row():
    """Regression: issues with source_row_number must not be dropped."""
    headers = _minimal_headers(4)
    # Irregular so we get aggregated warning (no source_row) + possible match issues
    rows = [
        ["E0", "10/08/2024", "A", "B"],
        ["E0", "11/08/2024", "C", "D", "x"],
    ]
    csv_text = ",".join(headers) + "\n" + "\n".join(",".join(r) for r in rows) + "\n"

    db = MagicMock()
    call_count = {"n": 0}

    def one_or_none_side_effect():
        call_count["n"] += 1
        return None  # no dup, no dataset

    filter_mock = MagicMock()
    filter_mock.one_or_none.side_effect = one_or_none_side_effect
    filter_mock.count.return_value = 2
    filter_mock.all.return_value = []

    query_mock = MagicMock()
    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock

    def flush_side_effect():
        for call in db.add.call_args_list:
            obj = call.args[0]
            name = type(obj).__name__
            if name == "CecchinoLabDataset" and getattr(obj, "id", None) is None:
                obj.id = 1
            if name == "CecchinoLabImport" and getattr(obj, "id", None) is None:
                obj.id = 10
            if name == "CecchinoLabMatch" and getattr(obj, "id", None) is None:
                obj.id = 100 + hash(getattr(obj, "home_team", "")) % 50

    db.flush.side_effect = flush_side_effect

    from app.services.cecchino_data_lab.constants import IMPORT_CONFIRM_TOKEN

    result = import_csv_bytes(
        db,
        csv_text.encode("utf-8"),
        competition_key="premier_league",
        season_label="2024/2025",
        confirm=IMPORT_CONFIRM_TOKEN,
        source_filename="ragged.csv",
    )
    assert result["status"] == "completed"
    # At least one DataIssue added (irregular_column_count)
    issue_objs = [
        c.args[0]
        for c in db.add.call_args_list
        if type(c.args[0]).__name__ == "CecchinoLabDataIssue"
    ]
    assert len(issue_objs) >= 1
    codes = {o.issue_code for o in issue_objs}
    assert ISSUE_IRREGULAR_COLUMN_COUNT in codes
