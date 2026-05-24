"""Test dashboard monitoraggio: doppio esito e risoluzione snapshot."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.tracked_monitoring_dashboard_service import (
    compute_dashboard_summary,
    compute_prognosis_outcome,
    format_fixture_status_label,
)


def test_compute_prognosis_outcome_ft_won():
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="won",
            result_total_sot=10.0,
            line_value=7.5,
        )
        == "Vinta"
    )


def test_compute_prognosis_outcome_ft_lost_official_line():
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="lost",
            result_total_sot=8.0,
            line_value=9.5,
        )
        == "Persa"
    )


def test_compute_prognosis_outcome_initial_won_official_lost():
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="won",
            result_total_sot=8.0,
            line_value=7.5,
        )
        == "Vinta"
    )
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="won",
            result_total_sot=8.0,
            line_value=9.5,
        )
        == "Persa"
    )


def test_compute_prognosis_outcome_live_beaten():
    assert (
        compute_prognosis_outcome(
            fixture_status="1H",
            pick_status="live",
            result_total_sot=9.0,
            line_value=7.5,
        )
        == "Vinta live"
    )


def test_compute_prognosis_outcome_live_not_beaten():
    assert (
        compute_prognosis_outcome(
            fixture_status="2H",
            pick_status="live",
            result_total_sot=6.0,
            line_value=7.5,
        )
        == "Live"
    )


def test_compute_prognosis_outcome_pending():
    assert (
        compute_prognosis_outcome(
            fixture_status="NS",
            pick_status="pending",
            result_total_sot=None,
            line_value=7.5,
        )
        == "In attesa"
    )


def test_compute_prognosis_outcome_nd_no_sot_ft():
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="unavailable",
            result_total_sot=None,
            line_value=7.5,
        )
        == "N/D"
    )


def test_format_fixture_status_label():
    assert format_fixture_status_label("NS", None) == "NS"
    assert format_fixture_status_label("1H", 38) == "LIVE 38'"
    assert format_fixture_status_label("HT", None) == "HT"
    assert format_fixture_status_label("FT", 90) == "FT 90'"


def test_compute_dashboard_summary_dual_win_rate():
    rows = [
        {"initial_outcome": "Vinta", "official_outcome": "Vinta", "is_live_fixture": False},
        {"initial_outcome": "Persa", "official_outcome": "Vinta", "is_live_fixture": False},
        {"initial_outcome": "Live", "official_outcome": "Live", "is_live_fixture": True},
    ]
    s = compute_dashboard_summary(rows)
    assert s["total"] == 3
    assert s["live"] == 1
    assert s["initial_won"] == 1
    assert s["initial_lost"] == 1
    assert s["official_won"] == 2
    assert s["official_lost"] == 0
    assert s["initial_win_rate"] == 0.5
    assert s["official_win_rate"] == 1.0


def test_fiorentina_atalanta_scenario():
    """Esempio Fiorentina–Atalanta: 8.18/9.96, Over 7.5/9.5, reali 10 → entrambi Vinta."""
    line_initial = 7.5
    line_official = 9.5
    real = 10.0
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="won",
            result_total_sot=real,
            line_value=line_initial,
        )
        == "Vinta"
    )
    assert (
        compute_prognosis_outcome(
            fixture_status="FT",
            pick_status="won",
            result_total_sot=real,
            line_value=line_official,
        )
        == "Vinta"
    )
    pick = SimpleNamespace(
        initial_predicted_total_sot=8.18,
        initial_predicted_home_sot=4.0,
        initial_predicted_away_sot=4.18,
        initial_suggested_pick="Over 7.5 SOT",
        initial_line_value=7.5,
        predicted_total_sot=9.96,
        predicted_home_sot=5.0,
        predicted_away_sot=4.96,
        suggested_pick="Over 9.5 SOT",
        line_value=9.5,
        initial_odd=None,
        official_odd=None,
    )
    assert pick.initial_predicted_total_sot == 8.18
    assert pick.predicted_total_sot == 9.96
