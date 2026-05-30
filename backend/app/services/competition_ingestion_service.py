from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    FINISHED_STATUSES,
)
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixtureProviderLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    League,
    PlayerSeasonProfile,
    Season,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.competition_service import CompetitionService
from app.services.ingestion_service import IngestionService
from app.services.league_season_api_helpers import (
    BOOTSTRAP_HEAVY_WARNING,
    LeaguePickInfo,
    SeasonNotAvailableError,
    estimate_bootstrap_api_calls,
    parse_league_pick,
    season_not_available_payload,
)
from app.services.player_data.profile_builder import build_player_season_profiles_for_competition
from app.services.player_data.player_match_stats_ingestion import ingest_competition_player_match_stats

logger = logging.getLogger(__name__)


def _lineup_counts_payload(
    *,
    api_football_lineup_rows_count: int,
    sportapi_lineup_rows_count: int,
    sportapi_mappings_count: int,
) -> dict[str, Any]:
    return {
        "api_football_lineup_rows_count": api_football_lineup_rows_count,
        "sportapi_lineup_rows_count": sportapi_lineup_rows_count,
        "sportapi_mappings_count": sportapi_mappings_count,
        "lineups_required_for_v21": False,
    }


def _build_v21_refresh_response(
    *,
    comp: Competition,
    round_label: str | None,
    future_fixtures_count: int,
    upcoming_count: int,
    fixture_ids: list[int],
    v21_result: dict[str, Any],
    warnings: list[str],
    lineup_payload: dict[str, Any],
) -> dict[str, Any]:
    predictions_created = int(v21_result.get("predictions_created_or_updated") or 0)
    errors = list(v21_result.get("errors") or [])
    v21_status = str(v21_result.get("status") or "")
    first_error = errors[0] if errors else None

    if predictions_created == 0:
        overall_status = "error"
        code = str(v21_result.get("code") or "v21_all_fixtures_failed")
        if v21_result.get("message") == "no_upcoming_fixtures":
            code = "v21_no_upcoming_fixtures"
        message = "Generazione v2.1 fallita: nessuna prediction salvata."
        if first_error:
            message = f"Generazione v2.1 fallita su fixture {first_error.get('fixture_id')}: {first_error.get('error')}"
    elif v21_status == "partial" or errors:
        overall_status = "partial_error"
        code = "v21_partial_failures"
        message = (
            f"Generazione v2.1 parziale: {predictions_created} prediction salvate, "
            f"{len(v21_result.get('fixtures_failed') or [])} fixture fallite."
        )
    else:
        overall_status = "ok"
        code = None
        message = None

    payload: dict[str, Any] = {
        "status": overall_status,
        "competition_id": comp.id,
        "competition_key": comp.key,
        "competition_name": comp.name,
        "season": comp.season,
        "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        "fixtures_processed": int(v21_result.get("fixtures_processed") or upcoming_count),
        "predictions_created_or_updated": predictions_created,
        "round": round_label,
        "future_fixtures_count": future_fixtures_count,
        "next_round_fixtures": upcoming_count,
        "fixture_ids_processed": fixture_ids,
        "fixtures_succeeded": v21_result.get("fixtures_succeeded") or [],
        "fixtures_failed": v21_result.get("fixtures_failed") or [],
        "failed_step": "v21_generate",
        "warnings": warnings,
        "errors": errors,
        "v21": v21_result,
        **lineup_payload,
    }
    if code:
        payload["code"] = code
    if message:
        payload["message"] = message
    if first_error:
        payload["failed_fixture_id"] = first_error.get("fixture_id")
        payload["error_type"] = first_error.get("error_type")
        payload["details"] = first_error.get("details") or first_error.get("error")
    return payload


@dataclass
class LeagueSeasonValidation:
    pick: LeaguePickInfo
    error: dict[str, Any] | None = None


