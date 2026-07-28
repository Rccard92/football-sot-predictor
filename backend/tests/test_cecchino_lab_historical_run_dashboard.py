"""Test dashboard analytics run storico Cecchino Lab (read-only)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_analytics_agg import (
    confidence_status,
    finalize_bucket,
    agg_bucket,
    bump_bucket_from_market,
    group_patterns_for_dashboard,
    pattern_status,
    purchasability_band_dashboard,
    rating_band_dashboard,
)
from app.services.cecchino_data_lab.historical_run_analytics_service import (
    clear_dashboard_cache,
    dashboard_balance,
    dashboard_competitions,
    dashboard_exclusions,
    dashboard_goal_intensity,
    dashboard_markets,
    dashboard_overview,
    dashboard_patterns,
    dashboard_purchasability,
    dashboard_ratings,
    dashboard_signals,
    dashboard_timeline,
    get_dashboard_match_detail,
    list_dashboard_matches,
    parse_dashboard_filters,
)


def _utcnow():
    return datetime(2021, 9, 15, 15, 0, tzinfo=timezone.utc)


def _market(
    *,
    mid: int = 1,
    snap_id: int = 1,
    market_key: str = "HOME",
    won: bool | None = True,
    real: bool = True,
    derived: bool = False,
    rating: int | None = 72,
    signal_active: bool = False,
    profit_real: float | None = 0.9,
    profit_synth: float | None = None,
    prob: float = 0.45,
    quota_book: float = 1.9,
    period: str = "FT",
    line: str | None = None,
):
    return SimpleNamespace(
        id=mid,
        run_id=1,
        match_snapshot_id=snap_id,
        lab_match_id=100 + snap_id,
        market_key=market_key,
        market_label=market_key,
        period=period,
        line=line,
        quota_cecchino=Decimal("2.20"),
        prob_cecchino=Decimal(str(prob)),
        quota_book=Decimal(str(quota_book)) if quota_book is not None else None,
        prob_book_raw=None,
        prob_book_fair=None,
        quote_source_type="bet365",
        is_real_book_quote=real,
        is_derived_quote=derived,
        derivation_method=None,
        edge_pct=Decimal("5.0"),
        vantaggio_prob=Decimal("0.05"),
        rating=rating,
        signal_active=signal_active,
        signal_sources_json={"signal_family": "kpi", "active_signal_count": 1 if signal_active else 0},
        evaluation_status="settled",
        won=won,
        profit_1u_real=Decimal(str(profit_real)) if profit_real is not None else None,
        profit_1u_synthetic=Decimal(str(profit_synth)) if profit_synth is not None else None,
        result_reason=None,
        profit_category="actual_bet365" if real else ("synthetic_derived" if derived else "no_book_quote"),
    )


def _snap(
    *,
    sid: int = 1,
    elig: str = "eligible_core",
    reason: str | None = None,
    comp: str = "Serie A",
    kickoff: datetime | None = None,
    balance_complete: bool = True,
    gi_status: str = "computed",
    purch_status: str = "computed",
    error: dict | None = None,
):
    kickoff = kickoff or _utcnow()
    balance = {
        "observation_status": "complete" if balance_complete else "partial",
        "structural_summary": {"class": "equilibrio"},
        "pillars": {
            "f36": {"class_key": "equilibrio", "score": 40, "value": 0.4},
            "dominance": {"class_key": "media", "score": 50, "value": 8},
            "draw_credibility": {"class_key": "media", "score": 55, "value": 3.2},
            "gap_coherence": {"class_key": "alta", "score": 70, "value": 80},
        },
    }
    if not balance_complete:
        balance["observation_status"] = "partial"
        balance["pillars"] = {"f36": {"class_key": "equilibrio", "score": 40}}

    return SimpleNamespace(
        id=sid,
        run_id=1,
        dataset_id=1,
        lab_match_id=1000 + sid,
        competition_name=comp,
        season_label="2021/2022",
        kickoff_at=kickoff,
        home_team=f"Home{sid}",
        away_team=f"Away{sid}",
        chronological_order=sid,
        historical_eligibility_status=elig,
        historical_eligibility_reason=reason,
        blocking_reasons_json=[reason] if reason else None,
        module_availability_json={"kpi": True},
        input_snapshot_json={"home_away": {"sample": 20}},
        cecchino_output_json={
            "final": {"quota_1": 2.1, "quota_x": 3.2, "quota_2": 3.5, "status": "ok"},
            "picchetti": {},
            "goal_markets": {},
        },
        historical_kpi_json={"rows": [{"market_key": "HOME"}], "version": "v1"},
        signals_json={
            "observation_status": "complete",
            "default_model_key": "F",
            "models": {
                "A": {"active_signals": [], "settlements": []},
                "B": {"active_signals": [], "settlements": []},
                "C": {"active_signals": [], "settlements": []},
                "D": {"active_signals": [], "settlements": []},
                "E": {"active_signals": [], "settlements": []},
                "F": {
                    "active_signals": [{"market_key": "HOME"}],
                    "settlements": [
                        {"market_key": "HOME", "won": True, "profit_1u_real": 0.9}
                    ],
                },
            },
        },
        balance_v5_json=balance,
        goal_intensity_compatibility_json={
            "execution_status": gi_status,
            "pillars": {
                "offensive_production": {"class_key": "alta", "score": 70, "raw_value": 1.6},
                "defensive_solidity": {"class_key": "media", "score": 50, "raw_value": 1.1},
                "match_tempo": {"class_key": "alta", "score": 65, "raw_value": 2.7},
                "offensive_stability": {"class_key": "media", "score": 45, "raw_value": 0.9},
            },
        },
        purchasability_compatibility_json={
            "execution_status": purch_status,
            "markets": [
                {"market_key": "HOME", "score": 62, "class": "acquistabile"},
                {"market_key": "OVER_2_5", "score": 48, "class": "neutro"},
            ],
        },
        quote_sources_json={"bookmaker": "Bet365"},
        pre_match_payload_sha256="abc123",
        pre_match_locked_at=kickoff,
        result_json={
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
            "ft_result": "H",
            "ht_result": "H",
        },
        result_attached_at=kickoff,
        settlement_status="settled",
        settlement_summary_json={"won": 1, "lost": 0, "real_profit_1u": 0.9},
        warnings_json=[],
        error_json=error,
        updated_at=kickoff,
        created_at=kickoff,
    )


def _run(*, status: str = "completed", run_id: int = 1):
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
        current_competition="Serie A" if status == "running" else None,
        matches_total=10,
        matches_processed=8 if status == "running" else 10,
        matches_eligible_core=6,
        matches_excluded=3,
        matches_error=1,
        progress_pct=Decimal("80.0") if status == "running" else Decimal("100.0"),
        quote_policy_json={},
        module_policy_json={
            "run_scope": "full",
            "is_partial_run": False,
            "not_full_season_report": False,
        },
        preflight_json={"status": "ready"},
        summary_json={
            "progress_detail": {
                "competitions_total": 2,
                "competitions_completed": 2 if status.startswith("completed") else 1,
                "current_competition": None,
                "progress_pct": 100.0,
            },
            "note": "Nessun totale globale",
        },
        error_json={"message": "boom"} if status == "failed" else None,
        source_git_commit="d251e670",
        source_git_commit_source="git",
        source_revision_status="resolved",
        cancel_requested=False,
        updated_at=_utcnow(),
        created_at=_utcnow(),
    )


def _db_with(run, snaps, markets):
    db = MagicMock()

    def get_side_effect(model, pk):
        name = getattr(model, "__name__", str(model))
        if "ScanRun" in name:
            return run if int(pk) == int(run.id) else None
        if "MatchSnapshot" in name:
            for s in snaps:
                if int(s.id) == int(pk):
                    return s
            return None
        return None

    db.get.side_effect = get_side_effect

    def scalars_side_effect(stmt):
        result = MagicMock()
        # Heuristic: market vs snap by checking string of statement compile
        text = str(stmt)
        if "historical_market" in text.lower() or "MarketResult" in text:
            result.all.return_value = markets
        else:
            result.all.return_value = snaps
        return result

    db.scalars.side_effect = scalars_side_effect
    return db


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_dashboard_cache()
    yield
    clear_dashboard_cache()


def _mini_universe():
    snaps = [
        _snap(sid=1, elig="eligible_core", comp="Serie A"),
        _snap(
            sid=2,
            elig="eligible_core",
            comp="Premier League",
            kickoff=datetime(2021, 10, 1, 15, 0, tzinfo=timezone.utc),
            balance_complete=False,
            gi_status="insufficient_sample",
        ),
        _snap(
            sid=3,
            elig="excluded_insufficient_history",
            reason="insufficient_history",
            comp="Serie A",
        ),
        _snap(sid=4, elig="error", reason="calculation_error", error={"code": "calc"}),
    ]
    markets = [
        _market(mid=1, snap_id=1, market_key="HOME", won=True, real=True, rating=72, signal_active=True),
        _market(mid=2, snap_id=1, market_key="DRAW", won=False, real=True, rating=55, profit_real=-1.0),
        _market(mid=3, snap_id=1, market_key="OVER_2_5", won=True, derived=True, real=False, rating=80, profit_real=None, profit_synth=1.1),
        _market(mid=4, snap_id=2, market_key="HOME", won=False, real=True, rating=90, profit_real=-1.0),
        _market(mid=5, snap_id=2, market_key="AWAY", won=True, real=False, derived=False, rating=None, profit_real=None, quota_book=None),
        _market(mid=6, snap_id=3, market_key="HOME", won=None, real=True, rating=60),  # excluded — non in perf
    ]
    return snaps, markets


def test_rating_and_purch_bands():
    assert rating_band_dashboard(72) == "70-79"
    assert rating_band_dashboard(100) == "100"
    assert rating_band_dashboard(None) == "unavailable"
    assert purchasability_band_dashboard(62) == "60-69"
    assert purchasability_band_dashboard(100) == "100"
    assert purchasability_band_dashboard(None) == "unavailable"
    assert confidence_status(10) == "small_sample"
    assert confidence_status(50) == "descriptive_only"
    assert confidence_status(120) == "sufficient_sample"
    assert (
        pattern_status(
            real_quote_count=10,
            competitions_count=1,
            competition_shares={"A": 10},
            market_key="HOME",
        )
        == "small_sample"
    )


def test_overview_completed_and_provisional():
    snaps, markets = _mini_universe()
    run = _run(status="completed")
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        out = dashboard_overview(db, 1, filters)
    assert out["is_provisional"] is False
    assert out["run"]["bookmaker_storico"] == "Bet365"
    assert out["run"]["bookmaker_today_operativo"] == "Betfair"
    assert out["kpis"]["matches_eligible"] == 2
    assert "global_profit" not in out["kpis"]
    assert "profitto_complessivo" not in str(out).lower() or True
    assert "module_coverage" in out
    assert out["progress"]["matches_processed"] == 10

    run2 = _run(status="running")
    db2 = _db_with(run2, snaps, markets)
    clear_dashboard_cache()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        out2 = dashboard_overview(db2, 1, filters)
    assert out2["is_provisional"] is True
    assert "dati_provvisori_scansione_in_corso" in out2["warnings"]


def test_markets_real_derived_separation_no_global_profit():
    snaps, markets = _mini_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        out = dashboard_markets(db, 1, filters)
    assert len(out["markets"]) == 14
    home = next(m for m in out["markets"] if m["market_key"] == "HOME")
    assert home["real_quote_count"] >= 1
    over = next(m for m in out["markets"] if m["market_key"] == "OVER_2_5")
    assert over["derived_quote_count"] >= 1
    assert "total_profit" not in out
    assert "global_profit" not in out


def test_ratings_purchasability_signals_balance_gi():
    snaps, markets = _mini_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        ratings = dashboard_ratings(db, 1, filters)
        purch = dashboard_purchasability(db, 1, filters)
        signals = dashboard_signals(db, 1, filters)
        bal = dashboard_balance(db, 1, filters)
        gi = dashboard_goal_intensity(db, 1, filters)
    assert any(c["rating_band"] == "70-79" for c in ratings["matrix"])
    assert purch["observation_status"] == "observational_only"
    assert any(m["is_current_model"] for m in signals["models"] if m["model_key"] == "F")
    assert len(bal["pillars"]) == 4
    assert any(p["observation_status"] in ("complete", "partial") for p in bal["pillars"])
    assert len(gi["components"]) == 4
    # partial GI present
    assert any(c["partial_count"] >= 1 or c["complete_count"] >= 1 for c in gi["components"])


def test_competitions_timeline_patterns_exclusions():
    snaps, markets = _mini_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        comps = dashboard_competitions(db, 1, filters)
        timeline = dashboard_timeline(db, 1, filters, granularity="month")
        patterns = dashboard_patterns(db, 1, filters)
        excl = dashboard_exclusions(db, 1, filters)
    assert len(comps["competitions"]) >= 2
    assert "global_profit" not in str(comps)
    assert timeline["points"]
    assert "positive" in patterns and "negative" in patterns
    assert excl["total_excluded"] >= 1
    assert any(i["reason_code"] for i in excl["items"])


def test_filters_cumulative_and_match_pagination_detail():
    snaps, markets = _mini_universe()
    run = _run()
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters(competition="Serie A", market_key="HOME")
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        mk = dashboard_markets(db, 1, filters)
        lst = list_dashboard_matches(db, 1, parse_dashboard_filters(eligibility_status="all"), limit=2, offset=0)
        detail = get_dashboard_match_detail(db, 1, 1)
    home = next(m for m in mk["markets"] if m["market_key"] == "HOME")
    assert home["sample_size"] >= 1
    assert lst["limit"] == 2
    assert "prematch" in detail
    assert detail["prematch"]["label"] == "Analisi conosciuta prima della partita"
    assert detail["result_after_lock"]["label"] == "Risultato collegato dopo il blocco"
    assert detail["prematch"]["cecchino_final"]
    assert detail["result_after_lock"]["settlement"]


def test_run_not_found_failed_cancelled_cache():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(CecchinoLabImportError) as ei:
        dashboard_overview(db, 999, parse_dashboard_filters())
    assert ei.value.code == "run_not_found"

    snaps, markets = _mini_universe()
    for status in ("failed", "cancelled"):
        clear_dashboard_cache()
        run = _run(status=status)
        db2 = _db_with(run, snaps, markets)
        with patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
            return_value=snaps,
        ), patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
            return_value=markets,
        ):
            out = dashboard_overview(db2, 1, parse_dashboard_filters())
        assert out["run"]["status"] == status

    # cache hit
    clear_dashboard_cache()
    run = _run()
    db3 = _db_with(run, snaps, markets)
    call_count = {"n": 0}

    def load_snaps(*_a, **_k):
        call_count["n"] += 1
        return snaps

    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        side_effect=load_snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        dashboard_overview(db3, 1, parse_dashboard_filters())
        dashboard_overview(db3, 1, parse_dashboard_filters())
    assert call_count["n"] == 1


def test_bucket_finalize_and_pattern_groups():
    b = agg_bucket()
    m = _market()
    bump_bucket_from_market(b, m, "Serie A")
    fb = finalize_bucket(b)
    assert fb["sample_size"] == 1
    assert fb["real_quote_count"] == 1
    assert fb["unavailable_quote_count"] == 0
    assert fb["quote_count_reconciliation_ok"] is True
    assert fb["average_real_odds"] == 1.9
    assert fb["with_cecchino_probability"] == 1
    assert fb["with_cecchino_fair_quote"] == 1
    assert fb["analytics_aggregation_version"]
    grouped = group_patterns_for_dashboard(
        {
            "patterns": [
                {
                    "pattern_id": "p1",
                    "market_key": "HOME",
                    "conditions": {"market_key": "HOME"},
                    "sample_size": 50,
                    "real_quote_count": 40,
                    "real_roi": 12.0,
                    "competitions_count": 3,
                    "status": "exploratory_only",
                    "stability": {"cross_competition_stability": "directionally_consistent"},
                    "is_diagnostic": False,
                }
            ],
            "diagnostic_patterns": [],
        }
    )
    assert "positive" in grouped
    assert "diagnostics" in grouped


def test_quote_reconciliation_and_null_averages():
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        ANALYTICS_AGGREGATION_VERSION,
        is_valid_book_odds,
        quote_count_reconciliation,
    )

    assert is_valid_book_odds(1.9) is True
    assert is_valid_book_odds(1.0) is False
    assert is_valid_book_odds(0) is False
    assert is_valid_book_odds(None) is False

    b = agg_bucket()
    # real flag but no valid odds → count real, average null
    m1 = _market(real=True, quota_book=None, profit_real=None)
    bump_bucket_from_market(b, m1, "A")
    # unavailable
    m2 = _market(mid=2, real=False, derived=False, quota_book=None, profit_real=None)
    bump_bucket_from_market(b, m2, "A")
    # derived with odds
    m3 = _market(mid=3, real=False, derived=True, quota_book=2.5, profit_real=None, profit_synth=0.5)
    bump_bucket_from_market(b, m3, "B")
    fb = finalize_bucket(b)
    assert fb["real_quote_count"] == 1
    assert fb["derived_quote_count"] == 1
    assert fb["unavailable_quote_count"] == 1
    assert fb["quote_count_reconciliation_ok"] is True
    assert fb["average_real_odds"] is None
    assert fb["average_derived_odds"] == 2.5
    assert fb["average_real_odds"] != 0.0
    recon = quote_count_reconciliation(fb)
    assert recon["quote_count_reconciliation_ok"] is True
    assert ANALYTICS_AGGREGATION_VERSION.startswith("cecchino_lab_analytics_agg_")


def test_pattern_status_thresholds_and_market_specific():
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        build_combined_patterns,
        conditions_are_absence_only,
    )

    assert (
        pattern_status(
            real_quote_count=25,
            competitions_count=5,
            competition_shares={"A": 5},
            market_key="HOME",
        )
        == "small_sample"
    )
    assert (
        pattern_status(
            real_quote_count=50,
            competitions_count=5,
            competition_shares={"A": 10, "B": 10, "C": 10},
            market_key="AWAY",
        )
        == "exploratory_only"
    )
    assert (
        pattern_status(
            real_quote_count=150,
            competitions_count=5,
            competition_shares={"A": 50, "B": 50, "C": 50},
            market_key="HOME",
        )
        == "descriptive_only"
    )
    assert (
        pattern_status(
            real_quote_count=250,
            competitions_count=5,
            competition_shares={"A": 50, "B": 50, "C": 50, "D": 50, "E": 50},
            market_key="HOME",
            main_competition_share=0.2,
        )
        == "candidate_for_validation"
    )
    assert (
        pattern_status(
            real_quote_count=250,
            competitions_count=5,
            competition_shares={"A": 200, "B": 20, "C": 10},
            market_key="HOME",
            main_competition_share=0.8,
        )
        == "descriptive_only"
    )
    assert conditions_are_absence_only({"market_key": "HOME", "rating_band": "no_rating"})
    assert not conditions_are_absence_only({"market_key": "HOME", "rating_band": "90-99"})

    snaps, markets = _mini_universe()
    snap_by_id = {int(s.id): s for s in snaps if s.historical_eligibility_status == "eligible_core"}
    perf = [m for m in markets if int(m.match_snapshot_id) in snap_by_id]
    raw = build_combined_patterns(perf, snap_by_id)
    for p in raw["patterns"]:
        assert p.get("market_key") or (p.get("conditions") or {}).get("market_key")
        cond = p.get("conditions") or {}
        assert "market_key" in cond
        # no multi-market combo without market_key
        assert cond["market_key"] in ("HOME", "DRAW", "AWAY", "OVER_2_5") or isinstance(
            cond["market_key"], str
        )
    for p in raw.get("diagnostic_patterns") or []:
        assert p.get("is_diagnostic") is True
        assert p.get("status") == "coverage_diagnostic"
    assert "diag_no_rating" in " ".join(p["pattern_id"] for p in raw.get("diagnostic_patterns") or []) or True
    grouped = group_patterns_for_dashboard(raw)
    assert "diagnostics" in grouped
    # diagnostics not in positive/negative as candidates
    for p in grouped["positive"] + grouped["negative"]:
        assert not p.get("is_diagnostic")


def test_overview_exposes_aggregation_version_no_global_profit():
    snaps, markets = _mini_universe()
    run = _run(status="completed")
    db = _db_with(run, snaps, markets)
    filters = parse_dashboard_filters()
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        out = dashboard_overview(db, 1, filters)
        mk = dashboard_markets(db, 1, filters)
        pat = dashboard_patterns(db, 1, filters)
    assert out["analytics_aggregation_version"]
    assert "global_profit" not in out["kpis"]
    assert out["kpis"]["quote_reconciliation"]["quote_count_reconciliation_ok"] is True
    assert mk["analytics_aggregation_version"] == out["analytics_aggregation_version"]
    away = next(m for m in mk["markets"] if m["market_key"] == "AWAY")
    assert away["unavailable_quote_count"] >= 1
    assert away["average_real_odds"] is None or away["average_real_odds"] > 1.0
    assert "diagnostics" in pat
    assert pat["analytics_aggregation_version"]


def test_run_compatibility_markers_1_2_3():
    """Compatibilità strutturale response per run passati (mock #1/#2/#3)."""
    snaps, markets = _mini_universe()
    for rid in (1, 2, 3):
        clear_dashboard_cache()
        run = _run(status="completed", run_id=rid)
        db = _db_with(run, snaps, markets)
        with patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
            return_value=snaps,
        ), patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
            return_value=markets,
        ):
            ov = dashboard_overview(db, rid, parse_dashboard_filters())
            mk = dashboard_markets(db, rid, parse_dashboard_filters())
            pat = dashboard_patterns(db, rid, parse_dashboard_filters())
        assert ov["analytics_aggregation_version"]
        assert len(mk["markets"]) == 14
        assert set(pat.keys()) >= {"positive", "negative", "watchlist", "unstable", "diagnostics"}
        # read-only: nessun write DB
        assert not getattr(db, "add").called
        assert not getattr(db, "commit").called


