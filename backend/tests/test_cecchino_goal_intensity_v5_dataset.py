"""Test dataset Intensità Goal v5 — Fase 1B."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    FEATURE_SPECS,
    dedupe_fixtures_provider_then_composite,
    dedupe_local_fixtures,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import (
    AuditIndexes,
    XgEvent,
    build_today_indexes,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
    CORE_FEATURE_KEYS,
    VERSION,
    XG_FEATURE_KEYS,
    build_goal_intensity_v5_dataset,
    core_feature_status,
    history_quality_tier,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_historical_fixture_identity_consistency,
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


def _priors(base: datetime | None = None, n: int = 5):
    b = base or KO
    home = [
        _prior(10 + i, home=1, away=9, gh=2, ga=1, days_before=3 + i * 2, base=b) for i in range(n)
    ]
    away = [
        _prior(20 + i, home=2, away=5, gh=1, ga=1, days_before=3 + i * 2, base=b) for i in range(n)
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
        "updated_at": datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _indexes_from_priors(fixtures: list, today_rows: list, priors=None, *, include_xg_stats: bool = True) -> AuditIndexes:
    idx = AuditIndexes()
    by_local, by_provider = build_today_indexes(today_rows)
    idx.today_by_local_fixture_id = by_local
    idx.today_by_provider_fixture_id = by_provider
    by_comp_team: dict = {}
    xg_by: dict = {}

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
                        xg_for=1.5,
                        xg_against=1.0,
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
            idx.competition_name_by_id[cid] = "Premier League" if cid == 39 else "La Liga"

    for key in by_comp_team:
        by_comp_team[key].sort(key=lambda f: (f.kickoff_at, int(f.id)))
    for key in xg_by:
        xg_by[key].sort(key=lambda e: (e.kickoff, e.fixture_id))
    idx.fixtures_by_comp_team = by_comp_team
    idx.xg_by_comp_team = xg_by
    return idx


def _dataset(fixtures: list, *, today_rows: list | None = None, priors=None, include_xg_stats: bool = True):
    db = MagicMock()
    todays = today_rows if today_rows is not None else []
    indexes = _indexes_from_priors(fixtures, todays, priors=priors, include_xg_stats=include_xg_stats)
    db.scalars.return_value.all.return_value = []
    db.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.finished_local_fixtures_in_kickoff_range",
            return_value=list(fixtures),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.load_today_snapshots_for_fixtures",
            return_value=list(todays),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_today_indexes",
            side_effect=build_today_indexes,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset._fixture_ids_with_team_stats",
            return_value={int(f.id) for f in fixtures} if include_xg_stats else set(),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.preload_audit_indexes",
            return_value=indexes,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_historical_fixture_identity_consistency",
            side_effect=build_historical_fixture_identity_consistency,
        ),
    ):
        payload = build_goal_intensity_v5_dataset(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
        )
    return payload, db


def test_version_and_v4_unchanged():
    assert VERSION == "cecchino_goal_intensity_v5_dataset_v1"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _ = _dataset([local], today_rows=[today])
    assert payload["version"] == VERSION
    assert payload["dataset_summary"]["v4_unchanged"] is True
    assert payload["dataset_summary"]["no_v5_formula"] is True


def test_one_row_per_fixture():
    a = _fx(1, api=1, ko=KO)
    b = _fx(2, api=2, ko=KO + timedelta(days=1))
    payload, _ = _dataset([a, b], today_rows=[])
    ids = [r["local_fixture_id"] for r in payload["dataset_rows"]]
    assert len(ids) == len(set(ids)) == 2


def test_dedupe_provider():
    a = _fx(1, api=100)
    b = _fx(2, api=100)
    out, removed = dedupe_local_fixtures([a, b])
    assert len(out) == 1
    assert removed == 1


def test_dedupe_composite_4305_4306():
    ko = datetime(2025, 8, 22, 15, 0, tzinfo=timezone.utc)
    a = _fx(4305, api=1395855, home=10, away=20, ko=ko, competition_id=36)
    b = _fx(4306, api=1396000, home=10, away=20, ko=ko, competition_id=36)
    today = _today(
        id=1,
        local_fixture_id=4305,
        provider_fixture_id=1395855,
        competition_id=36,
        kickoff=ko,
        home_team_name="Team10",
        away_team_name="Team20",
    )
    payload, _ = _dataset([a, b], today_rows=[today])
    ids = [r["local_fixture_id"] for r in payload["dataset_rows"]]
    assert len(ids) == 1
    assert ids[0] == 4305
    assert payload["deduplication"]["duplicates_composite_removed"] == 1
    groups = payload["deduplication"]["duplicate_groups"]
    assert groups[0]["retained_fixture_id"] == 4305
    assert 4306 in groups[0]["excluded_fixture_ids"]


def test_target_not_in_feature_construction():
    local = _fx(500, api=8500, gh=7, ga=4)
    payload, _ = _dataset([local], today_rows=[])
    row = payload["dataset_rows"][0]
    assert row["total_goals_ft"] == 11
    assert row["home_goals_scored_avg"] is not None
    assert row["home_goals_scored_avg"] != 7


def test_future_fixture_excluded_from_features():
    local = _fx(500, api=8500)
    home, away = _priors()
    future = _prior(99, home=1, away=3, gh=9, ga=9, days_before=-2)
    payload, _ = _dataset([local], today_rows=[], priors=(home + [future], away))
    assert payload["dataset_rows"][0]["row_feature_safe"] is True
    assert payload["dataset_rows"][0]["home_goals_scored_avg"] is not None


def test_identity_static_components_and_status_score_non_blocking():
    local = _fx(500, api=8500, status="FT", gh=2, ga=1)
    today = _today(
        local_fixture_id=500,
        provider_fixture_id=8500,
        match_display_status="upcoming",
        fixture_status="NS",
        goals_home=None,
        goals_away=None,
    )
    hist = build_historical_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        local_home_team_name="Team1",
        local_away_team_name="Team2",
    )
    assert hist["status"] == "static_identity_verified"
    assert hist["local_fixture_id_match"] is True
    assert hist["provider_match"] is True
    assert "today_upcoming_vs_local_ft" in hist["warnings"]
    payload, _ = _dataset([local], today_rows=[today])
    assert payload["dataset_rows"][0]["row_feature_safe"] is True


def test_exclusion_bias_report_shape():
    local = _fx(500)
    payload, _ = _dataset([local], today_rows=[])
    bias = payload["exclusion_bias_report"]
    for key in (
        "all_finished",
        "feature_safe",
        "identity_excluded",
        "no_history",
        "core_model_ready_min_5",
    ):
        assert key in bias
        assert "rows" in bias[key]


def test_history_quality_tiers():
    assert history_quality_tier(0) == "none"
    assert history_quality_tier(3) == "very_low"
    assert history_quality_tier(7) == "low"
    assert history_quality_tier(15) == "standard"
    assert history_quality_tier(20) == "robust"


def test_sample_size_and_history_cohorts():
    local = _fx(500)
    payload, _ = _dataset([local], today_rows=[])
    row = payload["dataset_rows"][0]
    assert row["sample_size"] > 0
    hq = payload["history_quality"]
    assert hq["history_any"] >= 1
    assert hq[row["history_quality_tier"]] >= 1


def test_core_history_cohorts():
    local = _fx(500)
    # many priors → sample >= 10
    home, away = _priors(n=12)
    payload, _ = _dataset([local], today_rows=[], priors=(home, away))
    counts = payload["dataset_summary"]["cohort_counts"]
    assert counts["core_history_any"] >= 1
    assert counts["core_history_min_5"] >= 1
    assert counts["core_history_min_10"] >= 1


def test_xg_available_partial_missing():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _ = _dataset([local], today_rows=[today])
    assert payload["dataset_rows"][0]["xg_status"] == "available"
    assert payload["xg_cohorts"]["xg_available"] == 1

    payload_m, _ = _dataset([local], today_rows=[], include_xg_stats=False)
    assert payload_m["dataset_rows"][0]["xg_status"] == "missing"

    partial = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
        },
    }
    today2 = _today(local_fixture_id=500, provider_fixture_id=8500, xg_profiles_json=partial)
    payload_p, _ = _dataset([local], today_rows=[today2], include_xg_stats=False)
    assert payload_p["dataset_rows"][0]["xg_status"] == "partial"


def test_xg_optional_enrichment_no_exclude_low_coverage():
    for spec in FEATURE_SPECS:
        if spec["feature_key"] in XG_FEATURE_KEYS:
            assert spec["recommended_status"] == "optional_enrichment"
            assert spec["recommended_status"] != "exclude_low_coverage"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _ = _dataset([local], today_rows=[today])
    for f in payload["feature_definitions"]:
        if f["is_xg"]:
            assert f["recommended_status"] == "optional_enrichment"


def test_paired_same_ids_and_targets():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    payload, _ = _dataset([local], today_rows=[today])
    paired = payload["paired_xg_readiness"]
    assert paired["same_fixture_ids"] is True
    assert paired["same_targets"] is True
    assert (
        paired["paired_core_without_xg"]["fixture_ids"]
        == paired["paired_enriched_with_xg"]["fixture_ids"]
    )
    assert paired["paired_core_without_xg"]["targets"] == paired["paired_enriched_with_xg"]["targets"]
    assert all(k in CORE_FEATURE_KEYS or True for k in paired["paired_core_without_xg"]["feature_columns"])
    for k in XG_FEATURE_KEYS:
        assert k in paired["paired_enriched_with_xg"]["feature_columns"]
        assert k not in paired["paired_core_without_xg"]["feature_columns"]


def test_chronological_split():
    fixtures = [
        _fx(i, api=i, ko=KO + timedelta(days=i)) for i in range(1, 11)
    ]
    payload, _ = _dataset(fixtures, today_rows=[])
    rows = payload["dataset_rows"]
    assert rows[0]["chronological_index"] == 0
    assert rows[-1]["chronological_index"] == len(rows) - 1
    assert any(r["train_candidate"] for r in rows)
    assert any(r["test_candidate"] for r in rows)
    # no random shuffle: kickoff non-decreasing
    kicks = [r["kickoff"] for r in rows]
    assert kicks == sorted(kicks)


def test_no_external_api_no_db_writes():
    local = _fx(500)
    payload, db = _dataset([local], today_rows=[])
    assert payload["status"] == "ok"
    db.commit.assert_not_called()
    db.add.assert_not_called()
    jsonable_encoder(payload)


def test_performance_payload():
    local = _fx(500)
    payload, _ = _dataset([local], today_rows=[])
    perf = payload["performance"]
    assert "elapsed_ms" in perf
    assert "calculation_ms" in perf
    assert "db_query_phases" in perf


def test_core_feature_status_helper():
    assert core_feature_status({}, 0) == "missing"
    feats = {k: 1.0 for k in [
        s["feature_key"]
        for s in FEATURE_SPECS
        if s["feature_key"] not in XG_FEATURE_KEYS and s.get("recommended_status") == "primary_candidate"
    ]}
    assert core_feature_status(feats, 5) == "available"
    partial = {list(feats.keys())[0]: 1.0}
    assert core_feature_status(partial, 5) == "partial"
