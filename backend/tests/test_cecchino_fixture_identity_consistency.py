"""Test fixture identity consistency — Fase 2A.2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.encoders import jsonable_encoder

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_balance_v5_preview import (
    VERSION,
    build_balance_v5_preview,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    apply_minimal_kickoff_realignment,
    build_fixture_identity_consistency,
    flag_stale_calculation_snapshot,
)


KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
KO_TOL = datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc)  # −4h, stesso giorno
KO_OVER = KO + timedelta(hours=7)
KO_DAYS = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)


def _today(**kwargs):
    base = dict(
        id=9510,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=10,
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=KO,
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
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _output(target: datetime | None = KO) -> dict:
    if target is None:
        return {}
    return {
        "data_quality": {
            "leakage_check": {"target_kickoff": target.isoformat()},
        }
    }


def _xg(cutoff: datetime | None = KO) -> dict:
    if cutoff is None:
        return {}
    return {
        "xg_profiles": {
            "anti_leakage": {"fixture_date_cutoff": cutoff.isoformat()},
        }
    }


def test_1_fixture_coerente():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
    )
    assert result["status"] == "consistent"
    assert result["provider_match"] is True
    assert result["kickoff_match"] is True
    assert result["snapshot_match"] is True
    assert result["warnings"] == []


def test_2_provider_fixture_id_differente():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(api_fixture_id=999),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
    )
    assert result["status"] == "inconsistent"
    assert result["provider_match"] is False
    assert "provider_fixture_id_mismatch" in result["warnings"]


def test_3_local_fixture_id_missing_unavailable():
    result = build_fixture_identity_consistency(
        today_row=_today(local_fixture_id=None),
        local_fixture=None,
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
    )
    assert result["status"] == "unavailable"
    assert "missing_local_fixture" in result["warnings"]


def test_4_squadre_differenti():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
        local_home_team_name="Flamengo",
        local_away_team_name="Santos",
    )
    assert result["status"] == "inconsistent"
    assert result["teams_match"] is False
    assert "teams_mismatch" in result["warnings"]


def test_5_competizione_differente():
    result = build_fixture_identity_consistency(
        today_row=_today(competition_id=10),
        local_fixture=_local(competition_id=99),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
    )
    assert result["status"] == "inconsistent"
    assert result["competition_match"] is False
    assert "competition_mismatch" in result["warnings"]


def test_6_kickoff_entro_tolleranza():
    result = build_fixture_identity_consistency(
        today_row=_today(kickoff=KO),
        local_fixture=_local(kickoff_at=KO_TOL),
        cecchino_output=_output(KO_TOL),
        expected_goal_diagnostics=_xg(KO_TOL),
    )
    assert result["kickoff_match"] is True
    assert result["status"] == "consistent"


def test_7_kickoff_oltre_tolleranza():
    result = build_fixture_identity_consistency(
        today_row=_today(kickoff=KO),
        local_fixture=_local(kickoff_at=KO_OVER),
        cecchino_output=_output(KO_OVER),
        expected_goal_diagnostics=_xg(KO_OVER),
    )
    assert result["kickoff_match"] is False
    assert result["status"] == "inconsistent"
    assert "fixture_kickoff_mismatch" in result["warnings"]


def test_8_target_kickoff_diverso_di_piu_giorni():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(),
    )
    assert result["status"] == "inconsistent"
    assert result["snapshot_match"] is False
    assert "calculation_target_kickoff_mismatch" in result["warnings"]


def test_9_xg_cutoff_differente():
    result = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(KO_DAYS),
    )
    assert result["status"] == "inconsistent"
    assert "xg_cutoff_mismatch" in result["warnings"]


def test_10_preview_disponibile_se_consistent():
    consistency = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
    )
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
        identity_consistency=consistency,
    )
    assert preview["status"] == "ok"
    assert preview["version"] == VERSION
    assert VERSION == "balance_v5_preview_v1_1"
    assert all(p["status"] != "unavailable" or p["key"] == "draw_credibility" for p in preview["pillars"])


def test_11_preview_bloccata_se_inconsistent():
    consistency = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(api_fixture_id=1),
        cecchino_output=_output(),
        expected_goal_diagnostics=_xg(),
    )
    assert consistency["status"] == "inconsistent"
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
        identity_consistency=consistency,
    )
    assert preview["status"] == "unavailable"
    assert "fixture_identity_mismatch" in preview["warnings"]
    assert all(p["status"] == "unavailable" for p in preview["pillars"])
    assert all(p["index"] is None for p in preview["pillars"])


def test_12_market_bloccato_se_inconsistent():
    consistency = {"status": "inconsistent", "warnings": ["fixture_kickoff_mismatch"]}
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
        identity_consistency=consistency,
    )
    market = preview["market_deviation"]
    assert market["status"] == "unavailable"
    assert market["index"] is None
    assert market["pairs"] == []
    assert "fixture_identity_mismatch" in market["warnings"]


def test_15_formule_invariate_su_preview_ok():
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.1,
        quota_cecchino_x=3.4,
        quota_cecchino_2=3.6,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    preview = build_balance_v5_preview(balance_analysis=bal, identity_consistency={"status": "consistent"})
    f36 = next(p for p in preview["pillars"] if p["key"] == "f36")
    assert f36["index"] == bal["f36"]["score"]
    assert preview["production_changes"] is False


def test_16_response_serializzabile():
    consistency = build_fixture_identity_consistency(
        today_row=_today(),
        local_fixture=_local(kickoff_at=KO_DAYS),
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
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
    encoded = jsonable_encoder({"fixture_identity_consistency": consistency, "balance_v5_preview": preview})
    assert encoded["fixture_identity_consistency"]["status"] == "inconsistent"
    assert encoded["balance_v5_preview"]["version"] == "balance_v5_preview_v1_1"


def test_kickoff_realignment_minimal():
    today = _today(kickoff=KO, warnings_json=[])
    local = _local(kickoff_at=KO_DAYS)
    consistency = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
    )
    assert consistency["provider_match"] is True
    assert consistency["kickoff_match"] is False
    meta = apply_minimal_kickoff_realignment(today, local, consistency)
    assert meta["applied"] is True
    assert today.kickoff == KO_DAYS
    assert any("kickoff_rescheduled_realigned" in w for w in today.warnings_json)


def test_stale_snapshot_flag():
    today = _today(warnings_json=[])
    local = _local()
    consistency = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=_output(KO_DAYS),
        expected_goal_diagnostics=_xg(KO_DAYS),
    )
    assert consistency["kickoff_match"] is True
    assert consistency["snapshot_match"] is False
    meta = flag_stale_calculation_snapshot(today, consistency)
    assert meta["applied"] is True
    assert "stale_calculation_snapshot_requires_recalc" in today.warnings_json
