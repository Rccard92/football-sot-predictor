"""Service Cecchino — dati fixture PIT, persistenza, nessun motore SOT."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoPrediction, Competition, Fixture, Team
from app.services.cecchino.cecchino_constants import CECCHINO_VERSION, STATUS_ERROR
from app.services.cecchino.cecchino_engine import build_full_cecchino_output, manual_input_to_snapshot
from app.services.cecchino.cecchino_fixture_history import (
    LEAKAGE_FAILED,
    audit_leakage,
    build_data_quality,
    build_fixture_contexts,
    contexts_to_calculation_input,
    load_finished_fixtures_for_team,
    picchetto_sample_meta,
)
from app.services.cecchino.cecchino_engine import input_from_manual_dict
from app.services.next_round_selection import select_next_round_fixtures

logger = logging.getLogger(__name__)


@dataclass
class CecchinoBuildBundle:
    input_snapshot: dict[str, Any]
    data_quality: dict[str, Any]
    warnings: list[str]
    leakage_failed: bool


def _all_prior_fixtures_for_audit(db: Session, target: Fixture) -> list[Fixture]:
    hid = int(target.home_team_id)
    aid = int(target.away_team_id)
    home = load_finished_fixtures_for_team(db, target, hid)
    away = load_finished_fixtures_for_team(db, target, aid)
    by_id = {int(f.id): f for f in home + away}
    return sorted(by_id.values(), key=lambda f: (f.kickoff_at, int(f.id)))


def build_calculation_input_for_fixture(
    db: Session,
    fixture: Fixture,
) -> CecchinoBuildBundle:
    """Costruisce input engine, data_quality e snapshot da fixture DB."""
    ctx = build_fixture_contexts(db, fixture)
    prior_pool = _all_prior_fixtures_for_audit(db, fixture)
    leakage_check, leakage_reasons = audit_leakage(prior_pool, fixture)

    warnings: list[str] = []
    leakage_failed = leakage_check == LEAKAGE_FAILED

    if leakage_failed:
        data_quality = build_data_quality(
            ctx,
            leakage_check=leakage_check,
            leakage_reasons=leakage_reasons,
        )
        return CecchinoBuildBundle(
            input_snapshot=ctx.to_input_snapshot(),
            data_quality=data_quality,
            warnings=data_quality.get("warnings") or [],
            leakage_failed=True,
        )

    data_quality = build_data_quality(
        ctx,
        leakage_check=leakage_check,
        leakage_reasons=leakage_reasons,
    )
    warnings = list(data_quality.get("warnings") or [])

    snapshot = ctx.to_input_snapshot()
    snapshot["fixture_id"] = int(fixture.id)
    snapshot["home_team_id"] = int(fixture.home_team_id)
    snapshot["away_team_id"] = int(fixture.away_team_id)

    return CecchinoBuildBundle(
        input_snapshot=snapshot,
        data_quality=data_quality,
        warnings=warnings,
        leakage_failed=False,
    )


def _team_brief(db: Session, team_id: int) -> dict[str, Any]:
    t = db.get(Team, int(team_id))
    if t is None:
        return {"id": int(team_id), "name": str(team_id), "logo_url": None}
    return {"id": int(t.id), "name": t.name, "logo_url": t.logo_url}


def _fixture_brief(db: Session, fx: Fixture) -> dict[str, Any]:
    return {
        "fixture_id": int(fx.id),
        "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
        "status": fx.status,
        "round": fx.round,
        "home_team": _team_brief(db, int(fx.home_team_id)),
        "away_team": _team_brief(db, int(fx.away_team_id)),
    }


def _merge_warnings(*parts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        for w in p:
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


def calculate_and_persist_for_fixture(
    db: Session,
    comp: Competition,
    fixture: Fixture,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    try:
        bundle = build_calculation_input_for_fixture(db, fixture)

        if bundle.leakage_failed:
            return {
                "status": "error",
                "code": "cecchino_leakage_failed",
                "cecchino_version": CECCHINO_VERSION,
                "competition_id": int(comp.id),
                "fixture": _fixture_brief(db, fixture),
                "calculation_status": STATUS_ERROR,
                "input_snapshot": bundle.input_snapshot,
                "data_quality": bundle.data_quality,
                "warnings": bundle.warnings,
                "message": "Leakage check failed: fixture history violates PIT rules",
            }

        ctx = build_fixture_contexts(db, fixture)
        inp = contexts_to_calculation_input(ctx)
        calc = build_full_cecchino_output(
            inp,
            picchetto_sample_meta=picchetto_sample_meta(ctx),
        )
        warnings = _merge_warnings(bundle.warnings, calc.warnings)
        output = calc.to_dict()
        output["data_quality"] = bundle.data_quality

        payload = {
            "status": "ok",
            "cecchino_version": CECCHINO_VERSION,
            "competition_id": int(comp.id),
            "fixture": _fixture_brief(db, fixture),
            "calculation_status": calc.status,
            "input_snapshot": bundle.input_snapshot,
            "data_quality": bundle.data_quality,
            "output": output,
            "warnings": warnings,
        }
        if persist:
            _upsert_prediction(
                db,
                comp=comp,
                fixture=fixture,
                calculation_status=calc.status,
                input_snapshot=bundle.input_snapshot,
                output=output,
                warnings=warnings,
            )
            db.commit()
        return payload
    except Exception as exc:
        logger.exception("Cecchino calculate failed fixture_id=%s", fixture.id)
        db.rollback()
        return {
            "status": "error",
            "code": "cecchino_calculation_error",
            "cecchino_version": CECCHINO_VERSION,
            "competition_id": int(comp.id),
            "fixture_id": int(fixture.id),
            "calculation_status": STATUS_ERROR,
            "message": str(exc),
            "warnings": [],
        }


def _upsert_prediction(
    db: Session,
    *,
    comp: Competition,
    fixture: Fixture,
    calculation_status: str,
    input_snapshot: dict[str, Any],
    output: dict[str, Any],
    warnings: list[str],
) -> CecchinoPrediction:
    existing = db.scalar(
        select(CecchinoPrediction).where(
            CecchinoPrediction.competition_id == int(comp.id),
            CecchinoPrediction.fixture_id == int(fixture.id),
            CecchinoPrediction.cecchino_version == CECCHINO_VERSION,
        ),
    )
    if existing is not None:
        row = existing
    else:
        row = CecchinoPrediction(
            competition_id=int(comp.id),
            fixture_id=int(fixture.id),
            cecchino_version=CECCHINO_VERSION,
            home_team_id=int(fixture.home_team_id),
            away_team_id=int(fixture.away_team_id),
        )
        db.add(row)
    row.status = calculation_status
    row.input_snapshot_json = input_snapshot
    row.output_json = output
    row.warnings_json = warnings
    return row


def _load_stored_row(
    db: Session,
    comp_id: int,
    fixture_id: int,
) -> CecchinoPrediction | None:
    return db.scalar(
        select(CecchinoPrediction).where(
            CecchinoPrediction.competition_id == int(comp_id),
            CecchinoPrediction.fixture_id == int(fixture_id),
            CecchinoPrediction.cecchino_version == CECCHINO_VERSION,
        ),
    )


def build_fixture_detail(
    db: Session,
    comp: Competition,
    fixture: Fixture,
    *,
    recalculate: bool = False,
) -> dict[str, Any]:
    if recalculate:
        return calculate_and_persist_for_fixture(db, comp, fixture, persist=True)

    row = _load_stored_row(db, int(comp.id), int(fixture.id))
    if row is not None and row.output_json:
        dq = (row.output_json or {}).get("data_quality") or {}
        return {
            "status": "ok",
            "cecchino_version": CECCHINO_VERSION,
            "competition_id": int(comp.id),
            "fixture": _fixture_brief(db, fixture),
            "calculation_status": row.status,
            "input_snapshot": row.input_snapshot_json,
            "data_quality": dq,
            "output": row.output_json,
            "warnings": row.warnings_json or [],
            "stored": True,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    return calculate_and_persist_for_fixture(db, comp, fixture, persist=True)


def _upcoming_fixtures(db: Session, comp: Competition, *, limit: int) -> tuple[list[Fixture], str | None]:
    raw = list(
        db.scalars(
            select(Fixture)
            .where(Fixture.competition_id == comp.id)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all(),
    )
    selection = select_next_round_fixtures(raw, limit=limit, only_next_round=True)
    return selection.fixtures, selection.final_round


def build_upcoming_list(
    db: Session,
    comp: Competition,
    *,
    limit: int = 50,
    recalculate: bool = False,
) -> dict[str, Any]:
    fixtures, round_label = _upcoming_fixtures(db, comp, limit=limit)
    items: list[dict[str, Any]] = []
    for fx in fixtures:
        if recalculate:
            detail = calculate_and_persist_for_fixture(db, comp, fx, persist=True)
        else:
            row = _load_stored_row(db, int(comp.id), int(fx.id))
            if row is not None and row.output_json:
                final = (row.output_json or {}).get("final") or {}
                dq = (row.output_json or {}).get("data_quality") or {}
                detail = {
                    "status": "ok",
                    "calculation_status": row.status,
                    "warnings": row.warnings_json or [],
                    "data_quality": dq,
                    "final": final,
                    "stored": True,
                }
            else:
                detail = calculate_and_persist_for_fixture(db, comp, fx, persist=True)

        final = (detail.get("output") or {}).get("final") if detail.get("output") else detail.get("final")
        dq = detail.get("data_quality") or (detail.get("output") or {}).get("data_quality") or {}
        items.append(
            {
                "fixture": _fixture_brief(db, fx),
                "calculation_status": detail.get("calculation_status"),
                "warnings": detail.get("warnings") or [],
                "data_quality": {
                    "leakage_check": dq.get("leakage_check"),
                    "sample_home_total": dq.get("sample_home_total"),
                    "sample_away_total": dq.get("sample_away_total"),
                },
                "final_quota_1": (final or {}).get("quota_1"),
                "final_quota_x": (final or {}).get("quota_x"),
                "final_quota_2": (final or {}).get("quota_2"),
                "final_prob_1_pct": (final or {}).get("prob_1_pct"),
                "final_prob_x_pct": (final or {}).get("prob_x_pct"),
                "final_prob_2_pct": (final or {}).get("prob_2_pct"),
            },
        )

    return {
        "status": "ok",
        "cecchino_version": CECCHINO_VERSION,
        "competition_id": int(comp.id),
        "round_label": round_label,
        "fixtures_count": len(items),
        "fixtures": items,
    }


def recalculate_for_competition(
    db: Session,
    comp: Competition,
    *,
    fixture_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if fixture_id is not None:
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {
                "status": "error",
                "code": "fixture_not_found",
                "competition_id": int(comp.id),
                "fixture_id": int(fixture_id),
            }
        if int(fx.competition_id or 0) != int(comp.id):
            return {
                "status": "error",
                "code": "fixture_competition_mismatch",
                "competition_id": int(comp.id),
                "fixture_id": int(fixture_id),
            }
        result = calculate_and_persist_for_fixture(db, comp, fx, persist=True)
        return {
            "status": "ok",
            "recalculated_count": 1,
            "results": [result],
        }

    upcoming = build_upcoming_list(db, comp, limit=limit, recalculate=True)
    return {
        "status": "ok",
        "recalculated_count": upcoming.get("fixtures_count", 0),
        "round_label": upcoming.get("round_label"),
        "fixtures": upcoming.get("fixtures"),
    }


def debug_calculate_from_manual(data: dict[str, Any]) -> dict[str, Any]:
    """Endpoint debug: calcolo senza DB."""
    snapshot = manual_input_to_snapshot(data)
    inp = input_from_manual_dict(data)
    calc = build_full_cecchino_output(inp)
    output = calc.to_dict()
    output["data_quality"] = {
        "sample_home_context": None,
        "sample_away_context": None,
        "sample_home_total": None,
        "sample_away_total": None,
        "sample_home_recent_context": None,
        "sample_away_recent_context": None,
        "sample_home_recent_total": None,
        "sample_away_recent_total": None,
        "leakage_check": "not_applicable",
        "warnings": ["manual_input:no_db"],
        "fixture_ids_used": {},
    }
    return {
        "status": "ok",
        "cecchino_version": CECCHINO_VERSION,
        "calculation_status": calc.status,
        "input_snapshot": snapshot,
        "data_quality": output["data_quality"],
        "output": output,
        "warnings": calc.warnings,
    }
