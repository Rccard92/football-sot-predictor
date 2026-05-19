"""Provider API-Football injuries per fixture upcoming."""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_injuries_sources import (
    SOURCE_DETAIL_FIXTURE_DIRECT,
    SOURCE_DETAIL_IDS_BATCH,
    SOURCE_DETAIL_LEAGUE_SEASON_FILTERED,
    fetch_injuries_multi_source,
    item_api_fixture_id,
)
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.availability.providers.base import (
    SOURCE_API_FOOTBALL_INJURIES,
    AvailabilityProvider,
    ProviderContext,
    ProviderFetchResult,
    PROVIDER_INJURIES,
)
from app.services.availability.providers.types import NormalizedAvailabilityCandidate


def _injuries_item_to_candidate(
    item: dict[str, Any],
    *,
    source_detail: str,
    fx: Fixture,
    ctx: ProviderContext,
) -> NormalizedAvailabilityCandidate | None:
    parsed = parse_injuries_item(item)
    if parsed is None or parsed.api_player_id is None:
        return None
    ko = fx.kickoff_at
    fixture_date = parsed.fixture_date or (ko.date() if hasattr(ko, "date") else None)
    return NormalizedAvailabilityCandidate(
        fixture_id=int(fx.id),
        api_fixture_id=int(fx.api_fixture_id),
        season=int(ctx.season_year),
        league_id=int(ctx.league_internal_id),
        api_league_id=int(ctx.api_league_id),
        team_id=None,
        api_team_id=parsed.api_team_id,
        team_name=parsed.team_name,
        player_id=None,
        api_player_id=parsed.api_player_id,
        player_name=parsed.player_name,
        availability_status=parsed.availability_status,
        availability_type=parsed.availability_type,
        reason=parsed.reason,
        source=SOURCE_API_FOOTBALL_INJURIES,
        source_detail=source_detail,
        record_scope="fixture_level",
        confidence="HIGH",
        applicability_status="candidate",
        applicability_reason=None,
        start_date=parsed.start_date,
        end_date=parsed.end_date,
        fixture_date=fixture_date,
        reported_at=parsed.reported_at,
        raw_json=dict(parsed.raw_json) if parsed.raw_json else {},
    )


class ApiFootballInjuriesProvider(AvailabilityProvider):
    name = PROVIDER_INJURIES

    def fetch_candidates(self, ctx: ProviderContext) -> ProviderFetchResult:
        result = ProviderFetchResult(provider_name=PROVIDER_INJURIES, called=True, status="success")
        try:
            api = ctx.api_client or ApiFootballClient()
            fetch_result = fetch_injuries_multi_source(
                api,
                api_league_id=int(ctx.api_league_id),
                season_year=int(ctx.season_year),
                upcoming_api_fixture_ids=ctx.upcoming_api_fixture_ids,
            )
            result.api_calls = fetch_result.api_calls
            result.raw_items_total = sum(s.results_total for s in fetch_result.sources.values())

            for item, source_detail in fetch_result.merged_items:
                api_fx = item_api_fixture_id(item)
                if api_fx is None or api_fx not in ctx.fx_by_api_id:
                    continue
                fx = ctx.fx_by_api_id[api_fx]
                cand = _injuries_item_to_candidate(item, source_detail=source_detail, fx=fx, ctx=ctx)
                if cand is not None:
                    result.candidates.append(cand)
        except ApiFootballError as exc:
            result.called = True
            result.status = "error"
            result.error = str(exc)[:500]
        except Exception as exc:  # noqa: BLE001
            result.called = True
            result.status = "error"
            result.error = str(exc)[:500]
        return result
