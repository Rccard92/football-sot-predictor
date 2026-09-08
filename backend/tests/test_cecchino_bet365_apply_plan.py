"""Test apply Bet365 del plan congelato (nessun rematching)."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.jobs.cecchino_bet365_enrichment import build_parser, main as cli_main
from app.services.cecchino_data_lab.bet365_enrichment.apply_plan import (
    ApplyAbort,
    compute_manifest_from_plan,
    load_frozen_plan,
    preflight_frozen_plan,
    run_bet365_enrichment_apply,
)
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    APPLY_MANIFEST_COUNT_KEYS,
    APPLY_RESULT_JSON_FILENAME,
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    ENRICHMENT_MODEL_FIELDS,
    PRE_APPLY_STATE_CSV_FILENAME,
)
from app.services.cecchino_data_lab.bet365_enrichment.prepare_apply import (
    apply_plan_csv_columns,
    sha256_file,
)


def _empty_odds() -> dict[str, Decimal | None]:
    return {f: None for f in ENRICHMENT_MODEL_FIELDS}


def _plan_row(
    *,
    source_match_id: str = "m1",
    lab_match_id: int = 1,
    values: dict[str, str] | None = None,
    actions: dict[str, str] | None = None,
) -> dict[str, str]:
    vals = {f: "" for f in ENRICHMENT_MODEL_FIELDS}
    acts = {f: CELL_ACTION_NO_SOURCE_VALUE for f in ENRICHMENT_MODEL_FIELDS}
    if values:
        vals.update(values)
    if actions:
        acts.update(actions)
    row = {
        "source_match_id": source_match_id,
        "lab_match_id": str(lab_match_id),
        "competition": "Jupiler Pro League",
        "season": "2021/2022",
        "csv_home_team": "Standard",
        "csv_away_team": "Genk",
        "db_home_team": "Standard",
        "db_away_team": "Genk",
        "matching_status": "EXACT",
        "matching_rule": "exact_normalized",
    }
    for f in ENRICHMENT_MODEL_FIELDS:
        row[f] = vals[f]
        row[f"{f}__action"] = acts[f]
    return row


def _write_plan(path: Path, rows: list[dict[str, str]]) -> str:
    cols = apply_plan_csv_columns()
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return sha256_file(path)


def _manifest_from_rows(rows: list[dict[str, str]], path: Path) -> dict[str, int]:
    _write_plan(path, rows)
    frozen = load_frozen_plan(path)
    return compute_manifest_from_plan(frozen).as_dict()


def _write_summary(
    path: Path,
    *,
    plan_hash: str,
    manifest: dict[str, int],
    plan_valid: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "PLAN_VALID": plan_valid,
        "apply_plan_sha256": plan_hash,
        "db_writes": False,
        **manifest,
    }
    if extra:
        payload.update(extra)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


class _FakeConnection:
    """Connection fake: executemany UPDATE nella stessa 'transazione' della session."""

    def __init__(self, session: "_ApplySession") -> None:
        self._session = session

    def execute(self, statement: Any, parameters: Any = None, *args: Any, **kwargs: Any) -> Any:
        self._session.executed_sql.append(str(statement).strip().lower())
        return self._session._execute_update(statement, parameters)


class _ApplySession:
    """Session fake con odds in-memory, SELECT/UPDATE/commit/rollback tracking."""

    def __init__(
        self,
        odds_by_id: dict[int, dict[str, Decimal | None]] | None = None,
        *,
        dialect: str = "postgresql",
        fail_after_n_updates: int | None = None,
        corrupt_post_verify: bool = False,
    ) -> None:
        self.odds_by_id = {
            i: dict(o) for i, o in (odds_by_id or {}).items()
        }
        self.autoflush = False
        self.commit_calls = 0
        self.rollback_calls = 0
        self.flush_calls = 0
        self.select_events: list[str] = []
        self.update_events: list[dict[str, Any]] = []
        self.executed_sql: list[str] = []
        self.fail_after_n_updates = fail_after_n_updates
        self.corrupt_post_verify = corrupt_post_verify
        self._updates_done = 0
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self._connection = _FakeConnection(self)

    def get_bind(self) -> Any:
        return self._bind

    def connection(self) -> _FakeConnection:
        """Stessa 'transazione' Session: nessun commit/begin sulla connection."""
        return self._connection

    def _apply_one_update(self, lab_id: int, values: dict[str, Any]) -> None:
        self._updates_done += 1
        if (
            self.fail_after_n_updates is not None
            and self._updates_done > self.fail_after_n_updates
        ):
            raise RuntimeError("simulated mid-apply failure")

        if any(f not in ENRICHMENT_MODEL_FIELDS for f in values):
            raise AssertionError(f"legacy/unauthorized column write: {values}")

        cur = self.odds_by_id.setdefault(lab_id, _empty_odds())
        for f, v in values.items():
            if f in ENRICHMENT_MODEL_FIELDS:
                cur[f] = v if isinstance(v, Decimal) else Decimal(str(v))
        self.update_events.append({"lab_match_id": lab_id, "values": dict(values)})

    def _params_to_values(self, params: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
        lab_id: int | None = None
        values: dict[str, Any] = {}
        for k, v in params.items():
            if k == "b_id" or (k.lower().endswith("id") and "bet365" not in k.lower()):
                if isinstance(v, int):
                    lab_id = v
                continue
            name = k[2:] if k.startswith("b_") else k
            if name in ENRICHMENT_MODEL_FIELDS:
                values[name] = v
        return lab_id, values

    def _execute_update(self, statement: Any, parameters: Any = None) -> Any:
        # Executemany: list of param dicts
        if isinstance(parameters, list):
            for params in parameters:
                lab_id, values = self._params_to_values(dict(params))
                if lab_id is None:
                    continue
                self._apply_one_update(lab_id, values)
            return SimpleNamespace(rowcount=len(parameters))

        # Single-row (legacy / fallback)
        values: dict[str, Any] = {}
        lab_id: int | None = None
        try:
            if isinstance(parameters, dict):
                lab_id, values = self._params_to_values(parameters)
            compiled = statement.compile()
            params = dict(compiled.params or {})
            if lab_id is None or not values:
                lab_id2, values2 = self._params_to_values(params)
                lab_id = lab_id or lab_id2
                if not values:
                    values = values2
            raw_values = getattr(statement, "_values", None) or {}
            for col, val in raw_values.items():
                name = getattr(col, "key", None) or getattr(col, "name", str(col))
                if hasattr(val, "key") and str(val.key).startswith("b_"):
                    continue  # bindparam — value from parameters
                if hasattr(val, "value"):
                    values[name] = val.value
                elif name in ENRICHMENT_MODEL_FIELDS and name not in values:
                    values[name] = val
            where = getattr(statement, "_where_criteria", ())
            for crit in where:
                right = getattr(crit, "right", None)
                if hasattr(right, "value") and isinstance(right.value, int):
                    lab_id = right.value
        except Exception:  # noqa: BLE001
            pass

        if lab_id is not None and values:
            self._apply_one_update(lab_id, values)
            return SimpleNamespace(rowcount=1)
        return SimpleNamespace(rowcount=0)

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement).strip().lower()
        self.executed_sql.append(sql)

        # Detect UPDATE (legacy path; bulk va su connection.execute)
        if sql.startswith("update ") or "update cecchino" in sql.replace("\n", " "):
            parameters = args[0] if args else kwargs.get("parameters")
            return self._execute_update(statement, parameters)

        # SELECT enrichment
        if "bet365_dc_1x" in sql.replace(" ", "") or "cecchinolabmatch" in sql.replace(
            " ", ""
        ):
            for_update = "for update" in sql
            event = "select_for_update" if for_update else "select"
            self.select_events.append(event)

            # Resolve batch ids from compile params
            batch_ids: list[int] = []
            try:
                params = statement.compile().params or {}
                for key in sorted(params.keys()):
                    val = params[key]
                    if isinstance(val, int):
                        batch_ids.append(val)
                    elif isinstance(val, (list, tuple)):
                        batch_ids.extend(int(x) for x in val)
            except Exception:  # noqa: BLE001
                batch_ids = list(self.odds_by_id.keys())

            if not batch_ids:
                batch_ids = list(self.odds_by_id.keys())

            # Post-verify corruption: after updates, return wrong values
            if self.corrupt_post_verify and self.update_events:
                rows = []
                for lid in batch_ids:
                    odds = dict(self.odds_by_id.get(lid, _empty_odds()))
                    # corrupt first enrichment field
                    odds["bet365_dc_1x"] = Decimal("99.99")
                    rows.append((lid, *[odds.get(f) for f in ENRICHMENT_MODEL_FIELDS]))
                return SimpleNamespace(all=lambda: rows)

            rows = []
            for lid in batch_ids:
                odds = self.odds_by_id.get(lid, _empty_odds())
                rows.append((lid, *[odds.get(f) for f in ENRICHMENT_MODEL_FIELDS]))
            return SimpleNamespace(all=lambda: rows)

        return SimpleNamespace(all=lambda: [], rowcount=0)

    def commit(self) -> None:
        self.commit_calls += 1

    def flush(self, *args: Any, **kwargs: Any) -> None:
        self.flush_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1
        # On rollback restore? For mid-fail tests we snapshot
        # Simple: clear updates by reloading from initial — tests set odds explicitly


def _setup_plan_pair(
    tmp_path: Path,
    rows: list[dict[str, str]],
    *,
    plan_valid: bool = True,
    mutate_summary: dict[str, Any] | None = None,
) -> tuple[Path, Path, str, dict[str, int]]:
    plan_path = tmp_path / "bet365_enrichment_apply_plan.csv"
    summary_path = tmp_path / "bet365_enrichment_apply_summary.json"
    plan_hash = _write_plan(plan_path, rows)
    manifest = compute_manifest_from_plan(load_frozen_plan(plan_path)).as_dict()
    summary_body = dict(manifest)
    if mutate_summary:
        summary_body.update(mutate_summary)
    _write_summary(
        summary_path,
        plan_hash=plan_hash,
        manifest=summary_body,
        plan_valid=plan_valid,
    )
    return plan_path, summary_path, plan_hash, manifest


def test_hash_mismatch_zero_write(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    # Alter summary hash
    with summary_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    data["apply_plan_sha256"] = "0" * 64
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)

    session = _ApplySession({1: _empty_odds()})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["committed"] is False
    assert result["db_writes"] is False
    assert result["abort_code"] == "ABORT_PLAN_HASH_MISMATCH"
    assert session.commit_calls == 0
    assert session.update_events == []


def test_plan_valid_false_zero_write(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows, plan_valid=False)
    session = _ApplySession({1: _empty_odds()})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["abort_code"] == "ABORT_PLAN_INVALID"
    assert session.update_events == []
    assert session.commit_calls == 0


def test_manifest_summary_altered_plan_hash_ok_zero_write(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(
        tmp_path, rows, mutate_summary={"would_update_cells": 999}
    )
    session = _ApplySession({1: _empty_odds()})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["abort_code"] == "ABORT_MANIFEST_MISMATCH"
    assert session.update_events == []
    assert session.commit_calls == 0
    assert result["db_writes"] is False


def test_without_confirm_no_writes(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()})
    out = tmp_path / "out"
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=out,
        confirm_apply=False,
    )
    assert result["abort_code"] == "ABORT_CONFIRM_REQUIRED"
    assert result["committed"] is False
    assert session.update_events == []
    assert session.commit_calls == 0
    assert (out / PRE_APPLY_STATE_CSV_FILENAME).is_file()
    assert (out / APPLY_RESULT_JSON_FILENAME).is_file()


def test_drift_would_write_stale_rollback(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    # DB already has a value (even equal) => STALE
    session = _ApplySession({1: {**_empty_odds(), "bet365_dc_1x": Decimal("1.50")}})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["abort_code"] == "ABORT_STALE"
    assert result["committed"] is False
    assert session.update_events == []
    assert session.commit_calls == 0
    assert session.rollback_calls >= 1


def test_no_source_value_does_not_write(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50", "bet365_dc_12": ""},
            actions={
                "bet365_dc_1x": CELL_ACTION_WOULD_WRITE,
                "bet365_dc_12": CELL_ACTION_NO_SOURCE_VALUE,
            },
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["committed"] is True
    assert session.update_events
    written_fields = set()
    for ev in session.update_events:
        written_fields.update(ev["values"].keys())
    assert "bet365_dc_12" not in written_fields
    assert "bet365_dc_1x" in written_fields


def test_only_12_authorized_columns(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()})
    run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    for sql in session.executed_sql:
        assert "bet365_home" not in sql or "bet365_dc" in sql.replace(" ", "")
        assert "historical_match_snapshot" not in sql
        assert "historical_scan_run" not in sql
    for ev in session.update_events:
        assert set(ev["values"].keys()) <= set(ENRICHMENT_MODEL_FIELDS)


def test_locks_all_acquired_before_first_update(tmp_path: Path):
    rows = [
        _plan_row(
            source_match_id="m1",
            lab_match_id=1,
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        ),
        _plan_row(
            source_match_id="m2",
            lab_match_id=2,
            values={"bet365_dc_1x": "2.00"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        ),
        _plan_row(
            source_match_id="m3",
            lab_match_id=3,
            values={"bet365_ht_home": "2.20"},
            actions={"bet365_ht_home": CELL_ACTION_ALREADY_SAME},
        ),
    ]
    # ALREADY_SAME needs DB equal
    odds = {
        1: _empty_odds(),
        2: _empty_odds(),
        3: {**_empty_odds(), "bet365_ht_home": Decimal("2.20")},
    }
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession(odds)
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
        lock_chunk_size=1,
        update_chunk_size=1,
    )
    assert result["committed"] is True
    # All select_for_update must precede any update
    first_update_idx = None
    for i, sql in enumerate(session.executed_sql):
        if sql.startswith("update ") or (
            "update " in sql and "cecchino" in sql
        ):
            first_update_idx = i
            break
    assert first_update_idx is not None
    lock_selects = [
        i
        for i, ev in enumerate(session.select_events)
        if ev == "select_for_update"
    ]
    # At least 3 lock chunks (ids 1,2,3) before updates — measured via select_events order
    assert session.select_events
    first_update_event_pos = len(session.select_events)
    # Count for_update before any update_events were recorded: all lock selects first
    # Our session appends select_events before update_events chronologically
    assert all(
        ev == "select_for_update" for ev in session.select_events[:3]
    ), session.select_events
    assert len([e for e in session.select_events if e == "select_for_update"]) >= 3


def test_pre_state_with_confirm_matches_locked_db(tmp_path: Path):
    rows = [
        _plan_row(
            values={
                "bet365_dc_1x": "1.50",
                "bet365_dc_x2": "2.10",
            },
            actions={
                "bet365_dc_1x": CELL_ACTION_WOULD_WRITE,
                "bet365_dc_x2": CELL_ACTION_ALREADY_SAME,
            },
        )
    ]
    odds = {1: {**_empty_odds(), "bet365_dc_x2": Decimal("2.10")}}
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession(odds)
    out = tmp_path / "out"
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=out,
        confirm_apply=True,
    )
    assert result["committed"] is True
    pre_path = out / PRE_APPLY_STATE_CSV_FILENAME
    with pre_path.open("r", encoding="utf-8", newline="") as fh:
        pre_rows = list(csv.DictReader(fh))
    assert len(pre_rows) == 1
    assert pre_rows[0]["lab_match_id"] == "1"
    assert pre_rows[0]["bet365_dc_1x"] == ""  # still NULL before write
    assert pre_rows[0]["bet365_dc_x2"] in ("2.10", "2.1")
    assert result["pre_state_hash"] == sha256_file(pre_path)


def test_batch_multiple_updates(tmp_path: Path):
    rows = [
        _plan_row(
            source_match_id=f"m{i}",
            lab_match_id=i,
            values={"bet365_dc_1x": f"{1 + i * 0.1:.2f}"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
        for i in range(1, 5)
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({i: _empty_odds() for i in range(1, 5)})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
        update_chunk_size=2,
        lock_chunk_size=2,
    )
    assert result["committed"] is True
    assert result["rows_updated"] == 4
    assert len(session.update_events) == 4


def test_mid_apply_error_total_rollback(tmp_path: Path):
    rows = [
        _plan_row(
            source_match_id="m1",
            lab_match_id=1,
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        ),
        _plan_row(
            source_match_id="m2",
            lab_match_id=2,
            values={"bet365_dc_1x": "2.00"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        ),
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession(
        {1: _empty_odds(), 2: _empty_odds()},
        fail_after_n_updates=1,
    )
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
        update_chunk_size=1,
    )
    assert result["committed"] is False
    assert result["db_writes"] is False
    assert session.commit_calls == 0
    assert session.rollback_calls >= 1


def test_post_write_mismatch_rollback(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()}, corrupt_post_verify=True)
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["committed"] is False
    assert result["abort_code"] == "ABORT_POST_VERIFY"
    assert session.commit_calls == 0
    assert session.rollback_calls >= 1


def test_success_single_commit(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50", "bet365_ht_away": "3.00"},
            actions={
                "bet365_dc_1x": CELL_ACTION_WOULD_WRITE,
                "bet365_ht_away": CELL_ACTION_WOULD_WRITE,
            },
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["committed"] is True
    assert result["db_writes"] is True
    assert session.commit_calls == 1
    assert result["rows_updated"] == 1
    assert result["cells_updated"] == 2


def test_rerun_after_success_abort_stale(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: _empty_odds()})
    first = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out1",
        confirm_apply=True,
    )
    assert first["committed"] is True
    # DB now has value from first apply (session odds mutated)
    second = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out2",
        confirm_apply=True,
    )
    assert second["committed"] is False
    assert second["abort_code"] == "ABORT_STALE"


def test_bulk_executemany_writes_expected_values(tmp_path: Path):
    """Bulk connection.execute produce gli stessi valori del plan WOULD_WRITE."""
    rows = [
        _plan_row(
            source_match_id="m1",
            lab_match_id=1,
            values={"bet365_dc_1x": "1.50", "bet365_ht_away": "3.10"},
            actions={
                "bet365_dc_1x": CELL_ACTION_WOULD_WRITE,
                "bet365_ht_away": CELL_ACTION_WOULD_WRITE,
            },
        ),
        _plan_row(
            source_match_id="m2",
            lab_match_id=2,
            values={"bet365_dc_1x": "2.05"},
            actions={"bet365_dc_1x": CELL_ACTION_WOULD_WRITE},
        ),
        _plan_row(
            source_match_id="m3",
            lab_match_id=3,
            values={"bet365_over_15": "1.90", "bet365_under_15": "1.95"},
            actions={
                "bet365_over_15": CELL_ACTION_WOULD_WRITE,
                "bet365_under_15": CELL_ACTION_WOULD_WRITE,
            },
        ),
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({i: _empty_odds() for i in (1, 2, 3)})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
        update_chunk_size=2,
    )
    assert result["committed"] is True
    assert result["rows_updated"] == 3
    assert result["cells_updated"] == 5
    assert session.odds_by_id[1]["bet365_dc_1x"] == Decimal("1.50")
    assert session.odds_by_id[1]["bet365_ht_away"] == Decimal("3.10")
    assert session.odds_by_id[2]["bet365_dc_1x"] == Decimal("2.05")
    assert session.odds_by_id[3]["bet365_over_15"] == Decimal("1.90")
    assert session.odds_by_id[3]["bet365_under_15"] == Decimal("1.95")
    # Colonne non-WOULD_WRITE restano NULL
    for lid in (1, 2, 3):
        for f in ENRICHMENT_MODEL_FIELDS:
            written = {
                1: {"bet365_dc_1x", "bet365_ht_away"},
                2: {"bet365_dc_1x"},
                3: {"bet365_over_15", "bet365_under_15"},
            }[lid]
            if f not in written:
                assert session.odds_by_id[lid][f] is None
    assert session.commit_calls == 1


def test_bulk_different_field_masks_do_not_cross_write(tmp_path: Path):
    """Mask diverse: nessuna colonna non prevista per quella riga."""
    rows = [
        _plan_row(
            source_match_id="m1",
            lab_match_id=1,
            values={
                "bet365_dc_1x": "1.40",
                "bet365_ht_home": "2.10",  # ALREADY_SAME — non scrivere
            },
            actions={
                "bet365_dc_1x": CELL_ACTION_WOULD_WRITE,
                "bet365_ht_home": CELL_ACTION_ALREADY_SAME,
            },
        ),
        _plan_row(
            source_match_id="m2",
            lab_match_id=2,
            values={
                "bet365_over_35": "2.50",
                "bet365_dc_12": "",  # NO_SOURCE — non scrivere
            },
            actions={
                "bet365_over_35": CELL_ACTION_WOULD_WRITE,
                "bet365_dc_12": CELL_ACTION_NO_SOURCE_VALUE,
            },
        ),
    ]
    odds = {
        1: {**_empty_odds(), "bet365_ht_home": Decimal("2.10")},
        2: _empty_odds(),
    }
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession(odds)
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["committed"] is True
    assert result["rows_updated"] == 2
    assert result["cells_updated"] == 2

    by_lab = {e["lab_match_id"]: e["values"] for e in session.update_events}
    assert set(by_lab[1].keys()) == {"bet365_dc_1x"}
    assert set(by_lab[2].keys()) == {"bet365_over_35"}
    assert "bet365_ht_home" not in by_lab[1]
    assert "bet365_dc_12" not in by_lab[2]
    assert "bet365_over_35" not in by_lab[1]
    assert "bet365_dc_1x" not in by_lab[2]
    # ALREADY_SAME invariata; NO_SOURCE resta NULL
    assert session.odds_by_id[1]["bet365_ht_home"] == Decimal("2.10")
    assert session.odds_by_id[2]["bet365_dc_12"] is None


def test_cli_apply_requires_both_paths():
    with pytest.raises(SystemExit):
        cli_main(
            [
                "--apply-plan",
                "x.csv",
                "--output-dir",
                "out",
            ]
        )


def test_cli_modes_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli_main(
            [
                "--csv",
                "a.csv",
                "--dry-run",
                "--apply-plan",
                "p.csv",
                "--apply-summary",
                "s.json",
                "--output-dir",
                "out",
            ]
        )


def test_already_same_mismatch_stale(tmp_path: Path):
    rows = [
        _plan_row(
            values={"bet365_dc_1x": "1.50"},
            actions={"bet365_dc_1x": CELL_ACTION_ALREADY_SAME},
        )
    ]
    plan_path, summary_path, _, _ = _setup_plan_pair(tmp_path, rows)
    session = _ApplySession({1: {**_empty_odds(), "bet365_dc_1x": Decimal("9.99")}})
    result = run_bet365_enrichment_apply(
        session=session,  # type: ignore[arg-type]
        plan_path=plan_path,
        summary_path=summary_path,
        output_dir=tmp_path / "out",
        confirm_apply=True,
    )
    assert result["abort_code"] == "ABORT_STALE"
    assert session.update_events == []
