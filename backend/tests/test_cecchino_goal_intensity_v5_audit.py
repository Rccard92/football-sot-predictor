"""Test audit Intensità Goal v5 — xG opzionale (v1_4)."""

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
    FEATURE_SPECS,
    _snapshot_pre_kickoff_score,
    dedupe_local_fixtures,
    extract_features_for_local_fixture,
    extract_features_from_indexes,
    resolve_xg_feature_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import (
    AuditIndexes,
    XgEvent,
    build_today_indexes,
)
from app.services.cecchino.cecchino_goal_intensity_v5_availability import (
    build_goal_intensity_v5_availability,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_historical_fixture_identity_consistency,
)


KO = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
FLOAT_TOL = 1e-6


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


def _xg_profiles(*, cutoff: str | None = None, excluded: bool = True) -> dict:
    return {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {
            "fixture_date_cutoff": cutoff or KO.isoformat(),
            "current_fixture_excluded": excluded,
        },
    }


def _today(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    defaults = {
        "id": 100,
        "provider_source": "api_football",
        "provider_fixture_id": 8500,
        "local_fixture_id": 500,
        "competition_id": 39,
        "scan_date": date(2026, 3, 14),
        "kickoff": KO,
        "match_display_status": "upcoming",
        "fixture_status": "NS",
        "goals_home": None,
        "goals_away": None,
        "score_fulltime_home": None,
        "score_fulltime_away": None,
        "home_team_name": "Team1",
        "away_team_name": "Team2",
        "cecchino_output_json": {},
        "xg_profiles_json": _xg_profiles(),
        "odds_snapshot_json": None,
        "odds_checked_at": None,
        "country_name": "England",
        "created_at": datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),  # post-match: non deve vincere
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _indexes_from_priors(
    fixtures: list,
    today_rows: list,
    priors=None,
    *,
    xg_for: float = 1.5,
    xg_against: float = 1.0,
    include_xg_stats: bool = True,
) -> AuditIndexes:
    idx = AuditIndexes()
    by_local, by_provider = build_today_indexes(today_rows)
    idx.today_by_local_fixture_id = by_local
    idx.today_by_provider_fixture_id = by_provider

    by_comp_team: dict[tuple[int | None, int], list] = {}
    xg_by: dict[tuple[int | None, int], list[XgEvent]] = {}

    def _add_hist(fx):
        comp = int(fx.competition_id) if fx.competition_id is not None else None
        for tid in (int(fx.home_team_id), int(fx.away_team_id)):
            key = (comp, tid)
            by_comp_team.setdefault(key, []).append(fx)
            if include_xg_stats:
                xg_by.setdefault(key, []).append(
                    XgEvent(
                        kickoff=fx.kickoff_at,
                        fixture_id=int(fx.id),
                        api_fixture_id=int(fx.api_fixture_id) if fx.api_fixture_id is not None else None,
                        xg_for=xg_for,
                        xg_against=xg_against,
                    )
                )

    for local in fixtures:
        if local.home_team_id is None or local.away_team_id is None:
            continue
        base = local.kickoff_at
        if priors is not None:
            home_p, away_p = priors
        else:
            home_p, away_p = _priors(base=base)
        for fx in home_p + away_p:
            _add_hist(fx)
        _add_hist(local)
        idx.team_name_by_id[int(local.home_team_id)] = f"Team{local.home_team_id}"
        idx.team_name_by_id[int(local.away_team_id)] = f"Team{local.away_team_id}"
        if local.competition_id is not None:
            cid = int(local.competition_id)
            idx.country_by_competition_id[cid] = "England" if cid == 39 else "Spain"

    for key in by_comp_team:
        by_comp_team[key].sort(key=lambda f: (f.kickoff_at, int(f.id)))
    for key in xg_by:
        xg_by[key].sort(key=lambda e: (e.kickoff, e.fixture_id))
    idx.fixtures_by_comp_team = by_comp_team
    idx.xg_by_comp_team = xg_by
    return idx


def _audit(
    fixtures: list,
    *,
    today_rows: list | None = None,
    identity=None,
    identity_error=None,
    priors=None,
    xg_profiles_override=None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_xg_stats: bool = True,
):
    from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
        COHORT_BASIS,
        ELIGIBILITY_SOURCE_PERSISTED,
        HISTORICAL_FEATURE_SOURCE,
        RESULT_SOURCE,
        TARGET_SOURCE,
        GoalIntensityTarget,
        GoalIntensityTodayCohort,
    )

    db = MagicMock()
    todays = today_rows if today_rows is not None else []
    if todays and xg_profiles_override is not None:
        for t in todays:
            t.xg_profiles_json = xg_profiles_override

    indexes = _indexes_from_priors(
        fixtures, todays, priors=priors, include_xg_stats=include_xg_stats
    )
    identity_payload = identity if identity is not None else None

    id_patch_kwargs: dict = {}
    if identity_error is not None:
        id_patch_kwargs["side_effect"] = identity_error
    elif identity_payload is not None:
        id_patch_kwargs["return_value"] = identity_payload
    else:
        id_patch_kwargs["side_effect"] = build_historical_fixture_identity_consistency

    load_hist = MagicMock(side_effect=AssertionError("N+1: load_finished_fixtures_for_team nel loop"))
    build_xg = MagicMock(side_effect=AssertionError("N+1: build_current_season_team_xg_profile nel loop"))
    db.get = MagicMock(side_effect=AssertionError("N+1: db.get nel loop"))

    targets = []
    selected_today = []
    for fx in fixtures:
        today = None
        for t in todays:
            if getattr(t, "local_fixture_id", None) is not None and int(t.local_fixture_id) == int(fx.id):
                today = t
                break
            if (
                getattr(t, "provider_fixture_id", None) is not None
                and getattr(fx, "api_fixture_id", None) is not None
                and int(t.provider_fixture_id) == int(fx.api_fixture_id)
            ):
                today = t
                break
        if today is None:
            today = _today(
                id=100 + int(fx.id),
                local_fixture_id=int(fx.id),
                provider_fixture_id=int(fx.api_fixture_id) if fx.api_fixture_id is not None else 8000 + int(fx.id),
                competition_id=int(fx.competition_id) if fx.competition_id is not None else 39,
                kickoff=fx.kickoff_at,
                xg_profiles_json=_xg_profiles() if include_xg_stats else None,
            )
            today.eligibility_status = "eligible"
            today.scan_date = date(2026, 6, 20)
        selected_today.append(today)
        targets.append(
            GoalIntensityTarget(
                today_row=today,
                local_fixture=fx,
                eligibility_status="eligible",
                eligibility_source=ELIGIBILITY_SOURCE_PERSISTED,
                eligibility_reason_codes=[],
                scan_date=getattr(today, "scan_date", None) or date(2026, 6, 20),
                selection={},
            )
        )

    fake_cohort = GoalIntensityTodayCohort(
        date_from=date(2026, 6, 19),
        date_to=date_to or date(2026, 7, 17),
        date_from_clamped=True,
        warnings=[],
        error=None,
        today_rows_raw=list(todays) or selected_today,
        targets=targets,
        eligible_pending=[],
        eligible_unresolved=[],
        eligibility_diagnostics={
            "today_rows_raw": len(todays) or len(selected_today),
            "today_unique_matches": len(targets),
            "today_eligible_matches": len(targets),
            "today_ineligible_matches": 0,
            "today_eligibility_unknown": 0,
            "eligible_finished_matches": len(targets),
            "eligible_pending_matches": 0,
            "eligible_unresolved_matches": 0,
            "ineligible_by_reason": {},
            "ineligible_by_competition": {},
            "ineligible_by_scan_date": {},
            "cohort_basis": COHORT_BASIS,
            "target_source": TARGET_SOURCE,
            "result_source": RESULT_SOURCE,
            "historical_feature_source": HISTORICAL_FEATURE_SOURCE,
        },
        diagnostic_examples=[],
        local_fixtures=[t.local_fixture for t in targets],
        selected_today_rows=selected_today,
    )

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_goal_intensity_today_cohort",
            return_value=fake_cohort,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.preload_audit_indexes",
            return_value=indexes,
        ) as preload_mock,
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_historical_fixture_identity_consistency",
            **id_patch_kwargs,
        ) as id_mock,
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.load_finished_fixtures_for_team",
            load_hist,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.build_current_season_team_xg_profile",
            build_xg,
        ),
    ):
        payload = build_goal_intensity_v5_audit(
            db,
            date_from=date_from or date(2026, 6, 19),
            date_to=date_to or date(2026, 7, 17),
        )
    return payload, db, id_mock, preload_mock, load_hist, build_xg


