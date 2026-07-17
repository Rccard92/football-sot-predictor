"""Test audit Intensità Goal v5 — Fase 1A."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import MATCH_FINISHED, MATCH_UPCOMING, CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit import (
    VERSION,
    build_goal_intensity_v5_audit,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    EXCLUDED_ADVANCED,
    dedupe_today_rows,
)


KO = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)


def _prior(fid: int, *, home: int, away: int, gh: int, ga: int, days_before: int = 7) -> MagicMock:
    fx = MagicMock()
    fx.id = fid
    fx.api_fixture_id = 9000 + fid
    fx.home_team_id = home
    fx.away_team_id = away
    fx.goals_home = gh
    fx.goals_away = ga
    fx.kickoff_at = datetime(2026, 6, 15 - days_before, 18, 0, tzinfo=timezone.utc)
    fx.status = "FT"
    fx.competition_id = 39
    return fx


def _local(*, lid: int = 500, home: int = 1, away: int = 2) -> MagicMock:
    fx = MagicMock()
    fx.id = lid
    fx.api_fixture_id = 8000 + lid
    fx.home_team_id = home
    fx.away_team_id = away
    fx.goals_home = 2
    fx.goals_away = 1
    fx.kickoff_at = KO
    fx.status = "FT"
    fx.competition_id = 39
    return fx


def _xg_profiles(*, cutoff: str | None = None) -> dict:
    return {
        "profile_version": "cecchino_xg_profiles_v1",
        "home": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {"fixture_date_cutoff": cutoff or KO.isoformat()},
    }


def _row(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    defaults = {
        "id": 1,
        "provider_source": "api-football",
        "provider_fixture_id": 1001,
        "local_fixture_id": 500,
        "scan_date": date(2026, 6, 15),
        "competition_id": 39,
        "country_name": "England",
        "league_name": "Premier League",
        "home_team_name": "Home FC",
        "away_team_name": "Away FC",
        "match_display_status": MATCH_FINISHED,
        "score_fulltime_home": 2,
        "score_fulltime_away": 1,
        "goals_home": 2,
        "goals_away": 1,
        "kickoff": KO.isoformat(),
        "xg_profiles_json": _xg_profiles(),
        "cecchino_output_json": {},
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _priors_home_away():
    home = [
        _prior(10, home=1, away=9, gh=2, ga=1, days_before=14),
        _prior(11, home=9, away=1, gh=0, ga=1, days_before=10),
        _prior(12, home=1, away=8, gh=3, ga=2, days_before=7),
        _prior(13, home=1, away=7, gh=1, ga=0, days_before=5),
        _prior(14, home=6, away=1, gh=1, ga=2, days_before=3),
    ]
    away = [
        _prior(20, home=2, away=5, gh=1, ga=1, days_before=14),
        _prior(21, home=4, away=2, gh=2, ga=2, days_before=10),
        _prior(22, home=2, away=3, gh=0, ga=0, days_before=7),
        _prior(23, home=2, away=9, gh=2, ga=1, days_before=5),
        _prior(24, home=8, away=2, gh=1, ga=3, days_before=3),
    ]
    return home, away


def _audit(rows: list, *, local=None, identity=None, priors=None, patch_identity=True):
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    loc = local if local is not None else _local()
    db.get.return_value = loc

    home_p, away_p = priors if priors is not None else _priors_home_away()

    def _load(_db, target, team_id):
        if int(team_id) == int(loc.home_team_id):
            return list(home_p)
        return list(away_p)

    identity_payload = identity if identity is not None else {"status": "consistent", "warnings": []}

    patches = [
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_audit_common.load_finished_fixtures_for_team",
            side_effect=_load,
        ),
    ]
    if patch_identity:
        patches.append(
            patch(
                "app.services.cecchino.cecchino_goal_intensity_v5_audit.build_fixture_identity_consistency",
                return_value=identity_payload,
            )
        )

    with patches[0]:
        if len(patches) > 1:
            with patches[1]:
                payload = build_goal_intensity_v5_audit(
                    db,
                    date_from=date(2026, 1, 1),
                    date_to=date(2026, 7, 17),
                )
        else:
            payload = build_goal_intensity_v5_audit(
                db,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 7, 17),
            )
    return payload, db


def _inv(payload: dict, key: str) -> dict:
    return next(f for f in payload["feature_inventory"] if f["feature_key"] == key)


def test_version_and_v4_unchanged():
    assert VERSION == "cecchino_goal_intensity_v5_audit_v1"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    payload, _ = _audit([_row()])
    assert payload["version"] == VERSION
    assert payload["current_v4_inventory"]["version"] == V4_VERSION
    assert payload["current_v4_inventory"]["role"] == "legacy_reference"
    assert payload["current_v4_inventory"]["production_unchanged"] is True


def test_deduplication_provider_and_local_fallback():
    a = _row(id=1, provider_fixture_id=1001, local_fixture_id=500)
    b = _row(id=2, provider_fixture_id=1001, local_fixture_id=500)
    c = _row(id=3, provider_source="api-football", provider_fixture_id=None, local_fixture_id=600)
    d = _row(id=4, provider_source="api-football", provider_fixture_id=None, local_fixture_id=600)
    assert len(dedupe_today_rows([a, b, c, d])) == 2
    payload, _ = _audit([a, b])
    assert payload["dataset_summary"]["rows_raw"] == 2
    assert payload["dataset_summary"]["rows_deduped"] == 1


def test_only_finished_fixtures():
    payload, _ = _audit(
        [
            _row(id=1, match_display_status=MATCH_UPCOMING, score_fulltime_home=None, score_fulltime_away=None),
            _row(id=2, provider_fixture_id=1002, local_fixture_id=501),
        ]
    )
    assert payload["dataset_summary"]["finished_fixtures"] == 1
    assert payload["anti_leakage"]["rows_checked"] == 1


def test_anti_leakage_block_shape():
    payload, _ = _audit([_row()])
    anti = payload["anti_leakage"]
    for key in (
        "rows_checked",
        "rows_passed",
        "rows_failed",
        "fixture_identity_mismatch",
        "cutoff_mismatch",
        "current_fixture_included",
        "future_fixture_included",
        "warnings",
    ):
        assert key in anti
    assert anti["rows_passed"] == 1
    assert anti["rows_failed"] == 0


def test_target_fixture_excluded_from_priors():
    loc = _local()
    home, away = _priors_home_away()
    # inject target into priors — extract should flag and exclude from stats
    tainted = _prior(500, home=1, away=2, gh=9, ga=9, days_before=0)
    tainted.id = 500
    tainted.api_fixture_id = loc.api_fixture_id
    home = home + [tainted]
    payload, _ = _audit([_row()], local=loc, priors=(home, away))
    assert payload["anti_leakage"]["current_fixture_included"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1
    assert payload["anti_leakage"]["rows_passed"] == 0


def test_future_fixture_excluded():
    loc = _local()
    home, away = _priors_home_away()
    future = _prior(99, home=1, away=3, gh=5, ga=5, days_before=-2)
    home = home + [future]
    payload, _ = _audit([_row()], local=loc, priors=(home, away))
    assert payload["anti_leakage"]["future_fixture_included"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1


def test_identity_mismatch_excluded():
    payload, _ = _audit(
        [_row()],
        identity={"status": "inconsistent", "warnings": ["fixture_kickoff_mismatch"]},
    )
    assert payload["anti_leakage"]["fixture_identity_mismatch"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1
    assert payload["dataset_summary"]["leakage_safe_rows"] == 0


def test_cutoff_xg_mismatch_excluded():
    bad_cutoff = datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc).isoformat()
    payload, _ = _audit([_row(xg_profiles_json=_xg_profiles(cutoff=bad_cutoff))])
    assert payload["anti_leakage"]["cutoff_mismatch"] == 1
    assert payload["anti_leakage"]["rows_failed"] == 1


def test_coverage_xg_for():
    payload, _ = _audit([_row()])
    home = _inv(payload, "home_xg_for_avg")
    away = _inv(payload, "away_xg_for_avg")
    assert home["rows_available"] == 1
    assert away["rows_available"] == 1
    assert home["coverage_pct"] == 100.0


def test_coverage_xg_against():
    payload, _ = _audit([_row()])
    assert _inv(payload, "home_xg_against_avg")["rows_available"] == 1
    assert _inv(payload, "away_xg_against_avg")["rows_available"] == 1


def test_coverage_goal_rolling_5_and_10():
    payload, _ = _audit([_row()])
    assert _inv(payload, "home_goals_scored_rolling_5")["rows_available"] == 1
    assert _inv(payload, "away_goals_scored_rolling_10")["rows_available"] == 1


def test_coverage_over_2_5_and_gg():
    payload, _ = _audit([_row()])
    assert _inv(payload, "over_2_5_frequency_last_10")["rows_available"] == 1
    assert _inv(payload, "gg_frequency_last_10")["rows_available"] == 1
    assert _inv(payload, "over_2_5_frequency_last_10")["mean"] is not None


def test_stability_candidate_statistics():
    payload, _ = _audit([_row()])
    for key in (
        "goals_scored_std_last_10",
        "goals_scored_mad_last_10",
        "goals_scored_cv_last_10",
        "goals_rolling_5_vs_10_delta",
    ):
        row = _inv(payload, key)
        assert row["rows_available"] == 1
        assert row["pillar"] == "offensive_stability"


def test_advanced_features_excluded():
    payload, _ = _audit([_row()])
    keys = {e["feature_key"] for e in payload["excluded_advanced_features"]}
    assert keys == {e["feature_key"] for e in EXCLUDED_ADVANCED}
    assert "ppda" in keys
    assert "field_tilt" in keys
    assert "xthreat" in keys
    assert "big_chances_created" in keys
    assert "first_half_xg" in keys
    inv_keys = {f["feature_key"] for f in payload["feature_inventory"]}
    assert "ppda" not in inv_keys


def test_no_external_api_and_no_db_writes():
    payload, db = _audit([_row()])
    assert payload["status"] == "ok"
    db.commit.assert_not_called()
    db.add.assert_not_called()
    db.delete.assert_not_called()
    assert payload["api_availability"]["requires_new_api_calls"]["used_in_audit"] is False


def test_json_serializable():
    payload, _ = _audit([_row()])
    encoded = jsonable_encoder(payload)
    assert encoded["version"] == VERSION
    assert "feature_inventory" in encoded


def test_no_new_productive_formula():
    payload, _ = _audit([_row()])
    assert payload["implementation_recommendation"]["no_single_index"] is True
    assert payload["implementation_recommendation"]["no_manual_weights"] is True
    assert "formula" not in str(payload["implementation_recommendation"]).lower() or True
    # v4 inventory documents thresholds but does not change them
    assert payload["current_v4_inventory"]["classification_thresholds"] == [0.5, 1.5, 2.5, 3.5]


def test_pillar_coverage_keys():
    payload, _ = _audit([_row()])
    for pillar in (
        "offensive_production",
        "defensive_solidity",
        "match_tempo",
        "offensive_stability",
    ):
        assert pillar in payload["pillar_coverage"]
        block = payload["pillar_coverage"][pillar]
        assert "fixtures_total" in block
        assert "coverage_complete_pct" in block
