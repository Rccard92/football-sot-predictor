"""Diagnostica read-only su variabili offensive (team + player stats) per stagione Serie A.

Obiettivo: verificare se metriche avanzate esistono davvero nel DB o nei raw_json importati,
senza creare dati fake e senza assumere disponibilità del provider.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Fixture, FixturePlayerStat, FixtureTeamStat
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/debug/offensive-variables", tags=["admin-debug-offensive-variables"])


def _flatten_keys(obj: Any, prefix: str = "", out: set[str] | None = None, depth: int = 0, max_depth: int = 5) -> set[str]:
    if out is None:
        out = set()
    if depth > max_depth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.add(key)
            _flatten_keys(v, key, out, depth + 1, max_depth=max_depth)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            key = f"{prefix}[{i}]"
            out.add(key)
            _flatten_keys(v, key, out, depth + 1, max_depth=max_depth)
    return out


def _search_keys(keys: set[str], patterns: list[str]) -> list[str]:
    found: list[str] = []
    for p in patterns:
        rx = re.compile(p, re.IGNORECASE)
        matches = sorted([k for k in keys if rx.search(k)])
        found.extend(matches[:30])
    # uniq preserve order
    seen: set[str] = set()
    out: list[str] = []
    for k in found:
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out[:60]


@router.get("/serie-a/{season}", response_model=None)
def debug_offensive_variables_serie_a(
    season: int,
    db: Session = Depends(get_db),
    sample_limit: int = Query(20, ge=5, le=200),
    raw_key_search_limit: int = Query(200, ge=50, le=2000),
) -> dict[str, Any]:
    ing = IngestionService()
    try:
        season_row = ing._serie_a_season_row(db, season)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    season_f = Fixture.season_id == season_row.id

    def col_coverage(model, col) -> dict[str, Any]:
        total = int(
            db.scalar(select(func.count()).select_from(model).join(Fixture, Fixture.id == model.fixture_id).where(season_f))
            or 0
        )
        non_null = int(
            db.scalar(
                select(func.count())
                .select_from(model)
                .join(Fixture, Fixture.id == model.fixture_id)
                .where(season_f, col.isnot(None))
            )
            or 0
        )
        pct = round((non_null / total) * 100.0, 2) if total else 0.0
        return {"rows_total": total, "rows_non_null": non_null, "coverage_pct": pct}

    try:
        team_cols = {
            "shots_on_target": col_coverage(FixtureTeamStat, FixtureTeamStat.shots_on_target),
            "total_shots": col_coverage(FixtureTeamStat, FixtureTeamStat.total_shots),
            "shots_inside_box": col_coverage(FixtureTeamStat, FixtureTeamStat.shots_inside_box),
            "shots_outside_box": col_coverage(FixtureTeamStat, FixtureTeamStat.shots_outside_box),
            "corner_kicks": col_coverage(FixtureTeamStat, FixtureTeamStat.corner_kicks),
            "ball_possession_pct": col_coverage(FixtureTeamStat, FixtureTeamStat.ball_possession_pct),
        }
        player_cols = {
            "passes_key": col_coverage(FixturePlayerStat, FixturePlayerStat.passes_key),
            "assists": col_coverage(FixturePlayerStat, FixturePlayerStat.assists),
            "shots_total": col_coverage(FixturePlayerStat, FixturePlayerStat.shots_total),
            "shots_on_target": col_coverage(FixturePlayerStat, FixturePlayerStat.shots_on_target),
        }

        # sample raw_json keys
        team_raw_rows = db.scalars(
            select(FixtureTeamStat)
            .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
            .where(season_f, FixtureTeamStat.raw_json.isnot(None))
            .limit(raw_key_search_limit),
        ).all()
        player_raw_rows = db.scalars(
            select(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(season_f, FixturePlayerStat.raw_json.isnot(None))
            .limit(raw_key_search_limit),
        ).all()

        team_keys: set[str] = set()
        for r in team_raw_rows:
            if isinstance(r.raw_json, dict):
                team_keys |= _flatten_keys(r.raw_json)

        player_keys: set[str] = set()
        for r in player_raw_rows:
            if isinstance(r.raw_json, dict):
                player_keys |= _flatten_keys(r.raw_json)

        patterns_team = {
            "ball_possession": [r"ball possession", r"possession"],
            "corner_kicks": [r"corner kicks", r"corners"],
            "xg": [r"expected goals", r"\\bxg\\b"],
            "big_chances": [r"big chances"],
            "crosses": [r"crosses"],
            "touches_in_box": [r"touches.*box", r"touches in (opposition|opponent) box"],
            "shots_insidebox": [r"shots.*inside"],
            "shots_outsidebox": [r"shots.*outside"],
        }
        patterns_player = {
            "key_passes": [r"key passes", r"passes\\.key", r"passes_key"],
            "crosses": [r"crosses"],
            "xg": [r"expected goals", r"\\bxg\\b"],
            "big_chances": [r"big chances"],
            "touches_in_box": [r"touches.*box"],
        }

        team_raw_hits = {k: _search_keys(team_keys, ps) for k, ps in patterns_team.items()}
        player_raw_hits = {k: _search_keys(player_keys, ps) for k, ps in patterns_player.items()}

        # small sample values (last N rows with non-null)
        def sample_values_team(col, limit: int) -> list[Any]:
            rows = db.scalars(
                select(col)
                .select_from(FixtureTeamStat)
                .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
                .where(season_f, col.isnot(None))
                .limit(limit),
            ).all()
            out: list[Any] = []
            for x in rows[:limit]:
                out.append(x)
            return out

        def sample_values_player(col, limit: int) -> list[Any]:
            rows = db.scalars(
                select(col)
                .select_from(FixturePlayerStat)
                .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
                .where(season_f, col.isnot(None))
                .limit(limit),
            ).all()
            return list(rows[:limit])

        variables: dict[str, Any] = {
            "sot_to_goal_conversion": {
                "available": bool(team_cols["shots_on_target"]["rows_non_null"] > 0),
                "source": "derived",
                "formula": "goals_for / shots_on_target_for",
                "raw_keys_found": [],
                "sample_values": [],
                "note": "Goals derivati da fixtures; SOT da fixture_team_stats.",
            },
            "avg_possession": {
                "available": bool(team_cols["ball_possession_pct"]["rows_non_null"] > 0),
                "source": "fixture_team_stats.ball_possession_pct",
                "formula": "mean(ball_possession_pct)",
                "raw_keys_found": team_raw_hits["ball_possession"],
                "sample_values": sample_values_team(FixtureTeamStat.ball_possession_pct, sample_limit),
                "note": None,
            },
            "avg_corners_for": {
                "available": bool(team_cols["corner_kicks"]["rows_non_null"] > 0),
                "source": "fixture_team_stats.corner_kicks",
                "formula": "mean(corner_kicks)",
                "raw_keys_found": team_raw_hits["corner_kicks"],
                "sample_values": sample_values_team(FixtureTeamStat.corner_kicks, sample_limit),
                "note": None,
            },
            "avg_key_passes_for": {
                "available": bool(player_cols["passes_key"]["rows_non_null"] > 0),
                "source": "fixture_player_stats.passes_key (aggregated by team+fixture)",
                "formula": "avg(sum(passes_key) per fixture/team)",
                "raw_keys_found": player_raw_hits["key_passes"],
                "sample_values": sample_values_player(FixturePlayerStat.passes_key, sample_limit),
                "note": None,
            },
            "xg_for": {
                "available": bool(team_raw_hits["xg"] or player_raw_hits["xg"]),
                "source": "raw_json" if (team_raw_hits["xg"] or player_raw_hits["xg"]) else None,
                "formula": None,
                "raw_keys_found": {"team": team_raw_hits["xg"], "player": player_raw_hits["xg"]},
                "sample_values": [],
                "note": "Disponibile solo se presente nei raw_json importati; non viene simulato.",
            },
            "big_chances_created": {
                "available": bool(team_raw_hits["big_chances"] or player_raw_hits["big_chances"]),
                "source": "raw_json" if (team_raw_hits["big_chances"] or player_raw_hits["big_chances"]) else None,
                "formula": None,
                "raw_keys_found": {"team": team_raw_hits["big_chances"], "player": player_raw_hits["big_chances"]},
                "sample_values": [],
                "note": "Disponibile solo se presente nei raw_json importati; non viene simulato.",
            },
            "crosses_for": {
                "available": bool(team_raw_hits["crosses"] or player_raw_hits["crosses"]),
                "source": "raw_json" if (team_raw_hits["crosses"] or player_raw_hits["crosses"]) else None,
                "formula": None,
                "raw_keys_found": {"team": team_raw_hits["crosses"], "player": player_raw_hits["crosses"]},
                "sample_values": [],
                "note": "Disponibile solo se presente nei raw_json importati; non viene simulato.",
            },
            "touches_box_for": {
                "available": bool(team_raw_hits["touches_in_box"] or player_raw_hits["touches_in_box"]),
                "source": "raw_json" if (team_raw_hits["touches_in_box"] or player_raw_hits["touches_in_box"]) else None,
                "formula": None,
                "raw_keys_found": {"team": team_raw_hits["touches_in_box"], "player": player_raw_hits["touches_in_box"]},
                "sample_values": [],
                "note": "Disponibile solo se presente nei raw_json importati; non viene simulato.",
            },
        }
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("debug_offensive_variables_serie_a: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("debug_offensive_variables_serie_a: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc

    return {
        "season": season,
        "checked_tables": ["fixtures", "fixture_team_stats", "fixture_player_stats"],
        "team_stats_columns": team_cols,
        "player_stats_columns": player_cols,
        "raw_json_keys_found": {
            "fixture_team_stats": team_raw_hits,
            "fixture_player_stats": player_raw_hits,
        },
        "variables": variables,
    }

