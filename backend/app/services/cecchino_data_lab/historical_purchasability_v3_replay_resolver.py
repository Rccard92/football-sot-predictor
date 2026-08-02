"""Resolver read-only del replay Acquistabilità V3 ufficiale per una Run storica.

STEP 3C.2 — nessuna lettura V1.1/V2, nessun hardcode di replay_id.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_purchasability_v3_replay_result import (
    CecchinoLabPurchasabilityV3ReplayResult,
)
from app.models.cecchino_lab_purchasability_v3_replay_run import (
    COMPLETED_STATUSES,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    CecchinoLabPurchasabilityV3ReplayRun,
)
from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError

# Allineate a historical_purchasability_v3_replay_service (no import del service → no ciclo DB).
REPLAY_SCHEMA_VERSION = "cecchino_lab_purchasability_v3_replay_v1"
REPLAY_ENGINE_VERSION = "cecchino_lab_purchasability_v3_replay_engine_v1"

LEGACY_PURCHASABILITY_FALLBACK_ALLOWED = False

PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE = "purchasability_v3_replay_not_available"
PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE_MSG = (
    "Acquistabilità V3 non è disponibile per questa Run. Completa il replay V3 "
    "prima di aprire analytics o report."
)

OFFICIAL_COMPLETED_STATUSES = frozenset(
    {STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS}
)


def assert_legacy_fallback_forbidden(*, context: str = "") -> None:
    """Hard guard: qualsiasi tentativo di fallback legacy deve fallire."""
    if LEGACY_PURCHASABILITY_FALLBACK_ALLOWED:
        raise CecchinoLabImportError(
            "legacy_purchasability_fallback_misconfigured",
            "LEGACY_PURCHASABILITY_FALLBACK_ALLOWED deve restare False.",
            status_code=500,
            details={"context": context},
        )
    raise CecchinoLabImportError(
        "legacy_purchasability_fallback_forbidden",
        "Fallback Acquistabilità legacy (V1.1/V2) non consentito nei percorsi ufficiali.",
        status_code=409,
        details={
            "context": context,
            "legacy_fallback_allowed": False,
            "official_purchasability_source": "replay_v3",
        },
    )


def _versions_compatible(replay: CecchinoLabPurchasabilityV3ReplayRun) -> bool:
    if not (replay.formula_version or "").strip():
        return False
    if str(replay.replay_schema_version) != REPLAY_SCHEMA_VERSION:
        return False
    if str(replay.replay_engine_version) != REPLAY_ENGINE_VERSION:
        return False
    if str(replay.candidate_version) != PURCHASABILITY_V3_CANDIDATE_VERSION:
        return False
    if str(replay.formula_version) != PURCHASABILITY_V3_FORMULA_VERSION:
        return False
    return True


def _integrity_ok(replay: CecchinoLabPurchasabilityV3ReplayRun) -> bool:
    if str(replay.status) not in OFFICIAL_COMPLETED_STATUSES:
        return False
    if int(replay.results_persisted or 0) != int(replay.evaluations_total or 0):
        return False
    if int(replay.error_count or 0) != 0:
        return False
    if int(replay.unclassified_count or 0) != 0:
        return False
    if int(replay.results_persisted or 0) <= 0:
        return False
    if not (replay.preflight_schema_version or "").strip():
        return False
    if not (replay.integrity_policy_version or "").strip():
        return False
    return True


def _results_really_present(db: Session, replay_id: int, expected: int) -> bool:
    R = CecchinoLabPurchasabilityV3ReplayResult
    counted = db.execute(
        select(func.count())
        .select_from(R)
        .where(R.replay_run_id == int(replay_id))
    ).scalar_one()
    return int(counted or 0) == int(expected) and int(expected) > 0


def _sort_key(replay: CecchinoLabPurchasabilityV3ReplayRun) -> tuple[Any, ...]:
    """Priorità: formula ufficiale (già filtrata) → completed_at recente → id alto."""
    completed = replay.completed_at
    # None completed_at va in fondo
    completed_ts = completed.timestamp() if completed is not None else float("-inf")
    return (completed_ts, int(replay.id))


def list_compatible_official_replays(
    db: Session, source_scan_run_id: int
) -> list[CecchinoLabPurchasabilityV3ReplayRun]:
    """Restituisce i replay ufficiali compatibili ordinati (migliore per ultimo)."""
    assert_legacy_not_used = LEGACY_PURCHASABILITY_FALLBACK_ALLOWED is False
    if not assert_legacy_not_used:
        assert_legacy_fallback_forbidden(context="list_compatible_official_replays")

    rows = (
        db.execute(
            select(CecchinoLabPurchasabilityV3ReplayRun).where(
                CecchinoLabPurchasabilityV3ReplayRun.source_scan_run_id
                == int(source_scan_run_id),
                CecchinoLabPurchasabilityV3ReplayRun.status.in_(
                    list(OFFICIAL_COMPLETED_STATUSES)
                ),
            )
        )
        .scalars()
        .all()
    )

    compatible: list[CecchinoLabPurchasabilityV3ReplayRun] = []
    for replay in rows:
        if not _versions_compatible(replay):
            continue
        if not _integrity_ok(replay):
            continue
        if not _results_really_present(
            db, int(replay.id), int(replay.results_persisted)
        ):
            continue
        compatible.append(replay)

    compatible.sort(key=_sort_key)
    return compatible


def try_resolve_official_purchasability_v3_replay(
    db: Session, source_scan_run_id: int
) -> CecchinoLabPurchasabilityV3ReplayRun | None:
    """Come resolve, ma ritorna None invece di sollevare se assente."""
    compatible = list_compatible_official_replays(db, source_scan_run_id)
    if not compatible:
        return None
    return compatible[-1]


def resolve_official_purchasability_v3_replay(
    db: Session, source_scan_run_id: int
) -> CecchinoLabPurchasabilityV3ReplayRun:
    """Trova il replay V3 ufficiale compatibile per la Run.

    Non hardcodifica replay_id. Nessun fallback legacy.
    """
    replay = try_resolve_official_purchasability_v3_replay(db, source_scan_run_id)
    if replay is None:
        raise CecchinoLabImportError(
            PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE,
            PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE_MSG,
            status_code=409,
            details={
                "source_scan_run_id": int(source_scan_run_id),
                "official_purchasability_source": "replay_v3",
                "legacy_fallback_allowed": False,
                "legacy_fallback_used": False,
                "compatible_statuses": sorted(OFFICIAL_COMPLETED_STATUSES),
                "required_replay_schema_version": REPLAY_SCHEMA_VERSION,
                "required_replay_engine_version": REPLAY_ENGINE_VERSION,
                "required_candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
                "required_formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            },
        )
    return replay


def official_purchasability_unavailable_payload(
    *, source_scan_run_id: int
) -> dict[str, Any]:
    """Payload standard quando il replay V3 non è disponibile (dashboard / sintesi)."""
    return {
        "status": "unavailable",
        "reason": PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE,
        "message": PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE_MSG,
        "official_purchasability_version": "V3",
        "official_version": "V3",
        "source_type": "historical_replay",
        "official_purchasability_source": "replay_v3",
        "source_scan_run_id": int(source_scan_run_id),
        "replay_id": None,
        "legacy_fallback_allowed": False,
        "legacy_fallback_used": False,
        "legacy_purchasability_read": False,
        "formula_recomputed": False,
        "cta": {
            "label": "Verifica o avvia replay Acquistabilità",
            "path": f"/cecchino-lab/purchasability-replay?run_id={int(source_scan_run_id)}",
        },
    }


__all__ = [
    "LEGACY_PURCHASABILITY_FALLBACK_ALLOWED",
    "OFFICIAL_COMPLETED_STATUSES",
    "PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE",
    "PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE_MSG",
    "assert_legacy_fallback_forbidden",
    "list_compatible_official_replays",
    "official_purchasability_unavailable_payload",
    "resolve_official_purchasability_v3_replay",
    "try_resolve_official_purchasability_v3_replay",
]