def _inv(payload: dict, key: str) -> dict:
    return next(f for f in payload["feature_inventory"] if f["feature_key"] == key)


def _approx_eq(a, b, tol=FLOAT_TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def test_version_and_v4_unchanged():
    assert VERSION == "cecchino_goal_intensity_v5_audit_v1_5"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["version"] == VERSION
    assert payload["current_v4_inventory"]["production_unchanged"] is True
    assert payload.get("cohort_basis") == "cecchino_today_eligible_scan_date"


def test_loop_does_not_call_history_xg_or_db_get():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, db, _, preload_mock, load_hist, build_xg = _audit([local], today_rows=[today])
    assert preload_mock.called
    load_hist.assert_not_called()
    build_xg.assert_not_called()
    db.get.assert_not_called()
    assert payload["performance"]["index_sizes"]["history_index_teams"] >= 1


def test_identity_called_with_keyword_arguments():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, id_mock, _, _, _ = _audit([local], today_rows=[today])
    assert id_mock.called
    kwargs = id_mock.call_args.kwargs
    assert "today_row" in kwargs
    assert "local_fixture" in kwargs
    assert payload["anti_leakage"]["static_identity_verified"] == 1
    assert payload["anti_leakage"]["identity_check_errors"] == 0


def test_upcoming_today_vs_local_ft_not_identity_fail():
    local = _fx(500, api=8500, status="FT", gh=2, ga=1)
    today = _today(
        local_fixture_id=500,
        provider_fixture_id=8500,
        match_display_status="upcoming",
        fixture_status="NS",
        goals_home=None,
        goals_away=None,
    )
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["static_identity_verified"] == 1
    assert payload["anti_leakage"]["static_identity_failed"] == 0
    assert payload["dataset_summary"]["leakage_safe_rows"] == 1


def test_today_no_score_vs_local_score_not_blocking():
    local = _fx(500, api=8500, gh=3, ga=2)
    today = _today(local_fixture_id=500, provider_fixture_id=8500, goals_home=None, goals_away=None)
    hist = build_historical_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        local_home_team_name="Team1",
        local_away_team_name="Team2",
    )
    assert hist["status"] == "static_identity_verified"
    assert hist["score_match"] is False
    assert "today_no_score_vs_local_score" in hist["warnings"]


