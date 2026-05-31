"""Test deduplica indisponibili SportAPI (Step K / JK.1)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.fixture_missing_player import FixtureMissingPlayer
from app.services.backtest.pit_player_rolling_stats import RawPlayerRow, missing_to_rows
from app.services.backtest.pit_unavailable_dedup import (
    dedupe_missing_player_rows,
    dedupe_raw_unavailable_rows,
    normalize_player_name_for_dedup,
)


def _missing_row(
    *,
    fixture_id: int = 359,
    team_side: str = "home",
    provider_player_id: int = 1001,
    player_name: str = "Tomori",
    reason: str = "injury",
) -> FixtureMissingPlayer:
    row = MagicMock(spec=FixtureMissingPlayer)
    row.fixture_id = fixture_id
    row.team_side = team_side
    row.provider_player_id = provider_player_id
    row.player_name = player_name
    row.provider_name = "sportapi"
    row.reason = reason
    row.description = None
    row.external_type = None
    row.position = "D"
    return row


def test_dedupe_missing_player_rows_eight_to_four():
    rows = [
        _missing_row(provider_player_id=1001, player_name="Tomori", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1001, player_name="Tomori", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1002, player_name="Pulisic", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1002, player_name="Pulisic", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1003, player_name="Modric", team_side="home", reason="suspended"),
        _missing_row(provider_player_id=1003, player_name="Modric", team_side="home", reason="suspended"),
        _missing_row(provider_player_id=2001, player_name="Bernasconi", team_side="away", reason="injury"),
        _missing_row(provider_player_id=2001, player_name="Bernasconi", team_side="away", reason="injury"),
    ]
    deduped = dedupe_missing_player_rows(rows)
    assert len(deduped) == 4


def test_missing_to_rows_applies_dedupe():
    rows = [
        _missing_row(provider_player_id=1001),
        _missing_row(provider_player_id=1001),
    ]
    out = missing_to_rows(rows)
    assert len(out) == 1
    assert out[0].provider_player_id == 1001


def test_dedupe_raw_unavailable_rows_by_provider_id():
    rows = [
        RawPlayerRow(
            player_name="Tomori",
            provider_player_id=1001,
            api_player_id=None,
            position="D",
            is_starter=False,
            is_unavailable=True,
            absence_group="injured",
        ),
        RawPlayerRow(
            player_name="Tomori duplicate",
            provider_player_id=1001,
            api_player_id=None,
            position="D",
            is_starter=False,
            is_unavailable=True,
            absence_group="injured",
        ),
    ]
    deduped = dedupe_raw_unavailable_rows(rows, fixture_id=359)
    assert len(deduped) == 1


def test_normalize_player_name_strips_accents():
    assert normalize_player_name_for_dedup("Pulišić") == normalize_player_name_for_dedup("Pulisic")


def test_scan_fixture_normalized_plus_raw_counts_four_only():
    from app.models import Fixture, FixtureLineup, FixtureProviderLineup
    from app.services.backtest.historical_unavailable_audit_service import HistoricalUnavailableAuditService

    fixture = MagicMock(spec=Fixture)
    fixture.id = 359
    fixture.home_team_id = 1
    fixture.away_team_id = 2
    fixture.round = "Regular Season - 36"
    fixture.competition_id = 10

    missing = [
        _missing_row(provider_player_id=1001, player_name="Tomori", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1002, player_name="Pulisic", team_side="home", reason="injury"),
        _missing_row(provider_player_id=1003, player_name="Modric", team_side="home", reason="suspension"),
        _missing_row(provider_player_id=2001, player_name="Bernasconi", team_side="away", reason="injury"),
    ]

    lineup = MagicMock(spec=FixtureLineup)
    lineup.team_id = 1
    lineup.raw_json = {
        "injured": [
            {"id": 1001, "name": "Tomori"},
            {"id": 1002, "name": "Pulisic"},
        ],
    }

    provider = MagicMock(spec=FixtureProviderLineup)
    provider.raw_payload = {
        "missingPlayers": {
            "home": [{"id": 1001, "name": "Tomori"}],
            "away": [{"id": 2001, "name": "Bernasconi"}],
        },
    }
    provider.provider_event_id = 999

    db = MagicMock()
    scalars_calls = {"n": 0}

    def _scalar(stmt):
        stmt_str = str(stmt)
        if "FixtureProviderLineup" in stmt_str:
            return provider
        if "FixtureProviderMapping" in stmt_str:
            return None
        return None

    def _scalars(_stmt):
        result = MagicMock()
        if scalars_calls["n"] == 0:
            result.all.return_value = missing
        elif scalars_calls["n"] == 1:
            result.all.return_value = [lineup]
        else:
            result.all.return_value = []
        scalars_calls["n"] += 1
        return result

    db.scalars.side_effect = _scalars
    db.scalar.side_effect = _scalar

    scan = HistoricalUnavailableAuditService()._scan_fixture(
        db,
        fixture=fixture,
        home_name="AC Milan",
        away_name="Atalanta",
    )

    assert scan.total_unavailable == 4
    assert scan.home.total == 3
    assert scan.away.total == 1
    assert scan.home.injured == 2
    assert scan.home.suspended == 1
    assert scan.source_paths_used_for_counts == {"fixture_missing_players.sportapi"}
    assert scan.source_paths_detected_diagnostic
    assert "fixture_lineups.raw_json" in scan.source_paths_detected_diagnostic