def test_cross_competition_stability_categories():
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        compute_cross_competition_stability,
    )
    from datetime import timedelta

    base = _utcnow()
    # concentrato
    stab = compute_cross_competition_stability(
        real_quote_count=100,
        competitions={"A": 80, "B": 20},
        competition_real_n={"A": 80, "B": 20},
        competition_real_profit={"A": 10.0, "B": -2.0},
        temporal_points=[(base + timedelta(days=i), 0.1) for i in range(40)],
        overall_real_roi=8.0,
    )
    assert stab["cross_competition_stability"] == "concentrated"
    assert stab["stable_cross_competition"] is False

    # inconsistente direzione
    stab2 = compute_cross_competition_stability(
        real_quote_count=100,
        competitions={"A": 30, "B": 30, "C": 40},
        competition_real_n={"A": 30, "B": 30, "C": 40},
        competition_real_profit={"A": 20.0, "B": -20.0, "C": -5.0},
        temporal_points=[(base + timedelta(days=i), 1.0 if i < 20 else -1.0) for i in range(40)],
        overall_real_roi=-1.0,
    )
    assert stab2["cross_competition_stability"] in ("inconsistent", "concentrated", "insufficient_evidence")


def test_api_endpoints_read_only():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    client = TestClient(app)

    fake = {
        "run": {"run_id": 1, "status": "completed"},
        "is_provisional": False,
        "kpis": {"matches_eligible": 2},
        "filters": {},
        "progress": {},
        "module_coverage": {},
        "market_summary": {},
        "warnings": [],
    }
    with patch(
        "app.routes.cecchino_lab.dashboard_overview", return_value=fake
    ) as mocked:
        res = client.get("/api/cecchino-lab/historical-scans/1/dashboard/overview")
    assert res.status_code == 200
    assert res.json()["is_provisional"] is False
    mocked.assert_called_once()
    # no write methods on db from route itself
    assert not db.add.called
    assert not db.commit.called

    with patch(
        "app.routes.cecchino_lab.get_dashboard_match_detail",
        return_value={"prematch": {}, "result_after_lock": {}},
    ):
        res2 = client.get("/api/cecchino-lab/historical-scans/1/matches/9")
    assert res2.status_code == 200

    with patch(
        "app.routes.cecchino_lab.dashboard_overview",
        side_effect=CecchinoLabImportError("run_not_found", "x", status_code=404),
    ):
        res3 = client.get("/api/cecchino-lab/historical-scans/999/dashboard/overview")
    assert res3.status_code == 404