def test_identity_exception_still_fail_closed():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, db, _, _, _, _ = _audit([local], today_rows=[today], identity_error=RuntimeError("boom"))
    assert payload["anti_leakage"]["identity_check_errors"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1
    assert "fixture_identity_check_failed" in payload["anti_leakage"]["warnings"]
    db.commit.assert_not_called()


def test_static_provider_mismatch_excluded():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=9999)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["static_identity_failed"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0


def test_local_fixture_is_historical_base_not_scan_date():
    """La distribuzione temporale usa kickoff locale, non scan_date Today."""
    june = _fx(1, api=1, ko=datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc), competition_id=39)
    july = _fx(2, api=2, ko=datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc), competition_id=40)
    t1 = _today(
        id=101,
        local_fixture_id=1,
        provider_fixture_id=1,
        competition_id=39,
        kickoff=june.kickoff_at,
        scan_date=date(2026, 6, 20),
    )
    t1.eligibility_status = "eligible"
    t2 = _today(
        id=102,
        local_fixture_id=2,
        provider_fixture_id=2,
        competition_id=40,
        kickoff=july.kickoff_at,
        scan_date=date(2026, 6, 20),  # stesso mese scan: se usasse scan_date entrambi in giugno
    )
    t2.eligibility_status = "eligible"
    payload, _, _, _, _, _ = _audit(
        [june, july],
        today_rows=[t1, t2],
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 17),
    )
    temporal = payload["dataset_summary"]["temporal_distribution"]
    assert temporal["2026-06"]["count"] == 1
    assert temporal["2026-07"]["count"] == 1
    assert payload["dataset_summary"]["cohort_basis"] == "cecchino_today_eligible_scan_date"
    assert payload["dataset_summary"]["competitions"] == 2


