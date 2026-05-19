"""Fetch e merge multi-source injuries API-Football per fixture upcoming."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_parsing import (
    SOURCE_DETAIL_FIXTURE_DIRECT,
    SOURCE_DETAIL_IDS_BATCH,
    SOURCE_DETAIL_LEAGUE_SEASON_FILTERED,
)

SOURCE_PRIORITY: dict[str, int] = {
    SOURCE_DETAIL_IDS_BATCH: 0,
    SOURCE_DETAIL_LEAGUE_SEASON_FILTERED: 1,
    SOURCE_DETAIL_FIXTURE_DIRECT: 2,
}


@dataclass
class SourceFetchStats:
    called: bool = False
    results_total: int = 0
    records_matching_upcoming: int = 0
    error: str | None = None


@dataclass
class InjuriesFetchResult:
    sources: dict[str, SourceFetchStats] = field(default_factory=dict)
    merged_items: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    api_calls: int = 0


def item_api_fixture_id(item: dict[str, Any]) -> int | None:
    fx = item.get("fixture")
    if not isinstance(fx, dict):
        return None
    try:
        fid = fx.get("id")
        return int(fid) if fid is not None else None
    except (TypeError, ValueError):
        return None


def filter_items_for_upcoming(
    items: list[dict[str, Any]],
    upcoming_api_fixture_ids: set[int],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fid = item_api_fixture_id(item)
        if fid is not None and fid in upcoming_api_fixture_ids:
            out.append(item)
    return out


def dedupe_key(item: dict[str, Any]) -> tuple[int | None, int | None, int | None] | None:
    pl = item.get("player") if isinstance(item.get("player"), dict) else {}
    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    try:
        pid = int(pl["id"]) if pl.get("id") is not None else None
    except (TypeError, ValueError):
        pid = None
    try:
        tid = int(tm["id"]) if tm.get("id") is not None else None
    except (TypeError, ValueError):
        tid = None
    fid = item_api_fixture_id(item)
    if pid is None or tid is None or fid is None:
        return None
    return fid, tid, pid


def merge_sourced_items(
    batches: list[tuple[list[dict[str, Any]], str]],
) -> list[tuple[dict[str, Any], str]]:
    """Dedup con priorità: ids_batch > league_season_filtered > fixture_direct."""
    best: dict[tuple[int, int, int], tuple[dict[str, Any], str, int]] = {}
    for items, source_detail in batches:
        prio = SOURCE_PRIORITY.get(source_detail, 99)
        for item in items:
            if not isinstance(item, dict):
                continue
            key = dedupe_key(item)
            if key is None:
                continue
            prev = best.get(key)
            if prev is None or prio < prev[2]:
                best[key] = (item, source_detail, prio)
    return [(item, detail) for item, detail, _ in best.values()]


def fetch_injuries_multi_source(
    api: ApiFootballClient,
    *,
    api_league_id: int,
    season_year: int,
    upcoming_api_fixture_ids: list[int],
) -> InjuriesFetchResult:
    upcoming_set = {int(x) for x in upcoming_api_fixture_ids}
    result = InjuriesFetchResult()
    batches_for_merge: list[tuple[list[dict[str, Any]], str]] = []

    # A — ids batch
    ids_stats = SourceFetchStats()
    result.sources["ids_batch"] = ids_stats
    if upcoming_api_fixture_ids:
        ids_stats.called = True
        try:
            raw_items, errs = api.get_injuries_by_ids(upcoming_api_fixture_ids)
            result.api_calls += max(1, (len(upcoming_api_fixture_ids) + 19) // 20)
            ids_stats.results_total = len(raw_items)
            if errs:
                ids_stats.error = "; ".join(str(e) for e in errs[:3])[:500]
            matched = filter_items_for_upcoming(raw_items, upcoming_set)
            ids_stats.records_matching_upcoming = len(matched)
            batches_for_merge.append((matched, SOURCE_DETAIL_IDS_BATCH))
        except ApiFootballError as exc:
            ids_stats.error = str(exc)[:500]
            ids_stats.called = False

    # B — league + season, filtrato
    league_stats = SourceFetchStats(called=True)
    result.sources["league_season_filtered"] = league_stats
    try:
        league_raw = api.get_injuries(int(api_league_id), int(season_year))
        result.api_calls += 1
        league_stats.results_total = len(league_raw)
        matched = filter_items_for_upcoming(league_raw, upcoming_set)
        league_stats.records_matching_upcoming = len(matched)
        batches_for_merge.append((matched, SOURCE_DETAIL_LEAGUE_SEASON_FILTERED))
    except ApiFootballError as exc:
        league_stats.error = str(exc)[:500]
        league_stats.called = False

    # C — fixture direct (fallback diagnostico)
    fixture_stats = SourceFetchStats(called=True)
    result.sources["fixture_direct"] = fixture_stats
    direct_all: list[dict[str, Any]] = []
    for api_fx_id in upcoming_api_fixture_ids:
        try:
            batch = api.get_injuries_by_fixture(int(api_fx_id))
            result.api_calls += 1
            direct_all.extend(batch)
        except ApiFootballError:
            continue
    fixture_stats.results_total = len(direct_all)
    matched_direct = filter_items_for_upcoming(direct_all, upcoming_set)
    fixture_stats.records_matching_upcoming = len(matched_direct)
    batches_for_merge.append((matched_direct, SOURCE_DETAIL_FIXTURE_DIRECT))

    result.merged_items = merge_sourced_items(batches_for_merge)
    return result
