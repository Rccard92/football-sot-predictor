"""Apply del plan Bet365 congelato: solo plan+summary, nessuna riscoperta alias."""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    APPLY_LOCK_CHUNK_SIZE,
    APPLY_MANIFEST_COUNT_KEYS,
    APPLY_PLAN_IDENTITY_COLUMNS,
    APPLY_RESULT_JSON_FILENAME,
    APPLY_UPDATE_CHUNK_SIZE,
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_INVALID_SOURCE_VALUE,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    ENRICHMENT_MODEL_FIELDS,
    LEGACY_BET365_COLUMNS,
    PRE_APPLY_STATE_CSV_FILENAME,
)
from app.services.cecchino_data_lab.bet365_enrichment.prepare_apply import (
    apply_plan_csv_columns,
    sha256_file,
)

logger = logging.getLogger(__name__)


class ApplyAbort(Exception):
    """Abort preflight/apply senza scrittura (o dopo rollback)."""

    def __init__(self, reason: str, *, code: str = "ABORT") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass
class FrozenPlanRow:
    source_match_id: str
    lab_match_id: int
    field_values: dict[str, str] = field(default_factory=dict)
    field_actions: dict[str, str] = field(default_factory=dict)

    def has_action(self, action: str) -> bool:
        return any(a == action for a in self.field_actions.values())


@dataclass
class PlanManifest:
    plan_rows: int
    duplicate_source_match_ids: int
    duplicate_lab_match_ids: int
    would_update_rows: int
    would_update_cells: int
    already_same_cells: int
    no_source_value_cells: int
    conflict_cells: int
    invalid_source_value_cells: int
    ambiguous_rows: int = 0  # plan congelato non include AMBIGUOUS

    def as_dict(self) -> dict[str, int]:
        return {k: int(getattr(self, k)) for k in APPLY_MANIFEST_COUNT_KEYS}


