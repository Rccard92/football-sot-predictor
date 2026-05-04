"""Costruisce profili aggregati tiri in porta per giocatore (stagione); non modifica il baseline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureLineup, FixturePlayerStat, FixtureTeamStat, Player, PlayerSotProfile
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


def _start_xi_api_ids(start_xi: Any) -> set[int]:
    out: set[int] = set()
    if not start_xi or not isinstance(start_xi, list):
        return out
    for item in start_xi:
        if not isinstance(item, dict):
            continue
        pl = item.get("player") or {}
        pid = pl.get("id")
        if pid is None:
            continue
        try:
            out.add(int(pid))
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class _Appearance:
    fixture_id: int
    team_id: int
    kickoff: Any
    minutes: int
    sot: int
    substitute: bool | None
    is_start: bool


@dataclass
class _Agg:
    team_id: int
    appearances: list[_Appearance] = field(default_factory=list)
    total_shots: int = 0


class PlayerSotProfileService:
    def build_for_season(self, db: Session, season_year: int) -> dict[str, Any]:
        ing = IngestionService()
        try:
            season_row = ing._serie_a_season_row(db, season_year)
        except ValueError as exc:
            return {"status": "error", "message": str(exc), "rows_upserted": 0}

        lineups = db.scalars(
            select(FixtureLineup).join(Fixture, Fixture.id == FixtureLineup.fixture_id).where(
                Fixture.season_id == season_row.id,
            ),
        ).all()
        lineup_starters: dict[tuple[int, int], set[int]] = {}
        for lu in lineups:
            lineup_starters[(lu.fixture_id, lu.team_id)] = _start_xi_api_ids(lu.start_xi)

        fps = db.scalars(
            select(FixturePlayerStat)
            .join(Fixture, Fixture.id == FixturePlayerStat.fixture_id)
            .where(
                Fixture.season_id == season_row.id,
                Fixture.status.in_(FINISHED_STATUSES),
            ),
        ).all()

        by_player: dict[int, _Agg] = {}

        for fp in fps:
            fx = db.get(Fixture, fp.fixture_id)
            if fx is None:
                continue
            pl = db.get(Player, fp.player_id)
            if pl is None:
                continue
            m = int(fp.minutes or 0)
            sot = int(fp.shots_on_target or 0)
            st = int(fp.shots_total or 0)
            sub = fp.substitute
            starters = lineup_starters.get((fp.fixture_id, fp.team_id))
            is_start = False
            if starters is not None and starters:
                is_start = pl.api_player_id in starters
            else:
                is_start = m >= 46 and sub is not True

            if m <= 0 and sot == 0 and st == 0:
                continue

            if fp.player_id not in by_player:
                by_player[fp.player_id] = _Agg(team_id=fp.team_id)
            agg = by_player[fp.player_id]
            if agg.team_id != fp.team_id:
                logger.warning(
                    "player %s: team_id incoerente tra apparizioni, uso ultimo team_id=%s",
                    fp.player_id,
                    fp.team_id,
                )
                agg.team_id = fp.team_id
            agg.total_shots += int(fp.shots_total or 0)
            agg.appearances.append(
                _Appearance(
                    fixture_id=fp.fixture_id,
                    team_id=fp.team_id,
                    kickoff=fx.kickoff_at,
                    minutes=m,
                    sot=sot,
                    substitute=sub,
                    is_start=is_start,
                ),
            )

        db.execute(delete(PlayerSotProfile).where(PlayerSotProfile.season_id == season_row.id))

        n_ok = 0
        for player_id, agg in by_player.items():
            apps = sorted(agg.appearances, key=lambda a: a.kickoff)
            appearances = len(apps)
            if appearances == 0:
                continue
            starts = sum(1 for a in apps if a.is_start)
            total_minutes = sum(a.minutes for a in apps)
            total_sot = sum(a.sot for a in apps)
            avg_minutes = total_minutes / appearances if appearances else 0.0
            sot_per90 = (total_sot / total_minutes * 90.0) if total_minutes > 0 else None

            team_sot_sum = 0
            for a in apps:
                fts = db.scalar(
                    select(FixtureTeamStat).where(
                        FixtureTeamStat.fixture_id == a.fixture_id,
                        FixtureTeamStat.team_id == a.team_id,
                    ),
                )
                if fts and fts.shots_on_target is not None:
                    team_sot_sum += int(fts.shots_on_target)
            team_share = (100.0 * total_sot / team_sot_sum) if team_sot_sum > 0 else None

            last5 = apps[-5:]
            per90s: list[float] = []
            for a in last5:
                if a.minutes > 0:
                    per90s.append(a.sot / a.minutes * 90.0)
            last5_avg = sum(per90s) / len(per90s) if per90s else None

            rel = 50
            if total_minutes >= 900:
                rel += 20
            if appearances >= 10:
                rel += 10
            if total_minutes < 300:
                rel -= 20
            rel = max(0, min(100, rel))

            norm_sot = 0.0
            if sot_per90 is not None:
                norm_sot = min(max(float(sot_per90) / 2.0, 0.0), 1.0)
            norm_share = min(max((team_share or 0.0) / 100.0, 0.0), 1.0)
            norm_rel = rel / 100.0
            impact = round(0.50 * norm_sot + 0.30 * norm_share + 0.20 * norm_rel, 4)

            row = PlayerSotProfile(
                season_id=season_row.id,
                team_id=agg.team_id,
                player_id=player_id,
                appearances=appearances,
                starts=starts,
                total_minutes=total_minutes,
                avg_minutes=round(avg_minutes, 2),
                total_shots=agg.total_shots,
                total_shots_on_target=total_sot,
                shots_on_target_per90=round(float(sot_per90), 4) if sot_per90 is not None else None,
                team_sot_share_pct=round(float(team_share), 4) if team_share is not None else None,
                last5_shots_on_target_per90=round(float(last5_avg), 4) if last5_avg is not None else None,
                reliability_score=rel,
                impact_score=impact,
            )
            db.add(row)
            n_ok += 1

        db.commit()
        return {"status": "success", "rows_upserted": n_ok, "season": season_year}

    def summary(self, db: Session, season_year: int) -> dict[str, Any]:
        ing = IngestionService()
        try:
            season_row = ing._serie_a_season_row(db, season_year)
        except ValueError as exc:
            return {
                "season": season_year,
                "players_profiled": 0,
                "avg_impact_score": 0.0,
                "top_players_by_impact": [],
                "top_players_by_sot_per90": [],
                "message": str(exc),
            }

        total = int(
            db.scalar(select(func.count()).select_from(PlayerSotProfile).where(
                PlayerSotProfile.season_id == season_row.id,
            ))
            or 0,
        )
        avg_imp = db.scalar(
            select(func.avg(PlayerSotProfile.impact_score)).where(
                PlayerSotProfile.season_id == season_row.id,
                PlayerSotProfile.impact_score.isnot(None),
            ),
        )
        avg_imp_f = round(float(avg_imp or 0.0), 4)

        top_imp = db.execute(
            select(PlayerSotProfile, Player)
            .join(Player, Player.id == PlayerSotProfile.player_id)
            .where(PlayerSotProfile.season_id == season_row.id)
            .order_by(PlayerSotProfile.impact_score.desc().nulls_last())
            .limit(10),
        ).all()
        top_sot = db.execute(
            select(PlayerSotProfile, Player)
            .join(Player, Player.id == PlayerSotProfile.player_id)
            .where(PlayerSotProfile.season_id == season_row.id)
            .order_by(PlayerSotProfile.shots_on_target_per90.desc().nulls_last())
            .limit(10),
        ).all()

        def pack(rows: list[Any], n: int = 5) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for pr, pl in rows[:n]:
                out.append(
                    {
                        "player_id": pl.id,
                        "name": pl.name,
                        "team_id": pr.team_id,
                        "impact_score": pr.impact_score,
                        "shots_on_target_per90": pr.shots_on_target_per90,
                        "appearances": pr.appearances,
                    },
                )
            return out

        return {
            "season": season_year,
            "players_profiled": total,
            "avg_impact_score": avg_imp_f,
            "top_players_by_impact": pack(list(top_imp), 5),
            "top_players_by_sot_per90": pack(list(top_sot), 5),
        }

    def top_for_team(
        self,
        db: Session,
        *,
        season_id: int,
        team_id: int,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            select(PlayerSotProfile, Player)
            .join(Player, Player.id == PlayerSotProfile.player_id)
            .where(
                PlayerSotProfile.season_id == season_id,
                PlayerSotProfile.team_id == team_id,
            )
            .order_by(PlayerSotProfile.impact_score.desc().nulls_last())
            .limit(limit),
        ).all()
        out: list[dict[str, Any]] = []
        for pr, pl in rows:
            out.append(
                {
                    "player_id": pl.id,
                    "name": pl.name,
                    "impact_score": pr.impact_score,
                    "shots_on_target_per90": pr.shots_on_target_per90,
                    "appearances": pr.appearances,
                },
            )
        return out
