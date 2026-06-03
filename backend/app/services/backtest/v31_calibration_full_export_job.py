"""Job asincrono export JSON completo dataset v3.1 (rebuild PIT per fixture)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.core.database import SessionLocal
from app.services.backtest.round_analysis_calibration_export import _select_analyses_for_calibration
from app.services.backtest.v31_calibration_dataset_builder import (
    PROGRESS_EVERY_FULL,
    _iter_calibration_fixtures,
    assemble_full_dataset_payload,
    build_single_full_row,
)

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]

_store_lock = threading.Lock()
_jobs: dict[str, "FullExportJobState"] = {}


def _chunk_meta_dict(
    *,
    chunk_part: int | None,
    chunk_total_parts: int | None,
    round_from: int | None,
    round_to: int | None,
) -> dict[str, Any] | None:
    if chunk_part is None or round_from is None or round_to is None:
        return None
    return {
        "part": int(chunk_part),
        "total_parts": int(chunk_total_parts or 1),
        "round_from": int(round_from),
        "round_to": int(round_to),
    }


@dataclass
class FullExportJobState:
    job_id: str
    status: JobStatus
    competition_id: int
    season_year: int
    use_latest_version_per_round: bool
    include_all_versions: bool
    round_from: int | None = None
    round_to: int | None = None
    chunk_part: int | None = None
    chunk_total_parts: int | None = None
    rows_expected: int = 0
    rows_done: int = 0
    progress_pct: float = 0.0
    duration_seconds: float = 0.0
    current_fixture_id: int | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    cancel_requested: bool = False
    result_payload: dict[str, Any] | None = None
    pit_errors: list[dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "competition_id": self.competition_id,
            "season_year": self.season_year,
            "rows_expected": self.rows_expected,
            "rows_done": self.rows_done,
            "progress_pct": round(self.progress_pct, 1),
            "duration_seconds": round(self.duration_seconds, 1),
            "current_fixture_id": self.current_fixture_id,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exportable": (
                self.result_payload.get("exportable") is True
                if isinstance(self.result_payload, dict)
                else None
            ),
            "anti_leakage_status": (
                (self.result_payload.get("anti_leakage_check") or {}).get("status")
                if isinstance(self.result_payload, dict)
                else None
            ),
        }
        if self.round_from is not None:
            out["round_from"] = self.round_from
        if self.round_to is not None:
            out["round_to"] = self.round_to
        if self.chunk_part is not None:
            out["chunk_part"] = self.chunk_part
        return out


def _get_job(job_id: str) -> FullExportJobState | None:
    with _store_lock:
        return _jobs.get(job_id)


def _update_job(job_id: str, **kwargs: Any) -> None:
    with _store_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)


def _count_chunk_fixtures(
    db: Any,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool,
    include_all_versions: bool,
    round_from: int | None,
    round_to: int | None,
) -> int:
    from app.services.backtest.round_analysis_calibration_export import (
        _select_analyses_for_calibration,
    )

    analyses, _excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    return len(
        _iter_calibration_fixtures(
            analyses,
            fixtures_by_id,
            round_from=round_from,
            round_to=round_to,
        ),
    )


def start_full_export_job(
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    round_from: int | None = None,
    round_to: int | None = None,
    chunk_part: int | None = None,
    chunk_total_parts: int | None = None,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    rows_expected = 0
    db = SessionLocal()
    try:
        rows_expected = _count_chunk_fixtures(
            db,
            competition_id=int(competition_id),
            season_year=int(season_year),
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            round_from=round_from,
            round_to=round_to,
        )
    finally:
        db.close()

    job = FullExportJobState(
        job_id=job_id,
        status="queued",
        competition_id=int(competition_id),
        season_year=int(season_year),
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
        round_from=round_from,
        round_to=round_to,
        chunk_part=chunk_part,
        chunk_total_parts=chunk_total_parts,
        rows_expected=rows_expected,
    )
    with _store_lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_full_export_job,
        args=(job_id,),
        daemon=True,
        name=f"v31-full-export-{job_id[:8]}",
    )
    thread.start()
    return job.to_public_dict()


def cancel_full_export_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "not_found"}
    if job.status in ("done", "failed", "cancelled"):
        return job.to_public_dict()
    _update_job(job_id, cancel_requested=True)
    if job.status == "queued":
        _update_job(
            job_id,
            status="cancelled",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error_message="Cancelled before start",
        )
    return _get_job(job_id).to_public_dict()  # type: ignore[union-attr]


def get_full_export_job_status(job_id: str) -> dict[str, Any] | None:
    job = _get_job(job_id)
    if job is None:
        return None
    return job.to_public_dict()


def get_full_export_job_download(job_id: str) -> dict[str, Any] | None:
    job = _get_job(job_id)
    if job is None or job.status != "done" or not job.result_payload:
        return None
    anti = job.result_payload.get("anti_leakage_check") or {}
    if anti.get("status") != "ok":
        return None
    return job.result_payload


def _run_full_export_job(job_id: str) -> None:
    job = _get_job(job_id)
    if job is None:
        return

    _update_job(
        job_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    t_job = time.perf_counter()
    db = SessionLocal()
    try:
        logger.info(
            "V31_FULL_EXPORT_LOAD_ANALYSES_START competition_id=%s season_year=%s",
            job.competition_id,
            job.season_year,
        )
        t_load = time.perf_counter()
        analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
            db,
            competition_id=job.competition_id,
            season_year=job.season_year,
            use_latest_version_per_round=job.use_latest_version_per_round,
            include_all_versions=job.include_all_versions,
        )
        max_round = max((int(a.round_number) for a in analyses), default=38)
        fixtures = _iter_calibration_fixtures(
            analyses,
            fixtures_by_id,
            round_from=job.round_from,
            round_to=job.round_to,
        )
        rows_expected = job.rows_expected or len(fixtures)
        load_ms = int((time.perf_counter() - t_load) * 1000)
        logger.info(
            "V31_FULL_EXPORT_LOAD_ANALYSES_DONE analyses=%s fixtures=%s duration_ms=%s",
            len(analyses),
            rows_expected,
            load_ms,
        )

        if job.chunk_part is not None:
            logger.info(
                "V31_FULL_EXPORT_CHUNK_START part=%s round_from=%s round_to=%s rows_expected=%s",
                job.chunk_part,
                job.round_from,
                job.round_to,
                rows_expected,
            )

        _update_job(job_id, rows_expected=rows_expected)
        logger.info(
            "V31_DATASET_EXPORT_START format=json detail=full rows_expected=%s job_id=%s",
            rows_expected,
            job_id,
        )

        from app.services.backtest.point_in_time_context_service import PointInTimeContextService

        pit_svc = PointInTimeContextService()
        rows: list[dict[str, Any]] = []
        pit_errors: list[dict[str, Any]] = []

        for _analysis, orm_row, rn in fixtures:
            current = _get_job(job_id)
            if current is None or current.cancel_requested:
                _update_job(
                    job_id,
                    status="cancelled",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error_message="Cancelled by user",
                    duration_seconds=time.perf_counter() - t_job,
                )
                logger.info("V31_DATASET_EXPORT_CANCELLED job_id=%s", job_id)
                return

            fid = int(orm_row.fixture_id)
            _update_job(job_id, current_fixture_id=fid)
            t_row = time.perf_counter()
            logger.info("V31_FULL_EXPORT_BUILD_ROW_START fixture_id=%s", fid)

            row, err = build_single_full_row(
                db,
                orm_row,
                competition_id=job.competition_id,
                season_year=job.season_year,
                round_number=rn,
                max_round=max_round,
                pit_svc=pit_svc,
            )
            row_ms = int((time.perf_counter() - t_row) * 1000)
            logger.info(
                "V31_FULL_EXPORT_BUILD_ROW_DONE fixture_id=%s duration_ms=%s",
                fid,
                row_ms,
            )

            if err:
                pit_errors.append(err)
            elif row:
                rows.append(row)

            rows_done = len(rows)
            progress = (100.0 * rows_done / rows_expected) if rows_expected else 0.0
            _update_job(
                job_id,
                rows_done=rows_done,
                progress_pct=progress,
                duration_seconds=time.perf_counter() - t_job,
                pit_errors=pit_errors,
            )

            if rows_done % PROGRESS_EVERY_FULL == 0 and rows_done > 0:
                logger.info(
                    "V31_DATASET_EXPORT_PROGRESS detail=full rows_done=%s rows_expected=%s",
                    rows_done,
                    rows_expected,
                )
                if job.chunk_part is not None:
                    logger.info(
                        "V31_FULL_EXPORT_CHUNK_PROGRESS part=%s rows_done=%s rows_expected=%s",
                        job.chunk_part,
                        rows_done,
                        rows_expected,
                    )

        chunk_meta = _chunk_meta_dict(
            chunk_part=job.chunk_part,
            chunk_total_parts=job.chunk_total_parts,
            round_from=job.round_from,
            round_to=job.round_to,
        )
        payload = assemble_full_dataset_payload(
            db,
            rows=rows,
            excluded=excluded + pit_errors,
            competition_id=job.competition_id,
            season_year=job.season_year,
            max_round=max_round,
            use_latest_version_per_round=job.use_latest_version_per_round,
            chunk_meta=chunk_meta,
        )
        anti = payload.get("anti_leakage_check") or {}
        duration_ms = int((time.perf_counter() - t_job) * 1000)

        if anti.get("status") != "ok":
            _update_job(
                job_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error_message="Anti-leakage check failed on full export",
                result_payload=payload,
                duration_seconds=time.perf_counter() - t_job,
            )
            logger.warning(
                "V31_DATASET_EXPORT_DONE format=json detail=full status=failed anti_leakage job_id=%s",
                job_id,
            )
            return

        _update_job(
            job_id,
            status="done",
            finished_at=datetime.now(timezone.utc).isoformat(),
            result_payload=payload,
            progress_pct=100.0,
            rows_done=len(rows),
            duration_seconds=time.perf_counter() - t_job,
        )
        if job.chunk_part is not None:
            logger.info(
                "V31_FULL_EXPORT_CHUNK_DONE part=%s rows=%s duration_ms=%s",
                job.chunk_part,
                len(rows),
                duration_ms,
            )
        logger.info(
            "V31_DATASET_EXPORT_DONE format=json detail=full rows=%s duration_ms=%s job_id=%s",
            len(rows),
            duration_ms,
            job_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("V31 full export job failed job_id=%s", job_id)
        _update_job(
            job_id,
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error_message=str(exc)[:500],
            duration_seconds=time.perf_counter() - t_job,
        )
    finally:
        db.close()