def test_today_snapshot_optional_goal_features_without_today():
    """Senza Today eleggibile la riga non entra nella coorte model-ready."""
    local = _fx(500, api=8500)
    from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
        COHORT_BASIS,
        GoalIntensityTodayCohort,
        TARGET_SOURCE,
        RESULT_SOURCE,
        HISTORICAL_FEATURE_SOURCE,
    )

    empty = GoalIntensityTodayCohort(
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 17),
        date_from_clamped=False,
        warnings=[],
        error=None,
        today_rows_raw=[],
        targets=[],
        eligible_pending=[],
        eligible_unresolved=[],
        eligibility_diagnostics={
            "today_rows_raw": 0,
            "today_unique_matches": 0,
            "today_eligible_matches": 0,
            "today_ineligible_matches": 0,
            "today_eligibility_unknown": 0,
            "eligible_finished_matches": 0,
            "eligible_pending_matches": 0,
            "eligible_unresolved_matches": 0,
            "ineligible_by_reason": {},
            "ineligible_by_competition": {},
            "ineligible_by_scan_date": {},
            "cohort_basis": COHORT_BASIS,
            "target_source": TARGET_SOURCE,
            "result_source": RESULT_SOURCE,
            "historical_feature_source": HISTORICAL_FEATURE_SOURCE,
        },
        diagnostic_examples=[],
        local_fixtures=[],
        selected_today_rows=[],
    )
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_goal_intensity_today_cohort",
        return_value=empty,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_audit.preload_audit_indexes",
        return_value=_indexes_from_priors([local], []),
    ):
        payload = build_goal_intensity_v5_audit(
            db, date_from=date(2026, 6, 19), date_to=date(2026, 7, 17)
        )
    assert payload["dataset_summary"]["row_feature_safe"] == 0
    assert payload["eligibility_diagnostics"]["eligible_finished_matches"] == 0


def test_missing_teams_excluded():
    bad = _fx(500)
    bad.home_team_id = None
    payload, _, _, _, _, _ = _audit([bad], today_rows=[])
    assert payload["anti_leakage"]["local_fixture_missing_teams"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0


def test_competition_and_country_counts():
    a = _fx(1, api=1, competition_id=39)
    b = _fx(2, api=2, competition_id=140)
    payload, _, _, _, _, _ = _audit([a, b], today_rows=[])
    assert payload["dataset_summary"]["competitions"] == 2
    assert payload["dataset_summary"]["countries"] >= 1


def test_sample_size_nonzero_and_rolling():
    local = _fx(500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
    assert payload["dataset_summary"]["sample_size_mean"] > 0
    assert _inv(payload, "home_goals_scored_rolling_5")["mean"] is not None


def test_stability_dispersion_computed():
    local = _fx(500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
    for key in ("goals_scored_std_last_10", "goals_scored_mad_last_10", "goals_scored_cv_last_10"):
        assert _inv(payload, key)["rows_available"] == 1


def test_target_and_future_excluded_from_features():
    local = _fx(500, api=8500)
    home, away = _priors()
    tainted = _prior(500, home=1, away=2, gh=9, ga=9, days_before=0)
    tainted.id = 500
    tainted.api_fixture_id = 8500
    future = _prior(99, home=1, away=3, gh=5, ga=5, days_before=-2)
    payload, _, _, _, _, _ = _audit([local], today_rows=[], priors=(home + [tainted, future], away))
    assert payload["anti_leakage"]["rows_passed"] == 1
    mean_home = _inv(payload, "home_goals_scored_avg")["mean"]
    assert mean_home is not None
    assert mean_home < 5.0


def test_xg_from_today_snapshot():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["xg_from_today_snapshot"] == 1
    assert payload["anti_leakage"]["xg_anti_leakage_verified"] == 1
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 1


def test_xg_without_current_fixture_excluded_falls_back_to_stats():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    bad = _xg_profiles(excluded=False)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today], xg_profiles_override=bad)
    assert payload["anti_leakage"]["xg_from_today_snapshot"] == 0
    assert payload["anti_leakage"]["xg_from_fixture_team_stats"] == 1
    assert payload["anti_leakage"]["cutoff_mismatch"] == 0


def test_xg_from_fixture_team_stats_when_no_snapshot():
    local = _fx(500, api=8500)
    today = _today(
        local_fixture_id=500,
        provider_fixture_id=8500,
        xg_profiles_json=None,
        scan_date=date(2026, 6, 20),
    )
    today.eligibility_status = "eligible"
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["xg_from_fixture_team_stats"] == 1


def test_xg_cutoff_mismatch_excluded():
    """Cutoff unsafe + niente stats → excluded_unsafe, riga resta feature-safe, xG null."""
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    bad = _xg_profiles(cutoff=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc).isoformat())
    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        xg_profiles_override=bad,
        include_xg_stats=False,
    )
    assert payload["anti_leakage"]["cutoff_mismatch"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 0
    assert payload["dataset_summary"]["leakage_safe_rows"] == 1
    assert payload["dataset_summary"]["xg_cohorts"]["xg_excluded_unsafe"] == 1
    row = payload["fixture_audit_rows"][0]
    assert row["xg_status"] == "excluded_unsafe"
    assert row["row_feature_safe"] is True
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 0
    assert _inv(payload, "home_goals_scored_rolling_5")["rows_available"] == 1


def test_snapshot_score_ignores_kickoff_and_updated_at():
    row = _today(
        kickoff=KO,
        created_at=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 16, 20, 0, tzinfo=timezone.utc),
        scan_date=date(2026, 3, 1),
    )
    score = _snapshot_pre_kickoff_score(row, KO)
    assert score == datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)


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
    payload, db, _, _, _, _ = _audit([local], today_rows=[])
    assert payload["api_availability"]["requires_new_api_calls"]["used_in_audit"] is False
    db.commit.assert_not_called()
    db.add.assert_not_called()
    jsonable_encoder(payload)
    keys = {e["feature_key"] for e in payload["excluded_advanced_features"]}
    assert keys == {e["feature_key"] for e in EXCLUDED_ADVANCED}


