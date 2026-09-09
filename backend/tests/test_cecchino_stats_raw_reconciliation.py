"""Test dry-run riconciliazione stats da raw_json (zero scritture DB)."""

from __future__ import annotations

import ast
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    ENRICHMENT_MODEL_FIELDS,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.classify import (
    classify_cell,
    parse_source_for_field,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.constants import (
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    COVERAGE_GROUPS,
    RAW_TO_DB_FIELD_MAP,
    STATS_MODEL_FIELDS,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.dry_run import (
    MatchScanRow,
    build_summary_from_rows,
    classify_match,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.report import (
    write_reports,
)


def _ko() -> datetime:
    return datetime(2022, 8, 13, 15, 0, tzinfo=timezone.utc)


def _raw(**kwargs: Any) -> dict[str, Any]:
    base = {
        "Referee": "A Taylor",
        "HS": "10",
        "AS": "8",
        "HST": "4",
        "AST": "3",
        "HF": "12",
        "AF": "11",
        "HC": "5",
        "AC": "4",
        "HY": "2",
        "AY": "1",
        "HR": "0",
        "AR": "0",
        "HTHG": "1",
        "HTAG": "0",
        "HTR": "H",
        "FTHG": "2",
        "FTAG": "1",
        "FTR": "H",
    }
    base.update(kwargs)
    return base


def _db(**kwargs: Any) -> dict[str, Any]:
    base = {f: None for f in STATS_MODEL_FIELDS}
    base.update(kwargs)
    return base


def _row(
    *,
    lab_match_id: int = 1,
    competition: str = "Premier League",
    season: str = "2022/2023",
    raw: dict[str, Any] | None = None,
    db: dict[str, Any] | None = None,
    source_file: str = "E0.csv",
    source_row: int = 2,
) -> MatchScanRow:
    return MatchScanRow(
        lab_match_id=lab_match_id,
        source_file=source_file,
        source_row=source_row,
        competition=competition,
        season=season,
        kickoff=_ko(),
        home_team="Arsenal",
        away_team="Everton",
        raw_json=raw,
        db_values=db if db is not None else _db(),
    )


# --- classify unit ---


@pytest.mark.parametrize(
    "csv_key,field",
    list(RAW_TO_DB_FIELD_MAP.items()),
)
def test_raw_to_db_mapping_keys(csv_key: str, field: str):
    assert RAW_TO_DB_FIELD_MAP[csv_key] == field


def test_home_away_shots_mapping():
    raw = _raw(HS="15", AS="7")
    hs, inv_h = parse_source_for_field("home_shots", raw)
    as_, inv_a = parse_source_for_field("away_shots", raw)
    assert (hs, inv_h) == (15, False)
    assert (as_, inv_a) == (7, False)


def test_hst_ast_hf_af_hc_ac_hy_ay_hr_ar_referee_ht():
    raw = _raw()
    assert parse_source_for_field("home_shots_on_target", raw)[0] == 4
    assert parse_source_for_field("away_shots_on_target", raw)[0] == 3
    assert parse_source_for_field("home_fouls", raw)[0] == 12
    assert parse_source_for_field("away_fouls", raw)[0] == 11
    assert parse_source_for_field("home_corners", raw)[0] == 5
    assert parse_source_for_field("away_corners", raw)[0] == 4
    assert parse_source_for_field("home_yellow_cards", raw)[0] == 2
    assert parse_source_for_field("away_yellow_cards", raw)[0] == 1
    assert parse_source_for_field("home_red_cards", raw)[0] == 0
    assert parse_source_for_field("away_red_cards", raw)[0] == 0
    assert parse_source_for_field("referee", raw)[0] == "A Taylor"
    assert parse_source_for_field("ht_home_goals", raw)[0] == 1
    assert parse_source_for_field("ht_away_goals", raw)[0] == 0
    assert parse_source_for_field("ht_result", raw)[0] == "H"


def test_null_blank_source_no_source_value():
    assert (
        classify_cell(
            field="home_shots",
            db_value=None,
            source_value=None,
            source_invalid=False,
        )
        == CELL_ACTION_NO_SOURCE_VALUE
    )
    raw = _raw(HS="")
    val, inv = parse_source_for_field("home_shots", raw)
    assert val is None and inv is False
    assert (
        classify_cell(
            field="home_shots", db_value=None, source_value=val, source_invalid=inv
        )
        == CELL_ACTION_NO_SOURCE_VALUE
    )


def test_would_write_already_same_conflict():
    assert (
        classify_cell(
            field="home_shots",
            db_value=None,
            source_value=10,
            source_invalid=False,
        )
        == CELL_ACTION_WOULD_WRITE
    )
    assert (
        classify_cell(
            field="home_shots",
            db_value=10,
            source_value=10,
            source_invalid=False,
        )
        == CELL_ACTION_ALREADY_SAME
    )
    assert (
        classify_cell(
            field="home_shots",
            db_value=9,
            source_value=10,
            source_invalid=False,
        )
        == CELL_ACTION_CONFLICT
    )


def test_zero_is_valid_int_not_null():
    """0 da raw non è NULL: DB NULL + 0 → WOULD_WRITE."""
    assert (
        classify_cell(
            field="home_red_cards",
            db_value=None,
            source_value=0,
            source_invalid=False,
        )
        == CELL_ACTION_WOULD_WRITE
    )
    assert (
        classify_cell(
            field="home_red_cards",
            db_value=0,
            source_value=0,
            source_invalid=False,
        )
        == CELL_ACTION_ALREADY_SAME
    )


def test_no_raw_match_status():
    status, audit = classify_match(_row(raw=None, db=_db(home_shots=5)))
    assert status == "NO_RAW"
    assert all(a["action"] == CELL_ACTION_NO_SOURCE_VALUE for a in audit)
    assert len(audit) == len(STATS_MODEL_FIELDS)


# --- summary / coverage ---


def test_would_write_counts_as_source_coverage():
    row = _row(raw=_raw(HS="10"), db=_db())  # all DB null → WOULD_WRITE where source
    summary, _ = build_summary_from_rows([row])
    hs = summary["GLOBAL"]["fields"]["home_shots"]
    assert hs["would_write"] == 1
    assert hs["source_non_null"] == 1
    assert hs["source_coverage_pct"] == 100.0
    assert hs["db_coverage_pct"] == 0.0
    assert hs["aligned_coverage_pct"] == 0.0


def test_aligned_coverage_pct_formula():
    rows = [
        _row(
            lab_match_id=1,
            raw=_raw(HS="10"),
            db=_db(home_shots=10),  # SAME
        ),
        _row(
            lab_match_id=2,
            raw=_raw(HS="8"),
            db=_db(),  # WOULD_WRITE
        ),
    ]
    # Need full raw for other fields — use full _raw; only HS differs in DB
    rows[0] = _row(
        lab_match_id=1,
        raw=_raw(),
        db=_db(
            referee="A Taylor",
            home_shots=10,
            away_shots=8,
            home_shots_on_target=4,
            away_shots_on_target=3,
            home_fouls=12,
            away_fouls=11,
            home_corners=5,
            away_corners=4,
            home_yellow_cards=2,
            away_yellow_cards=1,
            home_red_cards=0,
            away_red_cards=0,
            ht_home_goals=1,
            ht_away_goals=0,
            ht_result="H",
            ft_home_goals=2,
            ft_away_goals=1,
            ft_result="H",
        ),
    )
    rows[1] = _row(lab_match_id=2, raw=_raw(HS="8"), db=_db())
    summary, _ = build_summary_from_rows(rows)
    hs = summary["GLOBAL"]["fields"]["home_shots"]
    assert hs["source_non_null"] == 2
    assert hs["already_same"] == 1
    assert hs["would_write"] == 1
    assert hs["aligned_coverage_pct"] == 50.0


def test_breakdown_views_no_cross_season():
    rows = [
        _row(lab_match_id=1, competition="Premier League", season="2021/2022"),
        _row(lab_match_id=2, competition="Premier League", season="2022/2023"),
        _row(lab_match_id=3, competition="Serie A", season="2022/2023"),
    ]
    rows = [
        _row(
            lab_match_id=r.lab_match_id,
            competition=r.competition,
            season=r.season,
            raw=_raw(),
            db=_db(),
        )
        for r in rows
    ]
    summary, _ = build_summary_from_rows(rows)
    assert "GLOBAL" in summary
    assert "COMPETITION" in summary
    assert "COMPETITION_SEASON" in summary
    assert "SEASON" not in summary  # no cross-competition season view
    assert set(summary["COMPETITION"]) == {"Premier League", "Serie A"}
    assert "Premier League||2021/2022" in summary["COMPETITION_SEASON"]
    assert "Premier League||2022/2023" in summary["COMPETITION_SEASON"]
    assert "Serie A||2022/2023" in summary["COMPETITION_SEASON"]
    assert summary["COMPETITION"]["Premier League"]["matches_total"] == 2
    assert summary["COMPETITION_SEASON"]["Serie A||2022/2023"]["matches_total"] == 1


def test_audit_cardinality_one_per_match_field(tmp_path: Path):
    rows = [
        _row(lab_match_id=1, raw=_raw(), db=_db()),
        _row(lab_match_id=2, raw=_raw(), db=_db(home_shots=10)),
    ]
    summary, audit = build_summary_from_rows(rows)
    pairs = [(a["lab_match_id"], a["field"]) for a in audit]
    assert len(pairs) == len(set(pairs))
    assert len(audit) == 2 * len(STATS_MODEL_FIELDS)

    paths = write_reports(output_dir=tmp_path, summary=summary, audit_rows=audit)
    with Path(paths["audit_path"]).open(encoding="utf-8") as fh:
        reader = list(csv.DictReader(fh))
    csv_pairs = [(int(r["lab_match_id"]), r["field"]) for r in reader]
    assert len(csv_pairs) == len(set(csv_pairs))


def test_idempotency():
    rows = [_row(lab_match_id=1, raw=_raw(), db=_db(home_shots=10))]
    s1, a1 = build_summary_from_rows(rows)
    s2, a2 = build_summary_from_rows(rows)
    assert s1["GLOBAL"] == s2["GLOBAL"]
    assert len(a1) == len(a2)
    assert [x["action"] for x in a1] == [x["action"] for x in a2]


def test_unique_match_counts_no_duplication():
    """Duplicati lab_match_id non devono gonfiare matches_total né i contatori."""
    row = _row(lab_match_id=42, raw=_raw(), db=_db())
    summary, audit = build_summary_from_rows([row, row])
    assert summary["matches_total"] == 1
    assert summary["unmatched_rows"] == 0
    assert summary["ambiguous_rows"] == 0
    assert len(audit) == len(STATS_MODEL_FIELDS)
    assert summary["GLOBAL"]["fields"]["home_shots"]["would_write"] == 1


# --- CORE BLOCK regression ---


def test_stats_fields_disjoint_from_bet365_enrichment():
    overlap = set(STATS_MODEL_FIELDS) & set(ENRICHMENT_MODEL_FIELDS)
    assert overlap == set()


def test_core_block_enrichment_fields_unchanged_snapshot():
    """Guard: le 12 colonne BLOCCO 1 enrichment non devono cambiare in questo task."""
    expected = (
        "bet365_dc_1x",
        "bet365_dc_12",
        "bet365_dc_x2",
        "bet365_over_05",
        "bet365_under_05",
        "bet365_over_15",
        "bet365_under_15",
        "bet365_over_35",
        "bet365_under_35",
        "bet365_ht_home",
        "bet365_ht_draw",
        "bet365_ht_away",
    )
    assert ENRICHMENT_MODEL_FIELDS == expected


def test_stats_package_does_not_import_core_engines():
    """Il package stats non deve importare runner/pattern/KPI/signals."""
    pkg = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino_data_lab" / "stats_raw_reconciliation"
    forbidden_substrings = (
        "historical_scan",
        "pattern",
        "purchasability",
        "kpi_signals",
        "bet365_enrichment",
        "goal_intensity",
        "cecchino_runner",
    )
    for py in pkg.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden_substrings:
                        assert bad not in alias.name, f"{py.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for bad in forbidden_substrings:
                    assert bad not in mod, f"{py.name} imports from {mod}"


def test_coverage_groups_cover_expected_keys():
    assert set(COVERAGE_GROUPS) == {
        "referee",
        "shots",
        "shots_on_target",
        "fouls",
        "corners",
        "yellow_cards",
        "red_cards",
        "halftime",
        "fulltime",
    }
