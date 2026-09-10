"""Preflight stagione RUN V2 (read-only, nessuna scrittura)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch

STATUS_READY = "ready"
STATUS_BLOCKED = "blocked"


def run_v2_preflight(db: Session, *, season_label: str) -> dict[str, Any]:
    """Conteggi dataset/match della stagione selezionata, senza side-effect."""
    season = str(season_label or "").strip()
    if not season:
        return {
            "season_label": "",
            "status": STATUS_BLOCKED,
            "matches_total": 0,
            "competitions_count": 0,
            "competitions": [],
            "datasets_count": 0,
            "date_range": {"start": None, "end": None},
            "blocking_anomalies": [
                {"code": "season_required", "message": "Stagione obbligatoria"}
            ],
            "warnings": [],
        }

    datasets = list(
        db.scalars(
            select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season)
        ).all()
    )
    if not datasets:
        return {
            "season_label": season,
            "status": STATUS_BLOCKED,
            "matches_total": 0,
            "competitions_count": 0,
            "competitions": [],
            "datasets_count": 0,
            "date_range": {"start": None, "end": None},
            "blocking_anomalies": [
                {
                    "code": "no_datasets",
                    "message": f"Nessun dataset per la stagione {season}",
                }
            ],
            "warnings": [],
        }

    dataset_ids = [int(d.id) for d in datasets]
    competitions = sorted(
        {str(d.competition_name) for d in datasets if d.competition_name}
    )
    matches_total = int(
        db.execute(
            select(func.count()).where(CecchinoLabMatch.dataset_id.in_(dataset_ids))
        ).scalar()
        or 0
    )
    first_kickoff, last_kickoff = db.execute(
        select(
            func.min(CecchinoLabMatch.kickoff_at),
            func.max(CecchinoLabMatch.kickoff_at),
        ).where(CecchinoLabMatch.dataset_id.in_(dataset_ids))
    ).one()

    warnings: list[dict[str, str]] = []
    if matches_total == 0:
        return {
            "season_label": season,
            "status": STATUS_BLOCKED,
            "matches_total": 0,
            "competitions_count": len(competitions),
            "competitions": competitions,
            "datasets_count": len(datasets),
            "date_range": {"start": None, "end": None},
            "blocking_anomalies": [
                {
                    "code": "no_matches",
                    "message": f"Nessun match per la stagione {season}",
                }
            ],
            "warnings": warnings,
        }

    return {
        "season_label": season,
        "status": STATUS_READY,
        "matches_total": matches_total,
        "competitions_count": len(competitions),
        "competitions": competitions,
        "datasets_count": len(datasets),
        "date_range": {
            "start": first_kickoff.isoformat() if first_kickoff else None,
            "end": last_kickoff.isoformat() if last_kickoff else None,
        },
        "blocking_anomalies": [],
        "warnings": warnings,
    }
