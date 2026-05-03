from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES, SOT_FEATURE_SET_VERSION
from app.models import Fixture, FixtureTeamStat, Season, TeamSotFeature
from app.services.sot_feature_math import (
    PriorMatch,
    compute_row_features,
    league_avg_sot_from_prior_fixtures,
)


class SotFeatureService:
    """
    Costruisce feature SOT per stagione. `league_id` è l'ID interno (`leagues.id`).
    """

    def build_features_for_season(self, db: Session, league_id: int, season_year: int) -> int:
        season = db.scalar(
            select(Season).where(Season.league_id == league_id, Season.year == season_year),
        )
        if season is None:
            raise ValueError(f"Stagione non trovata per league_id={league_id} year={season_year}")

        fixtures = db.scalars(
            select(Fixture)
            .where(
                Fixture.season_id == season.id,
                Fixture.status.in_(FINISHED_STATUSES),
            )
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()

        if not fixtures:
            return 0

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

        try:
            for f in fixtures:
                home_id = f.home_team_id
                away_id = f.away_team_id
                kickoff = f.kickoff_at

                prior_rows: list[tuple[int | None, int | None]] = []
                for pf in processed:
                    hs = sot_map.get((pf.id, pf.home_team_id))
                    aws = sot_map.get((pf.id, pf.away_team_id))
                    prior_rows.append((hs, aws))
                league_fallback = league_avg_sot_from_prior_fixtures(prior_rows)

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
                    league_fallback=league_fallback,
                    actual_sot=actual_home,
                )
                feats_away = compute_row_features(
                    current_kickoff=kickoff,
                    team_priors=away_prior,
                    is_home_current=False,
                    opponent_priors=home_prior,
                    opponent_is_home_current=True,
                    league_fallback=league_fallback,
                    actual_sot=actual_away,
                )

                rows_written += self._upsert_feature_row(db, f.id, home_id, feats_home)
                rows_written += self._upsert_feature_row(db, f.id, away_id, feats_away)

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
                home_hist = list(home_prior)
                home_hist.append(new_home)
                away_hist = list(away_prior)
                away_hist.append(new_away)
                team_history[home_id] = home_hist
                team_history[away_id] = away_hist
                processed.append(f)

            db.commit()
        except Exception:
            db.rollback()
            raise
        return rows_written

    def _upsert_feature_row(
        self,
        db: Session,
        fixture_id: int,
        team_id: int,
        features: dict[str, Any],
    ) -> int:
        row = db.scalar(
            select(TeamSotFeature).where(
                TeamSotFeature.fixture_id == fixture_id,
                TeamSotFeature.team_id == team_id,
            ),
        )
        if row is None:
            row = TeamSotFeature(
                fixture_id=fixture_id,
                team_id=team_id,
                feature_set_version=SOT_FEATURE_SET_VERSION,
                features=features,
            )
            db.add(row)
        else:
            row.feature_set_version = SOT_FEATURE_SET_VERSION
            row.features = features
        db.flush()
        return 1