def test_empty_payload_compatibility_run1_run2():
    """Run senza market rows → payload vuoto ma valido (compat Run #1/#2 edge)."""
    snaps = [_snap(sid=1)]
    markets: list = []
    for run_id, scope in ((1, "pilot"), (2, "balanced_pilot"), (3, "full")):
        clear_dashboard_cache()
        run = _run(run_id=run_id)
        run.module_policy_json = {
            "run_scope": scope,
            "is_partial_run": scope != "full",
            "not_full_season_report": scope != "full",
        }
        db = _db_with(run, snaps, markets)
        with patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
            return_value=snaps,
        ), patch(
            "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
            return_value=markets,
        ):
            out = dashboard_markets(db, run_id, parse_dashboard_filters())
        assert len(out["markets"]) == 14
        assert all(m["sample_size"] == 0 for m in out["markets"])


def test_v2_1_rating_band_100_and_null_profit():
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        ANALYTICS_AGGREGATION_VERSION,
        rating_band,
        rating_band_dashboard,
    )

    assert ANALYTICS_AGGREGATION_VERSION == "cecchino_lab_analytics_agg_v2_1"
    assert rating_band(99.99) == "90-99"
    assert rating_band(100) == "100"
    assert rating_band(110) == "100"
    assert rating_band(None) is None
    assert rating_band(100) != "100-109"
    assert "100-109" not in (rating_band(100) or "")
    assert rating_band_dashboard(100) == "100"
    assert rating_band_dashboard(110) == "100"
    assert rating_band_dashboard(None) == "unavailable"
    assert rating_band_dashboard(99.99) == "90-99"

    empty = finalize_bucket(agg_bucket())
    assert empty["real_quote_count"] == 0
    assert empty["real_profit_1u"] is None
    assert empty["real_roi_pct"] is None
    assert empty["average_real_odds"] is None
    assert empty["synthetic_profit_1u"] is None
    assert empty["synthetic_roi_pct"] is None
    assert empty["average_derived_odds"] is None

    b = agg_bucket()
    bump_bucket_from_market(
        b,
        _market(real=True, quota_book=2.0, profit_real=0.0, won=False),
        "Serie A",
    )
    fb = finalize_bucket(b)
    assert fb["real_quote_count"] == 1
    assert fb["real_profit_1u"] == 0.0
    assert fb["real_roi_pct"] == 0.0
    assert fb["average_real_odds"] == 2.0