def test_identity_mismatch_excluded():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        identity={"status": "static_identity_failed", "warnings": ["provider_fixture_id_mismatch"]},
    )
    assert payload["anti_leakage"]["static_identity_failed"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0


def test_performance_payload_has_phases():
    local = _fx(500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
    perf = payload["performance"]
    assert "elapsed_ms" in perf
    assert "calculation_ms" in perf
    assert "db_query_phases" in perf
    assert "index_sizes" in perf


def test_feature_equivalence_indexes_vs_v1_1_path():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    home, away = _priors()
    indexes = _indexes_from_priors([local], [today], priors=(home, away))

    db = MagicMock()

    def _load(_db, tgt, team_id):
        if int(team_id) == int(tgt.home_team_id):
            return list(home)
        return list(away)

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.load_finished_fixtures_for_team",
            side_effect=_load,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.build_current_season_team_xg_profile",
            return_value={"xg_for_avg": 1.5, "xg_against_avg": 1.0},
        ),
    ):
        feat_v11, meta_v11 = extract_features_for_local_fixture(db, local, today)

    feat_idx, meta_idx = extract_features_from_indexes(local, today, indexes)

    for spec in FEATURE_SPECS:
        key = spec["feature_key"]
        assert _approx_eq(feat_v11.get(key), feat_idx.get(key)), f"mismatch {key}"
    assert meta_v11["xg_source"] == meta_idx["xg_source"] == "today_snapshot"
    assert meta_v11["sample_size"] == meta_idx["sample_size"]


def test_feature_safe_rate_low_is_unusable():
    """20 feature-safe su 143 → unusable (~14%)."""
    fixtures = [_fx(i, api=i, ko=KO + timedelta(hours=i % 24)) for i in range(1, 144)]
    # solo 20 con today identity ok; gli altri senza today passano comunque...
    # per abbassare rate: forza identity fail su 123
    todays = []
    for i in range(1, 21):
        todays.append(
            _today(
                id=1000 + i,
                local_fixture_id=i,
                provider_fixture_id=i,
                competition_id=39,
                home_team_name="Team1",
                away_team_name="Team2",
            )
        )
    # 123 con provider mismatch → failed
    for i in range(21, 144):
        todays.append(
            _today(
                id=2000 + i,
                local_fixture_id=i,
                provider_fixture_id=999000 + i,  # mismatch
                competition_id=39,
            )
        )
    payload, _, _, _, _, _ = _audit(fixtures, today_rows=todays)
    rate = payload["dataset_summary"]["feature_safe_rate_pct"]
    assert rate < 20.0
    assert payload["dataset_summary"]["audit_quality"] == "unusable"
    assert payload["dataset_summary"]["audit_usable"] is False


