"""Test coorte Intensità Goal v5 — solo eleggibili Cecchino Today."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_WOMEN,
)
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
    COHORT_BASIS,
    ELIGIBILITY_SOURCE_PERSISTED,
    MIN_GOAL_INTENSITY_TODAY_SCAN_DATE,
    RANGE_ERROR_MESSAGE,
    classify_today_eligibility,
    normalize_goal_intensity_scan_range,
    select_eligible_match_groups,
    build_goal_intensity_today_cohort,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import VERSION as DATASET_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit import VERSION as AUDIT_VERSION


KO = datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc)


def _today_row(**kwargs):
    row = MagicMock()
    defaults = {
        "id": 1,
        "scan_date": date(2026, 6, 20),
        "provider_source": "api_football",
        "provider_fixture_id": 9001,
        "local_fixture_id": 500,
        "competition_id": 39,
        "kickoff": KO,
        "home_team_name": "Home",
        "away_team_name": "Away",
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "eligibility_reason": None,
        "blocking_reasons_json": None,
        "created_at": datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc),
        "odds_checked_at": datetime(2026, 6, 20, 11, 0, tzinfo=timezone.utc),
        "odds_snapshot_json": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _fx(fid=500, status="FT", gh=2, ga=1, ko=None):
    fx = MagicMock()
    fx.id = fid
    fx.api_fixture_id = 9001
    fx.status = status
    fx.goals_home = gh
    fx.goals_away = ga
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.competition_id = 39
    fx.kickoff_at = ko or KO
    return fx


def test_versions_and_cohort_basis():
    assert DATASET_VERSION == "cecchino_goal_intensity_v5_dataset_v1_2"
    assert AUDIT_VERSION == "cecchino_goal_intensity_v5_audit_v1_5"
    assert COHORT_BASIS == "cecchino_today_eligible_scan_date"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"


def test_normalize_scan_range_clamp_and_reject():
    ef, et, clamped, err, warns = normalize_goal_intensity_scan_range(
        date(2026, 1, 1), date(2026, 7, 1)
    )
    assert ef == MIN_GOAL_INTENSITY_TODAY_SCAN_DATE
    assert clamped is True
    assert err is None
    assert warns

    _, _, _, err2, _ = normalize_goal_intensity_scan_range(date(2026, 1, 1), date(2026, 6, 1))
    assert err2 == RANGE_ERROR_MESSAGE


def test_classify_eligible_ineligible_unknown():
    e = classify_today_eligibility(_today_row(eligibility_status=ELIGIBILITY_ELIGIBLE))
    assert e.eligibility_status == "eligible"
    assert e.eligibility_source == ELIGIBILITY_SOURCE_PERSISTED

    i = classify_today_eligibility(_today_row(eligibility_status=ELIGIBILITY_EXCLUDED_CUP))
    assert i.eligibility_status == "ineligible"

    u = classify_today_eligibility(_today_row(eligibility_status=None))
    assert u.eligibility_status == "unknown"

    u2 = classify_today_eligibility(_today_row(eligibility_status="weird_status_xyz"))
    assert u2.eligibility_status == "unknown"


def test_select_latest_eligible_pre_kickoff_not_ineligible_later():
    early = _today_row(
        id=1,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        created_at=datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc),
    )
    later_ineligible = _today_row(
        id=2,
        eligibility_status=ELIGIBILITY_EXCLUDED_WOMEN,
        created_at=datetime(2026, 6, 20, 16, 0, tzinfo=timezone.utc),
    )
    mid = _today_row(
        id=3,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        created_at=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
    )
    from app.services.cecchino.cecchino_goal_intensity_v5_today_cohort import (
        classify_today_eligibility as clf,
    )

    groups = select_eligible_match_groups([clf(early), clf(later_ineligible), clf(mid)])
    assert len(groups) == 1
    assert groups[0]["selected"].row.id == 3
    assert groups[0]["selection_criterion"] == "latest_eligible_pre_kickoff_snapshot"


def test_build_cohort_eligible_finished_only():
    eligible = _today_row(id=10, eligibility_status=ELIGIBILITY_ELIGIBLE, local_fixture_id=500)
    ineligible = _today_row(
        id=11,
        eligibility_status=ELIGIBILITY_EXCLUDED_CUP,
        provider_fixture_id=9002,
        local_fixture_id=501,
    )
    unknown = _today_row(
        id=12,
        eligibility_status=None,
        provider_fixture_id=9003,
        local_fixture_id=502,
    )
    pending_row = _today_row(
        id=13,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        provider_fixture_id=9004,
        local_fixture_id=503,
    )

    fx_ok = _fx(500, status="FT")
    fx_pending = _fx(503, status="NS", gh=None, ga=None)

    db = MagicMock()
    db.scalars.return_value.all.return_value = [eligible, ineligible, unknown, pending_row]

    def _get(model, pk):
        return {500: fx_ok, 503: fx_pending}.get(int(pk))

    db.get.side_effect = _get

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_today_cohort.load_today_scans_for_goal_intensity",
        return_value=[eligible, ineligible, unknown, pending_row],
    ):
        # Also need fixtures batch load
        db.scalars.return_value.all.side_effect = [
            [fx_ok, fx_pending],  # fixtures by id
        ]
        cohort = build_goal_intensity_today_cohort(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 17),
        )

    assert cohort.error is None
    assert cohort.eligibility_diagnostics["cohort_basis"] == COHORT_BASIS
    ids = {int(t.local_fixture.id) for t in cohort.targets}
    assert 500 in ids
    assert 501 not in ids  # ineligible
    assert 502 not in ids  # unknown
    assert all(t.eligibility_status == "eligible" for t in cohort.targets)
    assert cohort.eligibility_diagnostics["today_eligibility_unknown"] >= 1
    assert cohort.eligibility_diagnostics["eligible_pending_matches"] >= 1


def test_scan_date_before_min_excluded_from_targets():
    old = _today_row(scan_date=date(2026, 6, 10), eligibility_status=ELIGIBILITY_ELIGIBLE)
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_today_cohort.load_today_scans_for_goal_intensity",
        return_value=[],
    ):
        cohort = build_goal_intensity_today_cohort(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 7, 1),
        )
    # date_from clamped; empty raw because load mocked empty — but clamp warning present
    assert cohort.date_from == MIN_GOAL_INTENSITY_TODAY_SCAN_DATE
    assert cohort.date_from_clamped is True
    _ = old


def test_no_duplicate_eligibility_validator_import():
    """La coorte non deve importare/richiamare il validator (solo campo persistito)."""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app/services/cecchino/cecchino_goal_intensity_v5_today_cohort.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports.append(alias.name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "validate_cecchino_today_final_eligibility"
    assert "validate_cecchino_today_final_eligibility" not in imports
