from datetime import datetime

from pydantic import BaseModel


class StandingTeamRow(BaseModel):
    rank: int | None = None
    team_id: int
    team_name: str
    points: int | None = None
    played: int | None = None
    goals_diff: int | None = None
    form: str | None = None
    description: str | None = None


class LatestStandingsResponse(BaseModel):
    season: int
    snapshot_at: datetime | None = None
    teams: list[StandingTeamRow]
