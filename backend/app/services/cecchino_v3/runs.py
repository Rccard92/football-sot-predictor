"""Ricerca dei calcoli V3 di riferimento."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_v3 import V3_STATUS_COMPLETED, CecchinoV3Run
from app.services.cecchino_v3.constants import PHASE_FEATURES


def run_phase(run: CecchinoV3Run) -> int:
    return int((run.config_json or {}).get("phase") or 1)


def includes_lockbox(run: CecchinoV3Run) -> bool:
    features = PHASE_FEATURES.get(run_phase(run))
    return bool(features and features.lockbox)


def _completed_newest_first(db: Session):
    return db.scalars(
        select(CecchinoV3Run).where(CecchinoV3Run.status == V3_STATUS_COMPLETED).order_by(CecchinoV3Run.id.desc())
    )


def reference_model_run(db: Session) -> CecchinoV3Run | None:
    """Calcolo segnato come modello di riferimento (Fase 4)."""
    return next((r for r in _completed_newest_first(db) if (r.config_json or {}).get("reference_model")), None)


def final_model_run(db: Session) -> CecchinoV3Run | None:
    """Modello di riferimento esteso a tutte le stagioni storiche (calcolo finale)."""
    return next((r for r in _completed_newest_first(db) if includes_lockbox(r)), None)
