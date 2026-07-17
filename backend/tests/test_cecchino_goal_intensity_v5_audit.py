"""Test audit Intensità Goal v5 — Fase 1A.2."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit import (
    VERSION,
    build_goal_intensity_v5_audit,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    EXCLUDED_ADVANCED,
    dedupe_local_fixtures,
)


KO = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)


def _fx(
    fid: int,
    *,
    api: int | None = None,
    home: int = 1,
    away: int = 2,
    gh: int = 2,
    ga: int = 1,
    ko: datetime | None = None,
    competition_id: int = 39,
    status: str = "FT",
) -> MagicMock:
    fx = MagicMock()
    fx.id = fid
    fx.api_fixture_id = api if api is not None else 8000 + fid
    fx.home_team_id = home
    fx.away_team_id = away
    fx.goals_home = gh
    fx.goals_away = ga
    fx.kickoff_at = ko or KO
    fx.status = status
    fx.competition_id = competition_id
    return fx


def _prior(fid: int, *, home: int, away: int, gh: int, ga: int, days_before: int = 7, base: datetime | None = None) -> MagicMock:
    base_ko = base or KO
    return _fx(
        fid,
        home=home,
        away=away,
        gh=gh,
        ga=ga,
        ko=base_ko - timedelta(days=days_before),
        api=9000 + fid,
    )


def _priors(base: datetime | None = None):
    b = base or KO
    home = [
        _prior(10, home=1, away=9, gh=2, ga=1, days_before=14, base=b),
        _prior(11, home=9, away=1, gh=0, ga=1, days_before=10, base=b),
        _prior(12, home=1, away=8, gh=3, ga=2, days_before=7, base=b),
        _prior(13, home=1, away=7, gh=1, ga=0, days_before=5, base=b),
        _prior(14, home=6, away=1, gh=1, ga=2, days_before=3, base=b),
    ]
    away = [
        _prior(20, home=2, away=5, gh=1, ga=1, days_before=14, base=b),
        _prior(21, home=4, away=2, gh=2, ga=2, days_before=10, base=b),
        _prior(22, home=2, away=3, gh=0, ga=0, days_before=7, base=b),
        _prior(23, home=2, away=9, gh=2, ga=1, days_before=5, base=b),
        _prior(24, home=8, away=2, gh=1, ga=3, days_before=3, base=b),
    ]
    return home, away


def _today(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    defaults = {
        "id": 100,
        "provider_source": "api_football",
        "provider_fixture_id": 8500,
        "local_fixture_id": 500,
        "scan_date": date(2026, 3, 14),
        "kickoff": KO,
        "cecchino_output_json": {},
        "xg_profiles_json": {
            "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
            "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
            "anti_leakage": {"fixture_date_cutoff": KO.isoformat()},
        },
        "country_name": "England",
        "created_at": datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _competition(cid: int = 39, country: str = "England") -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.country = country
    return c


def _team(tid: int, name: str) -> MagicMock:
    t = MagicMock()
    t.id = tid
    t.name = name
    return t


def _audit(
    fixtures: list,
    *,
    today_rows: list | None = None,
    identity=None,
    identity_error=None,
    priors=None,
    xg_profiles_override=None,
):
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "Competition" in name:
            return _competition(int(pk), country="England" if int(pk) == 39 else "Spain")
        if "Team" in name:
            return _team(int(pk), f"Team{pk}")
        return None

    db.get.side_effect = _get

    def _load(_db, tgt, team_id):
        if priors is not None:
            home_p, away_p = priors
        else:
            home_p, away_p = _priors(base=tgt.kickoff_at)
        if int(team_id) == int(tgt.home_team_id):
            return list(home_p)
        return list(away_p)

    identity_payload = identity if identity is not None else {"status": "consistent", "warnings": []}

    todays = today_rows if today_rows is not None else []
    if todays and xg_profiles_override is not None:
        for t in todays:
            t.xg_profiles_json = xg_profiles_override

    id_patch_kwargs: dict = {}
    if identity_error is not None:
        id_patch_kwargs["side_effect"] = identity_error
    else:
        id_patch_kwargs["return_value"] = identity_payload

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.finished_local_fixtures_in_kickoff_range",
            return_value=list(fixtures),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.load_today_snapshots_for_fixtures",
            return_value=list(todays),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.load_finished_fixtures_for_team",
            side_effect=_load,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_fixture_identity_consistency",
            **id_patch_kwargs,
        ) as id_mock,
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.build_current_season_team_xg_profile",
            return_value={"xg_for_avg": 1.5, "xg_against_avg": 1.0},
        ),
    ):
        payload = build_goal_intensity_v5_audit(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
        )
    return payload, db, id_mock


def _inv(payload: dict, key: str) -> dict:
    return next(f for f in payload["feature_inventory"] if f["feature_key"] == key)


def test_version_and_v4_unchanged():
    assert VERSION == "cecchino_goal_intensity_v5_audit_v1_1"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _ = _audit([local], today_rows=[today])
    assert payload["version"] == VERSION
    assert payload["current_v4_inventory"]["production_unchanged"] is True


def test_identity_called_with_keyword_arguments():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, id_mock = _audit([local], today_rows=[today])
    assert id_mock.called
    kwargs = id_mock.call_args.kwargs
    assert "today_row" in kwargs
    assert "local_fixture" in kwargs
    assert kwargs["today_row"] is today
    assert kwargs["local_fixture"] is local
    assert payload["anti_leakage"]["identity_check_errors"] == 0


def test_identity_exception_still_fail_closed():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, db, _ = _audit([local], today_rows=[today], identity_error=RuntimeError("boom"))
    assert payload["anti_leakage"]["identity_check_errors"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1
    assert "fixture_identity_check_failed" in payload["anti_leakage"]["warnings"]
    assert payload["exclusion_reasons"]["identity_check_error"] == 1
    db.commit.assert_not_called()


def test_local_fixture_is_historical_base_not_scan_date():
    jan = _fx(1, api=1, ko=datetime(2026, 1, 20, 18, 0, tzinfo=timezone.utc), competition_id=39)
    feb = _fx(2, api=2, ko=datetime(2026, 2, 10, 18, 0, tzinfo=timezone.utc), competition_id=40)
    payload, _, _ = _audit([jan, feb], today_rows=[])
    temporal = payload["dataset_summary"]["temporal_distribution"]
    assert temporal["2026-01"]["count"] == 1
    assert temporal["2026-02"]["count"] == 1
    assert payload["dataset_summary"]["cohort_basis"] == "fixture_kickoff_at"
    assert payload["dataset_summary"]["competitions"] == 2


def test_january_february_present_when_fixtures_exist():
    fixtures = [
        _fx(i, api=i, ko=datetime(2026, m, 10, 18, 0, tzinfo=timezone.utc), competition_id=39)
        for i, m in enumerate((1, 2), start=1)
    ]
    payload, _, _ = _audit(fixtures, today_rows=[])
    assert payload["dataset_summary"]["temporal_distribution"]["2026-01"]["count"] == 1
    assert payload["dataset_summary"]["temporal_distribution"]["2026-02"]["count"] == 1


def test_empty_months_marked():
    only_jul = [_fx(1, api=1, ko=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc))]
    payload, _, _ = _audit(only_jul, today_rows=[])
    assert payload["dataset_summary"]["temporal_distribution"]["2026-01"]["note"] == "no_local_fixtures_in_month"


def test_today_snapshot_optional_goal_features_without_today():
    local = _fx(500, api=8500)
    payload, _, id_mock = _audit([local], today_rows=[])
    assert not id_mock.called
    assert payload["dataset_summary"]["today_snapshots_missing"] == 1
    assert payload["anti_leakage"]["identity_not_available"] == 1
    assert _inv(payload, "home_goals_scored_rolling_5")["rows_available"] == 1
    assert _inv(payload, "over_2_5_frequency_last_10")["rows_available"] == 1
    assert _inv(payload, "gg_frequency_last_10")["rows_available"] == 1
    assert _inv(payload, "goals_scored_std_last_10")["rows_available"] == 1


def test_missing_teams_excluded():
    bad = _fx(500)
    bad.home_team_id = None
    payload, _, _ = _audit([bad], today_rows=[])
    assert payload["anti_leakage"]["local_fixture_missing_teams"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0
    assert payload["exclusion_reasons"]["missing_teams"] == 1


def test_competition_and_country_counts():
    a = _fx(1, api=1, competition_id=39)
    b = _fx(2, api=2, competition_id=140)
    payload, _, _ = _audit([a, b], today_rows=[])
    assert payload["dataset_summary"]["competitions"] == 2
    assert payload["dataset_summary"]["countries"] >= 1


def test_sample_size_nonzero_and_rolling():
    local = _fx(500)
    payload, _, _ = _audit([local], today_rows=[])
    assert payload["dataset_summary"]["sample_size_mean"] > 0
    assert _inv(payload, "home_goals_scored_rolling_5")["mean"] is not None
    assert _inv(payload, "away_goals_scored_rolling_10")["mean"] is not None
    assert any(p["fixtures_with_any_feature"] > 0 for p in payload["pillar_coverage"].values())


def test_stability_dispersion_computed():
    local = _fx(500)
    payload, _, _ = _audit([local], today_rows=[])
    for key in ("goals_scored_std_last_10", "goals_scored_mad_last_10", "goals_scored_cv_last_10"):
        assert _inv(payload, key)["rows_available"] == 1


def test_target_and_provider_and_future_excluded():
    local = _fx(500, api=8500)
    home, away = _priors()
    tainted = _prior(500, home=1, away=2, gh=9, ga=9, days_before=0)
    tainted.id = 500
    tainted.api_fixture_id = 8500
    future = _prior(99, home=1, away=3, gh=5, ga=5, days_before=-2)
    payload, _, _ = _audit([local], today_rows=[], priors=(home + [tainted, future], away))
    assert payload["anti_leakage"]["current_fixture_included"] >= 1 or payload["anti_leakage"]["future_fixture_included"] >= 1
    assert payload["anti_leakage"]["rows_failed"] == 1


def test_xg_from_today_snapshot():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["xg_from_today_snapshot"] == 1
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 1


def test_xg_from_fixture_team_stats_when_no_snapshot():
    local = _fx(500, api=8500)
    payload, _, _ = _audit([local], today_rows=[])
    assert payload["anti_leakage"]["xg_from_fixture_team_stats"] == 1
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 1


def test_xg_cutoff_mismatch_excluded():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    bad = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {"fixture_date_cutoff": datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc).isoformat()},
    }
    payload, _, _ = _audit([local], today_rows=[today], xg_profiles_override=bad)
    assert payload["anti_leakage"]["cutoff_mismatch"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1


def test_dedupe_local_fixtures():
    a = _fx(1, api=100)
    b = _fx(2, api=100)
    c = _fx(3, api=None)
    c.api_fixture_id = None
    d = _fx(3, api=None)
    d.api_fixture_id = None
    out, removed = dedupe_local_fixtures([a, b, c, d])
    assert len(out) == 2
    assert removed == 2


def test_no_external_api_no_db_writes_json():
    local = _fx(500)
    payload, db, _ = _audit([local], today_rows=[])
    assert payload["api_availability"]["requires_new_api_calls"]["used_in_audit"] is False
    db.commit.assert_not_called()
    db.add.assert_not_called()
    jsonable_encoder(payload)
    keys = {e["feature_key"] for e in payload["excluded_advanced_features"]}
    assert keys == {e["feature_key"] for e in EXCLUDED_ADVANCED}


def test_identity_mismatch_excluded():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _ = _audit(
        [local],
        today_rows=[today],
        identity={"status": "inconsistent", "warnings": ["fixture_kickoff_mismatch"]},
    )
    assert payload["anti_leakage"]["fixture_identity_mismatch"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0
