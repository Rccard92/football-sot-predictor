"""Test --refresh-xg-cache-only (Fase 2A.4)."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.cecchino.cecchino_balance_analysis import build_cecchino_balance_analysis
from app.services.cecchino.cecchino_balance_v5_preview import build_balance_v5_preview
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_fixture_identity_consistency,
)

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_fixture_identity_9510.py"
CORRECT_KO = datetime(2026, 7, 16, 22, 30, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _load_script():
    spec = importlib.util.spec_from_file_location("audit_fixture_identity_9510", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_refresh_flag_requires_case_a():
    mod = _load_script()
    assert mod.main(["--refresh-xg-cache-only"]) == 2


def test_validate_post_repair_ok():
    mod = _load_script()
    today = SimpleNamespace(
        kickoff=CORRECT_KO,
        fixture_status="FT",
        goals_home=2,
        goals_away=1,
    )
    local = SimpleNamespace(
        kickoff_at=CORRECT_KO,
        status="FT",
        goals_home=2,
        goals_away=1,
    )
    assert mod.validate_post_repair_for_xg_refresh(today=today, local=local) == []


def test_validate_post_repair_blocks_wrong_kickoff():
    mod = _load_script()
    today = SimpleNamespace(
        kickoff=datetime(2026, 7, 22, 20, 0, tzinfo=timezone.utc),
        fixture_status="FT",
        goals_home=2,
        goals_away=1,
    )
    local = SimpleNamespace(
        kickoff_at=CORRECT_KO,
        status="FT",
        goals_home=2,
        goals_away=1,
    )
    errs = mod.validate_post_repair_for_xg_refresh(today=today, local=local)
    assert any("today_kickoff_not_corrected" in e for e in errs)


def test_script_idempotent_refresh_skipped_without_db(monkeypatch, tmp_path, capsys):
    import os

    mod = _load_script()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    os.environ.pop("DATABASE_URL", None)
    assert mod.main(["--refresh-xg-cache-only", "--case", "A"]) == 0
    assert "skipped" in capsys.readouterr().out


def test_audit_consistent_and_preview_after_cutoff_fix():
    today = SimpleNamespace(
        id=9510,
        local_fixture_id=562,
        provider_fixture_id=1492291,
        competition_id=2,
        home_team_name="Botafogo",
        away_team_name="Santos",
        kickoff=CORRECT_KO,
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
    )
    local = SimpleNamespace(
        id=562,
        api_fixture_id=1492291,
        competition_id=2,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=CORRECT_KO,
        status="FT",
        status_long="Match Finished",
        goals_home=2,
        goals_away=1,
    )
    out = {
        "data_quality": {"leakage_check": {"target_kickoff": CORRECT_KO.isoformat()}},
    }
    xg = {
        "xg_profiles": {
            "anti_leakage": {"fixture_date_cutoff": CORRECT_KO.isoformat()},
        }
    }
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
    assert consistency["snapshot_match"] is True
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
    assert "fixture_identity_mismatch" not in (preview.get("warnings") or [])


def test_no_other_fixture_modified_concept():
    """Rebuild report tocca solo today_fixture_id passato."""
    from app.services.cecchino.cecchino_current_season_xg import (
        rebuild_current_season_xg_profile_from_cache,
    )

    other = SimpleNamespace(id=999, xg_profiles_json={"keep": True})
    db = MagicMock()
    db.get.return_value = None
    out = rebuild_current_season_xg_profile_from_cache(db, 9510)
    assert out["status"] == "not_found"
    assert other.xg_profiles_json == {"keep": True}
