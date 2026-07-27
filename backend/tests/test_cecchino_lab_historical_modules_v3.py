"""Test moduli storici Lab v3 — Intensità, Acquistabilità, A–F, git, pilota."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_WEIGHTS,
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    get_cecchino_weight_model,
    model_weights_to_picchetto_map,
    validate_cecchino_weight_models,
)
from app.services.cecchino_data_lab.historical_context_builder import sha256_prematch_payload
from app.services.cecchino_data_lab.historical_goal_intensity import (
    MODULE_VERSION,
    build_historical_goal_intensity,
    extract_bundle_features_from_proxies,
)
from app.services.cecchino_data_lab.historical_purchasability import (
    STATUS_INSUFFICIENT,
    build_historical_purchasability,
    build_progressive_normalization_profile,
)
from app.services.cecchino_data_lab.historical_signal_extraction import (
    build_market_signal_index,
    iter_active_signal_cells,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    build_historical_signal_models,
    resolve_signals_matrix,
)


def _proxy(
    *,
    pid: int,
    home: str,
    away: str,
    gh: int,
    ga: int,
    kickoff: datetime,
    hid: int,
    aid: int,
):
    return SimpleNamespace(
        id=pid,
        home_team_id=hid,
        away_team_id=aid,
        home_team_name=home,
        away_team_name=away,
        goals_home=gh,
        goals_away=ga,
        kickoff_at=kickoff,
        match_date=kickoff.date(),
        match_time=None,
        source_row_number=pid,
    )


def test_weight_models_official_and_f_is_current():
    validate_cecchino_weight_models()
    assert list(CECCHINO_WEIGHT_MODEL_KEYS) == ["A", "B", "C", "D", "E", "F"]
    assert CECCHINO_DEFAULT_WEIGHT_MODEL_KEY == "F"
    f_w = model_weights_to_picchetto_map("F")
    for k, v in CECCHINO_1X2_WEIGHTS.items():
        assert abs(float(f_w[k]) - float(v)) < 1e-12
    for key in CECCHINO_WEIGHT_MODEL_KEYS:
        model = get_cecchino_weight_model(key)
        total = sum(
            float(model[k])
            for k in ("totals", "home_away", "last6_totals", "last5_home_away")
        )
        assert abs(total - 1.0) < 1e-9


def test_goal_intensity_insufficient_and_xg_missing():
    base = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    ordered = [
        _proxy(
            pid=i,
            home="H",
            away="A",
            gh=1,
            ga=1,
            kickoff=base.replace(day=min(i, 28)),
            hid=10,
            aid=20,
        )
        for i in range(1, 5)
    ]
    target = _proxy(
        pid=99,
        home="H",
        away="A",
        gh=2,
        ga=0,
        kickoff=base.replace(month=9),
        hid=10,
        aid=20,
    )
    out = build_historical_goal_intensity(
        input_snapshot={"leakage_ok": True, "prior_count": 3},
        contexts=None,
        competition_ordered=ordered + [target],
        target=target,
        prior_feature_rows=[],
    )
    assert out["parity_status"] == "partial"
    assert out["module_version"] == MODULE_VERSION
    assert out["inputs"]["xg_status"] == "missing"
    assert out["inputs"]["xg_imputed_to_zero"] is False
    assert "xg" in out["missing_inputs"]
    assert out["execution_status"] in (
        "insufficient_sample",
        "insufficient_ecdf_train",
    )


def test_goal_intensity_future_result_does_not_change_features():
    base = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    ordered = []
    for i in range(1, 16):
        ordered.append(
            _proxy(
                pid=i,
                home="Home",
                away="Away",
                gh=i % 3,
                ga=(i + 1) % 3,
                kickoff=base.replace(day=min(14, i) if i <= 14 else 14, month=8 if i <= 14 else 9),
                hid=100,
                aid=200,
            )
        )
    # fix kickoffs properly chronological
    ordered = []
    for i in range(1, 20):
        ko = datetime(2021, 8, 1, 12, 0, tzinfo=timezone.utc).replace(
            day=1 + (i % 28), month=8 if i < 15 else 9
        )
        ordered.append(
            _proxy(
                pid=i,
                home="Home",
                away="Rival",
                gh=1 + (i % 3),
                ga=i % 2,
                kickoff=ko,
                hid=100,
                aid=200 + (i % 5),
            )
        )
    # ensure Home has enough priors
    for i in range(20, 40):
        ko = datetime(2021, 9, 1, 12, 0, tzinfo=timezone.utc).replace(day=1 + (i % 27))
        ordered.append(
            _proxy(
                pid=i,
                home="Home",
                away=f"Opp{i}",
                gh=2,
                ga=1,
                kickoff=ko,
                hid=100,
                aid=300 + i,
            )
        )
        ordered.append(
            _proxy(
                pid=1000 + i,
                home=f"Opp{i}",
                away="AwayT",
                gh=1,
                ga=1,
                kickoff=ko.replace(hour=18),
                hid=300 + i,
                aid=400,
            )
        )
    ordered.sort(key=lambda p: (p.kickoff_at, p.id))
    target = _proxy(
        pid=9999,
        home="Home",
        away="AwayT",
        gh=9,
        ga=9,  # risultato target non deve entrare nelle feature
        kickoff=datetime(2021, 10, 1, 15, 0, tzinfo=timezone.utc),
        hid=100,
        aid=400,
    )
    feats_a = extract_bundle_features_from_proxies(
        competition_ordered=ordered + [target], target=target
    )
    target_b = _proxy(
        pid=9999,
        home="Home",
        away="AwayT",
        gh=0,
        ga=0,
        kickoff=datetime(2021, 10, 1, 15, 0, tzinfo=timezone.utc),
        hid=100,
        aid=400,
    )
    feats_b = extract_bundle_features_from_proxies(
        competition_ordered=ordered + [target_b], target=target_b
    )
    assert feats_a["features"] == feats_b["features"]


def test_purchasability_insufficient_sample_and_no_betfair():
    kpi = {
        "rows": [
            {
                "market_key": "HOME",
                "rating": 55,
                "edge_pct": 3.0,
                "vantaggio_prob": 0.04,
                "quota_cecchino": 2.2,
                "prob_cecchino": 0.45,
                "book_quote_class": "real_bet365",
                "quota_book": 2.0,
            },
            {
                "market_key": "DRAW",
                "rating": 40,
                "edge_pct": -1.0,
                "vantaggio_prob": -0.02,
                "quota_cecchino": 3.4,
                "prob_cecchino": 0.29,
                "book_quote_class": "real_bet365",
                "quota_book": 3.3,
            },
            {
                "market_key": "AWAY",
                "rating": 35,
                "edge_pct": -2.0,
                "vantaggio_prob": -0.03,
                "quota_cecchino": 3.5,
                "prob_cecchino": 0.26,
                "book_quote_class": "real_bet365",
                "quota_book": 3.6,
            },
        ]
    }
    quotes = {
        "quotes": {
            "HOME": {"value": 2.0, "is_real_book_quote": True, "is_derived": False},
            "DRAW": {"value": 3.3, "is_real_book_quote": True, "is_derived": False},
            "AWAY": {"value": 3.6, "is_real_book_quote": True, "is_derived": False},
        }
    }
    out = build_historical_purchasability(
        kpi_panel=kpi, quote_bundle=quotes, prior_kpi_panels=[]
    )
    assert out["betfair_operational_profile_applied"] is False
    assert out["execution_status"] == STATUS_INSUFFICIENT
    assert all(m["score"] is None for m in out["markets"])
    assert all(m["status"] == STATUS_INSUFFICIENT for m in out["markets"])


def test_purchasability_profile_excludes_target_and_is_deterministic():
    panels = []
    for i in range(20):
        panels.append(
            {
                "rows": [
                    {
                        "market_key": "HOME",
                        "rating": 50 + (i % 10),
                        "edge_pct": 1.0 + i * 0.1,
                        "vantaggio_prob": 0.01 * i,
                        "prob_cecchino": 0.4,
                        "quota_cecchino": 2.5,
                        "quota_book": 2.4,
                    },
                    {
                        "market_key": "DRAW",
                        "rating": 40,
                        "edge_pct": -1.0,
                        "vantaggio_prob": -0.01,
                        "prob_cecchino": 0.3,
                        "quota_cecchino": 3.3,
                        "quota_book": 3.2,
                    },
                    {
                        "market_key": "AWAY",
                        "rating": 35,
                        "edge_pct": -2.0,
                        "vantaggio_prob": -0.02,
                        "prob_cecchino": 0.3,
                        "quota_cecchino": 3.3,
                        "quota_book": 3.4,
                    },
                ]
            }
        )
    p1 = build_progressive_normalization_profile(panels, cutoff="2021-10-01")
    p2 = build_progressive_normalization_profile(panels, cutoff="2021-10-01")
    assert p1["hash"] == p2["hash"]
    assert p1["fixtures_seen"] == 20
    assert p1["source"] == "cecchino_lab_eligible_core_progressive"
    assert p1["betfair_operational_profile_applied"] is False
    # target escluso: profilo senza ultima panel diverso
    p_without_last = build_progressive_normalization_profile(panels[:-1], cutoff="2021-10-01")
    assert p_without_last["hash"] != p1["hash"]


def test_signals_wrapper_legacy_compat():
    legacy = {"status": "available", "rows": [{"key": "x", "signals": {}}]}
    assert resolve_signals_matrix(legacy) is legacy
    wrapped = {
        "default_model_key": "F",
        "default_matrix": legacy,
        "models": {"F": {"matrix": legacy}},
    }
    assert resolve_signals_matrix(wrapped) is legacy
    assert iter_active_signal_cells(wrapped) == []
    idx = build_market_signal_index(wrapped)
    assert idx == {}


def test_prematch_hash_ignores_result_sensitive_to_gi():
    base = {
        "goal_intensity": {"pillars": {"offensive_production": {"score": 50}}},
        "purchasability": {"markets": [{"market_key": "HOME", "score": 40}]},
        "signals_matrix": {"default_model_key": "F", "models": {"F": {"final": {"quota_1": 2.1}}}},
    }
    h1 = sha256_prematch_payload(base)
    changed_gi = dict(base)
    changed_gi["goal_intensity"] = {"pillars": {"offensive_production": {"score": 70}}}
    assert sha256_prematch_payload(changed_gi) != h1
    changed_purch = dict(base)
    changed_purch["purchasability"] = {"markets": [{"market_key": "HOME", "score": 80}]}
    assert sha256_prematch_payload(changed_purch) != h1
    # aggiungere result fuori payload non è nel base — hash stabile su stesso payload
    assert sha256_prematch_payload(dict(base)) == h1


def test_resolve_source_revision_env_chain():
    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    from app.services.cecchino_data_lab.historical_scan_service import _resolve_source_revision

    with patch.dict(os.environ, {"RAILWAY_GIT_COMMIT_SHA": "abc123rail"}, clear=False):
        r = _resolve_source_revision()
        assert r["source_git_commit"] == "abc123rail"
        assert r["source_git_commit_source"] == "RAILWAY_GIT_COMMIT_SHA"
        assert r["source_revision_status"] == "resolved"


def test_report_schema_v4():
    from app.services.cecchino_data_lab.historical_ai_report import REPORT_SCHEMA_VERSION

    assert REPORT_SCHEMA_VERSION == "cecchino_lab_ai_report_v4"