def test_jul_01_03_upcoming_majority_feature_safe():
    """Periodo 2026-07-01→03: Today upcoming vs Local FT non deve massacrare feature-safe."""
    fixtures = []
    todays = []
    for i in range(1, 31):
        ko = datetime(2026, 7, 1 + (i % 3), 15, 0, tzinfo=timezone.utc)
        local = _fx(i, api=8000 + i, ko=ko, competition_id=39, status="FT")
        fixtures.append(local)
        todays.append(
            _today(
                id=3000 + i,
                local_fixture_id=i,
                provider_fixture_id=8000 + i,
                competition_id=39,
                kickoff=ko,
                match_display_status="upcoming",
                fixture_status="NS",
                goals_home=None,
                goals_away=None,
                created_at=ko - timedelta(days=1),
                scan_date=ko.date() - timedelta(days=1),
                xg_profiles_json=_xg_profiles(cutoff=ko.isoformat()),
                home_team_name="Team1",
                away_team_name="Team2",
            )
        )
    payload, _, _, _, _, _ = _audit(
        fixtures,
        today_rows=todays,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 3),
    )
    rate = payload["dataset_summary"]["feature_safe_rate_pct"]
    assert rate > 70.0
    assert payload["anti_leakage"]["static_identity_verified"] >= 25
    assert payload["anti_leakage"]["static_identity_failed"] == 0
    assert payload["dataset_summary"]["targets_all_finished"] == 30
    assert payload["dataset_summary"]["targets_feature_safe"] == payload["anti_leakage"]["row_feature_safe"]
    assert "xg_source_all_checked" in payload["anti_leakage"]
    assert "xg_source_feature_safe" in payload["anti_leakage"]


def test_availability_payload_shape():
    db = MagicMock()
    db.scalar.side_effect = [
        42,
        date(2026, 6, 19),
        date(2026, 7, 10),
    ]
    db.scalars.return_value.all.side_effect = [
        [39, 140],
        [MagicMock(id=39, country="England"), MagicMock(id=140, country="Spain")],
    ]
    payload = build_goal_intensity_v5_availability(db)
    assert payload["status"] == "ok"
    assert payload["cohort_basis"] == "cecchino_today_eligible_scan_date"
    assert payload["earliest_kickoff_date"] == "2026-06-19"
    assert payload["latest_kickoff_date"] == "2026-07-10"
    assert payload["min_scan_date"] == "2026-06-19"


def test_xg_status_available_complete():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    row = payload["fixture_audit_rows"][0]
    assert row["xg_status"] == "available"
    assert row["xg_source"] == "today_snapshot"
    assert set(row["xg_available_fields"]) == {
        "home_xg_for_avg",
        "away_xg_for_avg",
        "home_xg_against_avg",
        "away_xg_against_avg",
    }
    assert payload["dataset_summary"]["xg_cohorts"]["xg_available"] == 1
    assert payload["dataset_summary"]["xg_value_research_readiness"]["paired_fixture_count"] == 1
    assert payload["dataset_summary"]["xg_value_research_readiness"]["paired_comparison_possible"] is True
    assert payload["dataset_summary"]["xg_value_research_readiness"]["minimum_recommended_sample_reached"] is False


def test_xg_status_partial_no_fake_pairs():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    partial = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
        },
    }
    indexes = _indexes_from_priors([local], [today], include_xg_stats=False)
    today.xg_profiles_json = partial
    bundle = resolve_xg_feature_bundle(target=local, today_row=today, indexes=indexes)
    assert bundle["xg_status"] == "partial"
    assert bundle["home_xg_for_avg"] == 1.4
    assert bundle["away_xg_for_avg"] is None
    assert bundle["pair_xg_for_avg"] is None
    assert bundle["pair_xg_against_avg"] is None

    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        xg_profiles_override=partial,
        include_xg_stats=False,
    )
    assert payload["fixture_audit_rows"][0]["xg_status"] == "partial"
    assert payload["dataset_summary"]["leakage_safe_rows"] == 1
    assert _inv(payload, "pair_xg_for_avg")["rows_available"] == 0
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 1


def test_xg_status_missing_keeps_row_feature_safe_and_null_not_zero():
    local = _fx(500, api=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[], include_xg_stats=False)
    row = payload["fixture_audit_rows"][0]
    assert row["xg_status"] == "missing"
    assert row["row_feature_safe"] is True
    assert payload["dataset_summary"]["leakage_safe_rows"] == 1
    assert payload["dataset_summary"]["xg_cohorts"]["xg_missing"] == 1
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 0
    assert _inv(payload, "home_xg_for_avg")["mean"] is None
    assert _inv(payload, "home_goals_scored_avg")["rows_available"] == 1
    assert payload["dataset_summary"]["audit_usable"] is True or payload["dataset_summary"]["audit_quality"] != "unusable"


