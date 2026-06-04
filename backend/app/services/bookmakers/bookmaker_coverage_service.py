"""Coverage quote bookmaker sul prossimo turno (per competizione)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.services.bookmakers.bookmaker_constants import MARKET_MATCH_WINNER_1X2
from app.services.bookmakers.fixture_bookmaker_odds_repository import list_odds_for_fixtures
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures


def _team_name(db: Session, team_id: int | None) -> str | None:
    if not team_id:
        return None
    t = db.get(Team, int(team_id))
    return t.name if t else None


class BookmakerCoverageService:
    def __init__(self, comp_svc: CompetitionService | None = None) -> None:
        self._comp_svc = comp_svc or CompetitionService()

    def get_coverage(
        self,
        db: Session,
        competition_id: int,
        *,
        fixture_id: int | None = None,
        only_next_round: bool = True,
        market: str = MARKET_MATCH_WINNER_1X2,
        provider_source: str | None = None,
        bookmaker_name: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        comp = self._comp_svc.get_by_id_or_raise(db, competition_id)
        all_fixtures = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all(),
        )

        if fixture_id is not None:
            target = [f for f in all_fixtures if int(f.id) == int(fixture_id)]
            round_label = None
        elif only_next_round:
            sel = select_next_round_fixtures(all_fixtures, limit=limit, only_next_round=True)
            target = sel.fixtures
            round_label = sel.final_round
        else:
            sel = select_next_round_fixtures(
                all_fixtures,
                limit=limit,
                only_next_round=False,
            )
            target = sel.fixtures
            round_label = sel.final_round

        fixture_ids = [int(f.id) for f in target]
        odds_rows = list_odds_for_fixtures(
            db,
            competition_id=int(comp.id),
            fixture_ids=fixture_ids,
            normalized_market=market,
            provider_source=provider_source,
            bookmaker_name=bookmaker_name,
        )

        by_fixture: dict[int, list[dict[str, Any]]] = {fid: [] for fid in fixture_ids}
        bookmaker_set: set[str] = set()
        for o in odds_rows:
            bookmaker_set.add(o.bookmaker_name)
            by_fixture.setdefault(int(o.fixture_id), []).append(
                {
                    "bookmaker_name": o.bookmaker_name,
                    "provider_source": o.provider_source,
                    "provider_bookmaker_id": o.provider_bookmaker_id,
                    "home_odds": o.home_odds,
                    "draw_odds": o.draw_odds,
                    "away_odds": o.away_odds,
                    "odds_updated_at": o.odds_updated_at.isoformat() if o.odds_updated_at else None,
                },
            )

        fixtures_out: list[dict[str, Any]] = []
        with_odds = 0
        for fx in target:
            fid = int(fx.id)
            sample = by_fixture.get(fid) or []
            has = len(sample) > 0
            if has:
                with_odds += 1
            fixtures_out.append(
                {
                    "fixture_id": fid,
                    "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
                    "home_team": _team_name(db, fx.home_team_id),
                    "away_team": _team_name(db, fx.away_team_id),
                    "has_odds": has,
                    "odds_count": len(sample),
                    "sample_odds": sample[:5],
                },
            )

        total = len(target)
        coverage_pct = round(100.0 * with_odds / total, 1) if total else 0.0

        return {
            "competition_id": int(comp.id),
            "competition_key": comp.key,
            "round_label": round_label,
            "market": market,
            "provider_source": provider_source,
            "fixtures_total": total,
            "fixtures_with_odds": with_odds,
            "coverage_pct": coverage_pct,
            "bookmakers_found": sorted(bookmaker_set),
            "fixtures": fixtures_out,
        }
