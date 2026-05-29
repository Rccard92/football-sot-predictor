"""Test etichette stato formazione SportAPI per report rapido."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.sportapi.sportapi_lineup_status import (
    build_lineup_coverage_messages,
    formation_status_label,
)


def test_formation_status_missing():
    assert formation_status_label(has_lineup=False, confirmed=None, fetched_at=None) == "Mancante"


def test_formation_status_official():
    assert formation_status_label(has_lineup=True, confirmed=True, fetched_at=None) == "Ufficiale"


def test_formation_status_updated_within_6h():
    recent = datetime.now(timezone.utc) - timedelta(hours=3)
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=recent) == "Probabili aggiornate"


def test_formation_status_stale_over_6h():
    old = datetime.now(timezone.utc) - timedelta(hours=8)
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=old) == "Da aggiornare"


def test_formation_status_no_fetched_at():
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=None) == "Da aggiornare"


def test_build_lineup_coverage_full_sportapi_no_api_football():
    coverage = {
        "next_round_fixture_count": 10,
        "next_round_sportapi_lineups_count": 10,
        "next_round_coverage_pct": 100.0,
        "confirmed_lineups_count": 0,
        "probable_lineups_count": 10,
    }
    warnings, info = build_lineup_coverage_messages(coverage=coverage, api_football_lineups_count=0)
    assert warnings == []
    assert info == ["Formazioni SportAPI disponibili per tutto il turno."]


def test_build_lineup_coverage_partial():
    coverage = {
        "next_round_fixture_count": 10,
        "next_round_sportapi_lineups_count": 5,
        "next_round_coverage_pct": 50.0,
        "confirmed_lineups_count": 2,
        "probable_lineups_count": 3,
    }
    warnings, info = build_lineup_coverage_messages(coverage=coverage, api_football_lineups_count=0)
    assert len(warnings) == 1
    assert "5/10" in warnings[0]
    assert info == []


def test_build_lineup_coverage_none():
    coverage = {
        "next_round_fixture_count": 10,
        "next_round_sportapi_lineups_count": 0,
        "next_round_coverage_pct": 0.0,
        "confirmed_lineups_count": 0,
        "probable_lineups_count": 0,
    }
    warnings, info = build_lineup_coverage_messages(coverage=coverage, api_football_lineups_count=0)
    assert len(warnings) == 1
    assert "non disponibili" in warnings[0].lower()
    assert info == []


def test_build_lineup_coverage_api_football_only_legacy():
    coverage = {
        "next_round_fixture_count": 10,
        "next_round_sportapi_lineups_count": 0,
        "next_round_coverage_pct": 0.0,
        "confirmed_lineups_count": 0,
        "probable_lineups_count": 0,
    }
    warnings, info = build_lineup_coverage_messages(coverage=coverage, api_football_lineups_count=5)
    assert warnings == []
    assert info == []
