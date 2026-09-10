"""Export RUN V2: cinque artefatti rigenerabili dal DB.

Il database e la sorgente di verita: questi file sono una comodita e possono
essere ricostruiti in qualsiasi momento, anche su un filesystem effimero.

1. `<run>_FULL.csv` — una riga per partita, tutte le colonne classificate
2. `<run>_core_markets_long.csv` — una riga per partita x mercato x layer
3. `<run>_SOURCE_RAW.csv` — flatten di `raw_json`, colonne grezze Football-Data
4. `<run>_DATA_DICTIONARY.json` — classificazione di ogni colonna di ogni file
5. `<run>_run_summary.json` — coverage, distribuzioni, esito anti-leakage
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_match import CecchinoLabMatch
from app.models.cecchino_run_v2 import (
    CecchinoRunV2MarketResult,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino_data_lab.run_v2.column_registry import (
    CORE_MARKETS_LONG_COLUMNS,
    build_data_dictionary,
    full_export_columns,
)
from app.services.cecchino_data_lab.run_v2.constants import RUN_V2_VERSION

FILE_FULL = "FULL.csv"
FILE_MARKETS_LONG = "core_markets_long.csv"
FILE_SOURCE_RAW = "SOURCE_RAW.csv"
FILE_DATA_DICTIONARY = "DATA_DICTIONARY.json"
FILE_RUN_SUMMARY = "run_summary.json"

EXPORT_FILES = (
    FILE_FULL,
    FILE_MARKETS_LONG,
    FILE_SOURCE_RAW,
    FILE_DATA_DICTIONARY,
    FILE_RUN_SUMMARY,
)

# Lettura a blocchi: 31k snapshot con payload JSONB non stanno in memoria.
SNAPSHOT_CHUNK_SIZE = 500


def _serialize(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return value


def _snapshot_to_dict(snapshot: CecchinoRunV2MatchSnapshot) -> dict[str, Any]:
    return {
        column.name: getattr(snapshot, column.name)
        for column in snapshot.__table__.columns
    }


def _market_rows_by_layer(
    rows: list[CecchinoRunV2MarketResult],
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        layer = grouped.setdefault(str(row.observation_layer), {})
        layer[str(row.market_key)] = {
            column.name: getattr(row, column.name) for column in row.__table__.columns
        }
    return grouped


def _iter_snapshot_contexts(
    db: Session, *, run_id: int, run_version: str
) -> Iterator[dict[str, Any]]:
    """Contesti di riga, ordinati in modo deterministico."""
    snapshot_ids = [
        int(r[0])
        for r in db.execute(
            select(CecchinoRunV2MatchSnapshot.id)
            .where(CecchinoRunV2MatchSnapshot.run_id == run_id)
            .order_by(
                CecchinoRunV2MatchSnapshot.kickoff_at.asc(),
                CecchinoRunV2MatchSnapshot.lab_match_id.asc(),
            )
        ).all()
    ]

    for start in range(0, len(snapshot_ids), SNAPSHOT_CHUNK_SIZE):
        chunk = snapshot_ids[start : start + SNAPSHOT_CHUNK_SIZE]
        snapshots = {
            int(s.id): s
            for s in db.scalars(
                select(CecchinoRunV2MatchSnapshot).where(
                    CecchinoRunV2MatchSnapshot.id.in_(chunk)
                )
            ).all()
        }
        markets: dict[int, list[CecchinoRunV2MarketResult]] = {}
        for row in db.scalars(
            select(CecchinoRunV2MarketResult).where(
                CecchinoRunV2MarketResult.match_snapshot_id.in_(chunk)
            )
        ).all():
            markets.setdefault(int(row.match_snapshot_id), []).append(row)

        for snapshot_id in chunk:
            snapshot = snapshots.get(snapshot_id)
            if snapshot is None:
                continue
            grouped = _market_rows_by_layer(markets.get(snapshot_id, []))
            yield {
                "run_version": run_version,
                "snapshot": _snapshot_to_dict(snapshot),
                "markets": grouped,
                "equilibrium_state": _first_market_field(grouped, "equilibrium_state"),
                "goal_intensity_score": _first_market_field(grouped, "goal_intensity_score"),
            }
        db.expunge_all()


def _first_market_field(
    grouped: dict[str, dict[str, dict[str, Any]]], field: str
) -> Any:
    for row in (grouped.get("core_strict") or {}).values():
        value = row.get(field)
        if value is not None:
            return value
    return None


def write_full_csv(db: Session, *, run: CecchinoRunV2Run, path: Path) -> int:
    columns = full_export_columns()
    written = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([c.column for c in columns])
        for ctx in _iter_snapshot_contexts(
            db, run_id=int(run.id), run_version=str(run.run_version)
        ):
            writer.writerow([_serialize(c.getter(ctx)) for c in columns])
            written += 1
    return written


def write_core_markets_long_csv(db: Session, *, run: CecchinoRunV2Run, path: Path) -> int:
    columns = [c[0] for c in CORE_MARKETS_LONG_COLUMNS]
    written = 0

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)

        query = (
            select(CecchinoRunV2MarketResult, CecchinoRunV2MatchSnapshot)
            .join(
                CecchinoRunV2MatchSnapshot,
                CecchinoRunV2MarketResult.match_snapshot_id == CecchinoRunV2MatchSnapshot.id,
            )
            .where(CecchinoRunV2MarketResult.run_id == int(run.id))
            .order_by(
                CecchinoRunV2MatchSnapshot.kickoff_at.asc(),
                CecchinoRunV2MarketResult.lab_match_id.asc(),
                CecchinoRunV2MarketResult.market_key.asc(),
                CecchinoRunV2MarketResult.observation_layer.asc(),
            )
            .execution_options(yield_per=1000)
        )

        for result, snapshot in db.execute(query):
            row = {
                "run_id": result.run_id,
                "lab_match_id": result.lab_match_id,
                "competition": snapshot.competition_name,
                "season": snapshot.season_label,
                "season_start_year": snapshot.season_start_year,
                "kickoff": snapshot.kickoff_at,
                "home_team": snapshot.home_team,
                "away_team": snapshot.away_team,
                "history_count": snapshot.history_count,
            }
            for column in columns:
                if column in row:
                    continue
                row[column] = getattr(result, column, None)
            writer.writerow([_serialize(row.get(c)) for c in columns])
            written += 1

    return written


def _flatten_raw(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten_raw(child, sub, out)
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, ensure_ascii=False, default=str)
    else:
        out[prefix] = value


def write_source_raw_csv(db: Session, *, run: CecchinoRunV2Run, path: Path) -> tuple[int, list[str]]:
    """Flatten di `raw_json` per i match della run, con colonne dinamiche.

    Due passate a chunk: (1) scoperta chiavi, (2) scrittura CSV.
    Nessun accumulo dell'intero flatten in RAM. Output deterministico
    (colonne sorted) e lossless rispetto alla versione monolitica.
    """
    lab_match_ids = [
        int(r[0])
        for r in db.execute(
            select(CecchinoRunV2MatchSnapshot.lab_match_id)
            .where(CecchinoRunV2MatchSnapshot.run_id == int(run.id))
            .order_by(CecchinoRunV2MatchSnapshot.lab_match_id.asc())
        ).all()
    ]

    discovered: set[str] = set()
    for start in range(0, len(lab_match_ids), SNAPSHOT_CHUNK_SIZE):
        chunk = lab_match_ids[start : start + SNAPSHOT_CHUNK_SIZE]
        for _lab_match_id, raw in db.execute(
            select(CecchinoLabMatch.id, CecchinoLabMatch.raw_json).where(
                CecchinoLabMatch.id.in_(chunk)
            )
        ).all():
            flat: dict[str, Any] = {}
            _flatten_raw("", raw if isinstance(raw, dict) else {}, flat)
            discovered.update(flat.keys())
            del flat

    columns = sorted(discovered)
    by_id: dict[int, dict[str, Any]] = {}
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["lab_match_id", *columns])
        for start in range(0, len(lab_match_ids), SNAPSHOT_CHUNK_SIZE):
            chunk = lab_match_ids[start : start + SNAPSHOT_CHUNK_SIZE]
            by_id.clear()
            for lab_match_id, raw in db.execute(
                select(CecchinoLabMatch.id, CecchinoLabMatch.raw_json).where(
                    CecchinoLabMatch.id.in_(chunk)
                )
            ).all():
                flat = {}
                _flatten_raw("", raw if isinstance(raw, dict) else {}, flat)
                by_id[int(lab_match_id)] = flat
            for lab_match_id in chunk:
                flat = by_id.get(lab_match_id, {})
                writer.writerow([lab_match_id, *[_serialize(flat.get(c)) for c in columns]])

    return len(lab_match_ids), columns


def build_export_manifest_light(db: Session, *, run_id: int) -> dict[str, Any]:
    """Conteggi aggregate economici: nessuna generazione FULL/LONG/RAW."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise ValueError(f"run_v2 {run_id} inesistente")

    full_rows = int(
        db.execute(
            select(func.count())
            .select_from(CecchinoRunV2MatchSnapshot)
            .where(CecchinoRunV2MatchSnapshot.run_id == int(run_id))
        ).scalar_one()
    )
    long_rows = int(
        db.execute(
            select(func.count())
            .select_from(CecchinoRunV2MarketResult)
            .where(CecchinoRunV2MarketResult.run_id == int(run_id))
        ).scalar_one()
    )

    cached_raw_cols: int | None = None
    try:
        from app.services.cecchino_data_lab.run_v2 import ai_bundle_jobs as jobs_mod

        cached = jobs_mod.read_cached_export_counts(int(run_id))
        if isinstance(cached, dict) and cached.get("source_raw_columns") is not None:
            cached_raw_cols = int(cached["source_raw_columns"])
    except Exception:
        cached_raw_cols = None

    return {
        "run_id": int(run_id),
        "run_version": run.run_version or RUN_V2_VERSION,
        "lightweight": True,
        "files": {name: name for name in EXPORT_FILES},
        "counts": {
            "full_rows": full_rows,
            "core_markets_long_rows": long_rows,
            "source_raw_rows": full_rows,
            "full_columns": len(full_export_columns()),
            "source_raw_columns": cached_raw_cols,
        },
    }


