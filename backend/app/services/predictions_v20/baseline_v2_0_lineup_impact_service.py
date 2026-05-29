"""v2.0: base v1.1 × offensive lineup factor × opponent defensive weakness (DB only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
)
from app.models import Fixture, Team, TeamSotPrediction
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.sot_model_registry import get_model_display
from app.services.sportapi.sportapi_lineup_impact_service import LineupImpactSimulationService


class SotPredictionV20LineupImpactService:
    model_version = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    base_model_version = BASELINE_SOT_MODEL_VERSION_V11_SOT

    def _season_row(self, db: Session, season_year: int):
        from sqlalchemy import select

        from app.core.config import get_settings
        from app.models import League, Season
        from app.services.ingestion_service import IngestionService

        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            settings = get_settings()
            league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError("league_not_found")
        season = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))
        if season is None:
            raise ValueError("season_not_found")
        return league, season

    def _load_v11_base(
        self,
        db: Session,
        fixture_id: int,
        team_id: int,
    ) -> TeamSotPrediction | None:
        return db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(team_id),
                TeamSotPrediction.model_version == self.base_model_version,
            ),
        )

    def _pre_match_readiness(
        self,
        impact: dict[str, Any],
        *,
        home_hint: str,
        away_hint: str,
    ) -> dict[str, str]:
        li_avail = bool(impact.get("sportapi_lineups_available"))
        mapping_ok = "ok" if li_avail else "missing"
        home_roster = str((impact.get("home") or {}).get("roster_sync_hint") or "missing")
        away_roster = str((impact.get("away") or {}).get("roster_sync_hint") or "missing")
        roster = "ok" if home_roster == "ok" and away_roster == "ok" else ("missing" if home_roster == "missing" and away_roster == "missing" else "partial")
        pm = impact.get("player_matching_summary") or {}
        mapped = int(pm.get("AUTO_SAFE") or 0) + int(pm.get("REVIEW") or 0)
        total_m = int(pm.get("total") or 0)
        player_mapping = "ok" if total_m > 0 and mapped >= total_m * 0.5 else ("partial" if mapped else "missing")
        status = str(impact.get("status") or "")
        model_v20 = "ready" if status == "ok" and li_avail else ("partial" if li_avail else "fallback_v11")
        return {
            "sportapi_mapping": mapping_ok,
            "lineup_freshness": "ok" if li_avail else "missing",
            "roster_sync": roster,
            "player_mapping": player_mapping,
            "model_v20": model_v20,
        }

    def _compute_side_v20(
        self,
        *,
        base_sot: float,
        offensive_factor: float,
        opponent_defensive_weakness: float,
        impact: dict[str, Any],
    ) -> tuple[float, str, list[str], dict[str, Any]]:
        off = float(offensive_factor) if offensive_factor else 1.0
        opp_def = float(opponent_defensive_weakness) if opponent_defensive_weakness else 1.0
        adjusted = round(base_sot * off * opp_def, 3)

        warnings: list[str] = []
        lineup_status = "full"
        if not impact.get("sportapi_lineups_available"):
            lineup_status = "fallback_v11_only"
            warnings.append(
                "Lineup Impact non disponibile o incompleto: risultato equivalente/parziale rispetto a v1.1",
            )
        elif impact.get("status") != "ok":
            lineup_status = "partial"
            warnings.append(
                "Lineup Impact non disponibile o incompleto: risultato equivalente/parziale rispetto a v1.1",
            )
        if str(impact.get("confidence_label") or "") == "bassa":
            warnings.append("Confidence Lineup Impact bassa.")

        raw_extra = {
            "base_v1_1_sot": round(base_sot, 4),
            "offensive_lineup_factor": round(off, 4),
            "opponent_defensive_weakness_factor": round(opp_def, 4),
            "lineup_impact_status": lineup_status,
            "lineup_impact_confidence": impact.get("confidence_label"),
            "roster_filter_active": impact.get("roster_filter_active"),
            "lineup_impact_simulation_status": impact.get("status"),
        }
        return adjusted, lineup_status, warnings, raw_extra

    def generate_for_fixture(
        self,
        db: Session,
        fixture_id: int,
        *,
        home_team_name: str | None = None,
        away_team_name: str | None = None,
    ) -> dict[str, Any]:
        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"status": "error", "message": "Fixture non trovata"}

        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        hn = home_team_name or (home.name if home else "Casa")
        an = away_team_name or (away.name if away else "Trasferta")

        impact = LineupImpactSimulationService().simulate_for_fixture(
            db,
            int(fx.id),
            home_team_name=hn,
            away_team_name=an,
        )

        home_side = impact.get("home") or {}
        away_side = impact.get("away") or {}

        results: list[dict[str, Any]] = []
        for team_id, side_data, opp_side, tname in (
            (int(fx.home_team_id), home_side, away_side, hn),
            (int(fx.away_team_id), away_side, home_side, an),
        ):
            v11 = self._load_v11_base(db, int(fx.id), team_id)
            if v11 is None or v11.predicted_sot is None:
                results.append(
                    {
                        "fixture_id": int(fx.id),
                        "team_id": team_id,
                        "status": "incomplete",
                        "message": "Manca predizione v1.1 per questa squadra.",
                    },
                )
                continue

            base = float(v11.predicted_sot)
            off = float(side_data.get("offensive_lineup_factor") or side_data.get("factor") or 1.0)
            opp_def = float(
                side_data.get("opponent_defensive_weakness_factor")
                or opp_side.get("defensive_weakness_factor")
                or 1.0,
            )
            adjusted, lineup_status, warn, raw_extra = self._compute_side_v20(
                base_sot=base,
                offensive_factor=off,
                opponent_defensive_weakness=opp_def,
                impact=impact,
            )

            readiness = self._pre_match_readiness(
                impact,
                home_hint=str(home_side.get("roster_sync_hint") or "missing"),
                away_hint=str(away_side.get("roster_sync_hint") or "missing"),
            )

            team_row = db.get(Team, team_id)
            display = get_model_display(self.model_version)
            explanation_parts = [
                f"v2.0: base v1.1 {base:.2f} × off {off:.3f} × opp_def {opp_def:.3f} = {adjusted:.2f}",
            ]
            if warn:
                explanation_parts.append(warn[0])

            v11_raw = v11.raw_json if isinstance(v11.raw_json, dict) else {}
            merged_raw: dict[str, Any] = {
                **raw_extra,
                "lineup_impact_basis": "sportapi_lineup_top5_status",
                "sportapi_fetched_at": impact.get("sportapi_fetched_at"),
                "starters_count_home": impact.get("starters_count_home"),
                "starters_count_away": impact.get("starters_count_away"),
                "v11_base": dict(v11_raw),
                "predicted_sot": adjusted,
                "sportapi_lineups_available": bool(impact.get("sportapi_lineups_available")),
                "sportapi_lineup_confirmed": impact.get("confirmed"),
                "lineup_impact_side": dict(side_data),
                "pre_match_readiness": readiness,
                "lineup_impact_home": home_side,
                "lineup_impact_away": away_side,
                "warnings": warn,
                "formula": {
                    "type": "lineup_impact_multiplicative",
                    "terms": [
                        {
                            "key": "base_v1_1_sot",
                            "label": "Base SOT v1.1",
                            "value": round(base, 4),
                            "status": "available",
                        },
                        {
                            "key": "offensive_lineup_factor",
                            "label": "Fattore offensivo formazione",
                            "value": round(off, 4),
                            "status": "available" if impact.get("sportapi_lineups_available") else "fallback",
                        },
                        {
                            "key": "opponent_defensive_weakness_factor",
                            "label": "Debolezza difensiva avversario",
                            "value": round(opp_def, 4),
                            "status": "available" if impact.get("sportapi_lineups_available") else "fallback",
                        },
                        {
                            "key": "adjusted_sot",
                            "label": "SOT adjusted v2.0",
                            "value": adjusted,
                            "status": "available",
                        },
                    ],
                },
            }
            merged_raw = append_trace_to_raw_json(
                merged_raw,
                model_version=self.model_version,
                team_id=team_id,
                team_name=team_row.name if team_row else str(team_id),
                audit_map={},
                hours_to_kickoff=compute_hours_to_kickoff(fx.kickoff_at),
                prediction_confidence=impact.get("confidence_label"),
            )

            existing = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == int(fx.id),
                    TeamSotPrediction.team_id == int(team_id),
                    TeamSotPrediction.model_version == self.model_version,
                ),
            )
            if existing is None:
                existing = TeamSotPrediction(
                    fixture_id=int(fx.id),
                    team_id=int(team_id),
                    model_version=self.model_version,
                )
                db.add(existing)

            existing.predicted_sot = adjusted
            existing.raw_json = merged_raw
            existing.explanation = " ".join(explanation_parts)
            db.commit()

            results.append(
                {
                    "fixture_id": int(fx.id),
                    "team_id": team_id,
                    "status": "ok",
                    "predicted_sot": adjusted,
                    "lineup_impact_status": lineup_status,
                },
            )

        ok_n = sum(1 for r in results if r.get("status") == "ok")
        return {
            "status": "success" if ok_n else "partial_success",
            "fixture_id": int(fx.id),
            "predictions_ok": ok_n,
            "results": results,
        }

    def generate_for_upcoming_season(
        self,
        db: Session,
        season_year: int,
        *,
        limit: int = 200,
        competition_id: int | None = None,
    ) -> dict[str, Any]:
        try:
            if competition_id is None:
                _league, season = self._season_row(db, season_year)
            else:
                season = None
        except Exception as exc:
            return {
                "status": "error",
                "failed_step": "load_season",
                "message": str(exc),
                "partial_result": {"upcoming_fixtures": 0, "predictions_ok": 0, "errors": []},
            }

        if competition_id is not None:
            fixtures = list(
                db.scalars(
                    select(Fixture)
                    .where(Fixture.competition_id == competition_id)
                    .order_by(Fixture.kickoff_at.asc()),
                ).all(),
            )
        else:
            fixtures = list(
                db.scalars(
                    select(Fixture).where(Fixture.season_id == season.id).order_by(Fixture.kickoff_at.asc()),
                ).all(),
            )
        upcoming = [f for f in fixtures if (f.status or "").upper() not in FINISHED_STATUSES][:limit]

        if not upcoming:
            return {
                "status": "error",
                "failed_step": "no_upcoming",
                "message": "Nessuna fixture upcoming.",
                "partial_result": {"upcoming_fixtures": 0, "predictions_ok": 0, "errors": []},
            }

        home = db.get(Team, int(upcoming[0].home_team_id)) if upcoming else None
        away = db.get(Team, int(upcoming[0].away_team_id)) if upcoming else None

        ok_total = 0
        errors: list[dict[str, Any]] = []
        for fx in upcoming:
            h = db.get(Team, int(fx.home_team_id))
            a = db.get(Team, int(fx.away_team_id))
            try:
                out = self.generate_for_fixture(
                    db,
                    int(fx.id),
                    home_team_name=h.name if h else None,
                    away_team_name=a.name if a else None,
                )
                ok_total += int(out.get("predictions_ok") or 0)
                if out.get("status") != "success":
                    errors.extend(out.get("results") or [])
            except Exception as exc:  # noqa: BLE001
                errors.append({"fixture_id": int(fx.id), "error": str(exc)[:300]})

        display = get_model_display(self.model_version)
        status = "success" if ok_total >= len(upcoming) * 2 * 0.5 else ("partial_success" if ok_total else "error")

        return {
            "status": status,
            "season": int(season_year),
            "model_version": self.model_version,
            "model_label": display.label if display else self.model_version,
            "upcoming_fixtures": len(upcoming),
            "predictions_ok": ok_total,
            "errors": errors,
        }

    def generate_for_competition(self, db: Session, competition_id: int, *, limit: int = 200) -> dict[str, Any]:
        from app.models import Competition

        comp = db.get(Competition, competition_id)
        if comp is None:
            return {"status": "error", "message": f"Competition {competition_id} non trovata"}
        result = self.generate_for_upcoming_season(
            db, comp.season, limit=limit, competition_id=comp.id
        )
        result["competition_id"] = comp.id
        return result