class CompetitionIngestionService:
    def __init__(
        self,
        client: ApiFootballClient | None = None,
    ) -> None:
        self._ingest = IngestionService(client)
        self._comp_svc = CompetitionService(client)

    def _competition(self, db: Session, competition_id: int) -> Competition:
        comp = self._comp_svc.get_by_id_or_raise(db, competition_id)
        if comp.id != competition_id:
            logger.error(
                "competition scope mismatch requested=%s loaded=%s key=%s",
                competition_id,
                comp.id,
                comp.key,
            )
        return comp

    def _fetch_league_pick_from_api(self, comp: Competition) -> LeaguePickInfo:
        try:
            body = self._ingest._client.get(
                "leagues",
                {"id": comp.provider_league_id, "season": comp.season},
            )
        except ApiFootballError as exc:
            raise ApiFootballError(
                f"API leagues id={comp.provider_league_id} season={comp.season}: {exc}"
            ) from exc

        items = list(body.get("response") or [])
        if not items or not isinstance(items[0], dict):
            raise ApiFootballError(
                f"Lega provider_league_id={comp.provider_league_id} non trovata via API"
            )
        return parse_league_pick(
            picked=items[0],
            provider_league_id=comp.provider_league_id,
            requested_season=comp.season,
        )

    def _fetch_and_validate_league_season(
        self,
        db: Session,
        comp: Competition,
        *,
        dry_run: bool,
    ) -> LeagueSeasonValidation:
        _ = dry_run
        pick = self._fetch_league_pick_from_api(comp)
        if pick.requested_season_available:
            return LeagueSeasonValidation(pick=pick)

        error = season_not_available_payload(
            competition_id=comp.id,
            competition_key=comp.key,
            competition_name=comp.name,
            provider_league_id=comp.provider_league_id,
            requested_season=comp.season,
            available_seasons=pick.available_seasons,
            league_name=pick.league_name,
            country=pick.country,
        )
        return LeagueSeasonValidation(pick=pick, error=error)

    def _ensure_league_season(self, db: Session, comp: Competition) -> tuple[League, Season]:
        validation = self._fetch_and_validate_league_season(db, comp, dry_run=False)
        if validation.error is not None:
            raise SeasonNotAvailableError(validation.error)

        pick = validation.pick
        league = None
        if comp.league_id:
            league = db.get(League, comp.league_id)
        if league is None:
            league = db.scalar(
                select(League).where(League.api_league_id == comp.provider_league_id)
            )
        if league is None:
            league = self._ingest._upsert_league_from_picked(db, pick.raw_payload)
            comp.league_id = league.id

        season_row = None
        if comp.season_id:
            season_row = db.get(Season, comp.season_id)
        if season_row is None:
            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == comp.season)
            )
        if season_row is None:
            self._ingest._upsert_season_from_picked(db, league, pick.raw_payload, comp.season)
            db.flush()
            season_row = db.scalar(
                select(Season).where(Season.league_id == league.id, Season.year == comp.season)
            )
        if season_row is None:
            error = season_not_available_payload(
                competition_id=comp.id,
                competition_key=comp.key,
                competition_name=comp.name,
                provider_league_id=comp.provider_league_id,
                requested_season=comp.season,
                available_seasons=pick.available_seasons,
                league_name=pick.league_name,
                country=pick.country,
            )
            raise SeasonNotAvailableError(error)

        comp.league_id = league.id
        comp.season_id = season_row.id
        db.add(comp)
        db.commit()
        db.refresh(comp)
        return league, season_row

    def bootstrap(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        validation = self._fetch_and_validate_league_season(db, comp, dry_run=dry_run)
        if validation.error is not None:
            raise SeasonNotAvailableError(validation.error)

        try:
            team_items = self._ingest._client.get_teams(comp.provider_league_id, comp.season)
            fixture_items = self._ingest._client.get_fixtures(
                comp.provider_league_id, comp.season, status=None
            )
        except ApiFootballError as exc:
            return {"status": "error", "message": str(exc), "dry_run": dry_run}

        finished = [
            f
            for f in fixture_items
            if str(((f.get("fixture") or {}).get("status") or {}).get("short") or "").upper()
            in FINISHED_STATUSES
        ]
        upcoming = [f for f in fixture_items if f not in finished]
        league_season_cached = comp.league_id is not None and comp.season_id is not None
        estimate_api_calls, api_calls_breakdown = estimate_bootstrap_api_calls(
            dry_run=dry_run,
            league_season_cached=league_season_cached,
        )

        preview: dict[str, Any] = {
            "competition_id": comp.id,
            "competition_key": comp.key,
            "provider_league_id": comp.provider_league_id,
            "season": comp.season,
            "available_seasons": validation.pick.available_seasons,
            "teams_found": len(team_items),
            "fixtures_found": len(fixture_items),
            "finished_fixtures": len(finished),
            "future_fixtures": len(upcoming),
            "upcoming_fixtures": len(upcoming),
            "estimated_api_calls": estimate_api_calls,
            "api_calls_breakdown": api_calls_breakdown,
            "bootstrap_scope": "base",
            "dry_run": dry_run,
            "warnings": [],
        }
        if estimate_api_calls > 20:
            preview["warnings"].append(BOOTSTRAP_HEAVY_WARNING)

        if dry_run:
            preview["status"] = "dry_run"
            return preview

        league, season_row = self._ensure_league_season(db, comp)

        runs = []
        for fn in (
            lambda: self._ingest.bootstrap_sync_league_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_season_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_teams_for_competition(db, comp),
            lambda: self._ingest.bootstrap_sync_fixtures_for_competition(db, comp),
        ):
            run = fn()
            runs.append(
                {
                    "source": run.source,
                    "status": run.status,
                    "records_processed": run.records_processed,
                    "error_message": run.error_message,
                }
            )
            if run.status == "failed":
                break

        preview["status"] = "error" if any(r["status"] == "failed" for r in runs) else "ok"
        preview["runs"] = runs
        _ = league, season_row
        return preview

    def ingest_standings(self, db: Session, competition_id: int, *, dry_run: bool = False) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            return {"status": "dry_run", "competition_id": comp.id, "action": "ingest_standings"}
        run = self._ingest.ingest_standings_for_competition(db, comp)
        return {"status": run.status, "records_processed": run.records_processed}

    def ingest_team_stats(self, db: Session, competition_id: int, *, dry_run: bool = False) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.competition_id == comp.id,
                    Fixture.status.in_(tuple(FINISHED_STATUSES)),
                )
            )
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "finished_fixtures": int(n or 0),
                "estimated_api_calls": int(n or 0) * 2,
            }
        return self._ingest.sync_team_stats_for_competition(db, comp)

    def ingest_player_match_stats(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.competition_id == comp.id,
                    Fixture.status.in_(tuple(FINISHED_STATUSES)),
                )
            )
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "finished_fixtures": int(n or 0),
                "estimated_api_calls": int(n or 0),
            }
        return ingest_competition_player_match_stats(db, comp.id, force=force)

    def build_player_season_profiles(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            n = db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.competition_id == comp.id)
            )
            return {"status": "dry_run", "competition_id": comp.id, "fixtures_in_competition": int(n or 0)}
        return build_player_season_profiles_for_competition(db, comp.id)

    def ingest_lineups(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
        fixture_id: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        comp = self._competition(db, competition_id)
        if dry_run:
            return {"status": "dry_run", "competition_id": comp.id, "action": "ingest_lineups"}
        return self._ingest.ingest_lineups_for_competition(
            db, comp, fixture_id=fixture_id, force=force
        )

    def refresh_next_round(
        self,
        db: Session,
        competition_id: int,
        *,
        dry_run: bool = False,
        model_version: str | None = None,
        generate_mode: str = "default",
    ) -> dict[str, Any]:
        if not competition_id:
            return {
                "status": "error",
                "code": "invalid_competition_id",
                "message": "competition_id mancante o non valido",
                "competition_id": competition_id,
                "step": "validate_competition",
                "details": "competition_id richiesto",
            }

        comp = self._competition(db, competition_id)

        team_stats_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureTeamStat)
                .where(FixtureTeamStat.competition_id == comp.id)
            )
            or 0
        )
        player_profiles_count = int(
            db.scalar(
                select(func.count())
                .select_from(PlayerSeasonProfile)
                .where(PlayerSeasonProfile.competition_id == comp.id)
            )
            or 0
        )
        lineup_rows_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureLineup)
                .where(FixtureLineup.competition_id == comp.id)
            )
            or 0
        )
        api_football_lineup_rows_count = lineup_rows_count
        sportapi_mappings_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderMapping)
                .where(FixtureProviderMapping.competition_id == comp.id)
            )
            or 0
        )
        sportapi_lineup_rows_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderLineup)
                .where(FixtureProviderLineup.competition_id == comp.id)
            )
            or 0
        )

        all_fixtures = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
            ).all()
        )

        from app.services.next_round_selection import select_next_round_fixtures

        selection = select_next_round_fixtures(all_fixtures, limit=100, only_next_round=True)
        upcoming = selection.fixtures
        round_label = selection.final_round
        future_fixtures_count = selection.future_fixtures_count

        logger.info(
            "COMPETITION_NEXT_ROUND_SELECTION %s",
            selection.as_log_dict(competition_id=comp.id),
        )

        lineups_ready = sportapi_lineup_rows_count > 0 and sportapi_mappings_count > 0
        requested_mv = str(model_version).strip() if model_version else None
        mode = str(generate_mode or "default").strip()
        v21_only = mode == "v21_only" or requested_mv == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
        comparison_mode = mode == "v20_v21_comparison"
        model_versions_requested = [BASELINE_SOT_MODEL_VERSION_V11_SOT]
        if comparison_mode:
            model_versions_requested = [
                BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            ]
        elif v21_only:
            model_versions_requested = [BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS]
        elif lineups_ready:
            model_versions_requested.append(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
        else:
            model_versions_requested.append(
                f"{BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT} (degraded/fallback)"
            )

        lineup_payload = _lineup_counts_payload(
            api_football_lineup_rows_count=api_football_lineup_rows_count,
            sportapi_lineup_rows_count=sportapi_lineup_rows_count,
            sportapi_mappings_count=sportapi_mappings_count,
        )

        logger.info(
            "COMPETITION_NEXT_ROUND_REFRESH_START competition_id=%s competition_key=%s "
            "provider_league_id=%s season=%s model_versions=%s future_fixtures_count=%s "
            "next_round_fixtures=%s team_stats_count=%s player_profiles_count=%s "
            "api_football_lineup_rows_count=%s sportapi_lineup_rows_count=%s "
            "sportapi_mappings_count=%s lineups_required_for_v21=false round=%s",
            comp.id,
            comp.key,
            comp.provider_league_id,
            comp.season,
            model_versions_requested,
            future_fixtures_count,
            len(upcoming),
            team_stats_count,
            player_profiles_count,
            api_football_lineup_rows_count,
            sportapi_lineup_rows_count,
            sportapi_mappings_count,
            round_label,
        )

        if dry_run:
            dry_warnings = list(selection.warnings)
            return {
                "status": "dry_run",
                "competition_id": comp.id,
                "competition_key": comp.key,
                "competition_name": comp.name,
                "season": comp.season,
                "round": round_label,
                "future_fixtures_count": future_fixtures_count,
                "next_round_fixtures": len(upcoming),
                "team_stats_count": team_stats_count,
                "player_profiles_count": player_profiles_count,
                "lineup_rows_count": api_football_lineup_rows_count,
                "model_versions_requested": model_versions_requested,
                "selection": selection.as_log_dict(competition_id=comp.id),
                "warnings": dry_warnings,
                **lineup_payload,
            }

        if not upcoming:
            return {
                "status": "error",
                "code": selection.error_code or "no_future_fixtures",
                "message": "Nessuna partita futura trovata per questa competition.",
                "competition_id": comp.id,
                "step": "select_next_round",
                "details": f"future_fixtures_count={future_fixtures_count}, round={round_label}",
                "future_fixtures_count": future_fixtures_count,
                "selection": selection.as_log_dict(competition_id=comp.id),
            }

        for fx in upcoming:
            if fx.competition_id is None:
                return {
                    "status": "error",
                    "code": "guardrail_competition_id",
                    "message": "Fixture senza competition_id: refresh interrotto.",
                    "competition_id": comp.id,
                    "step": "guardrail_competition_id",
                    "fixture_id": int(fx.id),
                    "details": "competition_id obbligatorio su ogni fixture",
                }
            if int(fx.competition_id) != int(comp.id):
                return {
                    "status": "error",
                    "code": "guardrail_competition_id",
                    "message": "Fixture appartiene a un'altra competition.",
                    "competition_id": comp.id,
                    "step": "guardrail_competition_id",
                    "fixture_id": int(fx.id),
                    "details": f"fixture.competition_id={fx.competition_id}",
                }

        fixture_ids = [int(f.id) for f in upcoming]
        warnings: list[str] = list(selection.warnings)
        if not lineups_ready and not v21_only and not comparison_mode:
            warnings.append(
                "Lineups non disponibili: prediction generata senza impatto formazioni."
            )

        if comparison_mode:
            from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
                SotPredictionV20LineupImpactService,
            )
            from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
                SotPredictionV21WeightedComponentsService,
            )

            v20 = SotPredictionV20LineupImpactService()
            v21 = SotPredictionV21WeightedComponentsService()
            v20_result = v20.generate_for_competition(db, comp.id, fixture_ids=fixture_ids)
            v21_result = v21.generate_for_competition(db, comp.id, fixture_ids=fixture_ids)
            v20_n = int(v20_result.get("predictions_created_or_updated") or v20_result.get("predictions_ok") or 0)
            v21_n = int(v21_result.get("predictions_created_or_updated") or 0)
            warnings.extend(v20_result.get("warnings") or [])
            warnings.extend(v21_result.get("warnings") or [])
            overall_status = "ok"
            if v20_n == 0 and v21_n == 0:
                overall_status = "error"
            elif v20_n == 0 or v21_n == 0:
                overall_status = "partial_success"
            return {
                "status": overall_status,
                "competition_id": comp.id,
                "competition_key": comp.key,
                "competition_name": comp.name,
                "season": comp.season,
                "round": round_label,
                "generate_mode": "v20_v21_comparison",
                "future_fixtures_count": future_fixtures_count,
                "next_round_fixtures": len(upcoming),
                "fixture_ids_processed": fixture_ids,
                "model_versions_requested": model_versions_requested,
                "comparison_ready": v20_n > 0 and v21_n > 0,
                "warnings": warnings,
                "v20": {
                    "model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                    "predictions_created_or_updated": v20_n,
                    **{k: v for k, v in v20_result.items() if k not in ("predictions_created_or_updated",)},
                },
                "v21": {
                    "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
                    "predictions_created_or_updated": v21_n,
                    **{k: v for k, v in v21_result.items() if k not in ("predictions_created_or_updated",)},
                },
            }

        if v21_only:
            from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
                SotPredictionV21WeightedComponentsService,
            )

            v21 = SotPredictionV21WeightedComponentsService()
            v21_result = v21.generate_for_competition(db, comp.id, fixture_ids=fixture_ids)
            warnings.extend(v21_result.get("warnings") or [])
            errors = v21_result.get("errors") or []
            first_error = errors[0] if errors else None
            logger.info(
                "COMPETITION_NEXT_ROUND_V21_DONE competition_id=%s competition_key=%s status=%s "
                "predictions_created_or_updated=%s fixtures_processed=%s errors_count=%s first_error=%s",
                comp.id,
                comp.key,
                v21_result.get("status"),
                v21_result.get("predictions_created_or_updated"),
                v21_result.get("fixtures_processed"),
                len(errors),
                first_error,
            )
            return _build_v21_refresh_response(
                comp=comp,
                round_label=round_label,
                future_fixtures_count=future_fixtures_count,
                upcoming_count=len(upcoming),
                fixture_ids=fixture_ids,
                v21_result=v21_result,
                warnings=warnings,
                lineup_payload=lineup_payload,
            )

        from app.services.predictions_v11.baseline_v1_1_sot_service import (
            SotPredictionV11BaselineSotService,
        )
        from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import (
            SotPredictionV20LineupImpactService,
        )

        v11 = SotPredictionV11BaselineSotService()
        v20 = SotPredictionV20LineupImpactService()
        v11_result = v11.generate_for_competition(db, comp.id, fixture_ids=fixture_ids)
        if v11_result.get("status") == "error":
            return {
                "status": "error",
                "code": "v11_generation_failed",
                "message": str(v11_result.get("message") or "Generazione v1.1 fallita"),
                "competition_id": comp.id,
                "step": str(v11_result.get("failed_step") or "v11_generate"),
                "details": v11_result.get("details"),
                "v11": v11_result,
                "warnings": warnings,
            }

        v20_result = v20.generate_for_competition(db, comp.id, fixture_ids=fixture_ids)
        if not lineups_ready:
            v20_result["mode"] = "degraded_fallback"
            v20_result["lineups_available"] = False

        predictions_created = int(v11_result.get("predictions_created_or_updated") or 0)
        predictions_ok_v20 = int((v20_result or {}).get("predictions_ok") or 0)

        overall_status = "ok"
        if predictions_created == 0:
            overall_status = "error"
        elif v11_result.get("status") != "success" or int(v11_result.get("incomplete_predictions") or 0) > 0:
            overall_status = "partial_success"

        return {
            "status": overall_status,
            "competition_id": comp.id,
            "competition_key": comp.key,
            "competition_name": comp.name,
            "season": comp.season,
            "round": round_label,
            "future_fixtures_count": future_fixtures_count,
            "next_round_fixtures": len(upcoming),
            "fixture_ids_processed": fixture_ids,
            "predictions_created_or_updated": predictions_created,
            "predictions_ok_v20": predictions_ok_v20,
            "team_stats_count": team_stats_count,
            "player_profiles_count": player_profiles_count,
            "lineup_rows_count": lineup_rows_count,
            "sportapi_mappings_count": sportapi_mappings_count,
            "lineups_ready": lineups_ready,
            "model_versions_requested": model_versions_requested,
            "active_model_fallback": BASELINE_SOT_MODEL_VERSION_V11_SOT
            if not lineups_ready
            else None,
            "selection": selection.as_log_dict(competition_id=comp.id),
            "warnings": warnings,
            "v11": v11_result,
            "v20": v20_result,
        }
