"""Test preflight read-only replay Acquistabilità V3 (STEP 3A)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight import (
    FAIR_SUM_TOLERANCE,
    FORBIDDEN_FORMULA_FIELDS,
    INTEGRITY_MODE_FROZEN,
    INTEGRITY_MODE_PROSPECTIVE,
    INTEGRITY_POLICY_VERSION,
    PREFLIGHT_SCHEMA_VERSION,
    PROBE_SNAPSHOT_LIMIT,
    V3_MARKET_ORDER,
    adapter_contract_payload,
    build_adapter_panel_row,
    classify_performance,
    classify_quote_quality,
    classify_score_replay,
    clear_purchasability_v3_replay_preflight_cache,
    evaluate_historical_integrity_policy,
    run_purchasability_v3_replay_preflight,
)


def _utcnow() -> datetime:
    return datetime(2021, 9, 15, 15, 0, tzinfo=timezone.utc)


def _market(
    *,
    mid: int = 1,
    snap_id: int = 1,
    market_key: str = "HOME",
    won: bool | None = True,
    real: bool = True,
    derived: bool = False,
    quota_book: float | None = 2.0,
    quota_cecchino: float | None = 2.2,
    prob_cecchino: float = 0.45,
    prob_book_fair: float | None = 0.40,
    edge_pct: float | None = 10.0,
    vantaggio_prob: float | None = 0.05,
    derivation_method: str | None = None,
    profit_real: float | None = 1.0,
    profit_synth: float | None = None,
    quote_source_type: str = "bet365_closing",
    evaluation_status: str = "won",
):
    if derived and not real and derivation_method is None:
        derivation_method = "normalized_fair_probability_from_bet365_1x2"
    if derived and not real:
        profit_real = None
        if profit_synth is None and won is not None:
            profit_synth = 1.0 if won else -1.0
        if quote_source_type == "bet365_closing":
            quote_source_type = "derived_from_bet365_1x2_closing"
    return SimpleNamespace(
        id=mid,
        run_id=1,
        match_snapshot_id=snap_id,
        lab_match_id=100 + snap_id,
        market_key=market_key,
        market_label=market_key,
        period="FT",
        line=2.5 if "2_5" in market_key else None,
        quota_cecchino=Decimal(str(quota_cecchino)) if quota_cecchino is not None else None,
        prob_cecchino=Decimal(str(prob_cecchino)),
        quota_book=Decimal(str(quota_book)) if quota_book is not None else None,
        prob_book_raw=Decimal("0.42"),
        prob_book_fair=Decimal(str(prob_book_fair)) if prob_book_fair is not None else None,
        quote_source_type=quote_source_type,
        is_real_book_quote=real,
        is_derived_quote=derived,
        derivation_method=derivation_method,
        edge_pct=Decimal(str(edge_pct)) if edge_pct is not None else None,
        vantaggio_prob=Decimal(str(vantaggio_prob)) if vantaggio_prob is not None else None,
        rating=70,
        signal_active=False,
        signal_sources_json={},
        evaluation_status=evaluation_status,
        won=won,
        profit_1u_real=Decimal(str(profit_real)) if profit_real is not None else None,
        profit_1u_synthetic=Decimal(str(profit_synth)) if profit_synth is not None else None,
        result_reason="ft",
        profit_category="actual_bet365" if real else ("synthetic_derived" if derived else "no_book_quote"),
    )


def _snap(
    *,
    sid: int = 1,
    elig: str = "eligible_core",
    reason: str | None = None,
    comp: str = "Serie A",
    kickoff: datetime | None = None,
    locked_at: datetime | None = None,
    sha: str | None = "abc123hash",
    chronological_order: int | None = None,
):
    kickoff = kickoff or _utcnow()
    if locked_at is None and sha:
        locked_at = kickoff - timedelta(hours=2)
    return SimpleNamespace(
        id=sid,
        run_id=1,
        dataset_id=1,
        lab_match_id=100 + sid,
        competition_name=comp,
        season_label="2021/2022",
        kickoff_at=kickoff,
        home_team="Home",
        away_team="Away",
        chronological_order=chronological_order if chronological_order is not None else sid,
        historical_eligibility_status=elig,
        historical_eligibility_reason=reason,
        blocking_reasons_json=[],
        input_snapshot_json={},
        cecchino_output_json={},
        historical_kpi_json={"rows": []},
        signals_json={},
        balance_v5_json={},
        goal_intensity_compatibility_json={},
        purchasability_compatibility_json={},
        quote_sources_json={"bookmaker": "Bet365"},
        module_availability_json={},
        pre_match_payload_sha256=sha,
        pre_match_locked_at=locked_at,
        result_json={"ft_result": "H", "ht_result": "D"},
        result_attached_at=kickoff,
        settlement_status="settled",
        settlement_summary_json={"won": 1},
        warnings_json=[],
        error_json=None,
    )


def _run(
    *,
    status: str = "completed",
    run_id: int = 1,
    partial: bool = False,
):
    return SimpleNamespace(
        id=run_id,
        season_label="2021/2022",
        status=status,
        scan_version="cecchino_lab_historical_scan_v3",
        requested_at=_utcnow(),
        started_at=_utcnow(),
        completed_at=_utcnow() if status.startswith("completed") else None,
        current_dataset_id=None,
        current_match_id=None,
        current_competition=None,
        matches_total=10,
        matches_processed=10,
        matches_eligible_core=2,
        matches_excluded=1,
        matches_error=0,
        progress_pct=Decimal("100.0"),
        quote_policy_json={},
        module_policy_json={
            "run_scope": "pilot" if partial else "full",
            "is_partial_run": partial,
            "not_full_season_report": partial,
        },
        preflight_json={"status": "ready"},
        summary_json={},
        error_json={"message": "boom"} if status == "failed" else None,
        source_git_commit="adcf63db",
        source_git_commit_source="git",
        source_revision_status="resolved",
        cancel_requested=False,
        updated_at=_utcnow(),
        created_at=_utcnow(),
    )


def _v3_family_markets(snap_id: int, *, mid_start: int = 1) -> list:
    specs = [
        ("HOME", 0.45, True, False),
        ("DRAW", 0.30, True, False),
        ("AWAY", 0.25, True, False),
        ("OVER_2_5", 0.55, True, False),
        ("UNDER_2_5", 0.45, True, False),
        ("ONE_X", 0.75, False, True),
        ("X_TWO", 0.55, False, True),
        ("ONE_TWO", 0.70, False, True),
    ]
    out = []
    for i, (mk, fair, real, derived) in enumerate(specs):
        out.append(
            _market(
                mid=mid_start + i,
                snap_id=snap_id,
                market_key=mk,
                real=real,
                derived=derived,
                prob_book_fair=fair,
                quota_book=1.0 / fair if fair else 2.0,
                won=True,
                profit_real=0.9 if real else None,
                profit_synth=0.8 if derived else None,
            )
        )
    return out


def _db_with(run, snaps, markets):
    db = MagicMock()
    db.new = set()
    db.dirty = set()
    db.deleted = set()

    def get_side_effect(model, pk):
        name = getattr(model, "__name__", str(model))
        if "ScanRun" in name:
            return run if run is not None and int(pk) == int(run.id) else None
        return None

    db.get.side_effect = get_side_effect

    v3_keys = set(V3_MARKET_ORDER)

    def _supported_markets():
        return [m for m in markets if str(m.market_key) in v3_keys]

    def _unsupported_markets():
        return [m for m in markets if str(m.market_key) not in v3_keys]

    def _eligible_snaps():
        return [s for s in snaps if s.historical_eligibility_status == "eligible_core"]

    def _excluded_snaps():
        return [s for s in snaps if s.historical_eligibility_status != "eligible_core"]

    def _stmt_meta(stmt):
        text = ""
        params: dict = {}
        try:
            text = str(stmt).lower()
        except Exception:
            text = repr(stmt).lower()
        try:
            compiled = stmt.compile()
            params = dict(getattr(compiled, "params", {}) or {})
        except Exception:
            params = {}
        param_vals = {str(v) for v in params.values()}
        return text, params, param_vals

    def _from_market(text: str) -> bool:
        return "historical_market_result" in text or "market_results" in text

    def _from_snap(text: str) -> bool:
        return "historical_match_snapshot" in text or "match_snapshots" in text

    def _is_count(text: str) -> bool:
        return "count(" in text

    def execute_side_effect(stmt):
        from collections import Counter

        result = MagicMock()
        text, params, param_vals = _stmt_meta(stmt)
        has_eligible_core = "eligible_core" in param_vals
        has_group = "group by" in text
        has_notin = "not in" in text or "notin" in text

        if _is_count(text) and _from_market(text):
            n = len(_unsupported_markets()) if has_notin else len(_supported_markets())
            result.scalar.return_value = n
            result.all.return_value = [(n,)]
            return result

        if _is_count(text) and _from_snap(text):
            if has_group:
                if "eligibility_reason" in text:
                    c = Counter(
                        (s.historical_eligibility_reason or "unknown")
                        for s in _excluded_snaps()
                    )
                    result.all.return_value = list(c.items())
                    result.scalar.return_value = len(_excluded_snaps())
                    return result
                if "competition_name" in text:
                    c = Counter(s.competition_name for s in _eligible_snaps())
                    result.all.return_value = list(c.items())
                    result.scalar.return_value = len(_eligible_snaps())
                    return result
            n = len(_eligible_snaps()) if has_eligible_core else len(snaps)
            result.scalar.return_value = n
            result.all.return_value = [(n,)]
            return result

        if has_group and _from_snap(text):
            if "eligibility_reason" in text:
                c = Counter(
                    (s.historical_eligibility_reason or "unknown") for s in _excluded_snaps()
                )
                result.all.return_value = list(c.items())
                return result
            if "competition_name" in text:
                c = Counter(s.competition_name for s in _eligible_snaps())
                result.all.return_value = list(c.items())
                return result

        if _from_snap(text):
            ordered = sorted(
                _eligible_snaps(),
                key=lambda s: (
                    s.kickoff_at,
                    int(s.chronological_order or 0),
                    int(s.id),
                ),
            )
            lean = (
                "competition_name" in text
                or "pre_match_payload_sha256" in text
                or "lab_match_id" in text
            )
            if lean:
                result.all.return_value = ordered
            else:
                # Probe id selection — respect LIMIT if present in statement
                ids = [int(s.id) for s in ordered]
                if "desc" in text and "limit" in text:
                    ids = list(reversed(ids))[:10]
                    result.all.return_value = [(i,) for i in ids]
                elif "offset" in text:
                    mid_start = max(0, (len(ordered) // 2) - 5)
                    result.all.return_value = [(i,) for i in ids[mid_start : mid_start + 10]]
                elif "limit" in text:
                    result.all.return_value = [(i,) for i in ids[:10]]
                else:
                    result.all.return_value = [(i,) for i in ids]
            return result

        if _from_market(text):
            rows_sorted = sorted(
                _supported_markets(),
                key=lambda m: (int(m.match_snapshot_id), str(m.market_key), int(m.id)),
            )
            snap_ids = {int(s.id) for s in snaps}
            run_id_val = int(run.id) if run is not None else None
            int_params = [int(v) for v in params.values() if isinstance(v, int)]
            snap_filter = [i for i in int_params if i != run_id_val and i in snap_ids]
            # Expanded IN params may appear as many ints; also collect from list values
            for v in params.values():
                if isinstance(v, (list, tuple, set)):
                    for x in v:
                        if isinstance(x, int) and x in snap_ids and x != run_id_val:
                            snap_filter.append(x)
            if snap_filter:
                filt = set(snap_filter)
                rows_sorted = [m for m in rows_sorted if int(m.match_snapshot_id) in filt]

            def yield_per(_n):
                for m in rows_sorted:
                    yield m

            result.yield_per = yield_per
            result.__iter__ = lambda self=result: iter(rows_sorted)
            result.all.return_value = rows_sorted
            return result

        result.scalar.return_value = 0
        result.all.return_value = []
        result.yield_per = lambda _n: iter([])
        return result

    db.execute.side_effect = execute_side_effect

    def scalars_side_effect(stmt):
        result = MagicMock()
        result.all.side_effect = AssertionError(
            "scalars().all() non consentito nel preflight 3A.1"
        )
        return result

    db.scalars.side_effect = scalars_side_effect
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    return db


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_purchasability_v3_replay_preflight_cache()
    yield
    clear_purchasability_v3_replay_preflight_cache()


def _full_universe():
    snaps = [
        _snap(sid=1, elig="eligible_core", comp="Serie A", chronological_order=1),
        _snap(
            sid=2,
            elig="eligible_core",
            comp="Premier League",
            kickoff=_utcnow() + timedelta(days=30),
            chronological_order=2,
        ),
        _snap(
            sid=3,
            elig="excluded_insufficient_history",
            reason="insufficient_history",
            comp="Serie A",
            chronological_order=3,
        ),
    ]
    markets = _v3_family_markets(1, mid_start=1) + _v3_family_markets(2, mid_start=100)
    markets.append(
        _market(mid=200, snap_id=1, market_key="OVER_1_5", real=False, derived=False, quota_book=None)
    )
    return snaps, markets


def test_quote_real_derived_unavailable_inconsistent():
    real = _market(real=True, derived=False, quota_book=2.0)
    assert classify_quote_quality(real)[0] == "real"

    derived = _market(real=False, derived=True, quota_book=1.8)
    assert classify_quote_quality(derived)[0] == "derived"

    unavail = _market(real=False, derived=False, quota_book=None)
    assert classify_quote_quality(unavail)[0] == "unavailable"

    bad = _market(real=True, derived=True, quota_book=2.0)
    assert classify_quote_quality(bad)[0] == "inconsistent"

    real_no_quota = _market(real=True, derived=False, quota_book=None)
    assert classify_quote_quality(real_no_quota)[0] == "inconsistent"


def test_performance_statuses():
    real = _market(real=True, derived=False, profit_real=1.0, won=True)
    assert classify_performance(real, "real") == "real_profit_ready"

    derived = _market(real=False, derived=True, profit_synth=1.0, won=True)
    assert classify_performance(derived, "derived") == "synthetic_profit_ready"

    missing = _market(real=True, derived=False, profit_real=None, profit_synth=None, won=True)
    assert classify_performance(missing, "real") == "result_available_but_profit_missing"


def test_adapter_contract_units():
    c = adapter_contract_payload()
    assert c["unit_conversions"]["edge_pct"]["stored"] == "percentage_points"
    assert c["unit_conversions"]["vantaggio_prob"]["stored"] == "fraction_typical_lab"
    assert c["unit_conversions"]["prob_cecchino"]["stored"] == "fraction_0_1"
    assert "betfair_panel" in c["today_default_to_avoid"]
    assert "kpi_recalculation" in c["forbidden_recalculations"]


def test_adapter_panel_row_no_forbidden_fields():
    m = _market(derived=True)
    row = build_adapter_panel_row(m)
    for f in FORBIDDEN_FORMULA_FIELDS:
        assert f not in row
    assert "betfair_panel" not in str(row.get("quote_source"))
    assert row["derived_quote"] is True


def test_classify_exact_and_gate_only_and_missing():
    by_mk = {m.market_key: m for m in _v3_family_markets(1)}
    m = by_mk["HOME"]
    status, _ = classify_score_replay(
        market_key="HOME",
        m=m,
        by_mk=by_mk,
        integrity="ok",
        integrity_reasons=[],
        duplicate=False,
    )
    assert status == "exact_replay_ready"

    status3, _ = classify_score_replay(
        market_key="HOME",
        m=_market(edge_pct=None, vantaggio_prob=None),
        by_mk={},
        integrity="ok",
        integrity_reasons=[],
        duplicate=False,
    )
    assert status3 == "not_replayable_missing_inputs"

    status4, _ = classify_score_replay(
        market_key="OVER_1_5",
        m=_market(market_key="OVER_1_5"),
        by_mk={},
        integrity="ok",
        integrity_reasons=[],
        duplicate=False,
    )
    assert status4 == "unsupported_market"

    status5, _ = classify_score_replay(
        market_key="HOME",
        m=m,
        by_mk=by_mk,
        integrity="invalid",
        integrity_reasons=["malformed_pre_match_hash"],
        duplicate=False,
    )
    assert status5 == "invalid_integrity"

    status6, _ = classify_score_replay(
        market_key="HOME",
        m=m,
        by_mk=by_mk,
        integrity="ok",
        integrity_reasons=[],
        duplicate=True,
    )
    assert status6 == "ambiguous_market_join"


def test_run_not_found():
    db = _db_with(None, [], [])
    with pytest.raises(CecchinoLabImportError) as exc:
        run_purchasability_v3_replay_preflight(db, 999)
    assert exc.value.status_code == 404


def test_run_active_blocked():
    run = _run(status="running")
    db = _db_with(run, [], [])
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "run_active" for b in out["blockers"])
    assert out["replay_recommendation"]["can_replay_without_full_scan"] is False


def test_run_failed_blocked():
    run = _run(status="failed")
    db = _db_with(run, [], [])
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "run_terminal_incompatible" for b in out["blockers"])


def test_run_cancelled_blocked():
    run = _run(status="cancelled")
    db = _db_with(run, [], [])
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"


def test_run_complete_ready_or_warnings():
    snaps, markets = _full_universe()
    run = _run(status="completed")
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["schema_version"] == PREFLIGHT_SCHEMA_VERSION
    assert out["status"] in ("ready", "ready_with_warnings")
    assert out["source_integrity"]["snapshots_eligible_core"] == 2
    assert out["source_integrity"]["snapshots_excluded"] == 1
    assert out["workload"]["supported_markets_per_snapshot"] == 8
    assert out["workload"]["theoretical_evaluations"] == 16
    assert out["workload"]["exact_replay_ready"] >= 1
    assert out["replay_recommendation"]["can_replay_without_full_scan"] is True
    assert out["replay_recommendation"]["requires_model_recalculation"] is False
    assert out["bookmakers"]["historical"] == "Bet365"
    assert out["bookmakers"]["today_operational"] == "Betfair"
    assert out["anti_leakage"]["result_fields_passed_to_formula"] is False
    assert "result_json" in out["anti_leakage"]["forbidden_formula_fields"]
    assert out["probe"]["probe_snapshot_limit"] == PROBE_SNAPSHOT_LIMIT
    assert out["probe"]["probe_is_diagnostic_only"] is True
    assert out["probe"]["probe_not_a_backtest"] is True
    assert out["probe"].get("skipped") is True
    assert out["probe"].get("reason") == "not_requested"
    assert out["resource_profile"]["full_orm_entities_loaded"] is False
    assert out["resource_profile"]["strategy"] == "sql_aggregates_and_streaming"


def test_partial_run_warning():
    snaps, markets = _full_universe()
    run = _run(status="completed", partial=True)
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "ready_with_warnings"
    assert any(w["code"] == "partial_run" for w in out["warnings"])
    assert out["run"]["is_partial_run"] is True


def test_only_eligible_core_in_universe():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["source_integrity"]["snapshots_eligible_core"] == 2
    assert out["source_integrity"]["exclusions_by_reason"]["insufficient_history"] == 1
    assert out["by_market"]["HOME"]["eligible_rows"] == 2


def test_eight_markets_and_unsupported_excluded():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    for mk in V3_MARKET_ORDER:
        assert mk in out["by_market"]
    assert "OVER_1_5" not in out["by_market"]
    assert out["workload"]["unsupported_market_rows"] >= 1


def test_families_present():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["by_family"]["MATCH_WINNER_FT"]["snapshots_with_full_family"] == 2
    assert out["by_family"]["GOALS_FT_2_5"]["snapshots_with_full_family"] == 2
    assert out["by_family"]["DOUBLE_CHANCE"]["snapshots_with_full_family"] == 2


def test_integrity_hash_lock_before_kickoff():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["source_integrity"]["with_payload_hash"] == 2
    assert out["source_integrity"]["with_historical_freeze_lock"] == 2
    assert out["source_integrity"]["with_pre_match_hash"] == 2
    assert out["source_integrity"]["with_pre_match_lock"] == 2
    # Fixture default: lock < kickoff → prospective
    assert out["source_integrity"]["chronological_lock_check_passed"] == 2
    assert out["source_integrity"]["lock_before_kickoff"] == 2
    assert out["integrity_policy_version"] == INTEGRITY_POLICY_VERSION
    assert out["schema_version"] == PREFLIGHT_SCHEMA_VERSION


def test_lock_after_kickoff_historical_reconstruction_not_blocking():
    kick = _utcnow()
    snap = _snap(sid=1, locked_at=kick + timedelta(hours=1), kickoff=kick)
    markets = _v3_family_markets(1)
    run = _run()
    db = _db_with(run, [snap], markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["source_integrity"]["historical_reconstruction_verified"] == 1
    assert out["source_integrity"]["chronological_lock_check_not_applicable"] == 1
    assert out["workload"]["invalid_integrity"] == 0
    assert out["workload"]["exact_replay_ready"] + out["workload"]["ready_with_warning"] >= 1
    assert out["status"] in ("ready", "ready_with_warnings")
    policy = evaluate_historical_integrity_policy(snap)
    assert policy["integrity_mode"] == INTEGRITY_MODE_FROZEN
    assert policy["chronological_lock_check"] == "not_applicable"
    assert policy["captured_before_kickoff"] is False


def test_prospective_lock_before_kickoff_valid():
    kick = _utcnow()
    snap = _snap(sid=1, locked_at=kick - timedelta(hours=2), kickoff=kick)
    policy = evaluate_historical_integrity_policy(snap)
    assert policy["integrity_mode"] == INTEGRITY_MODE_PROSPECTIVE
    assert policy["chronological_lock_check"] == "passed"
    assert policy["captured_before_kickoff"] is True


def test_historical_incomplete_missing_hash():
    kick = _utcnow()
    snap = _snap(sid=1, locked_at=kick + timedelta(hours=1), kickoff=kick, sha=None)
    policy = evaluate_historical_integrity_policy(snap)
    assert policy["integrity_mode"] == "historical_reconstruction_incomplete"
    assert policy["integrity_gate"] == "incomplete"

def test_duplicate_market_key_blocker():
    snap = _snap(sid=1)
    markets = _v3_family_markets(1)
    markets.append(_market(mid=999, snap_id=1, market_key="HOME"))
    run = _run()
    db = _db_with(run, [snap], markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "duplicate_market_keys" for b in out["blockers"])
    assert out["workload"]["ambiguous_market_join"] >= 1


def test_fair_1x2_and_goals_tolerance():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["fair_probability_checks"]["fair_sum_tolerance"] == FAIR_SUM_TOLERANCE
    assert out["fair_probability_checks"]["fair_group_valid"] >= 2


def test_fair_out_of_tolerance():
    snap = _snap(sid=1)
    markets = _v3_family_markets(1)
    for m in markets:
        if m.market_key == "HOME":
            m.prob_book_fair = Decimal("0.90")
    run = _run()
    db = _db_with(run, [snap], markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["fair_probability_checks"]["fair_group_out_of_tolerance"] >= 1


def test_quote_quality_counts():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["quote_quality"]["real"] >= 1
    assert out["quote_quality"]["derived"] >= 1


def test_performance_coverage():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["performance_coverage"]["real_profit_ready"] >= 1
    assert out["performance_coverage"]["synthetic_profit_ready"] >= 1


def test_session_clean_no_writes():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    run_purchasability_v3_replay_preflight(db, 1)
    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.add.assert_not_called()
    db.delete.assert_not_called()
    assert len(db.new) == 0
    assert len(db.dirty) == 0
    assert len(db.deleted) == 0


def test_probe_max_30_deterministic():
    snaps = []
    markets = []
    base = _utcnow()
    for i in range(40):
        snaps.append(
            _snap(
                sid=i + 1,
                kickoff=base + timedelta(days=i),
                chronological_order=i + 1,
            )
        )
        markets.extend(_v3_family_markets(i + 1, mid_start=i * 20 + 1))
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert out["probe"]["snapshots_probed"] <= PROBE_SNAPSHOT_LIMIT
    ids = out["probe"]["probe_selected_snapshot_ids"]
    assert len(ids) <= PROBE_SNAPSHOT_LIMIT
    clear_purchasability_v3_replay_preflight_cache()
    out2 = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert out2["probe"]["probe_selected_snapshot_ids"] == ids


def test_cache_and_clear():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out1 = run_purchasability_v3_replay_preflight(db, 1)
    assert out1["cache_hit"] is False
    out2 = run_purchasability_v3_replay_preflight(db, 1)
    assert out2["cache_hit"] is True
    clear_purchasability_v3_replay_preflight_cache()
    out3 = run_purchasability_v3_replay_preflight(db, 1)
    assert out3["cache_hit"] is False


def test_issue_examples_capped():
    snaps, markets = _full_universe()
    for m in markets:
        if m.market_key == "DRAW" and m.match_snapshot_id == 1:
            m.edge_pct = None
            m.vantaggio_prob = None
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    for examples in out["issue_examples"].values():
        assert len(examples) <= 20
    assert len(out["problematic_snapshots"]) <= 20


def test_zero_eligible_blocked():
    snaps = [_snap(sid=1, elig="excluded_insufficient_history", reason="insufficient_history")]
    run = _run()
    db = _db_with(run, snaps, [])
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "zero_eligible_core" for b in out["blockers"])


def test_endpoint_404_and_200():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")

    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)

    def override():
        return db

    app.dependency_overrides[get_db] = override
    client = TestClient(app)

    db2 = _db_with(None, [], [])

    def override404():
        return db2

    app.dependency_overrides[get_db] = override404
    r404 = client.get("/api/cecchino-lab/historical-scans/999/purchasability-v3-replay/preflight")
    assert r404.status_code == 404

    app.dependency_overrides[get_db] = override
    clear_purchasability_v3_replay_preflight_cache()
    r = client.get("/api/cecchino-lab/historical-scans/1/purchasability-v3-replay/preflight")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ready", "ready_with_warnings")

    run_active = _run(status="running")
    db_active = _db_with(run_active, snaps, markets)
    app.dependency_overrides[get_db] = lambda: db_active
    clear_purchasability_v3_replay_preflight_cache()
    r2 = client.get("/api/cecchino-lab/historical-scans/1/purchasability-v3-replay/preflight")
    assert r2.status_code == 200
    assert r2.json()["status"] == "blocked"


def test_no_db_writes_in_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "db.commit" not in src
    assert "db.flush" not in src
    assert "db.add(" not in src
    assert "db.delete(" not in src


def test_opposite_draw_requires_home_away():
    by_mk = {m.market_key: m for m in _v3_family_markets(1)}
    status, _ = classify_score_replay(
        market_key="DRAW",
        m=by_mk["DRAW"],
        by_mk=by_mk,
        integrity="ok",
        integrity_reasons=[],
        duplicate=False,
    )
    assert status == "exact_replay_ready"

    by_mk_no_away = {k: v for k, v in by_mk.items() if k != "AWAY"}
    status2, codes = classify_score_replay(
        market_key="DRAW",
        m=by_mk["DRAW"],
        by_mk=by_mk_no_away,
        integrity="ok",
        integrity_reasons=[],
        duplicate=False,
    )
    assert status2 == "gate_only_replay_ready"
    assert any("missing_opposite" in c for c in codes)


def test_status_with_derived_warnings():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert "status_rules" in out
    assert out["status"] == "ready_with_warnings"
    assert any(w["code"] == "derived_quotes_diagnostic_only" for w in out["warnings"])


def test_include_probe_default_false_skips_formula(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("V3 non deve essere invocata in summary")

    monkeypatch.setattr(
        "app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight.calculate_purchasability_v3_batch",
        boom,
    )
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["probe"]["skipped"] is True
    assert out["probe"]["reason"] == "not_requested"
    assert called["n"] == 0


def test_include_probe_true_invokes_formula_max_30(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    calls = {"n": 0}

    real = None
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    real = mod.calculate_purchasability_v3_batch

    def wrapped(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod, "calculate_purchasability_v3_batch", wrapped)
    out = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert out["probe"].get("skipped") is not True
    assert calls["n"] <= PROBE_SNAPSHOT_LIMIT
    assert calls["n"] >= 1
    assert out["probe"]["snapshots_probed"] <= PROBE_SNAPSHOT_LIMIT


def test_cache_distinct_by_include_probe():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    s1 = run_purchasability_v3_replay_preflight(db, 1, include_probe=False)
    assert s1["cache_hit"] is False
    s2 = run_purchasability_v3_replay_preflight(db, 1, include_probe=False)
    assert s2["cache_hit"] is True
    p1 = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert p1["cache_hit"] is False
    assert p1["probe"].get("skipped") is not True
    p2 = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert p2["cache_hit"] is True


def test_no_full_orm_select_in_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "select(CecchinoLabHistoricalMatchSnapshot)" not in src
    assert "select(CecchinoLabHistoricalMarketResult)" not in src
    assert "markets_by_snap: dict[int, list[Any]]" not in src
    assert "PREFLIGHT_STREAM_YIELD_PER" in src
    assert "stream_results" in src
    assert "yield_per" in src
    lean_block = src.split("SNAPSHOT_LEAN_COLS")[1].split(")")[0]
    market_block = src.split("MARKET_STREAM_COLS")[1].split(")")[0]
    for heavy in (
        "input_snapshot_json",
        "cecchino_output_json",
        "historical_kpi_json",
        "result_json",
        "settlement_summary_json",
        "signal_sources_json",
    ):
        assert heavy not in lean_block
        assert heavy not in market_block


def test_resource_profile_and_max_rows_held():
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    out = run_purchasability_v3_replay_preflight(db, 1)
    rp = out["resource_profile"]
    assert rp["full_orm_entities_loaded"] is False
    assert rp["snapshot_json_fields_loaded"] is False
    assert rp["market_json_fields_loaded"] is False
    assert rp["stream_yield_per"] == 500
    assert rp["max_market_rows_held_in_memory"] <= 20
    assert rp["market_rows_streamed"] >= 1
    assert "query_profile" in out
    assert out["query_profile"]["market_stream_queries"] >= 1


def test_budget_rows_exceeded(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    monkeypatch.setattr(mod, "PREFLIGHT_MAX_SUPPORTED_ROWS", 1)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "preflight_resource_budget_exceeded" for b in out["blockers"])
    assert out["resource_profile"]["resource_budget_exceeded"] is True
    assert out["replay_recommendation"]["can_replay_without_full_scan"] is False


def test_budget_runtime_exceeded(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    monkeypatch.setattr(mod, "PREFLIGHT_MAX_RUNTIME_SECONDS", 0)
    out = run_purchasability_v3_replay_preflight(db, 1)
    assert out["status"] == "blocked"
    assert any(b["code"] == "preflight_resource_budget_exceeded" for b in out["blockers"])


def test_endpoint_unexpected_error_json():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")

    def boom_db():
        raise RuntimeError("simulated")

    app.dependency_overrides[get_db] = boom_db
    # Force failure inside handler by patching service
    import app.routes.cecchino_lab as route_mod

    original = route_mod.run_purchasability_v3_replay_preflight

    def raise_exc(*_a, **_k):
        raise RuntimeError("boom")

    route_mod.run_purchasability_v3_replay_preflight = raise_exc
    try:
        snaps, markets = _full_universe()
        run = _run()
        db = _db_with(run, snaps, markets)
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/cecchino-lab/historical-scans/1/purchasability-v3-replay/preflight")
        assert r.status_code == 500
        body = r.json()
        assert body["status"] == "error"
        assert body["error"] == "purchasability_v3_preflight_failed"
        assert "stack" not in body
        assert "traceback" not in str(body).lower()
    finally:
        route_mod.run_purchasability_v3_replay_preflight = original


def test_endpoint_include_probe_query_param():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    clear_purchasability_v3_replay_preflight_cache()
    r = client.get(
        "/api/cecchino-lab/historical-scans/1/purchasability-v3-replay/preflight"
    )
    assert r.status_code == 200
    assert r.json()["probe"]["reason"] == "not_requested"
    clear_purchasability_v3_replay_preflight_cache()
    r2 = client.get(
        "/api/cecchino-lab/historical-scans/1/purchasability-v3-replay/preflight?include_probe=true"
    )
    assert r2.status_code == 200
    assert r2.json()["probe"].get("invoked_v3_formula") is True


def test_schema_v2_and_integrity_policy_version():
    snaps, markets = _full_universe()
    out = run_purchasability_v3_replay_preflight(_db_with(_run(), snaps, markets), 1)
    assert out["schema_version"] == "cecchino_lab_purchasability_v3_replay_preflight_v2"
    assert out["integrity_policy_version"] == INTEGRITY_POLICY_VERSION
    assert out["source_integrity"]["integrity_policy_version"] == INTEGRITY_POLICY_VERSION


def test_workload_classification_complete_invariant():
    snaps, markets = _full_universe()
    out = run_purchasability_v3_replay_preflight(_db_with(_run(), snaps, markets), 1)
    wl = out["workload"]
    classified = (
        wl["exact_replay_ready"]
        + wl["ready_with_warning"]
        + wl["gate_only_ready"]
        + wl["not_replayable"]
        + wl["invalid_integrity"]
        + wl["ambiguous_market_join"]
    )
    assert wl["classified_evaluations_total"] == classified
    assert classified == wl["theoretical_evaluations"]
    assert wl["unclassified_evaluations"] == 0
    for mk, bucket in out["by_market"].items():
        m_sum = (
            bucket["exact_replay_ready"]
            + bucket["ready_with_warning"]
            + bucket["gate_only_ready"]
            + bucket["not_replayable"]
            + bucket["invalid_integrity"]
            + bucket["ambiguous_market_join"]
        )
        assert m_sum == bucket["eligible_rows"], mk
        assert bucket["classified_total"] == bucket["eligible_rows"]
        assert bucket["unclassified"] == 0


def test_quote_real_exact_derived_warning():
    snaps, markets = _full_universe()
    out = run_purchasability_v3_replay_preflight(_db_with(_run(), snaps, markets), 1)
    assert out["quote_quality"]["real"] >= 1
    assert out["quote_quality"]["derived"] >= 1
    assert out["workload"]["exact_replay_ready"] >= 1
    assert out["workload"]["ready_with_warning"] >= 1
    assert out["status"] == "ready_with_warnings"


def test_anti_leakage_phase_separation_fields():
    snaps, markets = _full_universe()
    out = run_purchasability_v3_replay_preflight(_db_with(_run(), snaps, markets), 1)
    al = out["anti_leakage"]
    assert al["performance_fields_loaded_but_not_forwarded"] is True
    assert al["formula_payload_forbidden_fields_found"] == []
    assert "edge_pct" in al["formula_payload_allowed_fields"]
    assert "won" in al["forbidden_formula_fields"]
    assert out["source_integrity"]["formula_input_whitelist_verified"] is True
    assert out["source_integrity"]["post_match_fields_excluded"] is True
    assert out["source_integrity"]["score_performance_phase_separation_verified"] is True


def test_probe_counters_and_by_market_invariant(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)

    def fake_batch(*, kpi_panel, fixture_meta):
        rows = (kpi_panel or {}).get("rows") or []
        items = []
        for r in rows:
            items.append(
                {
                    "market_key": r.get("market_key"),
                    "status": "available",
                    "score": 50,
                    "gate": {"gate_status": "passed"},
                }
            )
        return {"items": items}

    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    monkeypatch.setattr(mod, "calculate_purchasability_v3_batch", fake_batch)
    out = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    probe = out["probe"]
    assert probe["skipped"] is False
    assert probe["snapshots_selected"] == 2
    assert probe["snapshots_probed"] == 2
    assert probe["markets_expected"] == 16
    assert probe["panel_rows_submitted"] >= 8
    assert probe["formula_items_returned"] == probe["panel_rows_submitted"]
    assert probe["markets_scored"] == probe["formula_items_returned"]
    assert probe["markets_gate_failed"] == 0
    assert probe["markets_unavailable"] == 0
    assert probe["markets_not_applicable"] == 0
    assert probe["markets_unsupported"] == 0
    assert probe["markets_error"] == 0
    assert probe["markets_unclassified"] == 0
    classified = (
        probe["markets_scored"]
        + probe["markets_gate_failed"]
        + probe["markets_unavailable"]
        + probe["markets_not_applicable"]
        + probe["markets_unsupported"]
        + probe["markets_error"]
        + probe["markets_unclassified"]
    )
    assert probe["probe_classified_total"] == classified
    assert classified == probe["formula_items_returned"]
    assert probe["expected_vs_returned_status"] == "match"
    assert "by_market" in probe
    assert probe["by_market"]["HOME"]["scored"] >= 1
    assert not any(b["code"] == "probe_formula_error" for b in out["blockers"])


def test_probe_formula_error_blocks(monkeypatch):
    snaps, markets = _full_universe()
    run = _run()
    db = _db_with(run, snaps, markets)

    def boom(*, kpi_panel, fixture_meta):
        raise RuntimeError("formula boom")

    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_preflight as mod

    monkeypatch.setattr(mod, "calculate_purchasability_v3_batch", boom)
    out = run_purchasability_v3_replay_preflight(db, 1, include_probe=True)
    assert out["status"] == "blocked"
    assert any(b["code"] == "probe_formula_error" for b in out["blockers"])
    probe = out["probe"]
    assert probe["snapshots_with_error"] >= 1
    assert probe["markets_error"] >= 1
    assert all("traceback" not in str(e).lower() for e in probe.get("errors") or [])


def test_freeze_hash_and_lock_required_for_frozen():
    kick = _utcnow()
    snap = _snap(sid=1, locked_at=kick + timedelta(hours=3), kickoff=kick, sha="deadbeef")
    policy = evaluate_historical_integrity_policy(snap)
    assert policy["historical_payload_hash_present"] is True
    assert policy["historical_freeze_lock_present"] is True
    assert policy["integrity_mode"] == INTEGRITY_MODE_FROZEN
    snap2 = _snap(sid=2, kickoff=kick, sha="deadbeef")
    snap2.pre_match_locked_at = None
    policy2 = evaluate_historical_integrity_policy(snap2)
    assert policy2["integrity_mode"] == "historical_reconstruction_incomplete"
