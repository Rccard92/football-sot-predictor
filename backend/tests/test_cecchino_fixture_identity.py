"""Test fixture identity — Fase 2A.3 (raw sources, no GET write)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_balance_v5_preview import (
    VERSION,
    build_balance_v5_preview,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_fixture_identity_consistency,
)


KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
KO_TOL = datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc)
KO_OVER = KO + timedelta(hours=7)
KO_DAYS = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _today(**kwargs):
    base = dict(
        id=9510,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=10,
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=KO,
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
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


def _output(target: datetime | None = KO) -> dict:
    if target is None:
        return {}
    return {"data_quality": {"leakage_check": {"target_kickoff": target.isoformat()}}}


def _xg(cutoff: datetime | None = KO) -> dict:
    if cutoff is None:
        return {}
    return {"xg_profiles": {"anti_leakage": {"fixture_date_cutoff": cutoff.isoformat()}}}


def test_1_raw_values_not_overwritten():
    today = _today(kickoff=KO)
    local = _local(kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None)
    original_ko = today.kickoff
    result = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert today.kickoff is original_ko
    assert today.kickoff == KO
    assert result["raw_sources"]["today"]["kickoff"].startswith("2026-07-16")
    assert result["raw_sources"]["local_fixture"]["kickoff"].startswith("2026-07-22")


def test_2_list_detail_kickoff_divergence_is_inconsistent():
    result = build_fixture_identity_consistency(
        today_row=_today(kickoff=KO),
        local_fixture=_local(kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert result["status"] == "inconsistent"
    assert result["kickoff_match"] is False
    assert "today_local_kickoff_mismatch" in result["warnings"]


def test_3_future_kickoff_plus_ft():
    result = build_fixture_identity_consistency(
        today_row=_today(kickoff=KO_DAYS, fixture_status="FT", match_display_status="finished"),
        local_fixture=_local(kickoff_at=KO_DAYS, status="FT"),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert result["status"] == "inconsistent"
    assert result["chronological_status_valid"] is False
    assert "future_fixture_marked_finished" in result["warnings"]


def test_4_future_kickoff_plus_final_score():
    result = build_fixture_identity_consistency(
        today_row=_today(
            kickoff=KO_DAYS,
            fixture_status="NS",
            match_display_status="upcoming",
            goals_home=2,
            goals_away=1,
        ),
        local_fixture=_local(kickoff_at=KO_DAYS, status="NS", goals_home=2, goals_away=1),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert result["chronological_status_valid"] is False
    assert "future_fixture_has_final_score" in result["warnings"]
    assert result["status"] == "inconsistent"


def test_5_finished_vs_upcoming():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(status="NS", goals_home=None, goals_away=None),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
        now=NOW,
    )
    assert result["status_match"] is False
    assert "today_finished_local_upcoming" in result["warnings"]
    assert result["status"] == "inconsistent"


def test_6_status_coerente():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert result["status_match"] is True
    assert result["status"] == "consistent"


def test_7_score_coerente():
    result = build_fixture_identity_consistency(
        today_row=_today(goals_home=2, goals_away=1),
        local_fixture=_local(goals_home=2, goals_away=1),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert result["score_match"] is True


def test_8_provider_uguale_ma_kickoff_differente():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(api_fixture_id=1492291, kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert result["provider_match"] is True
    assert result["kickoff_match"] is False
    assert result["status"] == "inconsistent"


def test_9_false_positive_impedito_no_silent_realign():
    today = _today(kickoff=KO)
    local = _local(kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None)
    r1 = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert r1["status"] == "inconsistent"
    # second call same raw → still inconsistent (no mutation)
    r2 = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    assert r2["status"] == "inconsistent"
    assert today.kickoff == KO


def test_10_preview_bloccata():
    consistency = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
        now=NOW,
    )
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.1,
        quota_cecchino_x=3.4,
        quota_cecchino_2=3.6,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    preview = build_balance_v5_preview(balance_analysis=bal, identity_consistency=consistency)
    assert VERSION == "balance_v5_preview_v1_2"
    assert preview["status"] == "unavailable"
    assert all(p["index"] is None for p in preview["pillars"])
    assert preview["market_deviation"]["status"] == "unavailable"


def test_11_get_without_db_write():
    from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
    from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

    row = SimpleNamespace(
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
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
        scan_date=datetime(2026, 7, 16).date(),
        odds_snapshot_json={},
        stats_snapshot_json={},
        cecchino_output_json={
            "final": {
                "status": "available",
                "quota_1": 2.1,
                "quota_x": 3.4,
                "quota_2": 3.6,
                "prob_1": 0.42,
                "prob_x": 0.28,
                "prob_2": 0.30,
            },
            "data_quality": {"leakage_check": {"target_kickoff": KO_DAYS.isoformat()}},
            "signals_matrix": {},
        },
        warnings_json=[],
    )
    local = _local(kickoff_at=KO_DAYS, status="NS", goals_home=None, goals_away=None)
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

    with (
        patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"),
        patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={}),
        patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={}),
        patch(
            "app.services.cecchino.cecchino_today_service.build_expected_goal_engine_diagnostics_for_today_row",
            return_value=_xg(KO_DAYS),
        ),
        patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={}),
        patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail", return_value={"rows": []}),
        patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={}),
        patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={}),
    ):
        detail = get_today_fixture_detail(db, 9510)

    assert detail["kickoff"].startswith("2026-07-16")
    assert detail["fixture_identity_consistency"]["status"] == "inconsistent"
    assert "fixture_identity_minimal_fix_applied" not in (detail["warnings"] or [])
    db.commit.assert_not_called()
    assert row.kickoff == KO


def test_12_audit_endpoint_read_only():
    from app.services.cecchino.cecchino_fixture_identity_audit import build_fixture_identity_audit

    row = _today()
    row.provider_source = "api_football"
    row.scan_date = datetime(2026, 7, 16).date()
    row.eligibility_status = "eligible"
    row.country_name = "Brazil"
    row.league_name = "Serie A"
    row.cecchino_output_json = _output()
    row.warnings_json = []
    row.local_fixture_id = 562

    local = _local()
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        if "Fixture" in name and "Today" not in name:
            return local
        if "Team" in name:
            return SimpleNamespace(id=int(pk), api_team_id=int(pk), name="X")
        if "Competition" in name:
            return SimpleNamespace(id=10, name="Serie A", country="Brazil")
        return None

    db.get.side_effect = _get
    db.scalars.return_value.all.return_value = []

    with patch(
        "app.services.cecchino.cecchino_fixture_identity_audit.build_expected_goal_engine_diagnostics_for_today_row",
        return_value=_xg(),
    ):
        payload = build_fixture_identity_audit(db, 9510)

    assert payload["status"] == "ok"
    assert payload["read_only"] is True
    assert payload["today_fixture"]["kickoff"].startswith("2026-07-16")
    db.commit.assert_not_called()


def test_13_script_default_dry_run(capsys):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_fixture_identity_9510.py"
    spec = importlib.util.spec_from_file_location("audit_fixture_identity_9510", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "dry_run" in out or "skipped" in out


def test_14_no_fix_without_explicit_flag(capsys):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_fixture_identity_9510.py"
    spec = importlib.util.spec_from_file_location("audit_fixture_identity_9510", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main(["--apply-confirmed-fix"])
    assert code == 2


def test_15_formule_invariate():
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.1,
        quota_cecchino_x=3.4,
        quota_cecchino_2=3.6,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    preview = build_balance_v5_preview(
        balance_analysis=bal,
        identity_consistency={"status": "consistent"},
    )
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert f36["index"] == bal["f36"]["score"]
    assert preview["production_changes"] is False
    assert preview["version"] == "balance_v5_preview_v1_2"
    encoded = jsonable_encoder(preview)
    assert encoded["version"] == VERSION


def test_kickoff_entro_tolleranza_stesso_giorno():
    result = build_fixture_identity_consistency(
        today_row=_today(
            kickoff=KO_TOL,
            fixture_status="NS",
            match_display_status="upcoming",
            goals_home=None,
            goals_away=None,
            score_fulltime_home=None,
            score_fulltime_away=None,
        ),
        local_fixture=_local(
            kickoff_at=KO_TOL + timedelta(hours=2),
            status="NS",
            goals_home=None,
            goals_away=None,
        ),
        cecchino_output=_output(KO_TOL + timedelta(hours=2)),
        expected_goal_diagnostics=_xg(KO_TOL + timedelta(hours=2)),
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert result["kickoff_match"] is True
    assert result["status"] == "consistent"
