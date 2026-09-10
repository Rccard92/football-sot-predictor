"""Test mirati hardening RUN V2: provenance O/U, OU05 buyability, equilibrium, signals, AI bundle."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_0_5,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS
from app.services.cecchino_data_lab.run_v2.market_rows import _equilibrium_state
from app.services.cecchino_data_lab.run_v2.purchasability_v2 import (
    SOURCE_DC_FAIR_V2,
    _resolve_dc_fair_book_v2,
    _resolve_ou05_fair_book,
    _score_dc_items,
    _score_ou05_items,
    build_run_v2_purchasability,
)
from app.services.cecchino_data_lab.run_v2.quote_provenance import (
    OU_REAL_ONLY_KEYS,
    OU_SOURCE_COLUMN_BY_KEY,
    QuoteProvenanceError,
    align_strict_quote_provenance,
    build_market_provenance_matrix,
    enforce_ou_real_only,
    sync_kpi_rows_to_strict,
)
from app.services.cecchino_data_lab.run_v2.column_registry import full_export_columns


def _ou_entry(mk: str, value: float) -> dict:
    col = OU_SOURCE_COLUMN_BY_KEY[mk]
    return {
        "market_key": mk,
        "value": value,
        "is_real_quote": True,
        "is_derived": False,
        "source_column": col,
        "quote_source": "bet365_enrichment_closing_pre_kickoff",
        "pre_match_input_safe": True,
        "used_for_prediction": True,
        "economic_observation_only": False,
    }


def test_ou_present_marked_derived_fails():
    strict = {SEL_OVER_0_5: _ou_entry(SEL_OVER_0_5, 1.25)}
    strict[SEL_OVER_0_5]["is_derived"] = True
    strict[SEL_OVER_0_5]["is_real_quote"] = False
    with pytest.raises(QuoteProvenanceError) as exc:
        enforce_ou_real_only(strict)
    assert exc.value.violations


def test_align_and_sync_eight_ou_markets_real_only():
    strict = {
        SEL_OVER_0_5: _ou_entry(SEL_OVER_0_5, 1.18),
        SEL_UNDER_0_5: _ou_entry(SEL_UNDER_0_5, 5.50),
        SEL_OVER_1_5: _ou_entry(SEL_OVER_1_5, 1.40),
        SEL_UNDER_1_5: _ou_entry(SEL_UNDER_1_5, 2.90),
        SEL_OVER_2_5: {
            **_ou_entry(SEL_OVER_2_5, 1.85),
            "quote_source": "bet365_pre_reference_v4",
        },
        SEL_UNDER_2_5: {
            **_ou_entry(SEL_UNDER_2_5, 2.05),
            "quote_source": "bet365_pre_reference_v4",
        },
        SEL_OVER_3_5: _ou_entry(SEL_OVER_3_5, 2.40),
        SEL_UNDER_3_5: _ou_entry(SEL_UNDER_3_5, 1.55),
    }
    # Simula flag errati da adapter: align deve ripristinare REAL.
    for mk in OU_REAL_ONLY_KEYS:
        strict[mk]["is_derived"] = True
        strict[mk]["is_real_quote"] = False

    aligned = align_strict_quote_provenance(strict)
    for mk in OU_REAL_ONLY_KEYS:
        e = aligned[mk]
        assert e["is_real_quote"] is True
        assert e["is_derived"] is False
        assert e["source_column"] == OU_SOURCE_COLUMN_BY_KEY[mk]
        assert e["used_for_prediction"] is True
        assert e["pre_match_input_safe"] is True
        assert e["economic_observation_only"] is False

    panel = {
        "rows": [
            {
                "market_key": mk,
                "quota_book": 9.99,
                "book_source": "derived_from_something",
                "edge_pct": 1.0,
            }
            for mk in OU_REAL_ONLY_KEYS
        ]
    }
    synced = sync_kpi_rows_to_strict(panel, strict_by_market=aligned)
    for row in synced["rows"]:
        mk = row["market_key"]
        assert row["quota_book"] == round(float(aligned[mk]["value"]), 3)
        assert "derived" not in str(row["book_source"]).lower()
        assert row["book_quote_class"] == "real_bet365"


def test_dc_real_required_derived_fallback_allowed():
    strict = {
        SEL_ONE_X: {
            "value": 1.40,
            "is_real_quote": True,
            "is_derived": False,
            "source_column": "bet365_dc_1x",
            "quote_source": "bet365_enrichment_closing_pre_kickoff",
            "used_for_prediction": True,
            "pre_match_input_safe": True,
            "economic_observation_only": False,
        },
        SEL_X_TWO: {
            "value": 1.55,
            "is_real_quote": False,
            "is_derived": True,
            "source_column": None,
            "quote_source": "derived_from_bet365_1x2",
            "derivation_method": "1x2_sum",
            "used_for_prediction": True,
            "pre_match_input_safe": True,
            "economic_observation_only": False,
        },
    }
    aligned = align_strict_quote_provenance(strict)
    assert aligned[SEL_ONE_X]["is_real_quote"] is True
    assert aligned[SEL_ONE_X]["is_derived"] is False
    assert aligned[SEL_X_TWO]["is_derived"] is True
    assert aligned[SEL_X_TWO]["is_real_quote"] is False


def test_ou05_fair_book_verified():
    by_mk = {
        SEL_OVER_0_5: {"market_key": SEL_OVER_0_5, "quota_book": 1.22},
        SEL_UNDER_0_5: {"market_key": SEL_UNDER_0_5, "quota_book": 4.80},
    }
    fair = _resolve_ou05_fair_book(by_mk)
    assert fair[SEL_OVER_0_5]["fair_book_probability_verified"] is True
    assert fair[SEL_UNDER_0_5]["fair_book_probability_verified"] is True
    assert fair[SEL_OVER_0_5]["fair_book_probability"] is not None


def test_ou05_purchasability_not_missing_fair_book():
    panel = {
        "rows": [
            {
                "market_key": SEL_OVER_0_5,
                "quota_book": 1.20,
                "prob_cecchino": 0.78,
                "rating": 72,
                "book_source": "bet365_enrichment_closing_pre_kickoff",
                "edge_pct": 8.0,
            },
            {
                "market_key": SEL_UNDER_0_5,
                "quota_book": 5.00,
                "prob_cecchino": 0.18,
                "rating": 40,
                "book_source": "bet365_enrichment_closing_pre_kickoff",
                "edge_pct": -2.0,
            },
        ]
    }
    items = _score_ou05_items(
        kpi_panel=panel,
        fixture_meta={
            "today_fixture_id": 1,
            "kickoff": "2021-08-15T15:00:00+00:00",
            "snapshot_at": "2021-08-15T14:00:00+00:00",
        },
    )
    assert len(items) == 2
    for it in items:
        gate = it.get("gate") if isinstance(it.get("gate"), dict) else {}
        reasons = list(gate.get("gate_reason_codes") or [])
        reasons += list(it.get("gate_reason_codes") or [])
        # Accetta score o altri fail di gate V35, ma non missing_fair_book.
        assert "missing_fair_book_probability" not in reasons
        assert it.get("status") is not None


def _strict_1x2_complete() -> dict:
    return {
        SEL_HOME: {
            "value": 2.10,
            "is_real_quote": True,
            "is_derived": False,
            "quote_source": "bet365_enrichment_closing_pre_kickoff",
            "source_column": "bet365_home",
        },
        SEL_DRAW: {
            "value": 3.40,
            "is_real_quote": True,
            "is_derived": False,
            "quote_source": "bet365_enrichment_closing_pre_kickoff",
            "source_column": "bet365_draw",
        },
        SEL_AWAY: {
            "value": 3.50,
            "is_real_quote": True,
            "is_derived": False,
            "quote_source": "bet365_enrichment_closing_pre_kickoff",
            "source_column": "bet365_away",
        },
    }


def _dc_fixture_meta() -> dict:
    return {
        "today_fixture_id": 1,
        "kickoff": "2021-08-15T15:00:00+00:00",
        "snapshot_at": "2021-08-15T14:00:00+00:00",
    }


def _dc_real_row(
    mk: str,
    *,
    quota: float,
    prob: float,
    rating: float = 72,
    **extra,
) -> dict:
    row = {
        "market_key": mk,
        "quota_book": quota,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "bet365_enrichment_closing_pre_kickoff",
        "book_quote_class": "real_bet365",
        "derived_quote": False,
        "is_real_quote": True,
        "real_dc_quote": True,
        "edge_pct": 10.0,
    }
    row.update(extra)
    return row


def _gate_reasons(item: dict) -> list[str]:
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    reasons = list(gate.get("gate_reason_codes") or [])
    reasons += list(item.get("gate_reason_codes") or [])
    return reasons


def test_dc_fair_v2_a_real_plus_strict_trio_scores():
    """A) DC REAL + STRICT 1X2 completo + model/gate ok → score."""
    strict = _strict_1x2_complete()
    fair = _resolve_dc_fair_book_v2(strict)
    assert fair[SEL_ONE_X]["fair_book_probability_verified"] is True
    assert fair[SEL_ONE_X]["fair_book_probability_source"] == SOURCE_DC_FAIR_V2
    p_fair = float(fair[SEL_ONE_X]["fair_book_probability"])
    # Model sopra fair e EV>0 con quota 1.45.
    panel = {
        "rows": [
            _dc_real_row(SEL_ONE_X, quota=1.45, prob=max(0.85, p_fair + 0.12)),
            _dc_real_row(SEL_ONE_TWO, quota=1.50, prob=0.55, rating=55),
            _dc_real_row(SEL_X_TWO, quota=1.60, prob=0.40, rating=40),
        ]
    }
    items, _ = _score_dc_items(
        kpi_panel=panel,
        fixture_meta=_dc_fixture_meta(),
        strict_by_market=strict,
    )
    by_mk = {it["market_key"]: it for it in items}
    one_x = by_mk[SEL_ONE_X]
    assert one_x["status"] == "score"
    assert one_x["reference"]["score"] is not None
    assert one_x["reference"]["class"] is not None
    assert "missing_fair_book_probability" not in _gate_reasons(one_x)
    assert one_x["input"]["execution_quote_real"] is True
    assert one_x["input"]["fair_book_probability"] == pytest.approx(p_fair, rel=1e-6)


def test_dc_fair_v2_b_gate_failed_not_not_calculable():
    """B) DC REAL + fair ok ma rating insufficiente → gate_failed."""
    strict = _strict_1x2_complete()
    panel = {
        "rows": [
            _dc_real_row(SEL_ONE_X, quota=1.45, prob=0.90, rating=40),
            _dc_real_row(SEL_ONE_TWO, quota=1.50, prob=0.55, rating=40),
            _dc_real_row(SEL_X_TWO, quota=1.60, prob=0.40, rating=40),
        ]
    }
    items, _ = _score_dc_items(
        kpi_panel=panel,
        fixture_meta=_dc_fixture_meta(),
        strict_by_market=strict,
    )
    one_x = next(it for it in items if it["market_key"] == SEL_ONE_X)
    assert one_x["status"] == "gate_failed"
    assert one_x["status"] != "not_calculable"
    assert "missing_fair_book_probability" not in _gate_reasons(one_x)
    assert "rating_below_50" in _gate_reasons(one_x)


def test_dc_fair_v2_c_derived_execution_not_calculable():
    """C) DC derived → not_calculable + execution_quote_not_real."""
    strict = _strict_1x2_complete()
    panel = {
        "rows": [
            {
                "market_key": SEL_ONE_X,
                "quota_book": 1.45,
                "prob_cecchino": 0.90,
                "rating": 72,
                "book_source": "derived_from_bet365_1x2",
                "derived_quote": True,
                "is_real_quote": False,
                "force_derived_quote": True,
            },
            _dc_real_row(SEL_ONE_TWO, quota=1.50, prob=0.55),
            _dc_real_row(SEL_X_TWO, quota=1.60, prob=0.40),
        ]
    }
    items, _ = _score_dc_items(
        kpi_panel=panel,
        fixture_meta=_dc_fixture_meta(),
        strict_by_market=strict,
    )
    one_x = next(it for it in items if it["market_key"] == SEL_ONE_X)
    assert one_x["status"] == "not_calculable"
    assert "execution_quote_not_real" in _gate_reasons(one_x)


def test_dc_fair_v2_d_incomplete_strict_trio_missing_fair():
    """D) DC REAL ma trio STRICT incompleto → missing_fair_book_probability."""
    strict = {
        SEL_HOME: {
            "value": 2.10,
            "is_real_quote": True,
            "is_derived": False,
            "quote_source": "bet365_enrichment_closing_pre_kickoff",
        },
        # DRAW/AWAY mancanti
    }
    fair = _resolve_dc_fair_book_v2(strict)
    assert fair[SEL_ONE_X]["fair_book_probability_verified"] is False
    assert fair[SEL_ONE_X]["fair_book_probability"] is None
    assert fair[SEL_ONE_X]["exclusion_reason"] == "incomplete_market"

    panel = {
        "rows": [
            _dc_real_row(SEL_ONE_X, quota=1.45, prob=0.90),
            # KPI 1X2 presenti (V1 potrebbe risolvere) ma VIETATO usarli.
            {
                "market_key": SEL_HOME,
                "quota_book": 2.10,
                "prob_cecchino": 0.45,
                "rating": 60,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-1",
            },
            {
                "market_key": SEL_DRAW,
                "quota_book": 3.40,
                "prob_cecchino": 0.28,
                "rating": 55,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-1",
            },
            {
                "market_key": SEL_AWAY,
                "quota_book": 3.50,
                "prob_cecchino": 0.27,
                "rating": 55,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-1",
            },
        ]
    }
    items, _ = _score_dc_items(
        kpi_panel=panel,
        fixture_meta=_dc_fixture_meta(),
        strict_by_market=strict,
    )
    one_x = next(it for it in items if it["market_key"] == SEL_ONE_X)
    assert one_x["status"] == "not_calculable"
    assert "missing_fair_book_probability" in _gate_reasons(one_x)


def test_dc_fair_v2_e_kpi_provider_mismatch_does_not_block_strict_fair():
    """E) KPI 1X2 con bookmaker/provider diversi: fair da STRICT, execution REAL invariata."""
    strict = _strict_1x2_complete()
    panel = {
        "rows": [
            _dc_real_row(
                SEL_ONE_X,
                quota=1.45,
                prob=0.90,
                bookmaker_name="Bet365",
                bookmaker_provider_id="b365",
            ),
            {
                "market_key": SEL_HOME,
                "quota_book": 9.99,
                "prob_cecchino": 0.10,
                "rating": 50,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-other",
            },
            {
                "market_key": SEL_DRAW,
                "quota_book": 9.99,
                "prob_cecchino": 0.10,
                "rating": 50,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-other",
            },
            {
                "market_key": SEL_AWAY,
                "quota_book": 9.99,
                "prob_cecchino": 0.10,
                "rating": 50,
                "book_source": "betfair_raw_match_winner",
                "bookmaker_name": "Betfair",
                "bookmaker_provider_id": "bf-other",
            },
        ]
    }
    # Snapshot pre-score execution flags.
    dc_row = panel["rows"][0]
    before = {
        "is_real_quote": dc_row["is_real_quote"],
        "derived_quote": dc_row["derived_quote"],
        "quota_book": dc_row["quota_book"],
        "book_source": dc_row["book_source"],
    }
    expected_fair = _resolve_dc_fair_book_v2(strict)[SEL_ONE_X]["fair_book_probability"]
    items, dc_fair = _score_dc_items(
        kpi_panel=panel,
        fixture_meta=_dc_fixture_meta(),
        strict_by_market=strict,
    )
    one_x = next(it for it in items if it["market_key"] == SEL_ONE_X)
    assert dc_fair[SEL_ONE_X]["fair_book_probability_verified"] is True
    assert dc_fair[SEL_ONE_X]["fair_book_probability_source"] == SOURCE_DC_FAIR_V2
    assert one_x["input"]["fair_book_probability"] == pytest.approx(
        float(expected_fair), rel=1e-6
    )
    assert "missing_fair_book_probability" not in _gate_reasons(one_x)
    # Fair non ha mutato execution sulla riga KPI.
    assert dc_row["is_real_quote"] is before["is_real_quote"]
    assert dc_row["derived_quote"] is before["derived_quote"]
    assert dc_row["quota_book"] == before["quota_book"]
    assert dc_row["book_source"] == before["book_source"]
    assert one_x["input"]["execution_quote_real"] is True


def test_dc_fair_v2_build_payload_exports_diagnostics():
    """Compact markets espongono status/gate/fair provenance."""
    match = SimpleNamespace(
        id=42,
        kickoff_at=__import__("datetime").datetime(2021, 8, 15, 15, 0, tzinfo=__import__("datetime").timezone.utc),
        home_team="A",
        away_team="B",
    )
    strict = _strict_1x2_complete()
    panel = {
        "rows": [
            _dc_real_row(SEL_ONE_X, quota=1.45, prob=0.90),
            _dc_real_row(SEL_ONE_TWO, quota=1.50, prob=0.55, rating=55),
            _dc_real_row(SEL_X_TWO, quota=1.60, prob=0.40, rating=40),
            {
                "market_key": SEL_HOME,
                "quota_book": 2.10,
                "prob_cecchino": 0.45,
                "rating": 60,
                "book_source": "betfair_raw_match_winner",
            },
            {
                "market_key": SEL_DRAW,
                "quota_book": 3.40,
                "prob_cecchino": 0.28,
                "rating": 55,
                "book_source": "betfair_raw_match_winner",
            },
            {
                "market_key": SEL_AWAY,
                "quota_book": 3.50,
                "prob_cecchino": 0.27,
                "rating": 55,
                "book_source": "betfair_raw_match_winner",
            },
        ]
    }
    payload = build_run_v2_purchasability(
        kpi_panel=panel,
        match=match,
        season_label="2021-2022",
        competition_name="EPL",
        strict_by_market=strict,
    )
    assert payload.get("run_v2_dc_fair_strict_overlay") is True
    assert payload.get("dc_fair_probability_source") == SOURCE_DC_FAIR_V2
    by_mk = {m["market_key"]: m for m in payload["markets"] if isinstance(m, dict)}
    one_x = by_mk[SEL_ONE_X]
    assert one_x.get("v2_only_dc_fair_strict") is True
    assert one_x.get("status") == "score"
    assert one_x.get("gate_status") is not None
    assert isinstance(one_x.get("gate_reason_codes"), list)
    assert one_x.get("fair_book_probability") is not None
    assert one_x.get("fair_book_probability_source") == SOURCE_DC_FAIR_V2


def test_equilibrium_state_from_balance_v5_payload():
    balance = {
        "status": "ok",
        "structural_summary": "Geometria: Equilibrio. Dominanza: moderata.",
        "pillars": {
            "f36": {"class_key": "balance", "class_label": "Equilibrio"},
            "dominance": {"class_label": "moderata"},
        },
    }
    assert _equilibrium_state(balance) == "balance"


def test_full_export_includes_signals_columns():
    cols = {c.column for c in full_export_columns()}
    assert "core_signals_observation_status" in cols
    assert "core_signals_default_model_key" in cols
    assert "core_signals_active_count" in cols


def test_provenance_matrix_has_17_markets():
    strict = {}
    for m in CORE_MARKETS:
        col = m.strict_quote_columns[0] if m.strict_quote_columns else None
        if m.key in OU_REAL_ONLY_KEYS:
            strict[m.key] = _ou_entry(m.key, 1.90 if "OVER" in m.key else 2.10)
        else:
            strict[m.key] = {
                "value": 2.0,
                "is_real_quote": True,
                "is_derived": False,
                "source_column": col,
                "used_for_prediction": True,
                "pre_match_input_safe": True,
                "economic_observation_only": False,
            }
    matrix = build_market_provenance_matrix(strict_by_market=strict)
    assert len(matrix) == 17
    assert {r["market_key"] for r in matrix} == {m.key for m in CORE_MARKETS}


def test_ai_bundle_zip_members(monkeypatch, tmp_path):
    from app.services.cecchino_data_lab.run_v2 import ai_bundle as ai_mod

    run = SimpleNamespace(
        id=99,
        module_policy_json={"season_label": "2021/2022"},
        run_scope="balanced_pilot",
        status="completed",
        run_version="cecchino_run_v2",
        matches_total=10,
    )

    def fake_bundle(db, *, run_id, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, content in [
            ("FULL.csv", "a,b\n1,2\n"),
            ("core_markets_long.csv", "a,b\n1,2\n3,4\n"),
            ("SOURCE_RAW.csv", "lab_match_id,x\n1,y\n"),
            ("DATA_DICTIONARY.json", json.dumps({"ok": True})),
            ("run_summary.json", json.dumps({"matches": 10, "competitions": [], "leakage_audit": {}})),
        ]:
            p = output_dir / f"cecchino_run_v2_{run_id}_{name}"
            p.write_text(content, encoding="utf-8")
            files[name] = str(p)
        return {"files": files, "counts": {"full_rows": 1}}

    monkeypatch.setattr(ai_mod, "build_export_bundle", fake_bundle)

    class FakeDb:
        def get(self, model, pk):
            return run

    buf = io.BytesIO()
    filename, size = ai_mod.write_ai_bundle_zip(FakeDb(), 99, buf)
    assert "2021-2022" in filename
    assert "RUN_99" in filename
    assert size > 0
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        names = set(zf.namelist())
    assert names == set(ai_mod.ZIP_MEMBERS)
