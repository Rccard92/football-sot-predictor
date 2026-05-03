from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES, SOT_FEATURE_SET_VERSION
from app.models import Fixture, FixtureTeamStat, League, Season, TeamSotFeature
from app.services.ingestion_service import IngestionService
from app.services.sot_feature_math import (
    PriorMatch,
    compute_row_features,
    league_avg_sot_from_prior_fixtures,
)

logger = logging.getLogger(__name__)


def _num(val: float | None) -> Decimal | None:
    if val is None:
        return None
    return Decimal(str(round(float(val), 6)))


class SotFeatureService:
    """Feature engineering SOT per stagione (Serie A), senza data leakage."""

    def _season_and_fixtures_with_two_stats(
        self,
        db: Session,
        season_year: int,
    ) -> tuple[Season, list[Fixture]]:
        settings = get_settings()
        league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError(
                f"Lega con api_league_id={settings.default_league_id} non trovata",
            )
        season = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per year={season_year}")

        two_row_fx = (
            select(FixtureTeamStat.fixture_id.label("fid"))
            .group_by(FixtureTeamStat.fixture_id)
            .having(func.count() == 2)
            .subquery()
        )
        fixtures = db.scalars(
            select(Fixture)
            .join(two_row_fx, two_row_fx.c.fid == Fixture.id)
            .where(
                Fixture.season_id == season.id,
                Fixture.status.in_(FINISHED_STATUSES),
            )
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()
        return season, list(fixtures)

    def get_season_summary(self, db: Session, season_year: int) -> dict[str, Any]:
        try:
            season, fixtures = self._season_and_fixtures_with_two_stats(db, season_year)
        except ValueError:
            return {
                "season": season_year,
                "fixtures_completed": 0,
                "expected_feature_rows": 0,
                "feature_rows_total": 0,
                "coverage_pct": 0.0,
                "missing_feature_rows": 0,
            }

        expected = len(fixtures) * 2
        feature_rows_total = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotFeature)
                .join(Fixture, Fixture.id == TeamSotFeature.fixture_id)
                .where(Fixture.season_id == season.id),
            )
            or 0,
        )
        n_fix = len(fixtures)
        coverage = round(100.0 * feature_rows_total / expected, 2) if expected else 0.0
        missing = max(0, expected - feature_rows_total)
        return {
            "season": season_year,
            "fixtures_completed": n_fix,
            "expected_feature_rows": expected,
            "feature_rows_total": feature_rows_total,
            "coverage_pct": coverage,
            "missing_feature_rows": missing,
        }

    def build_features_for_season_admin(self, db: Session, season_year: int) -> dict[str, Any]:
        """
        Costruisce/aggiorna righe `team_sot_features`. Idempotente su (fixture_id, team_id).
        Crea ingestion_run con source `build_sot_features`.
        """
        settings = get_settings()
        baseline = settings.sot_feature_fallback_baseline

        summary: dict[str, Any] = {
            "status": "pending",
            "season": season_year,
            "fixtures_targeted": 0,
            "rows_upserted": 0,
            "errors": [],
        }

        ing = IngestionService()
        run = ing._begin_run(
            db,
            "build_sot_features",
            meta={"season": season_year, "step": "sot_features"},
        )

        try:
            season, fixtures = self._season_and_fixtures_with_two_stats(db, season_year)
        except ValueError as exc:
            logger.warning("build_sot_features: %s", exc)
            summary["status"] = "error"
            summary["message"] = str(exc)
            ing._finish_run(
                db,
                run,
                success=False,
                records_processed=0,
                error=str(exc),
                meta_merge={"summary": summary},
            )
            summary["ingestion_run_id"] = run.id
            return summary

        summary["fixtures_targeted"] = len(fixtures)
        if not fixtures:
            summary["status"] = "success"
            ing._finish_run(db, run, success=True, records_processed=0, meta_merge={"summary": summary})
            summary["ingestion_run_id"] = run.id
            return summary

        fixture_ids = [f.id for f in fixtures]
        stats = db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids)),
        ).all()
        sot_map: dict[tuple[int, int], int | None] = {
            (s.fixture_id, s.team_id): s.shots_on_target for s in stats
        }

        team_history: dict[int, list[PriorMatch]] = {}
        processed: list[Fixture] = []
        rows_written = 0

        for f in fixtures:
            home_id = f.home_team_id
            away_id = f.away_team_id
            kickoff = f.kickoff_at

            try:
                prior_rows: list[tuple[int | None, int | None]] = []
                for pf in processed:
                    hs = sot_map.get((pf.id, pf.home_team_id))
                    aws = sot_map.get((pf.id, pf.away_team_id))
                    prior_rows.append((hs, aws))
                league_avg = league_avg_sot_from_prior_fixtures(prior_rows)

                home_prior = team_history.get(home_id, [])
                away_prior = team_history.get(away_id, [])

                actual_home = sot_map.get((f.id, home_id))
                actual_away = sot_map.get((f.id, away_id))

                feats_home = compute_row_features(
                    current_kickoff=kickoff,
                    team_priors=home_prior,
                    is_home_current=True,
                    opponent_priors=away_prior,
                    opponent_is_home_current=False,
                    league_fallback=league_avg,
                    baseline=baseline,
                    actual_sot=actual_home,
                )
                feats_away = compute_row_features(
                    current_kickoff=kickoff,
                    team_priors=away_prior,
                    is_home_current=False,
                    opponent_priors=home_prior,
                    opponent_is_home_current=True,
                    league_fallback=league_avg,
                    baseline=baseline,
                    actual_sot=actual_away,
                )

                self._upsert_feature_row(
                    db,
                    fixture=f,
                    team_id=home_id,
                    opponent_team_id=away_id,
                    side="home",
                    feats=feats_home,
                )
                self._upsert_feature_row(
                    db,
                    fixture=f,
                    team_id=away_id,
                    opponent_team_id=home_id,
                    side="away",
                    feats=feats_away,
                )
                rows_written += 2

                home_against = actual_away
                away_against = actual_home
                new_home = PriorMatch(
                    kickoff=kickoff,
                    fixture_id=f.id,
                    is_home=True,
                    sot_for=actual_home,
                    sot_against=home_against,
                )
                new_away = PriorMatch(
                    kickoff=kickoff,
                    fixture_id=f.id,
                    is_home=False,
                    sot_for=actual_away,
                    sot_against=away_against,
                )
                team_history[home_id] = list(home_prior) + [new_home]
                team_history[away_id] = list(away_prior) + [new_away]
                processed.append(f)
            except Exception as exc:
                logger.exception(
                    "build_sot_features: errore fixture_id=%s api_fixture_id=%s",
                    f.id,
                    f.api_fixture_id,
                )
                summary["errors"].append(
                    {
                        "fixture_id": f.id,
                        "api_fixture_id": int(f.api_fixture_id),
                        "team_id": None,
                        "message": str(exc),
                    },
                )

        try:
            db.commit()
            summary["status"] = "success"
            summary["rows_upserted"] = rows_written
            ing._finish_run(
                db,
                run,
                success=True,
                records_processed=rows_written,
                meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
            )
        except Exception as exc:
            logger.exception("build_sot_features: commit fallito")
            db.rollback()
            summary["status"] = "error"
            summary["message"] = str(exc)
            try:
                ing._finish_run(
                    db,
                    run,
                    success=False,
                    records_processed=rows_written,
                    error=str(exc),
                    meta_merge={"summary": {k: v for k, v in summary.items() if k != "status"}},
                )
            except Exception:
                logger.exception("build_sot_features: impossibile finalizzare ingestion_run")

        summary["ingestion_run_id"] = run.id
        return summary

    def _upsert_feature_row(
        self,
        db: Session,
        *,
        fixture: Fixture,
        team_id: int,
        opponent_team_id: int,
        side: str,
        feats: dict[str, Any],
    ) -> None:
        row = db.scalar(
            select(TeamSotFeature).where(
                TeamSotFeature.fixture_id == fixture.id,
                TeamSotFeature.team_id == team_id,
            ),
        )
        meta = feats.get("meta")
        payload = {k: v for k, v in feats.items() if k != "meta"}
        features_json = {"meta": meta} if meta else None

        if row is None:
            row = TeamSotFeature(
                fixture_id=fixture.id,
                team_id=team_id,
                opponent_team_id=opponent_team_id,
                side=side,
                fixture_date=fixture.kickoff_at,
                season_avg_sot_for=_num(payload.get("season_avg_sot_for")),
                season_avg_sot_against=_num(payload.get("season_avg_sot_against")),
                home_away_avg_sot_for=_num(payload.get("home_away_avg_sot_for")),
                home_away_avg_sot_against=_num(payload.get("home_away_avg_sot_against")),
                last5_avg_sot_for=_num(payload.get("last5_avg_sot_for")),
                last5_avg_sot_against=_num(payload.get("last5_avg_sot_against")),
                last10_avg_sot_for=_num(payload.get("last10_avg_sot_for")),
                last10_avg_sot_against=_num(payload.get("last10_avg_sot_against")),
                opponent_season_avg_sot_conceded=_num(payload.get("opponent_season_avg_sot_conceded")),
                opponent_home_away_avg_sot_conceded=_num(
                    payload.get("opponent_home_away_avg_sot_conceded"),
                ),
                opponent_last5_avg_sot_conceded=_num(payload.get("opponent_last5_avg_sot_conceded")),
                rest_days=payload.get("rest_days"),
                actual_sot=payload.get("actual_sot"),
                fallback_used=bool(payload.get("fallback_used")),
                previous_matches_count=payload.get("previous_matches_count"),
                opponent_previous_matches_count=payload.get("opponent_previous_matches_count"),
                feature_set_version=SOT_FEATURE_SET_VERSION,
                features=features_json,
            )
            db.add(row)
        else:
            row.opponent_team_id = opponent_team_id
            row.side = side
            row.fixture_date = fixture.kickoff_at
            row.season_avg_sot_for = _num(payload.get("season_avg_sot_for"))
            row.season_avg_sot_against = _num(payload.get("season_avg_sot_against"))
            row.home_away_avg_sot_for = _num(payload.get("home_away_avg_sot_for"))
            row.home_away_avg_sot_against = _num(payload.get("home_away_avg_sot_against"))
            row.last5_avg_sot_for = _num(payload.get("last5_avg_sot_for"))
            row.last5_avg_sot_against = _num(payload.get("last5_avg_sot_against"))
            row.last10_avg_sot_for = _num(payload.get("last10_avg_sot_for"))
            row.last10_avg_sot_against = _num(payload.get("last10_avg_sot_against"))
            row.opponent_season_avg_sot_conceded = _num(payload.get("opponent_season_avg_sot_conceded"))
            row.opponent_home_away_avg_sot_conceded = _num(
                payload.get("opponent_home_away_avg_sot_conceded"),
            )
            row.opponent_last5_avg_sot_conceded = _num(payload.get("opponent_last5_avg_sot_conceded"))
            row.rest_days = payload.get("rest_days")
            row.actual_sot = payload.get("actual_sot")
            row.fallback_used = bool(payload.get("fallback_used"))
            row.previous_matches_count = payload.get("previous_matches_count")
            row.opponent_previous_matches_count = payload.get("opponent_previous_matches_count")
            row.feature_set_version = SOT_FEATURE_SET_VERSION
            row.features = features_json
        db.flush()

    def get_fixture_feature_rows(self, db: Session, fixture_id: int) -> list[TeamSotFeature]:
        rows = db.scalars(
            select(TeamSotFeature)
            .where(TeamSotFeature.fixture_id == fixture_id)
            .order_by(TeamSotFeature.side.desc().nulls_last(), TeamSotFeature.team_id.asc()),
        ).all()
        return list(rows)
