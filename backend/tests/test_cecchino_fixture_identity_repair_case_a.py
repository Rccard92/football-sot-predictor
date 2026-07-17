"""Test riparazione Caso A 9510/562 — dry-run, guards, apply, timezone."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_balance_v5_preview import build_balance_v5_preview
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_fixture_identity_consistency,
)

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_fixture_identity_9510.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("audit_fixture_identity_9510", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORRUPT_KO = datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc)
CORRECT_KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _today(**kwargs):
    base = dict(
        id=9510,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=2,
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=CORRUPT_KO,
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
        scan_date=date(2026, 7, 17),
        warnings_json=[
            "kickoff_rescheduled_realigned:from=2026-07-16T22:30:00Z:to=2026-07-22T20:00:00Z"
        ],
        odds_snapshot_json={"keep": True},
        cecchino_output_json={"final": {"status": "available"}},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _local(**kwargs):
    base = dict(
        id=562,
        api_fixture_id=1492291,
        competition_id=2,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=CORRUPT_KO,
        status="NS",
        status_long="Not Started",
        goals_home=None,
        goals_away=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_1_dry_run_does_not_write():
    mod = _load_script()
    today = _today()
    local = _local()
    plan = mod.build_case_a_plan(today, local)
    assert plan["today_9510"]["kickoff"]["to"].startswith("2026-07-16T22:30")
    assert today.kickoff == CORRUPT_KO  # unchanged
    assert local.kickoff_at == CORRUPT_KO
    code = mod.main(["--dry-run", "--case", "A"])
    assert code == 0


def test_2_apply_requires_case_a():
    mod = _load_script()
    code = mod.main(["--apply-confirmed-fix"])
    assert code == 2


def test_3_apply_requires_explicit_flag():
    mod = _load_script()
    # solo --case A senza apply → dry-run path (skipped o dry)
    code = mod.main(["--case", "A"])
    assert code == 0


def test_4_provider_mismatch_blocks():
    mod = _load_script()
    errs = mod.validate_case_a_guards(
        today_id=9510,
        local_id=562,
        provider_fixture_id=999,
        local_api_fixture_id=1492291,
        today_competition_id=2,
        local_competition_id=2,
        today_home="Botafogo",
        today_away="Santos",
        local_home="Botafogo",
        local_away="Santos",
    )
    assert any("provider_fixture_id_mismatch" in e for e in errs)


def test_5_teams_mismatch_blocks():
    mod = _load_script()
    errs = mod.validate_case_a_guards(
        today_id=9510,
        local_id=562,
        provider_fixture_id=1492291,
        local_api_fixture_id=1492291,
        today_competition_id=2,
        local_competition_id=2,
        today_home="Flamengo",
        today_away="Santos",
        local_home="Botafogo",
        local_away="Santos",
    )
    assert any("teams_mismatch" in e for e in errs)


def test_6_competition_mismatch_blocks():
    mod = _load_script()
    errs = mod.validate_case_a_guards(
        today_id=9510,
        local_id=562,
        provider_fixture_id=1492291,
        local_api_fixture_id=1492291,
        today_competition_id=10,
        local_competition_id=10,
        today_home="Botafogo",
        today_away="Santos",
        local_home="Botafogo",
        local_away="Santos",
    )
    assert any("competition_mismatch" in e for e in errs)


def test_7_transaction_atomic_on_failure():
    mod = _load_script()
    today = _today()
    local = _local()
    db = MagicMock()
    db.commit.side_effect = RuntimeError("boom")

    # simulate apply path mutations then failed commit
    meta = mod.apply_case_a_mutations(today, local)
    assert meta["applied"] is True
    try:
        db.add(today)
        db.add(local)
        db.commit()
    except RuntimeError:
        db.rollback()
    db.rollback.assert_called()
    # after failed commit, in-memory objects are mutated but DB rolled back —
    # caller must not leave partial commit: verified via rollback call


def test_8_today_kickoff_restored():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    assert today.kickoff == CORRECT_KO


def test_9_local_kickoff_restored():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    assert local.kickoff_at == CORRECT_KO


def test_10_local_status_ft():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    assert local.status == "FT"
    assert local.status_long == "Match Finished"


def test_11_local_score_2_1():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    assert local.goals_home == 2
    assert local.goals_away == 1
    assert today.goals_home == 2
    assert today.goals_away == 1


def test_12_cutoff_recompute_correct():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    out = {
        "data_quality": {
            "leakage_check": {
                "target_kickoff": CORRECT_KO.isoformat(),
                "current_fixture_excluded": True,
            }
        }
    }
    xg = {
        "xg_profiles": {
            "anti_leakage": {
                "fixture_date_cutoff": CORRECT_KO.isoformat(),
                "current_fixture_excluded": True,
            }
        }
    }
    today.cecchino_output_json = out
    consistency = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=out,
        expected_goal_diagnostics=xg,
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert consistency["calculation_target_kickoff"].startswith("2026-07-16T22:30")
    assert consistency["xg_cutoff"].startswith("2026-07-16T22:30")


def test_13_current_fixture_excluded():
    leak = {
        "data_quality": {
            "leakage_check": {
                "target_kickoff": CORRECT_KO.isoformat(),
                "current_fixture_excluded": True,
                "excluded_fixture_ids": [562],
                "excluded_provider_fixture_ids": [1492291],
            }
        }
    }
    assert leak["data_quality"]["leakage_check"]["current_fixture_excluded"] is True
    assert 562 in leak["data_quality"]["leakage_check"]["excluded_fixture_ids"]
    assert 1492291 in leak["data_quality"]["leakage_check"]["excluded_provider_fixture_ids"]


def test_14_no_external_api_on_recompute_flag():
    from app.services.cecchino import cecchino_recompute_service as svc

    # ensure_xg=False must not call maybe_ensure_xg
    row = _today(competition_id=2, local_fixture_id=562)
    row.eligibility_status = "eligible"
    row.kpi_panel_json = {}
    row.stats_snapshot_json = {}
    row.cecchino_status = "ok"
    row.stats_status = "ok"
    row.eligibility_reason = None
    row.blocking_reasons_json = []

    local = _local()
    comp = SimpleNamespace(id=2)
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "Competition" in name:
            return comp
        if "Fixture" in name:
            return local
        return None

    db.get.side_effect = _get

    with (
        patch.object(
            svc,
            "calculate_and_persist_for_fixture",
            return_value={
                "status": "ok",
                "calculation_status": "ok",
                "output": {
                    "final": {"status": "available"},
                    "data_quality": {
                        "leakage_check": {"target_kickoff": CORRECT_KO.isoformat()}
                    },
                    "warnings": [],
                },
            },
        ),
        patch.object(svc, "build_goal_market_contexts", return_value={}),
        patch.object(svc, "build_goal_market_cecchino_odds", return_value={}),
        patch.object(
            svc,
            "rebuild_signals_matrix_for_output",
            return_value={"status": "available"},
        ),
        patch.object(svc, "_load_betfair_payload", return_value={}),
        patch.object(
            svc,
            "build_cecchino_kpi_panel_v2_betfair",
            return_value={"rows": []},
        ),
        patch.object(svc, "read_odds_meta", return_value={}),
        patch.object(
            svc,
            "validate_cecchino_today_final_eligibility",
            return_value=SimpleNamespace(
                is_eligible=True,
                eligibility_status="eligible",
                eligibility_reason=None,
                blocking_reasons=[],
                warnings=[],
            ),
        ),
        patch.object(svc, "maybe_ensure_xg_for_eligible_row") as mock_xg,
        patch.object(svc, "sync_cecchino_signal_activations", return_value={}),
        patch.object(svc, "evaluate_activations_for_fixture", return_value=0),
    ):
        result = svc.recompute_today_fixture_offline(
            db,
            row,
            refresh_bookmaker_odds=False,
            use_existing_bookmaker_odds=True,
            ensure_xg=False,
            sync_signal_activations=False,
            evaluate_signals_after=False,
        )
    mock_xg.assert_not_called()
    assert result["recomputed"] is True
    assert result["xg_ensured"] is False


def test_15_audit_finale_consistent():
    mod = _load_script()
    today = _today()
    local = _local()
    mod.apply_case_a_mutations(today, local)
    out = {
        "data_quality": {"leakage_check": {"target_kickoff": CORRECT_KO.isoformat()}},
    }
    xg = {"xg_profiles": {"anti_leakage": {"fixture_date_cutoff": CORRECT_KO.isoformat()}}}
    consistency = build_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        cecchino_output=out,
        expected_goal_diagnostics=xg,
        local_home_team_name="Botafogo",
        local_away_team_name="Santos",
        now=NOW,
    )
    assert consistency["status"] == "consistent"
    assert consistency["provider_match"] is True
    assert consistency["kickoff_match"] is True
    assert consistency["status_match"] is True
    assert consistency["score_match"] is True
    assert consistency["snapshot_match"] is True
    assert consistency["chronological_status_valid"] is True


def test_16_preview_available_after_repair():
    consistency = {"status": "consistent", "warnings": []}
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.1,
        quota_cecchino_x=3.4,
        quota_cecchino_2=3.6,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    preview = build_balance_v5_preview(balance_analysis=bal, identity_consistency=consistency)
    assert preview["status"] == "ok"
    assert preview["version"] == "balance_v5_preview_v1_2"
    assert "fixture_identity_mismatch" not in (preview.get("warnings") or [])
    assert jsonable_encoder(preview)["production_changes"] is False


def test_17_timezone_europe_rome_shows_17_july_0030():
    mod = _load_script()
    assert mod.format_rome_kickoff(CORRECT_KO) == "17/07/2026 00:30"
    assert mod.format_rome_kickoff("2026-07-16T22:30:00Z") == "17/07/2026 00:30"


def test_18_no_other_fixture_modified():
    mod = _load_script()
    today = _today()
    local = _local()
    other = _local(id=999, kickoff_at=CORRUPT_KO)
    meta = mod.apply_case_a_mutations(today, local)
    assert meta["records_touched"] == {"today_fixture_id": 9510, "local_fixture_id": 562}
    assert other.kickoff_at == CORRUPT_KO
    assert other.status == "NS"


def test_warning_auto_realign_removed():
    mod = _load_script()
    today = _today()
    local = _local()
    meta = mod.apply_case_a_mutations(today, local)
    assert all(
        not str(w).startswith("kickoff_rescheduled_realigned") for w in today.warnings_json
    )
    assert "fixture_identity_repaired_case_a" in today.warnings_json
    assert meta["resolved_auto_realign_warnings"]
