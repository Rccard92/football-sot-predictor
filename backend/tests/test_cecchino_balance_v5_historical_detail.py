"""Test Balance v5 storico: current_strict vs historical_snapshot (casi A–J)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_FINISHED, MATCH_UPCOMING
from app.services.cecchino.cecchino_balance_v5_detail import (
    BOOK_BLOCKED,
    BOOK_UNAVAILABLE,
    META_BLOCKED,
    MODE_CURRENT,
    MODE_HISTORICAL,
    classify_book_snapshot_status,
    resolve_balance_detail_mode,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
KO_BAD = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
ROME_TODAY = date(2026, 7, 19)
SCAN_YESTERDAY = date(2026, 7, 18)
SCAN_TODAY = date(2026, 7, 19)


def _final(**kwargs):
    base = {
        "status": "available",
        "quota_1": 2.1,
        "quota_x": 3.4,
        "quota_2": 3.6,
        "prob_1": 0.42,
        "prob_x": 0.28,
        "prob_2": 0.30,
    }
    base.update(kwargs)
    return base


def _output(*, target: datetime | None = KO, with_final: bool = True, **extra):
    out: dict = {"signals_matrix": {}}
    if with_final:
        out["final"] = _final()
    if target is not None:
        out["data_quality"] = {"leakage_check": {"target_kickoff": target.isoformat()}}
    out.update(extra)
    return out


def _kpi_with_book():
    return {
        "version": "cecchino_kpi_v2_betfair",
        "rows": [
            {"market_key": SEL_HOME, "quota_cecchino": 2.1, "quota_book": 2.2, "segno": "1"},
            {"market_key": SEL_DRAW, "quota_cecchino": 3.4, "quota_book": 3.5, "segno": "X"},
            {"market_key": SEL_AWAY, "quota_cecchino": 3.6, "quota_book": 3.7, "segno": "2"},
        ],
    }


def _odds_snapshot(*, fetched_at: str | None, home=2.2, draw=3.5, away=3.7):
    meta = {}
    if fetched_at is not None:
        meta = {
            "odds_meta": {
                "odds_fetched_at": fetched_at,
                "odds_cached_at": fetched_at,
                "odds_source": "cached",
                "is_cached": True,
            }
        }
    return {
        "bookmakers": {"Betfair": {"HOME": home, "DRAW": draw, "AWAY": away}},
        **meta,
    }


def _row(**kwargs):
    base = dict(
        id=9510,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=10,
        country_name="Brazil",
        league_name="Serie A",
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=KO,
        fixture_status="NS",
        match_display_status=MATCH_UPCOMING,
        goals_home=None,
        goals_away=None,
        score_fulltime_home=None,
        score_fulltime_away=None,
        scan_date=SCAN_YESTERDAY,
        odds_snapshot_json={},
        stats_snapshot_json={},
        kpi_panel_json=None,
        cecchino_output_json=_output(),
        warnings_json=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _local(**kwargs):
    base = dict(
        id=562,
        api_fixture_id=1492291,
        competition_id=10,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=KO,
        status="FT",
        status_long="Match Finished",
        goals_home=2,
        goals_away=1,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _db_for(row, local):
    home = SimpleNamespace(name="Botafogo")
    away = SimpleNamespace(name="Santos")
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        if "Fixture" in name and "Today" not in name:
            return local
        if "Team" in name:
            return home if int(pk) == 1 else away
        return None

    db.get.side_effect = _get
    return db


_DETAIL_PATCHES = [
    patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"),
    patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={}),
    patch(
        "app.services.cecchino.cecchino_today_service.build_expected_goal_engine_diagnostics_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
        return_value={"status": "unavailable", "error": "bundle_missing"},
    ),
    patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=ROME_TODAY),
]


def _apply_detail_patches(fn):
    for p in reversed(_DETAIL_PATCHES):
        fn = p(fn)
    return fn


@_apply_detail_patches
def test_case_a_historical_upcoming_vs_local_ft(*_args):
    row = _row()
    local = _local()
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    ident = detail["fixture_identity_consistency"]
    assert meta["mode"] == MODE_HISTORICAL
    assert meta["status"] in ("verified", "partial")
    assert detail["balance_v5"]["status"] == "ok"
    assert ident["status"] == "consistent"
    assert ident["status_match"] is False
    assert ident["score_match"] is False
    assert ident["status_match_blocking"] is False
    assert ident["score_match_blocking"] is False


@_apply_detail_patches
def test_case_b_current_mismatch_still_blocks(*_args):
    row = _row(
        scan_date=SCAN_TODAY,
        fixture_status="FT",
        match_display_status=MATCH_FINISHED,
        goals_home=2,
        goals_away=1,
        cecchino_output_json=_output(target=KO_BAD),
    )
    local = _local(kickoff_at=KO_BAD, status="NS", goals_home=None, goals_away=None)
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    assert meta["mode"] == MODE_CURRENT
    assert detail["fixture_identity_consistency"]["status"] == "inconsistent"
    assert detail["balance_v5"]["status"] == "unavailable"
    assert meta["status_match_blocking"] is True
    assert meta["score_match_blocking"] is True


@_apply_detail_patches
def test_case_c_provider_mismatch_blocked(*_args):
    row = _row()
    local = _local(api_fixture_id=999999)
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    assert meta["mode"] == MODE_HISTORICAL
    assert meta["status"] == META_BLOCKED
    assert detail["balance_v5"]["status"] == "unavailable"
    assert "provider_fixture_id_mismatch" in (meta["warnings"] or [])


@_apply_detail_patches
def test_case_d_kickoff_mismatch_blocked(*_args):
    row = _row()
    local = _local(kickoff_at=KO_BAD)
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    assert meta["status"] == META_BLOCKED
    assert detail["balance_v5"]["status"] == "unavailable"


@_apply_detail_patches
def test_case_e_target_kickoff_mismatch_blocked(*_args):
    row = _row(cecchino_output_json=_output(target=KO_BAD))
    local = _local()
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    assert meta["status"] == META_BLOCKED
    assert detail["balance_v5"]["status"] == "unavailable"
    assert "historical_target_kickoff_mismatch" in (meta["warnings"] or [])


@_apply_detail_patches
@patch("app.services.cecchino.cecchino_today_service.load_betfair_odds_payload")
def test_case_f_book_pre_kickoff_no_db_fallback(mock_load, *_args):
    pre = (KO - timedelta(hours=2)).isoformat()
    row = _row(
        kpi_panel_json=None,
        odds_snapshot_json=_odds_snapshot(fetched_at=pre),
    )
    local = _local()
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    mock_load.assert_not_called()
    assert detail["balance_v5"]["status"] == "ok"
    md = detail["balance_v5"]["market_deviation"]
    assert md["status"] == "ok"
    assert any(p.get("quota_book") is not None for p in md.get("pairs") or [])
    assert detail["balance_v5_snapshot_meta"]["book_snapshot_status"] == "verified"


@_apply_detail_patches
def test_case_g_book_post_kickoff_pillars_ok_market_blocked(*_args):
    post = (KO + timedelta(hours=3)).isoformat()
    row = _row(
        kpi_panel_json=_kpi_with_book(),
        odds_snapshot_json=_odds_snapshot(fetched_at=post),
    )
    local = _local()
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    bal = detail["balance_v5"]
    assert bal["status"] == "ok"
    assert bal["pillars"]["f36"]["status"] != "unavailable"
    assert bal["market_deviation"]["status"] == "unavailable"
    assert "historical_book_snapshot_not_pre_match" in (bal["warnings"] or [])
    assert detail["balance_v5_snapshot_meta"]["book_snapshot_status"] == BOOK_BLOCKED


@_apply_detail_patches
def test_case_h_book_absent_pillars_ok(*_args):
    row = _row(kpi_panel_json={"version": "cecchino_kpi_v2_betfair", "rows": []}, odds_snapshot_json={})
    local = _local()
    detail = get_today_fixture_detail(_db_for(row, local), 9510)
    bal = detail["balance_v5"]
    assert bal["status"] == "ok"
    assert bal["market_deviation"]["status"] == "unavailable"
    assert detail["balance_v5_snapshot_meta"]["book_snapshot_status"] == BOOK_UNAVAILABLE
    # nessuna quota inventata
    for p in bal["market_deviation"].get("pairs") or []:
        assert p.get("quota_book") is None


@_apply_detail_patches
def test_case_i_output_absent_blocked_no_recompute(*_args):
    row = _row(cecchino_output_json={})
    local = _local()
    with patch(
        "app.services.cecchino.cecchino_today_service.build_cecchino_balance_v5"
    ) as mock_bal:
        # ancora chiamata ma identity forced inconsistent → unavailable
        from app.services.cecchino.cecchino_balance_v5 import build_cecchino_balance_v5 as real_bal

        mock_bal.side_effect = real_bal
        detail = get_today_fixture_detail(_db_for(row, local), 9510)
    meta = detail["balance_v5_snapshot_meta"]
    assert meta["status"] == META_BLOCKED
    assert detail["balance_v5"]["status"] == "unavailable"
    assert "historical_cecchino_output_absent" in (meta["warnings"] or []) or (
        "historical_cecchino_final_unavailable" in (meta["warnings"] or [])
    )


@_apply_detail_patches
@patch("app.services.cecchino.cecchino_today_service.load_betfair_odds_payload")
def test_case_j_get_readonly_no_recompute_no_commit(mock_load, *_args):
    row = _row(kpi_panel_json=_kpi_with_book())
    original_output = dict(row.cecchino_output_json)
    original_kpi = dict(row.kpi_panel_json)
    local = _local()
    db = _db_for(row, local)

    with (
        patch(
            "app.services.cecchino.cecchino_today_service.calculate_and_persist_for_fixture",
            create=True,
        ) as mock_calc,
        patch(
            "app.services.cecchino.cecchino_today_service.recompute_today_fixture_offline",
            create=True,
        ) as mock_recompute,
    ):
        # ensure attributes don't exist as real callables on module - patch create=True is enough
        detail = get_today_fixture_detail(db, 9510)

    assert detail["status"] == "ok"
    mock_load.assert_not_called()
    db.commit.assert_not_called()
    assert row.cecchino_output_json == original_output
    assert row.kpi_panel_json == original_kpi
    mock_calc.assert_not_called()
    mock_recompute.assert_not_called()


def test_resolve_mode_by_scan_date():
    assert resolve_balance_detail_mode(SCAN_YESTERDAY, ROME_TODAY) == MODE_HISTORICAL
    assert resolve_balance_detail_mode(SCAN_TODAY, ROME_TODAY) == MODE_CURRENT
    assert resolve_balance_detail_mode(None, ROME_TODAY) == MODE_CURRENT


def test_classify_book_post_kickoff():
    status, warns = classify_book_snapshot_status(
        kickoff=KO,
        odds_meta={"odds_fetched_at": (KO + timedelta(hours=1)).isoformat()},
        has_book_odds=True,
    )
    assert status == BOOK_BLOCKED
    assert "historical_book_snapshot_not_pre_match" in warns