def build_export_bundle(
    db: Session,
    *,
    run_id: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Rigenera i cinque artefatti dal DB e restituisce il manifest."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise ValueError(f"run_v2 {run_id} inesistente")

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"cecchino_run_v2_{run_id}"

    full_path = output_dir / f"{prefix}_{FILE_FULL}"
    long_path = output_dir / f"{prefix}_{FILE_MARKETS_LONG}"
    raw_path = output_dir / f"{prefix}_{FILE_SOURCE_RAW}"
    dict_path = output_dir / f"{prefix}_{FILE_DATA_DICTIONARY}"
    summary_path = output_dir / f"{prefix}_{FILE_RUN_SUMMARY}"

    full_rows = write_full_csv(db, run=run, path=full_path)
    long_rows = write_core_markets_long_csv(db, run=run, path=long_path)
    raw_rows, raw_columns = write_source_raw_csv(db, run=run, path=raw_path)

    dictionary = build_data_dictionary(run_id=int(run_id), source_raw_columns=raw_columns)
    dict_path.write_text(
        json.dumps(dictionary, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )

    summary = dict(run.summary_json or {})
    summary["export"] = {
        "prefix": prefix,
        "full_rows": full_rows,
        "core_markets_long_rows": long_rows,
        "source_raw_rows": raw_rows,
        "source_raw_columns": len(raw_columns),
        "full_columns": len(full_export_columns()),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return {
        "run_id": int(run_id),
        "run_version": run.run_version or RUN_V2_VERSION,
        "output_dir": str(output_dir),
        "files": {
            FILE_FULL: str(full_path),
            FILE_MARKETS_LONG: str(long_path),
            FILE_SOURCE_RAW: str(raw_path),
            FILE_DATA_DICTIONARY: str(dict_path),
            FILE_RUN_SUMMARY: str(summary_path),
        },
        "counts": {
            "full_rows": full_rows,
            "core_markets_long_rows": long_rows,
            "source_raw_rows": raw_rows,
            "full_columns": len(full_export_columns()),
            "source_raw_columns": len(raw_columns),
        },
    }


def full_csv_to_string(db: Session, *, run_id: int) -> str:
    """Variante in memoria di `FULL.csv`, per i test e per run piccole."""
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise ValueError(f"run_v2 {run_id} inesistente")

    columns = full_export_columns()
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([c.column for c in columns])
    for ctx in _iter_snapshot_contexts(
        db, run_id=int(run_id), run_version=str(run.run_version)
    ):
        writer.writerow([_serialize(c.getter(ctx)) for c in columns])
    return buffer.getvalue()
