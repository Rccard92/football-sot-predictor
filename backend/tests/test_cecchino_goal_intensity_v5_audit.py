"""Test audit Intensità Goal v5 — Fase 1A.3 (preload / DB-free loop)."""

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
    dedupe_local_fixtures,
    extract_features_for_local_fixture,
    extract_features_from_indexes,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import (
    AuditIndexes,
    XgEvent,
    build_today_indexes,
)
from app.services.cecchino.cecchino_goal_intensity_v5_availability import (
    build_goal_intensity_v5_availability,
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


def _indexes_from_priors(
    fixtures: list,
    today_rows: list,
    priors=None,
    *,
    xg_for: float = 1.5,
    xg_against: float = 1.0,
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
        # include target itself (as real preload would)
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
):
    db = MagicMock()
    todays = today_rows if today_rows is not None else []
    if todays and xg_profiles_override is not None:
        for t in todays:
            t.xg_profiles_json = xg_profiles_override

    indexes = _indexes_from_priors(fixtures, todays, priors=priors)
    identity_payload = identity if identity is not None else {"status": "consistent", "warnings": []}

    id_patch_kwargs: dict = {}
    if identity_error is not None:
        id_patch_kwargs["side_effect"] = identity_error
    else:
        id_patch_kwargs["return_value"] = identity_payload

    load_hist = MagicMock(side_effect=AssertionError("N+1: load_finished_fixtures_for_team nel loop"))
    build_xg = MagicMock(side_effect=AssertionError("N+1: build_current_season_team_xg_profile nel loop"))
    db_get = MagicMock(side_effect=AssertionError("N+1: db.get nel loop"))
    db.get = db_get

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
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.preload_audit_indexes",
            return_value=indexes,
        ) as preload_mock,
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_fixture_identity_consistency",
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
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
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
    assert VERSION == "cecchino_goal_intensity_v5_audit_v1_2"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["version"] == VERSION
    assert payload["current_v4_inventory"]["production_unchanged"] is True


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
    assert kwargs["today_row"] is today
    assert kwargs["local_fixture"] is local
    assert payload["anti_leakage"]["identity_check_errors"] == 0


def test_identity_exception_still_fail_closed():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, db, _, _, _, _ = _audit([local], today_rows=[today], identity_error=RuntimeError("boom"))
    assert payload["anti_leakage"]["identity_check_errors"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1
    assert "fixture_identity_check_failed" in payload["anti_leakage"]["warnings"]
    assert payload["exclusion_reasons"]["identity_check_error"] == 1
    db.commit.assert_not_called()


def test_local_fixture_is_historical_base_not_scan_date():
    jan = _fx(1, api=1, ko=datetime(2026, 1, 20, 18, 0, tzinfo=timezone.utc), competition_id=39)
    feb = _fx(2, api=2, ko=datetime(2026, 2, 10, 18, 0, tzinfo=timezone.utc), competition_id=40)
    payload, _, _, _, _, _ = _audit([jan, feb], today_rows=[])
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
    payload, _, _, _, _, _ = _audit(fixtures, today_rows=[])
    assert payload["dataset_summary"]["temporal_distribution"]["2026-01"]["count"] == 1
    assert payload["dataset_summary"]["temporal_distribution"]["2026-02"]["count"] == 1


def test_empty_months_marked():
    only_jul = [_fx(1, api=1, ko=datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc))]
    payload, _, _, _, _, _ = _audit(only_jul, today_rows=[])
    assert payload["dataset_summary"]["temporal_distribution"]["2026-01"]["note"] == "no_local_fixtures_in_month"


def test_today_snapshot_optional_goal_features_without_today():
    local = _fx(500, api=8500)
    payload, _, id_mock, _, _, _ = _audit([local], today_rows=[])
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
    payload, _, _, _, _, _ = _audit([bad], today_rows=[])
    assert payload["anti_leakage"]["local_fixture_missing_teams"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0
    assert payload["exclusion_reasons"]["missing_teams"] == 1


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
    assert _inv(payload, "away_goals_scored_rolling_10")["mean"] is not None
    assert any(p["fixtures_with_any_feature"] > 0 for p in payload["pillar_coverage"].values())


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
    # Esclusione corretta: riga safe, senza goal contaminati
    assert payload["anti_leakage"]["rows_passed"] == 1
    assert payload["anti_leakage"]["current_fixture_included"] == 0
    assert payload["anti_leakage"]["future_fixture_included"] == 0
    mean_home = _inv(payload, "home_goals_scored_avg")["mean"]
    assert mean_home is not None
    assert mean_home < 5.0  # non include i 9 goal del target


def test_xg_from_today_snapshot():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[today])
    assert payload["anti_leakage"]["xg_from_today_snapshot"] == 1
    assert _inv(payload, "home_xg_for_avg")["rows_available"] == 1


def test_xg_from_fixture_team_stats_when_no_snapshot():
    local = _fx(500, api=8500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
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
    payload, _, _, _, _, _ = _audit([local], today_rows=[today], xg_profiles_override=bad)
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
        identity={"status": "inconsistent", "warnings": ["fixture_kickoff_mismatch"]},
    )
    assert payload["anti_leakage"]["fixture_identity_mismatch"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0


def test_performance_payload_has_phases():
    local = _fx(500)
    payload, _, _, _, _, _ = _audit([local], today_rows=[])
    perf = payload["performance"]
    assert "elapsed_ms" in perf
    assert "calculation_ms" in perf
    assert "db_query_phases" in perf
    assert "index_sizes" in perf
    assert "fixtures_per_second" in perf


def test_today_indexes_lookup():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    by_local, by_provider = build_today_indexes([today])
    assert 500 in by_local
    assert 8500 in by_provider


def test_feature_equivalence_indexes_vs_v1_1_path():
    """Stesso campione → feature uguali tra path indici e path DB v1_1 (tol 1e-6)."""
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
        assert _approx_eq(feat_v11.get(key), feat_idx.get(key)), f"mismatch {key}: {feat_v11.get(key)} vs {feat_idx.get(key)}"
    assert meta_v11["xg_source"] == meta_idx["xg_source"]
    assert meta_v11["sample_size"] == meta_idx["sample_size"]


def test_availability_payload_shape():
    db = MagicMock()
    db.scalar.side_effect = [
        42,
        datetime(2025, 8, 1, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc),
    ]
    db.scalars.return_value.all.side_effect = [
        [39, 140],
        [MagicMock(id=39, country="England"), MagicMock(id=140, country="Spain")],
    ]
    payload = build_goal_intensity_v5_availability(db)
    assert payload["status"] == "ok"
    assert payload["finished_fixtures_with_result"] == 42
    assert payload["earliest_kickoff_date"] == "2025-08-01"
    assert payload["latest_kickoff_date"] == "2026-07-10"
    assert payload["competitions_count"] == 2
    assert payload["countries_count"] == 2
    assert payload["cohort_basis"] == "fixture_kickoff_at"
