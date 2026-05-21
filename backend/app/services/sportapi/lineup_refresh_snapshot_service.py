"""Snapshot stato predizione v2.0 + formazione SportAPI (solo lettura)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture, Team, TeamSotPrediction
from app.services.sportapi.sportapi_lineup_impact_service import LineupImpactSimulationService
from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit


def _side_from_prediction(
    row: TeamSotPrediction | None,
    side_data: dict[str, Any],
) -> dict[str, Any]:
    raw = row.raw_json if row and isinstance(row.raw_json, dict) else {}
    top_players = side_data.get("top_sot_players") or side_data.get("top5_sot_players") or []
    lineup_players = [
        {
            "player_id": p.get("player_id"),
            "player_name": p.get("player_name"),
            "lineup_status": p.get("status"),
            "replacement_player_name": p.get("replacement_player_name"),
            "team_sot_share_pct": p.get("team_sot_share_pct"),
        }
        for p in top_players
    ]
    return {
        "predicted_sot": float(row.predicted_sot) if row and row.predicted_sot is not None else None,
        "offensive_lineup_factor": float(
            raw.get("offensive_lineup_factor")
            or side_data.get("offensive_lineup_factor")
            or side_data.get("attacking_lineup_factor")
            or side_data.get("factor")
            or 1.0,
        ),
        "opponent_defensive_weakness_factor": float(
            raw.get("opponent_defensive_weakness_factor")
            or side_data.get("opponent_defensive_weakness_factor")
            or side_data.get("defensive_weakness_factor")
            or 1.0,
        ),
        "lineup_players": lineup_players,
    }


def _missing_flat(missing_grouped: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(missing_grouped, dict):
        return out
    for group, rows in missing_grouped.items():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict):
                out.append(
                    {
                        "player_name": r.get("player_name") or r.get("name"),
                        "group": group,
                    },
                )
    return out


def build_snapshot(
    db: Session,
    fixture_id: int,
    *,
    model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
) -> dict[str, Any]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"fixture_id": int(fixture_id), "v20_available": False, "error": "Fixture non trovata"}

    home = db.get(Team, int(fx.home_team_id))
    away = db.get(Team, int(fx.away_team_id))
    hn = home.name if home else "Casa"
    an = away.name if away else "Trasferta"

    preds = list(
        db.scalars(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.model_version == model_id,
            ),
        ).all(),
    )
    pred_home = next((p for p in preds if int(p.team_id) == int(fx.home_team_id)), None)
    pred_away = next((p for p in preds if int(p.team_id) == int(fx.away_team_id)), None)

    impact = LineupImpactSimulationService().simulate_for_fixture(
        db,
        int(fixture_id),
        active_model_version=model_id,
        home_team_name=hn,
        away_team_name=an,
    )
    lineups = build_sportapi_lineups_audit(db, int(fixture_id), home_team_name=hn, away_team_name=an)

    home_sa = lineups.get("home") or {}
    away_sa = lineups.get("away") or {}
    home_imp = impact.get("home") or {}
    away_imp = impact.get("away") or {}

    home_side = _side_from_prediction(pred_home, home_imp)
    away_side = _side_from_prediction(pred_away, away_imp)
    home_side["starters"] = home_sa.get("starters") or []
    home_side["missing_players"] = _missing_flat(home_sa.get("missing_players"))
    away_side["starters"] = away_sa.get("starters") or []
    away_side["missing_players"] = _missing_flat(away_sa.get("missing_players"))

    ph = home_side.get("predicted_sot")
    pa = away_side.get("predicted_sot")
    total = round(float(ph) + float(pa), 3) if ph is not None and pa is not None else None

    v20_ok = ph is not None and pa is not None

    fetched = lineups.get("fetched_at")
    fetched_iso = fetched.isoformat() if hasattr(fetched, "isoformat") else (str(fetched) if fetched else None)

    return {
        "fixture_id": int(fixture_id),
        "model_id": model_id,
        "v20_available": v20_ok,
        "home_team_name": hn,
        "away_team_name": an,
        "predicted_home_sot": ph,
        "predicted_away_sot": pa,
        "predicted_total_sot": total,
        "home": home_side,
        "away": away_side,
        "sportapi_fetched_at": fetched_iso,
        "sportapi_confirmed": lineups.get("confirmed"),
    }
