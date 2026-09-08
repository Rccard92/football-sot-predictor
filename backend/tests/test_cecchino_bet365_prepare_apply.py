"""Test prepare-apply Bet365 (plan read-only, zero DB writes)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.jobs.cecchino_bet365_enrichment import build_parser, main as cli_main
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    APPLY_PLAN_CSV_FILENAME,
    APPLY_PLAN_SUMMARY_FILENAME,
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_INVALID_SOURCE_VALUE,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    ENRICHMENT_MODEL_FIELDS,
    LAST_SEEN_ODDS_MAP,
)
from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    run_bet365_enrichment_dry_run,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    LabMatchCandidate,
    MatchResult,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.prepare_apply import (
    build_apply_plan_rows,
    classify_cell,
    evaluate_plan_invariants,
    load_enrichment_odds,
    parse_last_seen_odds,
    parse_odds_decimal,
    run_prepare_apply,
    sha256_file,
)


def _ko(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _candidate(**kwargs: Any) -> LabMatchCandidate:
    defaults = dict(
        id=1,
        dataset_id=10,
        competition_name="Jupiler Pro League",
        season_label="2021/2022",
        start_year=2021,
        home_team="Standard",
        away_team="Genk",
        kickoff_at=_ko(2021, 7, 23, 17, 45),
    )
    defaults.update(kwargs)
    return LabMatchCandidate(**defaults)


def _csv_row(**kwargs: Any) -> dict[str, str]:
    base = {
        "source_match_id": "m1",
        "competition_name": "Jupiler Pro League",
        "competition_api_name": "Jupiler Pro League",
        "season": "2021/2022",
        "season_start_year": "2021",
        "kickoff_utc": "2021-07-23 18:45:00",
        "home_team": "Standard",
        "away_team": "Genk",
        "bookmaker": "Bet365",
        "dc_1x_last_seen": "1.50",
        "dc_12_last_seen": "",
        "dc_x2_last_seen": "2.10",
        "ou_0_5_over_last_seen": "1.05",
        "ou_0_5_under_last_seen": "",
        "ou_1_5_over_last_seen": "1.30",
        "ou_1_5_under_last_seen": "3.40",
        "ou_3_5_over_last_seen": "",
        "ou_3_5_under_last_seen": "1.40",
        "ht_1_last_seen": "2.20",
        "ht_x_last_seen": "2.10",
        "ht_2_last_seen": "3.00",
        "dc_1x_opening": "9.99",
        "ou_0_5_over_opening": "9.99",
        "ht_1_opening": "9.99",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _empty_odds() -> dict[str, Decimal | None]:
    return {f: None for f in ENRICHMENT_MODEL_FIELDS}


def _matched_result(
    *,
    source_match_id: str = "m1",
    lab_id: int = 1,
    status: str = "EXACT",
    rule: str = "exact_normalized",
    odds_overrides: dict[str, str] | None = None,
    candidate: LabMatchCandidate | None = None,
) -> MatchResult:
    raw = _csv_row(source_match_id=source_match_id)
    if odds_overrides:
        raw.update(odds_overrides)
    csv_row = parse_csv_row(raw)
    cand = candidate or _candidate(id=lab_id)
    return MatchResult(
        csv_row=csv_row,
        match_status=status,
        matching_rule=rule,
        matched=cand,
    )


class _PrepareApplySession:
    """Session fake: SELECT candidati + SELECT odds a chunk; vieta DML."""

    def __init__(
        self,
        candidates: list[LabMatchCandidate],
        odds_by_id: dict[int, dict[str, Decimal | None]] | None = None,
    ) -> None:
        self._candidates = candidates
        self._odds_by_id = odds_by_id or {
            c.id: _empty_odds() for c in candidates
        }
        self.autoflush = False
        self.commit_calls = 0
        self.flush_calls = 0
        self.rollback_calls = 0
        self.executed_sql: list[str] = []
        self.select_odds_batches: list[list[int]] = []
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def get_bind(self) -> Any:
        return self._bind

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement).strip().lower()
        self.executed_sql.append(sql)
        forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ")
        for token in forbidden:
            if token in sql:
                raise AssertionError(f"DML vietato in prepare-apply: {sql}")

        # Odds SELECT: contiene colonne enrichment (bet365_dc_1x)
        if "bet365_dc_1x" in sql.replace(" ", ""):
            # Estrai ID dal batch corrente: usiamo i candidati filtrati
            # In SQLAlchemy compilato l'IN può non mostrare valori; simuliamo
            # restituendo tutti gli odds richiesti a chunk tramite ultima richiesta.
            # Per test chunk espliciti, load_enrichment_odds chiama per batch.
            # Recuperiamo batch da compiled params se presenti.
            params = getattr(statement, "compile", None)
            batch_ids: list[int] = []
            try:
                compiled = statement.compile(compile_kwargs={"literal_binds": False})
                # fallback: restituisci tutti gli id noti per questo test
                _ = compiled
            except Exception:  # noqa: BLE001
                pass

            # Heuristica: se la query ha .where con IN, SQLAlchemy passa params
            # Nei test unitari di load_enrichment_odds passiamo session e verifichiamo chunk count.
            # Qui restituiamo tutte le righe odds richieste filtrando su self._odds_by_id.
            # Il caller chiede batch specifici — senza params usiamo tutti gli id.
            # Meglio: parse bindparams from kwargs
            bind = kwargs.get("params") or {}
            if not bind and hasattr(statement, "_where_criteria"):
                # last resort: return all odds (chunk test uses dedicated spy)
                batch_ids = list(self._odds_by_id.keys())
            else:
                batch_ids = list(self._odds_by_id.keys())

            tuple_rows = []
            for lid in batch_ids:
                odds = self._odds_by_id.get(lid, _empty_odds())
                tuple_rows.append(
                    (lid, *[odds.get(f) for f in ENRICHMENT_MODEL_FIELDS])
                )
            self.select_odds_batches.append(batch_ids)
            return SimpleNamespace(all=lambda: tuple_rows)

        if "cecchino_lab_matches" in sql or "cecchinolabmatch" in sql.replace(" ", ""):
            rows = []
            for c in self._candidates:
                rows.append(
                    SimpleNamespace(
                        id=c.id,
                        dataset_id=c.dataset_id,
                        home_team=c.home_team,
                        away_team=c.away_team,
                        kickoff_at=c.kickoff_at,
                        competition_name=c.competition_name,
                        season_label=c.season_label,
                        start_year=c.start_year,
                    )
                )
            return SimpleNamespace(all=lambda: rows)

        return SimpleNamespace(all=lambda: [])

    def commit(self) -> None:
        self.commit_calls += 1
        raise AssertionError("commit vietato in prepare-apply")

    def flush(self, *args: Any, **kwargs: Any) -> None:
        self.flush_calls += 1
        raise AssertionError("flush vietato in prepare-apply")

    def rollback(self) -> None:
        self.rollback_calls += 1


class _ChunkRecordingSession(_PrepareApplySession):
    """Registra gli ID di ogni batch IN per verificare il chunking."""

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement).strip().lower()
        self.executed_sql.append(sql)
        forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ")
        for token in forbidden:
            if token in sql:
                raise AssertionError(f"DML vietato: {sql}")

        if "bet365_dc_1x" in sql.replace(" ", "") or (
            "cecchinolabmatch" in sql.replace(" ", "") and "bet365_dc" in sql.replace(" ", "")
        ):
            # Recupera bind values dell'IN
            batch_ids: list[int] = []
            try:
                compiled = statement.compile()
                params = compiled.params or {}
                # SQLAlchemy naming: id_1_1, id_1_2, ... oppure cecchino_lab_matches_id_1
                for key in sorted(params.keys()):
                    val = params[key]
                    if isinstance(val, int):
                        batch_ids.append(val)
                    elif isinstance(val, (list, tuple)):
                        batch_ids.extend(int(x) for x in val)
                if not batch_ids:
                    # Expanding IN: values may be in params as single list
                    for val in params.values():
                        if isinstance(val, (list, tuple)) and val and isinstance(val[0], int):
                            batch_ids = [int(x) for x in val]
                            break
            except Exception:  # noqa: BLE001
                batch_ids = []

            if not batch_ids:
                # Fallback: non riusciamo a leggere i bind — marca batch sconosciuto
                batch_ids = []

            self.select_odds_batches.append(list(batch_ids))
            rows = []
            for lid in batch_ids:
                odds = self._odds_by_id.get(lid, _empty_odds())
                rows.append((lid, *[odds.get(f) for f in ENRICHMENT_MODEL_FIELDS]))
            return SimpleNamespace(all=lambda: rows)

        return super().execute(statement, *args, **kwargs)


# --- Unit: parse / classify ---


def test_parse_empty_whitespace_no_source():
    assert parse_odds_decimal("").invalid is False
    assert parse_odds_decimal("").value is None
    assert parse_odds_decimal("   ").value is None
    assert classify_cell(None, parse_odds_decimal("")) == CELL_ACTION_NO_SOURCE_VALUE


def test_parse_numeric_and_classify():
    parsed = parse_odds_decimal("1.50")
    assert parsed.value == Decimal("1.50")
    assert classify_cell(None, parsed) == CELL_ACTION_WOULD_WRITE
    assert classify_cell(Decimal("1.5"), parsed) == CELL_ACTION_ALREADY_SAME
    assert classify_cell(Decimal("2.00"), parsed) == CELL_ACTION_CONFLICT


def test_parse_invalid_not_conflict():
    parsed = parse_odds_decimal("N/A")
    assert parsed.invalid is True
    assert classify_cell(None, parsed) == CELL_ACTION_INVALID_SOURCE_VALUE
    assert classify_cell(Decimal("1.5"), parsed) == CELL_ACTION_INVALID_SOURCE_VALUE
    assert classify_cell(None, parsed) != CELL_ACTION_CONFLICT


def test_opening_ignored_by_parse_last_seen():
    raw = _csv_row(dc_1x_last_seen="", dc_1x_opening="9.99")
    parsed = parse_last_seen_odds(
        {k: v for k, v in raw.items() if k in LAST_SEEN_ODDS_MAP or k.startswith("dc_")}
    )
    # Solo LAST_SEEN_ODDS_MAP keys
    odds = parse_last_seen_odds(
        {csv_col: raw.get(csv_col, "") for csv_col in LAST_SEEN_ODDS_MAP}
    )
    assert odds["bet365_dc_1x"].value is None
    assert odds["bet365_dc_1x"].invalid is False


def test_not_found_excluded_from_plan():
    matched = _matched_result(source_match_id="m1", lab_id=1)
    not_found = MatchResult(
        csv_row=parse_csv_row(_csv_row(source_match_id="m2", home_team="Unknown")),
        match_status="NOT_FOUND",
        matching_rule="not_found",
        matched=None,
    )
    rows = build_apply_plan_rows([matched, not_found], {1: _empty_odds()})
    assert len(rows) == 1
    assert rows[0].source_match_id == "m1"


def test_plan_actions_per_field_and_invariants_valid(tmp_path: Path):
    matched = _matched_result(source_match_id="m1", lab_id=1)
    db_odds = {1: _empty_odds()}
    plan_rows = build_apply_plan_rows([matched], db_odds)
    assert len(plan_rows) == 1
    actions = plan_rows[0].field_actions
    assert actions["bet365_dc_1x"] == CELL_ACTION_WOULD_WRITE
    assert actions["bet365_dc_12"] == CELL_ACTION_NO_SOURCE_VALUE

    inv = evaluate_plan_invariants(
        plan_rows=plan_rows,
        simulated_results=[matched],
        db_odds=db_odds,
    )
    assert inv["PLAN_VALID"] is True
    assert inv["plan_rows"] == inv["matched_rows"] == 1
    assert inv["duplicate_source_match_ids"] == 0
    assert inv["duplicate_lab_match_ids"] == 0
    assert inv["conflict_cells"] == 0
    assert inv["invalid_source_value_cells"] == 0


def test_duplicate_lab_match_id_invalidates():
    r1 = _matched_result(source_match_id="m1", lab_id=1)
    r2 = _matched_result(source_match_id="m2", lab_id=1)
    db_odds = {1: _empty_odds()}
    plan_rows = build_apply_plan_rows([r1, r2], db_odds)
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[r1, r2], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert inv["duplicate_lab_match_ids"] >= 1
    assert "duplicate_lab_match_ids" in inv["plan_validity_failures"]


def test_duplicate_source_match_id_invalidates():
    r1 = _matched_result(source_match_id="m1", lab_id=1)
    r2 = _matched_result(source_match_id="m1", lab_id=2)
    db_odds = {1: _empty_odds(), 2: _empty_odds()}
    plan_rows = build_apply_plan_rows([r1, r2], db_odds)
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[r1, r2], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert inv["duplicate_source_match_ids"] >= 1


def test_conflict_invalidates_plan():
    matched = _matched_result(
        source_match_id="m1",
        lab_id=1,
        odds_overrides={"dc_1x_last_seen": "1.50"},
    )
    db_odds = {1: {**_empty_odds(), "bet365_dc_1x": Decimal("9.99")}}
    plan_rows = build_apply_plan_rows([matched], db_odds)
    assert plan_rows[0].field_actions["bet365_dc_1x"] == CELL_ACTION_CONFLICT
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[matched], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert inv["conflict_cells"] >= 1


def test_already_same_and_would_write():
    matched = _matched_result(
        odds_overrides={"dc_1x_last_seen": "1.50", "dc_x2_last_seen": "2.10"}
    )
    db_odds = {
        1: {
            **_empty_odds(),
            "bet365_dc_1x": Decimal("1.5"),
            "bet365_dc_x2": None,
        }
    }
    plan_rows = build_apply_plan_rows([matched], db_odds)
    assert plan_rows[0].field_actions["bet365_dc_1x"] == CELL_ACTION_ALREADY_SAME
    assert plan_rows[0].field_actions["bet365_dc_x2"] == CELL_ACTION_WOULD_WRITE


def test_invalid_source_value_invalidates_not_as_conflict():
    matched = _matched_result(
        odds_overrides={"dc_1x_last_seen": "abc"}
    )
    db_odds = {1: _empty_odds()}
    plan_rows = build_apply_plan_rows([matched], db_odds)
    assert (
        plan_rows[0].field_actions["bet365_dc_1x"]
        == CELL_ACTION_INVALID_SOURCE_VALUE
    )
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[matched], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert inv["invalid_source_value_cells"] >= 1
    assert inv["invalid_source_value_rows"] >= 1
    assert inv["conflict_cells"] == 0
    assert "invalid_source_value_cells" in inv["plan_validity_failures"]
    assert "conflict_cells" not in inv["plan_validity_failures"]


def test_empty_source_match_id_invalidates():
    matched = _matched_result(source_match_id="")
    # force empty after parse
    matched.csv_row.source_match_id = ""
    db_odds = {1: _empty_odds()}
    plan_rows = build_apply_plan_rows([matched], db_odds)
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[matched], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert "empty_source_match_id" in inv["plan_validity_failures"]


def test_missing_lab_match_id_invalidates():
    matched = _matched_result()
    matched.matched = None  # type: ignore[assignment]
    # still MATCHED status but no lab id — build will set lab_match_id None
    # Need status still MATCHED for inclusion
    from app.services.cecchino_data_lab.bet365_enrichment.constants import (
        MATCH_STATUS_EXACT,
    )

    matched.match_status = MATCH_STATUS_EXACT
    db_odds = {1: _empty_odds()}
    plan_rows = build_apply_plan_rows([matched], db_odds)
    assert plan_rows[0].lab_match_id is None
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[matched], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert "missing_lab_match_id" in inv["plan_validity_failures"]


def test_lab_id_must_exist_in_db_select():
    matched = _matched_result(lab_id=99)
    db_odds: dict[int, dict[str, Decimal | None]] = {}  # SELECT non ha restituito 99
    plan_rows = build_apply_plan_rows([matched], db_odds)
    inv = evaluate_plan_invariants(
        plan_rows=plan_rows, simulated_results=[matched], db_odds=db_odds
    )
    assert inv["PLAN_VALID"] is False
    assert "lab_match_id_missing_from_db_select" in inv["plan_validity_failures"]


def test_load_enrichment_odds_chunks():
    odds_by_id = {i: _empty_odds() for i in range(1, 6)}
    session = _ChunkRecordingSession(
        candidates=[_candidate(id=i) for i in range(1, 6)],
        odds_by_id=odds_by_id,
    )
    result = load_enrichment_odds(session, [1, 2, 3, 4, 5], chunk_size=2)  # type: ignore[arg-type]
    assert len(result) == 5
    assert len(session.select_odds_batches) == 3  # 2+2+1
    for batch in session.select_odds_batches:
        assert len(batch) <= 2
    for sql in session.executed_sql:
        assert "update " not in sql
        assert "insert " not in sql


def test_run_prepare_apply_writes_plan_and_summary_freeze(tmp_path: Path):
    csv_path = tmp_path / "src.csv"
    fieldnames = list(_csv_row().keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(_csv_row())

    out = tmp_path / "out"
    matched = _matched_result()
    session = _PrepareApplySession([_candidate()], {1: _empty_odds()})

    summary = run_prepare_apply(
        session=session,  # type: ignore[arg-type]
        csv_path=csv_path,
        output_dir=out,
        simulated_results=[matched],
        csv_rows_total=1,
        read_only_transaction=False,
    )

    plan_path = out / APPLY_PLAN_CSV_FILENAME
    summary_path = out / APPLY_PLAN_SUMMARY_FILENAME
    assert plan_path.is_file()
    assert summary_path.is_file()
    assert summary["PLAN_VALID"] is True
    assert summary["db_writes"] is False
    assert summary["source_csv_sha256"] == sha256_file(csv_path)
    assert summary["apply_plan_sha256"] == sha256_file(plan_path)
    assert summary["would_update_cells"] > 0

    with plan_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        assert len(rows) == 1
        assert "bet365_dc_1x" in reader.fieldnames
        assert "bet365_dc_1x__action" in reader.fieldnames
        assert rows[0]["bet365_dc_1x__action"] == CELL_ACTION_WOULD_WRITE
        assert rows[0]["bet365_dc_12__action"] == CELL_ACTION_NO_SOURCE_VALUE

    with summary_path.open("r", encoding="utf-8") as fh:
        disk = json.load(fh)
    assert disk["PLAN_VALID"] is True
    assert disk["apply_plan_sha256"] == summary["apply_plan_sha256"]


def test_prepare_apply_end_to_end_no_db_writes(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    fieldnames = list(_csv_row().keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(_csv_row(home_team="Standard", away_team="Genk"))
        writer.writerow(
            _csv_row(
                source_match_id="m_nf",
                home_team="Unknown FC",
                away_team="Other FC",
            )
        )

    out = tmp_path / "out"
    session = _PrepareApplySession([_candidate()], {1: _empty_odds()})

    summary = run_bet365_enrichment_dry_run(
        csv_path=csv_path,
        output_dir=out,
        session=session,  # type: ignore[arg-type]
        prepare_apply=True,
    )

    assert summary["prepare_apply"] is True
    assert summary["discover_aliases"] is True
    assert summary["db_writes"] is False
    assert session.commit_calls == 0
    assert session.flush_calls == 0
    assert (out / APPLY_PLAN_CSV_FILENAME).is_file()
    assert (out / APPLY_PLAN_SUMMARY_FILENAME).is_file()

    apply = summary["apply_plan"]
    assert apply["db_writes"] is False
    assert apply["matched_rows"] == apply["plan_rows"]
    # NOT_FOUND escluso dal plan
    assert apply["not_found_rows"] >= 1
    assert apply["plan_rows"] == 1

    for sql in session.executed_sql:
        low = sql.lower()
        assert "insert " not in low
        assert "update " not in low
        assert "delete " not in low
        # legacy / snapshot non toccati
        assert "historical_match_snapshot" not in low
        assert "historical_scan_run" not in low
        assert "bet365_home" not in low or "bet365_dc" in low.replace(" ", "")


def test_cli_prepare_apply_requires_dry_run():
    parser = build_parser()
    with pytest.raises(SystemExit):
        # argparse error via main
        cli_main(
            [
                "--csv",
                "x.csv",
                "--output-dir",
                "out",
                "--prepare-apply",
            ]
        )


def test_legacy_bet365_columns_not_in_plan_actions():
    matched = _matched_result()
    plan_rows = build_apply_plan_rows([matched], {1: _empty_odds()})
    assert "bet365_home" not in plan_rows[0].field_actions
    assert "bet365_over_25" not in plan_rows[0].field_actions
    assert set(plan_rows[0].field_actions) == set(ENRICHMENT_MODEL_FIELDS)