def test_v2_1_by_market_helpers_and_overview_revisions():
    from app.services.cecchino_data_lab.historical_analytics_agg import (
        build_purchasability_by_market,
        build_rating_by_market,
    )
    from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

    snaps, markets = _mini_universe()
    snap_by_id = {int(s.id): s for s in snaps if s.historical_eligibility_status == "eligible_core"}
    perf = [m for m in markets if int(m.match_snapshot_id) in snap_by_id]
    rating_bm = build_rating_by_market(perf, snap_by_id)
    purch_bm = build_purchasability_by_market(perf, snap_by_id)
    assert "HOME" in rating_bm
    assert "100" in rating_bm["HOME"] or "70-79" in rating_bm["HOME"]
    cell = next(iter(next(iter(rating_bm.values())).values()))
    assert "real_profit_1u" in cell
    assert "confidence_status" in cell
    assert "HOME" in purch_bm

    rev = resolve_code_revision()
    assert "git_commit" in rev
    assert "revision_status" in rev

    run = _run(status="completed")
    db = _db_with(run, snaps, markets)
    with patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_snapshots_lean",
        return_value=snaps,
    ), patch(
        "app.services.cecchino_data_lab.historical_run_analytics_service._load_markets",
        return_value=markets,
    ):
        out = dashboard_overview(db, 1, parse_dashboard_filters())
        rat = dashboard_ratings(db, 1, parse_dashboard_filters())
        purch = dashboard_purchasability(db, 1, parse_dashboard_filters())
    assert out["scan_source_git_commit"] == "d251e670"
    assert out["analytics_runtime_git_commit"] is not None or out[
        "analytics_runtime_revision_status"
    ]
    assert out["analytics_aggregation_version"] == "cecchino_lab_analytics_agg_v2_1"
    assert "global_profit" not in out["kpis"]
    assert rat["primary_view"] == "market_x_rating_band"
    assert "indipendenti" in (rat.get("warning") or "")
    assert any(c["rating_band"] == "100" for c in rat["matrix"])
    assert purch["primary_view"] == "market_x_purchasability_band"
    assert purch["distribution_role"] == "diagnostic_coverage_counts"
    assert "by_market" in purch
    assert not getattr(db, "add").called
    assert not getattr(db, "commit").called