def _chunked(ids: Sequence[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(ids), size):
        yield list(ids[i : i + size])


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.normalize()


def _decimals_equal(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return _normalize_decimal(a) == _normalize_decimal(b)


def _count_duplicates(values: list[Any]) -> int:
    counts = Counter(values)
    return sum(1 for _v, n in counts.items() if n > 1)


def _supports_for_update(session: Session) -> bool:
    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
    return dialect == "postgresql"


def load_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ApplyAbort("summary JSON non è un oggetto", code="ABORT_SUMMARY_INVALID")
    return data


def load_frozen_plan(path: Path) -> list[FrozenPlanRow]:
    """Carica il plan congelato. Solo colonne identity + 12 enrichment + __action."""
    expected_cols = set(apply_plan_csv_columns())
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ApplyAbort("plan CSV senza header", code="ABORT_PLAN_HEADER")
        headers = [str(h) for h in reader.fieldnames]
        header_set = set(headers)

        legacy_hit = sorted(header_set & LEGACY_BET365_COLUMNS)
        if legacy_hit:
            raise ApplyAbort(
                f"colonne legacy non ammesse nel plan: {legacy_hit}",
                code="ABORT_LEGACY_COLUMNS",
            )

        # Solo colonne autorizzate (identity + enrichment + __action)
        unexpected = sorted(header_set - expected_cols)
        if unexpected:
            raise ApplyAbort(
                f"colonne non autorizzate nel plan: {unexpected}",
                code="ABORT_UNAUTHORIZED_COLUMNS",
            )
        missing = sorted(expected_cols - header_set)
        if missing:
            raise ApplyAbort(
                f"colonne plan mancanti: {missing}",
                code="ABORT_PLAN_HEADER",
            )

        rows: list[FrozenPlanRow] = []
        for raw in reader:
            source = str(raw.get("source_match_id") or "").strip()
            lab_raw = str(raw.get("lab_match_id") or "").strip()
            if not lab_raw:
                raise ApplyAbort(
                    "lab_match_id mancante in una riga del plan",
                    code="ABORT_MISSING_LAB_ID",
                )
            try:
                lab_id = int(lab_raw)
            except ValueError as exc:
                raise ApplyAbort(
                    f"lab_match_id non intero: {lab_raw}",
                    code="ABORT_MISSING_LAB_ID",
                ) from exc

            field_values: dict[str, str] = {}
            field_actions: dict[str, str] = {}
            for f in ENRICHMENT_MODEL_FIELDS:
                field_values[f] = str(raw.get(f) or "").strip()
                action = str(raw.get(f"{f}__action") or "").strip()
                field_actions[f] = action

            rows.append(
                FrozenPlanRow(
                    source_match_id=source,
                    lab_match_id=lab_id,
                    field_values=field_values,
                    field_actions=field_actions,
                )
            )
    return rows


def compute_manifest_from_plan(rows: list[FrozenPlanRow]) -> PlanManifest:
    source_ids = [r.source_match_id for r in rows]
    lab_ids = [r.lab_match_id for r in rows]
    would_update_rows = 0
    would_update_cells = 0
    already_same = 0
    no_source = 0
    conflicts = 0
    invalids = 0

    for row in rows:
        row_write = False
        for f in ENRICHMENT_MODEL_FIELDS:
            action = row.field_actions[f]
            if action == CELL_ACTION_WOULD_WRITE:
                would_update_cells += 1
                row_write = True
            elif action == CELL_ACTION_ALREADY_SAME:
                already_same += 1
            elif action == CELL_ACTION_NO_SOURCE_VALUE:
                no_source += 1
            elif action == CELL_ACTION_CONFLICT:
                conflicts += 1
            elif action == CELL_ACTION_INVALID_SOURCE_VALUE:
                invalids += 1
        if row_write:
            would_update_rows += 1

    return PlanManifest(
        plan_rows=len(rows),
        duplicate_source_match_ids=_count_duplicates(source_ids),
        duplicate_lab_match_ids=_count_duplicates(lab_ids),
        would_update_rows=would_update_rows,
        would_update_cells=would_update_cells,
        already_same_cells=already_same,
        no_source_value_cells=no_source,
        conflict_cells=conflicts,
        invalid_source_value_cells=invalids,
    )


def preflight_frozen_plan(
    *,
    plan_path: Path,
    summary_path: Path,
) -> tuple[list[FrozenPlanRow], dict[str, Any], PlanManifest, str]:
    """Preflight completo. Raise ApplyAbort se fallisce. Zero DB write."""
    if not plan_path.is_file():
        raise ApplyAbort(f"plan non trovato: {plan_path}", code="ABORT_PLAN_MISSING")
    if not summary_path.is_file():
        raise ApplyAbort(
            f"summary non trovato: {summary_path}", code="ABORT_SUMMARY_MISSING"
        )

    summary = load_summary(summary_path)
    plan_hash = sha256_file(plan_path)
    expected_hash = str(summary.get("apply_plan_sha256") or "").strip().lower()
    if not expected_hash:
        raise ApplyAbort(
            "summary senza apply_plan_sha256", code="ABORT_SUMMARY_INVALID"
        )
    if plan_hash.lower() != expected_hash:
        raise ApplyAbort(
            f"SHA256 plan mismatch: got={plan_hash} expected={expected_hash}",
            code="ABORT_PLAN_HASH_MISMATCH",
        )

    if summary.get("PLAN_VALID") is not True:
        raise ApplyAbort("PLAN_VALID non true nel summary", code="ABORT_PLAN_INVALID")

    rows = load_frozen_plan(plan_path)

    # Action non ammesse in plan valido
    for row in rows:
        if not row.source_match_id:
            raise ApplyAbort(
                "source_match_id vuoto nel plan", code="ABORT_EMPTY_SOURCE_ID"
            )
        for f, action in row.field_actions.items():
            if action == CELL_ACTION_CONFLICT:
                raise ApplyAbort(
                    f"CONFLICT presente nel plan (lab={row.lab_match_id} field={f})",
                    code="ABORT_CONFLICT_IN_PLAN",
                )
            if action == CELL_ACTION_INVALID_SOURCE_VALUE:
                raise ApplyAbort(
                    f"INVALID_SOURCE_VALUE nel plan (lab={row.lab_match_id} field={f})",
                    code="ABORT_INVALID_IN_PLAN",
                )
            if action not in (
                CELL_ACTION_WOULD_WRITE,
                CELL_ACTION_ALREADY_SAME,
                CELL_ACTION_NO_SOURCE_VALUE,
            ):
                raise ApplyAbort(
                    f"action sconosciuta '{action}' (lab={row.lab_match_id} field={f})",
                    code="ABORT_UNKNOWN_ACTION",
                )
            if action == CELL_ACTION_WOULD_WRITE:
                parsed = _as_decimal(row.field_values.get(f))
                if parsed is None:
                    raise ApplyAbort(
                        f"WOULD_WRITE senza valore numerico (lab={row.lab_match_id} field={f})",
                        code="ABORT_WOULD_WRITE_VALUE",
                    )

    manifest = compute_manifest_from_plan(rows)
    if manifest.duplicate_source_match_ids > 0:
        raise ApplyAbort(
            "duplicate source_match_id nel plan", code="ABORT_DUPLICATE_SOURCE"
        )
    if manifest.duplicate_lab_match_ids > 0:
        raise ApplyAbort(
            "duplicate lab_match_id nel plan", code="ABORT_DUPLICATE_LAB"
        )
    if manifest.conflict_cells > 0 or manifest.invalid_source_value_cells > 0:
        raise ApplyAbort(
            "conflict/invalid cells nel plan", code="ABORT_BAD_CELLS"
        )

    # Manifest match vs summary (non fidarsi dei conteggi summary)
    mismatches: list[str] = []
    computed = manifest.as_dict()
    for key in APPLY_MANIFEST_COUNT_KEYS:
        if key not in summary:
            mismatches.append(f"{key}: missing_in_summary")
            continue
        try:
            summary_val = int(summary[key])
        except (TypeError, ValueError):
            mismatches.append(f"{key}: non_int_in_summary={summary[key]!r}")
            continue
        if summary_val != computed[key]:
            mismatches.append(
                f"{key}: plan={computed[key]} summary={summary_val}"
            )
    if mismatches:
        raise ApplyAbort(
            "manifest mismatch: " + "; ".join(mismatches),
            code="ABORT_MANIFEST_MISMATCH",
        )

    return rows, summary, manifest, plan_hash


def ids_to_lock(rows: list[FrozenPlanRow]) -> list[int]:
    """lab_match_id con almeno WOULD_WRITE o ALREADY_SAME."""
    out: set[int] = set()
    for row in rows:
        if row.has_action(CELL_ACTION_WOULD_WRITE) or row.has_action(
            CELL_ACTION_ALREADY_SAME
        ):
            out.add(row.lab_match_id)
    return sorted(out)


def ids_to_update(rows: list[FrozenPlanRow]) -> list[int]:
    return sorted(
        {r.lab_match_id for r in rows if r.has_action(CELL_ACTION_WOULD_WRITE)}
    )


def _select_odds_stmt(batch: list[int], *, for_update: bool):
    columns = [getattr(CecchinoLabMatch, name) for name in ENRICHMENT_MODEL_FIELDS]
    stmt = select(CecchinoLabMatch.id, *columns).where(
        CecchinoLabMatch.id.in_(batch)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return stmt


def _rows_to_odds_map(raw_rows: Sequence[Any]) -> dict[int, dict[str, Decimal | None]]:
    result: dict[int, dict[str, Decimal | None]] = {}
    for row in raw_rows:
        odds: dict[str, Decimal | None] = {}
        for idx, field_name in enumerate(ENRICHMENT_MODEL_FIELDS):
            odds[field_name] = _as_decimal(row[idx + 1])
        result[int(row[0])] = odds
    return result


def load_odds_chunked(
    session: Session,
    lab_match_ids: Sequence[int],
    *,
    chunk_size: int,
    for_update: bool,
) -> dict[int, dict[str, Decimal | None]]:
    unique_ids = sorted({int(i) for i in lab_match_ids})
    if not unique_ids:
        return {}
    use_fu = for_update and _supports_for_update(session)
    result: dict[int, dict[str, Decimal | None]] = {}
    size = max(1, int(chunk_size))
    for batch in _chunked(unique_ids, size):
        stmt = _select_odds_stmt(batch, for_update=use_fu)
        result.update(_rows_to_odds_map(session.execute(stmt).all()))
    return result


def revalidate_locked_state(
    rows: list[FrozenPlanRow],
    db_odds: dict[int, dict[str, Decimal | None]],
) -> list[str]:
    """Ritorna lista failure; vuota se ok."""
    failures: list[str] = []
    for row in rows:
        if not (
            row.has_action(CELL_ACTION_WOULD_WRITE)
            or row.has_action(CELL_ACTION_ALREADY_SAME)
        ):
            continue
        current = db_odds.get(row.lab_match_id)
        if current is None:
            failures.append(f"lab_match_id={row.lab_match_id} missing_from_lock_select")
            continue
        for f in ENRICHMENT_MODEL_FIELDS:
            action = row.field_actions[f]
            db_val = current.get(f)
            if action == CELL_ACTION_WOULD_WRITE:
                if db_val is not None:
                    failures.append(
                        f"STALE WOULD_WRITE lab={row.lab_match_id} field={f} "
                        f"db={db_val}"
                    )
            elif action == CELL_ACTION_ALREADY_SAME:
                plan_val = _as_decimal(row.field_values.get(f))
                if not _decimals_equal(db_val, plan_val):
                    failures.append(
                        f"MISMATCH ALREADY_SAME lab={row.lab_match_id} field={f} "
                        f"db={db_val} plan={plan_val}"
                    )
            elif action in (
                CELL_ACTION_CONFLICT,
                CELL_ACTION_INVALID_SOURCE_VALUE,
            ):
                failures.append(
                    f"forbidden action {action} lab={row.lab_match_id} field={f}"
                )
    return failures


def write_pre_apply_state_csv(
    path: Path,
    db_odds: dict[int, dict[str, Decimal | None]],
    lab_match_ids: Sequence[int],
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["lab_match_id", *ENRICHMENT_MODEL_FIELDS]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for lab_id in sorted(set(int(i) for i in lab_match_ids)):
            odds = db_odds.get(lab_id, {})
            row: dict[str, str] = {"lab_match_id": str(lab_id)}
            for f in ENRICHMENT_MODEL_FIELDS:
                val = odds.get(f)
                row[f] = "" if val is None else str(val)
            writer.writerow(row)
    return sha256_file(path)


def apply_would_write_updates(
    session: Session,
    rows: list[FrozenPlanRow],
    *,
    chunk_size: int = APPLY_UPDATE_CHUNK_SIZE,
) -> tuple[int, int]:
    """UPDATE solo celle WOULD_WRITE via executemany sulla Connection.

    Raggruppa per identico set di colonne WOULD_WRITE; per ogni gruppo usa
    statement parametrizzato + connection.execute(stmt, params_list).
    Restano nella stessa transazione Session (nessun commit/begin sulla connection).
    Ritorna (rows_updated, cells_updated).
    """
    by_id = {r.lab_match_id: r for r in rows if r.has_action(CELL_ACTION_WOULD_WRITE)}
    total = len(by_id)
    if total == 0:
        return 0, 0

    # mask (tuple ordinata su ENRICHMENT_MODEL_FIELDS) -> [(lab_id, values)]
    groups: dict[tuple[str, ...], list[tuple[int, dict[str, Decimal]]]] = {}
    for lab_id in sorted(by_id.keys()):
        plan_row = by_id[lab_id]
        values: dict[str, Decimal] = {}
        for f in ENRICHMENT_MODEL_FIELDS:
            if plan_row.field_actions[f] != CELL_ACTION_WOULD_WRITE:
                continue
            parsed = _as_decimal(plan_row.field_values.get(f))
            if parsed is None:
                raise ApplyAbort(
                    f"WOULD_WRITE value missing lab={lab_id} field={f}",
                    code="ABORT_WOULD_WRITE_VALUE",
                )
            values[f] = parsed
        if not values:
            continue
        forbidden = set(values) - set(ENRICHMENT_MODEL_FIELDS)
        if forbidden:
            raise ApplyAbort(
                f"tentativo scrittura colonne non autorizzate: {forbidden}",
                code="ABORT_UNAUTHORIZED_WRITE",
            )
        mask = tuple(f for f in ENRICHMENT_MODEL_FIELDS if f in values)
        groups.setdefault(mask, []).append((lab_id, values))

    size = max(1, int(chunk_size))
    rows_updated = 0
    cells_updated = 0
    # Stessa transazione Session: nessun commit/begin sulla connection
    connection = session.connection()

    for mask in sorted(groups.keys()):
        cols = list(mask)
        entries = groups[mask]
        stmt = (
            update(CecchinoLabMatch)
            .where(CecchinoLabMatch.id == bindparam("b_id"))
            .values(**{c: bindparam(f"b_{c}") for c in cols})
        )
        for i in range(0, len(entries), size):
            chunk = entries[i : i + size]
            params_list = [
                {"b_id": lab_id, **{f"b_{c}": vals[c] for c in cols}}
                for lab_id, vals in chunk
            ]
            connection.execute(stmt, params_list)
            rows_updated += len(params_list)
            cells_updated += len(params_list) * len(cols)
            logger.info("updated_rows=%s/%s", rows_updated, total)

    return rows_updated, cells_updated


def post_write_verify(
    session: Session,
    rows: list[FrozenPlanRow],
    *,
    expected_rows: int,
    expected_cells: int,
    chunk_size: int,
) -> list[str]:
    update_ids = ids_to_update(rows)
    db_odds = load_odds_chunked(
        session, update_ids, chunk_size=chunk_size, for_update=False
    )
    failures: list[str] = []
    cells_ok = 0
    rows_ok = 0
    by_id = {r.lab_match_id: r for r in rows if r.has_action(CELL_ACTION_WOULD_WRITE)}

    for lab_id, plan_row in by_id.items():
        current = db_odds.get(lab_id)
        if current is None:
            failures.append(f"post-verify missing lab={lab_id}")
            continue
        row_ok = True
        for f in ENRICHMENT_MODEL_FIELDS:
            if plan_row.field_actions[f] != CELL_ACTION_WOULD_WRITE:
                continue
            plan_val = _as_decimal(plan_row.field_values.get(f))
            db_val = current.get(f)
            if not _decimals_equal(db_val, plan_val):
                failures.append(
                    f"post-verify mismatch lab={lab_id} field={f} "
                    f"db={db_val} plan={plan_val}"
                )
                row_ok = False
            else:
                cells_ok += 1
        if row_ok:
            rows_ok += 1

    if rows_ok != expected_rows:
        failures.append(
            f"updated_rows mismatch got={rows_ok} expected={expected_rows}"
        )
    if cells_ok != expected_cells:
        failures.append(
            f"updated_cells mismatch got={cells_ok} expected={expected_cells}"
        )
    return failures


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)


def run_bet365_enrichment_apply(
    *,
    session: Session,
    plan_path: str | Path,
    summary_path: str | Path,
    output_dir: str | Path,
    confirm_apply: bool = False,
    lock_chunk_size: int = APPLY_LOCK_CHUNK_SIZE,
    update_chunk_size: int = APPLY_UPDATE_CHUNK_SIZE,
) -> dict[str, Any]:
    """Applica plan congelato. Senza confirm_apply: solo preflight + pre-state RO."""
    plan_p = Path(plan_path)
    summary_p = Path(summary_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / APPLY_RESULT_JSON_FILENAME
    pre_state_path = out / PRE_APPLY_STATE_CSV_FILENAME
    ts = datetime.now(timezone.utc).isoformat()

    base_result: dict[str, Any] = {
        "timestamp": ts,
        "confirm_apply": bool(confirm_apply),
        "committed": False,
        "db_writes": False,
        "rollback_reason": None,
        "verification_failures": [],
        "rows_planned": 0,
        "cells_planned": 0,
        "rows_updated": 0,
        "cells_updated": 0,
        "plan_hash": None,
        "pre_state_hash": None,
        "abort_code": None,
    }

    try:
        rows, summary, manifest, plan_hash = preflight_frozen_plan(
            plan_path=plan_p, summary_path=summary_p
        )
    except ApplyAbort as exc:
        payload = {
            **base_result,
            "abort_code": exc.code,
            "rollback_reason": exc.reason,
            "PLAN_VALID": False,
        }
        _write_result(result_path, payload)
        payload["output_files"] = {"apply_result_json": str(result_path)}
        return payload

    base_result["plan_hash"] = plan_hash
    base_result["rows_planned"] = manifest.would_update_rows
    base_result["cells_planned"] = manifest.would_update_cells
    base_result["manifest"] = manifest.as_dict()
    base_result["summary_apply_plan_sha256"] = summary.get("apply_plan_sha256")

    lock_ids = ids_to_lock(rows)
    update_ids = ids_to_update(rows)

    # --- senza confirm: SELECT read-only + pre-state + exit ---
    if not confirm_apply:
        db_odds = load_odds_chunked(
            session,
            lock_ids,
            chunk_size=lock_chunk_size,
            for_update=False,
        )
        pre_hash = write_pre_apply_state_csv(pre_state_path, db_odds, lock_ids)
        payload = {
            **base_result,
            "pre_state_hash": pre_hash,
            "preflight_ok": True,
            "committed": False,
            "db_writes": False,
            "rollback_reason": "confirm_apply_required",
            "abort_code": "ABORT_CONFIRM_REQUIRED",
            "locked_lab_match_ids": len(lock_ids),
            "update_lab_match_ids": len(update_ids),
        }
        _write_result(result_path, payload)
        payload["output_files"] = {
            "apply_result_json": str(result_path),
            "pre_apply_state_csv": str(pre_state_path),
        }
        session.rollback()
        return payload

    # --- confirm-apply: LOCK ALL → REVALIDATE → PRE-STATE → UPDATE → VERIFY → COMMIT ---
    try:
        # LOCK ALL (nessun UPDATE durante l'acquisizione)
        locked_odds = load_odds_chunked(
            session,
            lock_ids,
            chunk_size=lock_chunk_size,
            for_update=True,
        )
        if len(locked_odds) != len(lock_ids):
            missing = sorted(set(lock_ids) - set(locked_odds.keys()))
            raise ApplyAbort(
                f"lock select incompleto: missing={missing[:20]}",
                code="ABORT_LOCK_INCOMPLETE",
            )

        failures = revalidate_locked_state(rows, locked_odds)
        if failures:
            raise ApplyAbort(
                "revalidation failed: " + "; ".join(failures[:20]),
                code="ABORT_STALE",
            )

        # PRE-STATE dallo stato lockato (prima degli UPDATE)
        pre_hash = write_pre_apply_state_csv(pre_state_path, locked_odds, lock_ids)
        base_result["pre_state_hash"] = pre_hash

        # UPDATE solo WOULD_WRITE
        rows_updated, cells_updated = apply_would_write_updates(
            session, rows, chunk_size=update_chunk_size
        )

        # POST-WRITE VERIFY (stessa transazione)
        verify_failures = post_write_verify(
            session,
            rows,
            expected_rows=manifest.would_update_rows,
            expected_cells=manifest.would_update_cells,
            chunk_size=lock_chunk_size,
        )
        if verify_failures or rows_updated != manifest.would_update_rows:
            if rows_updated != manifest.would_update_rows and not any(
                "updated_rows" in f for f in verify_failures
            ):
                verify_failures.append(
                    f"rows_updated={rows_updated} expected={manifest.would_update_rows}"
                )
            if cells_updated != manifest.would_update_cells and not any(
                "updated_cells" in f for f in verify_failures
            ):
                verify_failures.append(
                    f"cells_updated={cells_updated} expected={manifest.would_update_cells}"
                )
            raise ApplyAbort(
                "post-write verify failed: " + "; ".join(verify_failures[:20]),
                code="ABORT_POST_VERIFY",
            )

        session.commit()
        payload = {
            **base_result,
            "preflight_ok": True,
            "committed": True,
            "db_writes": True,
            "rows_updated": rows_updated,
            "cells_updated": cells_updated,
            "verification_failures": [],
            "rollback_reason": None,
            "abort_code": None,
            "locked_lab_match_ids": len(lock_ids),
            "update_lab_match_ids": len(update_ids),
        }
        _write_result(result_path, payload)
        payload["output_files"] = {
            "apply_result_json": str(result_path),
            "pre_apply_state_csv": str(pre_state_path),
        }
        return payload

    except ApplyAbort as exc:
        session.rollback()
        payload = {
            **base_result,
            "preflight_ok": True,
            "committed": False,
            "db_writes": False,
            "rows_updated": 0,
            "cells_updated": 0,
            "abort_code": exc.code,
            "rollback_reason": exc.reason,
            "verification_failures": [exc.reason],
        }
        _write_result(result_path, payload)
        payload["output_files"] = {
            "apply_result_json": str(result_path),
            "pre_apply_state_csv": str(pre_state_path)
            if pre_state_path.is_file()
            else None,
        }
        return payload
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("apply fallito: %s", exc)
        payload = {
            **base_result,
            "committed": False,
            "db_writes": False,
            "rows_updated": 0,
            "cells_updated": 0,
            "abort_code": "ABORT_UNEXPECTED",
            "rollback_reason": str(exc),
            "verification_failures": [str(exc)],
        }
        _write_result(result_path, payload)
        payload["output_files"] = {"apply_result_json": str(result_path)}
        return payload
