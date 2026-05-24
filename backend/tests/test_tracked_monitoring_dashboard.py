"""Test dashboard monitoraggio: doppio esito e risoluzione snapshot."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.tracked_monitoring_dashboard_service import (
    _official_with_stale_guard,
    compute_dashboard_summary,
    compute_prognosis_outcome,
    format_fixture_status_label,
)
from app.services.tracked_monitoring_snapshot_resolver import (
    resolve_initial_snapshot,
    resolve_official_snapshot,
)
from app.models.tracked_betting_pick import PICK_TYPE_CAUTIOUS


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


def test_bologna_inter_initial_vs_official_not_swapped():
    """initial_* errato ignorato; first before=7.71; official da after se pick.predicted stale."""
    pick = SimpleNamespace(
        initial_predicted_total_sot=9.5,
        initial_predicted_home_sot=None,
        initial_predicted_away_sot=None,
        initial_suggested_pick="Over 9.5 SOT",
        initial_line_value=9.5,
        predicted_total_sot=7.71,
        predicted_home_sot=3.5,
        predicted_away_sot=4.21,
        suggested_pick="Over 7.5 SOT",
        line_value=7.5,
        lineup_confirmed=True,
        pick_type=PICK_TYPE_CAUTIOUS,
        raw_prediction_payload=None,
    )
    first_impact = {
        "before_total_sot": 7.71,
        "before_home_sot": 3.5,
        "before_away_sot": 4.21,
        "after_total_sot": 9.5,
        "after_home_sot": 4.8,
        "after_away_sot": 4.7,
        "has_comparison": True,
    }
    latest_impact = first_impact
    fx = SimpleNamespace(id=1, home_team_id=1, away_team_id=2)
    initial = resolve_initial_snapshot(
        pick,  # type: ignore[arg-type]
        first_impact=first_impact,
        latest_impact=latest_impact,
        db=None,  # type: ignore[arg-type]
        fx=fx,  # type: ignore[arg-type]
        official_total_hint=9.5,
    )
    official = _official_with_stale_guard(pick, latest_impact, None, fx)  # type: ignore[arg-type]
    assert initial.total == 7.71
    assert official.total == 9.5


def test_initial_corrupt_without_impact_shows_unavailable():
    pick = SimpleNamespace(
        initial_predicted_total_sot=9.5,
        initial_predicted_home_sot=None,
        initial_predicted_away_sot=None,
        initial_suggested_pick="Over 9.5 SOT",
        initial_line_value=9.5,
        predicted_total_sot=9.5,
        predicted_home_sot=4.8,
        predicted_away_sot=4.7,
        suggested_pick="Over 9.5 SOT",
        line_value=9.5,
        lineup_confirmed=True,
        pick_type=PICK_TYPE_CAUTIOUS,
        raw_prediction_payload=None,
    )
    fx = SimpleNamespace(id=1, home_team_id=1, away_team_id=2)
    initial = resolve_initial_snapshot(
        pick,  # type: ignore[arg-type]
        first_impact=None,
        latest_impact=None,
        db=None,  # type: ignore[arg-type]
        fx=fx,  # type: ignore[arg-type]
        official_total_hint=9.5,
    )
    assert initial.total is None
    assert initial.source == "unavailable"


def test_initial_from_delta_reconstruction_only():
    pick = SimpleNamespace(
        initial_predicted_total_sot=9.5,
        initial_predicted_home_sot=None,
        initial_predicted_away_sot=None,
        initial_suggested_pick=None,
        initial_line_value=None,
        predicted_total_sot=9.5,
        predicted_home_sot=None,
        predicted_away_sot=None,
        suggested_pick=None,
        line_value=None,
        lineup_confirmed=True,
        pick_type=PICK_TYPE_CAUTIOUS,
        raw_prediction_payload=None,
    )
    latest = {
        "after_total_sot": 9.5,
        "delta_total_sot": 1.79,
        "after_home_sot": 4.8,
        "after_away_sot": 4.7,
        "delta_home_sot": 1.3,
        "delta_away_sot": 0.49,
        "has_comparison": True,
    }
    fx = SimpleNamespace(id=1, home_team_id=1, away_team_id=2)
    initial = resolve_initial_snapshot(
        pick,  # type: ignore[arg-type]
        first_impact=None,
        latest_impact=latest,
        db=None,  # type: ignore[arg-type]
        fx=fx,  # type: ignore[arg-type]
        official_total_hint=9.5,
    )
    assert initial.total == 7.71
    assert initial.source == "latest_delta_reconstruction"


def test_bologna_inter_dual_outcomes_ft():
    """SOT 8: iniziale Over 7.5 Vinta; official Over 8.5 Persa."""
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
            line_value=8.5,
        )
        == "Persa"
    )
