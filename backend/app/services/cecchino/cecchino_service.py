"""Service Cecchino — dati fixture PIT, persistenza, nessun motore SOT."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoPrediction, Competition, Fixture, Team
from app.services.cecchino.cecchino_constants import (
    CECCHINO_VERSION,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_ERROR,
    WARNING_PARTIAL_RECENT_SAMPLE,
)
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    WDLRecord,
    build_full_cecchino_output,
    manual_input_to_snapshot,
)
from app.services.next_round_selection import select_next_round_fixtures
from app.services.predictions_v10.v10_prior_context import (
    _prior_fixtures_for_team,
    _resolve_fixture_season_id,
)
from app.services.predictions_v11.split_fixtures import team_split_fixtures
from app.services.predictions_v11.v11_shared import last_n

logger = logging.getLogger(__name__)

LAST5_TARGET = 5
LAST6_TARGET = 6


def wdl_from_fixtures(fixtures: list[Fixture], team_id: int) -> WDLRecord:
    """Aggrega V/X/S da partite finite con gol disponibili."""
    wins = draws = losses = 0
    tid = int(team_id)
    for f in fixtures:
        if int(f.home_team_id) == tid:
            gf, ga = f.goals_home, f.goals_away
        elif int(f.away_team_id) == tid:
            gf, ga = f.goals_away, f.goals_home
        else:
            continue
        if gf is None or ga is None:
            continue
        if int(gf) > int(ga):
            wins += 1
        elif int(gf) < int(ga):
            losses += 1
        else:
            draws += 1
    return WDLRecord(wins=wins, draws=draws, losses=losses)


def _prior_for_team(db: Session, fixture: Fixture, team_id: int) -> list[Fixture]:
    season_id = _resolve_fixture_season_id(db, fixture)
    comp_id = int(fixture.competition_id) if fixture.competition_id is not None else None
    return _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=fixture.kickoff_at,
        cutoff_fixture_id=int(fixture.id),
        team_id=int(team_id),
        competition_id=comp_id,
        competition_scoped_only=comp_id is not None,
    )


def build_calculation_input_for_fixture(
    db: Session,
    fixture: Fixture,
) -> tuple[CecchinoCalculationInput, dict[str, Any], list[str]]:
    """Costruisce input engine da storico fixture (anti-leakage)."""
    hid = int(fixture.home_team_id)
    aid = int(fixture.away_team_id)
    home_prior = _prior_for_team(db, fixture, hid)
    away_prior = _prior_for_team(db, fixture, aid)

    home_split = team_split_fixtures(home_prior, hid, is_home_context=True)
    away_split = team_split_fixtures(away_prior, aid, is_home_context=False)

    home_last5 = last_n(home_split, LAST5_TARGET)
    away_last5 = last_n(away_split, LAST5_TARGET)
    home_last6 = last_n(home_prior, LAST6_TARGET)
    away_last6 = last_n(away_prior, LAST6_TARGET)

    warnings: list[str] = []
    if len(home_last5) < LAST5_TARGET or len(away_last5) < LAST5_TARGET:
        warnings.append(WARNING_PARTIAL_RECENT_SAMPLE)
    if len(home_last6) < LAST6_TARGET or len(away_last6) < LAST6_TARGET:
        warnings.append(WARNING_PARTIAL_RECENT_SAMPLE)

    inp = CecchinoCalculationInput(
        home_away=(wdl_from_fixtures(home_split, hid), wdl_from_fixtures(away_split, aid)),
        totals=(wdl_from_fixtures(home_prior, hid), wdl_from_fixtures(away_prior, aid)),
        last5_home_away=(wdl_from_fixtures(home_last5, hid), wdl_from_fixtures(away_last5, aid)),
        last6_totals=(wdl_from_fixtures(home_last6, hid), wdl_from_fixtures(away_last6, aid)),
    )

    snapshot = {
        PICCHETTO_KEY_HOME_AWAY: {
            "home": asdict(inp.home_away[0]),
            "away": asdict(inp.home_away[1]),
            "home_matches": len(home_split),
            "away_matches": len(away_split),
        },
        PICCHETTO_KEY_TOTALS: {
            "home": asdict(inp.totals[0]),
            "away": asdict(inp.totals[1]),
            "home_matches": len(home_prior),
            "away_matches": len(away_prior),
        },
        PICCHETTO_KEY_LAST5_HOME_AWAY: {
            "home": asdict(inp.last5_home_away[0]),
            "away": asdict(inp.last5_home_away[1]),
            "home_matches": len(home_last5),
            "away_matches": len(away_last5),
        },
        PICCHETTO_KEY_LAST6_TOTALS: {
            "home": asdict(inp.last6_totals[0]),
            "away": asdict(inp.last6_totals[1]),
            "home_matches": len(home_last6),
            "away_matches": len(away_last6),
        },
        "fixture_id": int(fixture.id),
        "home_team_id": hid,
        "away_team_id": aid,
    }
    return inp, snapshot, warnings


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
        inp, snapshot, input_warnings = build_calculation_input_for_fixture(db, fixture)
        calc = build_full_cecchino_output(inp)
        warnings = _merge_warnings(input_warnings, calc.warnings)
        output = calc.to_dict()
        payload = {
            "status": "ok",
            "cecchino_version": CECCHINO_VERSION,
            "competition_id": int(comp.id),
            "fixture": _fixture_brief(db, fixture),
            "calculation_status": calc.status,
            "input_snapshot": snapshot,
            "output": output,
            "warnings": warnings,
        }
        if persist:
            _upsert_prediction(
                db,
                comp=comp,
                fixture=fixture,
                calculation_status=calc.status,
                input_snapshot=snapshot,
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
        return {
            "status": "ok",
            "cecchino_version": CECCHINO_VERSION,
            "competition_id": int(comp.id),
            "fixture": _fixture_brief(db, fixture),
            "calculation_status": row.status,
            "input_snapshot": row.input_snapshot_json,
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
                detail = {
                    "status": "ok",
                    "calculation_status": row.status,
                    "warnings": row.warnings_json or [],
                    "final": final,
                    "stored": True,
                }
            else:
                detail = calculate_and_persist_for_fixture(db, comp, fx, persist=True)

        final = (detail.get("output") or {}).get("final") if detail.get("output") else detail.get("final")
        items.append(
            {
                "fixture": _fixture_brief(db, fx),
                "calculation_status": detail.get("calculation_status"),
                "warnings": detail.get("warnings") or [],
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
    inp_data = {
        "home_away": data["home_away"],
        "totals": data["totals"],
        "last5_home_away": data["last5_home_away"],
        "last6_totals": data["last6_totals"],
    }
    from app.services.cecchino.cecchino_engine import input_from_manual_dict

    inp = input_from_manual_dict(inp_data)
    calc = build_full_cecchino_output(inp)
    return {
        "status": "ok",
        "cecchino_version": CECCHINO_VERSION,
        "calculation_status": calc.status,
        "input_snapshot": snapshot,
        "output": calc.to_dict(),
        "warnings": calc.warnings,
    }
