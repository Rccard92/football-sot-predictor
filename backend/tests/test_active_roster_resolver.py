"""Test ActiveRosterResolver."""

from unittest.mock import MagicMock

from app.services.player_data.active_roster_resolver import ActiveRosterResolver, TeamRosterContext


def test_resolve_active_when_in_squad():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids={42},
        all_team_rows_count=5,
        has_squad_data=True,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    res = resolver.resolve_player(api_player_id=42, ctx=ctx)
    assert res.status == "ACTIVE"


def test_resolve_not_in_squad():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids={1},
        all_team_rows_count=5,
        has_squad_data=True,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    res = resolver.resolve_player(api_player_id=99, ctx=ctx)
    assert res.status == "NOT_IN_CURRENT_SQUAD"


def test_resolve_transferred_out():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids=set(),
        all_team_rows_count=5,
        has_squad_data=True,
        active_on_other_teams={77: 200},
    )
    resolver = ActiveRosterResolver(MagicMock())
    res = resolver.resolve_player(api_player_id=77, ctx=ctx)
    assert res.status == "TRANSFERRED_OUT"
    assert res.active_on_other_team is True


def test_resolve_unknown_without_squad_no_legacy_when_disabled():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids=set(),
        all_team_rows_count=0,
        has_squad_data=False,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    res = resolver.resolve_player(
        api_player_id=5,
        ctx=ctx,
        legacy_team_id=10,
        allow_legacy_active=False,
    )
    assert res.status == "UNKNOWN"


def test_resolve_legacy_active_when_allowed():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids=set(),
        all_team_rows_count=0,
        has_squad_data=False,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    res = resolver.resolve_player(
        api_player_id=5,
        ctx=ctx,
        legacy_team_id=10,
        allow_legacy_active=True,
    )
    assert res.status == "ACTIVE"
    assert res.roster_source == "legacy_team_id"


def test_filter_top_excludes_not_in_squad():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=100,
        internal_team_id=10,
        active_api_player_ids={1},
        all_team_rows_count=3,
        has_squad_data=True,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    candidates = [
        {
            "player_id": 10,
            "api_player_id": 99,
            "player_name": "Lookman",
            "shots_on_target_per90": 2.0,
            "team_sot_share_pct": 12.0,
        },
        {
            "player_id": 11,
            "api_player_id": 1,
            "player_name": "Kean",
            "shots_on_target_per90": 1.5,
            "team_sot_share_pct": 20.0,
        },
    ]
    top, excluded = resolver.filter_top_candidates(
        candidates=candidates,
        ctx=ctx,
        top_n=5,
        allow_legacy_active=False,
    )
    assert len(top) == 1
    assert top[0]["player_name"] == "Kean"
    assert len(excluded) == 1
    assert excluded[0]["player_name"] == "Lookman"


def test_filter_top_unknown_fill_when_no_squad_no_legacy():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=499,
        internal_team_id=10,
        active_api_player_ids=set(),
        all_team_rows_count=0,
        has_squad_data=False,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    candidates = [
        {
            "player_id": 10,
            "api_player_id": 99,
            "player_name": "Lookman",
            "legacy_team_id": 10,
            "shots_on_target_per90": 2.0,
            "team_sot_share_pct": 12.0,
        },
    ]
    top, excluded = resolver.filter_top_candidates(
        candidates=candidates,
        ctx=ctx,
        allow_legacy_active=False,
    )
    assert len(top) == 1
    assert top[0]["included_as_unknown"] is True
    assert top[0]["roster_status"] == "UNKNOWN"
    assert len(excluded) == 0


def test_collect_excluded_full_scan():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=499,
        internal_team_id=10,
        active_api_player_ids={1},
        all_team_rows_count=10,
        has_squad_data=True,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    candidates = [
        {
            "player_id": 10,
            "api_player_id": 99,
            "player_name": "Lookman",
            "shots_on_target_per90": 0.5,
            "team_sot_share_pct": 12.9,
        },
        {
            "player_id": 11,
            "api_player_id": 1,
            "player_name": "Kean",
            "shots_on_target_per90": 2.0,
            "team_sot_share_pct": 20.0,
        },
    ]
    excluded = resolver.collect_excluded_players(candidates=candidates, ctx=ctx)
    assert len(excluded) == 1
    assert excluded[0]["player_name"] == "Lookman"


def test_collect_excluded_empty_when_no_squad():
    ctx = TeamRosterContext(
        season_year=2025,
        league_id=1,
        api_team_id=499,
        internal_team_id=10,
        active_api_player_ids=set(),
        all_team_rows_count=0,
        has_squad_data=False,
        active_on_other_teams={},
    )
    resolver = ActiveRosterResolver(MagicMock())
    excluded = resolver.collect_excluded_players(
        candidates=[{"player_id": 1, "api_player_id": 99, "team_sot_share_pct": 15.0}],
        ctx=ctx,
    )
    assert excluded == []