def test_xg_provider_target_not_excluded_unsafe():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    bad = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
            "excluded_provider_fixture_ids": [9999],
        },
    }
    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        xg_profiles_override=bad,
        include_xg_stats=False,
    )
    row = payload["fixture_audit_rows"][0]
    assert row["xg_status"] == "excluded_unsafe"
    assert "provider_fixture_target_not_excluded" in row["xg_exclusion_reasons"]
    assert row["row_feature_safe"] is True
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 0


def test_xg_future_fixture_included_unsafe():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    bad = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
            "future_fixture_included": True,
        },
    }
    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        xg_profiles_override=bad,
        include_xg_stats=False,
    )
    row = payload["fixture_audit_rows"][0]
    assert row["xg_status"] == "excluded_unsafe"
    assert "future_fixture_included_in_xg" in row["xg_exclusion_reasons"]
    assert row["row_feature_safe"] is True


def test_xg_source_mixed_snapshot_plus_stats():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    partial_snap = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
        },
    }
    payload, _, _, _, _, _ = _audit(
        [local],
        today_rows=[today],
        xg_profiles_override=partial_snap,
        include_xg_stats=True,
    )
    row = payload["fixture_audit_rows"][0]
    assert row["xg_source"] == "mixed"
    assert row["xg_status"] == "available"
    assert payload["anti_leakage"]["xg_sources_feature_safe"]["mixed"] == 1


def test_xg_sources_counters_all_checked_and_feature_safe():
    a = _fx(1, api=1)
    b = _fx(2, api=2)
    today_ok = _today(id=10, local_fixture_id=1, provider_fixture_id=1)
    today_bad = _today(
        id=11,
        local_fixture_id=2,
        provider_fixture_id=999,
        home_team_name="Team1",
        away_team_name="Team2",
    )
    payload, _, _, _, _, _ = _audit([a, b], today_rows=[today_ok, today_bad])
    anti = payload["anti_leakage"]
    assert "xg_sources_all_checked" in anti
    assert "xg_sources_feature_safe" in anti
    assert sum(anti["xg_sources_all_checked"].values()) == 2
    assert sum(anti["xg_sources_feature_safe"].values()) == anti["row_feature_safe"]


def test_fixture_audit_rows_light_payload_no_raw_history():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    rows = payload["fixture_audit_rows"]
    assert len(rows) == 1
    expected = {
        "local_fixture_id",
        "provider_fixture_id",
        "competition_id",
        "country",
        "kickoff",
        "home_team",
        "away_team",
        "row_feature_safe",
        "static_identity_status",
        "snapshot_time_status",
        "xg_status",
        "xg_source",
        "xg_available_fields",
        "xg_missing_fields",
        "xg_exclusion_reasons",
        "sample_size",
        "target_total_goals_ft",
    }
    assert set(rows[0].keys()) == expected
    assert "history" not in rows[0]
    assert "features" not in rows[0]
    assert "priors" not in rows[0]


def test_core_and_enriched_feature_lists_and_readiness():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    core = payload["dataset_summary"]["core_features_without_xg"]
    enriched = payload["dataset_summary"]["enriched_features_with_xg"]
    assert "home_goals_scored_avg" in core
    assert "home_xg_for_avg" not in core
    assert "home_xg_for_avg" in enriched
    assert all(k in enriched for k in core)


def test_xg_low_coverage_does_not_force_unusable():
    """xG missing non degrada da solo a unusable se core feature-safe ok."""
    fixtures = [_fx(i, api=i, competition_id=39) for i in range(1, 6)]
    payload, _, _, _, _, _ = _audit(fixtures, today_rows=[], include_xg_stats=False)
    assert payload["dataset_summary"]["xg_cohorts"]["xg_missing"] == 5
    assert payload["dataset_summary"]["feature_safe_rate_pct"] >= 70
    assert payload["dataset_summary"]["audit_quality"] != "unusable"


def test_performance_payload_compatible_v1_2():
    local = _fx(500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
    perf = payload["performance"]
    assert "elapsed_ms" in perf
    assert "calculation_ms" in perf
    assert "db_query_phases" in perf
    assert "index_sizes" in perf
    assert "cohort_ms" in perf["db_query_phases"]
    assert "preload_ms" in perf["db_query_phases"]
