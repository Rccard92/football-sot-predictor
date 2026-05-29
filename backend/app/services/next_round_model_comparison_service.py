"""Confronto prossimo turno tra due modelli UI (v2.0 vs v2.1) — no fallback cross-version."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    FINISHED_STATUSES,
)
from app.models import Competition, Fixture, Team, TeamSotPrediction
from app.services.next_round_selection import select_next_round_fixtures
from app.services.prediction_readiness import _safe_details
from app.services.sot_betting_advice_service import (
    advice_context_from_upcoming_lineup,
    build_upcoming_report_markets,
)
from app.services.sot_model_registry import is_user_visible_model, label_for_model

logger = logging.getLogger(__name__)

_SIDE_KEY_BY_MODEL: dict[str, str] = {
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: "v20",
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: "v21",
}


def _response_side_key(model_version: str) -> str:
    return _SIDE_KEY_BY_MODEL.get(model_version, model_version.replace("baseline_", "").replace("_", "-"))


def _side_from_predictions(
    ph: TeamSotPrediction | None,
    pa: TeamSotPrediction | None,
    *,
    model_version: str,
    advice_ctx: dict[str, Any],
) -> dict[str, Any] | None:
    if ph is None or pa is None or ph.predicted_sot is None or pa.predicted_sot is None:
        return None
    home_sot = round(float(ph.predicted_sot), 2)
    away_sot = round(float(pa.predicted_sot), 2)
    total = round(home_sot + away_sot, 2)
    markets = build_upcoming_report_markets(
        home_sot,
        away_sot,
        model_version=model_version,
        context=advice_ctx,
    )
    market = markets[0] if markets else {}
    return {
        "model_version": model_version,
        "predicted_total_sot": total,
        "home_sot": home_sot,
        "away_sot": away_sot,
        "statistical_pick": market.get("statistical_pick"),
        "cautious_pick": market.get("cautious_pick"),
        "statistical_margin": market.get("statistical_margin"),
        "cautious_margin": market.get("cautious_margin"),
        "statistical_risk": market.get("statistical_risk"),
        "confidence_label": market.get("confidence_label"),
    }


def _compute_delta(
    base_side: dict[str, Any] | None,
    compare_side: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not base_side or not compare_side:
        return None
    base_total = float(base_side["predicted_total_sot"])
    compare_total = float(compare_side["predicted_total_sot"])
    base_home = float(base_side["home_sot"])
    compare_home = float(compare_side["home_sot"])
    base_away = float(base_side["away_sot"])
    compare_away = float(compare_side["away_sot"])
    total_delta = round(compare_total - base_total, 2)
    home_delta = round(compare_home - base_home, 2)
    away_delta = round(compare_away - base_away, 2)
    if abs(total_delta) < 0.05:
        direction = "stable"
    elif total_delta > 0:
        direction = "up"
    else:
        direction = "down"
    stat_base = base_side.get("statistical_pick")
    stat_compare = compare_side.get("statistical_pick")
    conf_base = base_side.get("confidence_label")
    conf_compare = compare_side.get("confidence_label")
    return {
        "total_sot": total_delta,
        "home_sot": home_delta,
        "away_sot": away_delta,
        "direction": direction,
        "pick_changed": stat_base != stat_compare,
        "confidence_changed": conf_base != conf_compare,
    }


def build_next_round_model_comparison_for_competition(
    db: Session,
    comp: Competition,
    *,
    base_model: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    compare_model: str = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    limit: int = 20,
    only_next_round: bool = True,
) -> tuple[dict[str, Any], int]:
    base_mv = str(base_model).strip()
    compare_mv = str(compare_model).strip()
    warnings: list[str] = []

    if not is_user_visible_model(base_mv):
        return (
            {
                "status": "error",
                "message": f"base_model non valido: {base_mv}",
                "competition_id": int(comp.id),
            },
            400,
        )
    if not is_user_visible_model(compare_mv):
        return (
            {
                "status": "error",
                "message": f"compare_model non valido: {compare_mv}",
                "competition_id": int(comp.id),
            },
            400,
        )
    if base_mv == compare_mv:
        return (
            {
                "status": "error",
                "message": "base_model e compare_model devono essere diversi.",
                "competition_id": int(comp.id),
            },
            400,
        )

    base_key = _response_side_key(base_mv)
    compare_key = _response_side_key(compare_mv)

    try:
        raw_upcoming = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
            ).all()
        )
        raw_upcoming = [f for f in raw_upcoming if (f.status or "").upper() not in FINISHED_STATUSES]
        selection = select_next_round_fixtures(
            raw_upcoming,
            limit=max(1, min(limit, 100)),
            only_next_round=only_next_round,
        )
        upcoming = selection.fixtures
        round_label = selection.final_round
        warnings.extend(selection.warnings)

        fx_ids = [int(f.id) for f in upcoming]
        team_ids = list({int(f.home_team_id) for f in upcoming} | {int(f.away_team_id) for f in upcoming})
        teams: dict[int, Team] = {}
        if team_ids:
            teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()}

        from app.services.sportapi.sportapi_lineup_status import (
            formation_status_from_lineup,
            load_lineups_by_fixture_ids,
        )

        lineups_by_fx = load_lineups_by_fixture_ids(db, fx_ids) if fx_ids else {}

        preds = (
            db.scalars(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id.in_(fx_ids) if fx_ids else False,
                    TeamSotPrediction.model_version.in_([base_mv, compare_mv]),
                )
            ).all()
            if fx_ids
            else []
        )
        pred_map: dict[tuple[int, int, str], TeamSotPrediction] = {
            (int(p.fixture_id), int(p.team_id), str(p.model_version)): p for p in preds
        }

        rows: list[dict[str, Any]] = []
        base_missing = 0
        compare_missing = 0

        for fx in upcoming:
            fid = int(fx.id)
            lineup_status = formation_status_from_lineup(lineups_by_fx.get(fid))
            advice_ctx = advice_context_from_upcoming_lineup(lineup_status)

            ph_base = pred_map.get((fid, int(fx.home_team_id), base_mv))
            pa_base = pred_map.get((fid, int(fx.away_team_id), base_mv))
            ph_compare = pred_map.get((fid, int(fx.home_team_id), compare_mv))
            pa_compare = pred_map.get((fid, int(fx.away_team_id), compare_mv))

            base_side = _side_from_predictions(
                ph_base,
                pa_base,
                model_version=base_mv,
                advice_ctx=advice_ctx,
            )
            compare_side = _side_from_predictions(
                ph_compare,
                pa_compare,
                model_version=compare_mv,
                advice_ctx=advice_ctx,
            )

            if base_side is None:
                base_missing += 1
                warnings.append(
                    f"Fixture {fid}: prediction {label_for_model(base_mv)} non disponibile.",
                )
            if compare_side is None:
                compare_missing += 1
                warnings.append(
                    f"Fixture {fid}: prediction {label_for_model(compare_mv)} non disponibile.",
                )

            row: dict[str, Any] = {
                "fixture_id": fid,
                "api_fixture_id": int(fx.api_fixture_id),
                "kickoff_at": fx.kickoff_at,
                "round": fx.round,
                "status_short": fx.status,
                "home_team": {
                    "id": int(fx.home_team_id),
                    "name": teams.get(int(fx.home_team_id)).name if int(fx.home_team_id) in teams else "",
                    "logo_url": teams.get(int(fx.home_team_id)).logo_url if int(fx.home_team_id) in teams else None,
                },
                "away_team": {
                    "id": int(fx.away_team_id),
                    "name": teams.get(int(fx.away_team_id)).name if int(fx.away_team_id) in teams else "",
                    "logo_url": teams.get(int(fx.away_team_id)).logo_url if int(fx.away_team_id) in teams else None,
                },
                base_key: base_side,
                compare_key: compare_side,
                "delta": _compute_delta(base_side, compare_side),
                "lineup_status": lineup_status,
            }
            rows.append(row)

        if base_missing > 0:
            warnings.append(
                f"{base_missing} fixture senza prediction {label_for_model(base_mv)} sul turno selezionato.",
            )
        if compare_missing > 0:
            warnings.append(
                f"{compare_missing} fixture senza prediction {label_for_model(compare_mv)} sul turno selezionato.",
            )

        payload: dict[str, Any] = {
            "status": "success",
            "competition_id": int(comp.id),
            "competition_name": comp.name,
            "competition_key": comp.key,
            "season": int(comp.season),
            "round": round_label,
            "base_model": {
                "model_version": base_mv,
                "label": label_for_model(base_mv),
                "response_key": base_key,
            },
            "compare_model": {
                "model_version": compare_mv,
                "label": label_for_model(compare_mv),
                "response_key": compare_key,
            },
            "matches_count": len(rows),
            "rows": rows,
            "missing": {
                "base_model_missing_predictions": int(base_missing),
                "compare_model_missing_predictions": int(compare_missing),
            },
            "warnings": warnings,
        }
        return payload, 200

    except (OperationalError, ProgrammingError) as exc:
        logger.warning("model-comparison: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return (
            {
                "status": "error",
                "message": "Database error",
                "details": _safe_details(exc),
                "competition_id": int(comp.id),
            },
            503,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("model-comparison: errore inatteso")
        return (
            {
                "status": "error",
                "message": "Errore inatteso",
                "details": _safe_details(exc),
                "competition_id": int(comp.id),
            },
            500,
        )
