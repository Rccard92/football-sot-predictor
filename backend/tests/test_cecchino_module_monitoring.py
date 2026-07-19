"""Test Monitoraggio Moduli — overview + analysis pack ZIP."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_module_monitoring_exports import (
    VALID_MODULE_KEYS,
    analysis_pack_filename,
    build_module_analysis_pack_zip,
    build_module_monitoring_overview,
    build_purchasability_module_overview,
)


def test_valid_module_keys():
    assert "purchasability" in VALID_MODULE_KEYS
    assert "balance-v5" in VALID_MODULE_KEYS
    assert "goal-intensity-v5" in VALID_MODULE_KEYS
    assert "signals" in VALID_MODULE_KEYS


def test_analysis_pack_filename_stable():
    name = analysis_pack_filename("purchasability", date(2026, 1, 1), date(2026, 3, 31))
    assert name == "SOT_MONITOR_purchasability_2026-01-01_2026-03-31.zip"


def test_invalid_module_key_raises():
    with pytest.raises(ValueError):
        build_module_analysis_pack_zip(
            MagicMock(),
            module_key="unknown",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
        )


def test_overview_adapters_independent(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "build_purchasability_module_overview",
        lambda *a, **k: {"module_key": "purchasability", "coverage": None},
    )
    monkeypatch.setattr(
        mon,
        "build_balance_module_overview",
        lambda *a, **k: {"module_key": "balance-v5", "coverage": 0.5},
    )
    monkeypatch.setattr(
        mon,
        "build_goal_intensity_module_overview",
        lambda *a, **k: {"module_key": "goal-intensity-v5", "coverage": None},
    )
    monkeypatch.setattr(
        mon,
        "build_signals_module_overview",
        lambda *a, **k: {"module_key": "signals", "coverage": None},
    )
    out = build_module_monitoring_overview(
        MagicMock(), date_from=date(2026, 1, 1), date_to=date(2026, 3, 1)
    )
    assert len(out["modules"]) == 4
    assert out["modules"][0]["module_key"] == "purchasability"
    assert "generated_at" in out


def test_purchasability_pack_zip_contents(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "build_purchasability_validation_health",
        lambda *a, **k: {"snapshot_persistence_coverage": None, "result_settled_count": 0},
    )
    monkeypatch.setattr(
        mon,
        "build_purchasability_validation_summary",
        lambda *a, **k: {
            "metrics": {"settled": 0},
            "by_score_band": [{"score_band": "ZERO", "rows": 0}],
            "candidate_version": "x",
            "policy_version": "y",
        },
    )
    monkeypatch.setattr(
        mon,
        "build_purchasability_promotion_readiness",
        lambda *a, **k: {
            "status": "collecting_data",
            "warnings": [],
            "data_gates": {},
            "prima_data_teorica_promozione": None,
        },
    )
    monkeypatch.setattr(
        mon,
        "export_purchasability_validation_csv",
        lambda *a, **k: "id,market_key\n1,HOME\n",
    )

    data, filename = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="purchasability",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        include_rows=True,
    )
    assert filename.startswith("SOT_MONITOR_purchasability_")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "README_ANALISI.md" in names
        assert "CHATGPT_HANDOFF.md" in names
        assert "manifest.json" in names
        assert "versions.json" in names
        assert "filters.json" in names
        assert "health.json" in names
        assert "summary.json" in names
        assert "readiness.json" in names
        assert "rows.csv" in names
        handoff = zf.read("CHATGPT_HANDOFF.md").decode("utf-8")
        assert "Acquistabilità" in handoff or "purchasability" in handoff
        assert "Domande consigliate" in handoff
        rows = zf.read("rows.csv")
        assert rows.startswith(b"\xef\xbb\xbf")
        manifest = json.loads(zf.read("manifest.json"))
        assert "secret" not in json.dumps(manifest).lower()
        # JSON strict
        json.loads(zf.read("summary.json"))


@pytest.mark.parametrize(
    "module_key",
    ["balance-v5", "goal-intensity-v5", "signals"],
)
def test_other_module_packs(module_key, monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "build_balance_module_overview",
        lambda *a, **k: {"module_key": "balance-v5", "warnings": []},
    )
    monkeypatch.setattr(
        mon,
        "build_goal_intensity_module_overview",
        lambda *a, **k: {"module_key": "goal-intensity-v5", "warnings": []},
    )
    monkeypatch.setattr(
        mon,
        "build_signals_module_overview",
        lambda *a, **k: {"module_key": "signals", "warnings": []},
    )

    data, filename = build_module_analysis_pack_zip(
        MagicMock(),
        module_key=module_key,
        date_from=date(2026, 2, 1),
        date_to=date(2026, 2, 28),
        include_rows=False,
    )
    assert module_key in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "manifest.json" in zf.namelist()
        assert "CHATGPT_HANDOFF.md" in zf.namelist()
        json.loads(zf.read("filters.json"))


def test_purchasability_overview_empty(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "build_purchasability_validation_health",
        lambda *a, **k: {
            "snapshot_persistence_coverage": None,
            "fixtures_with_kpi_panel": 0,
            "result_settled_count": 0,
        },
    )
    monkeypatch.setattr(
        mon,
        "build_purchasability_promotion_readiness",
        lambda *a, **k: {"status": "collecting_data", "prima_data_teorica_promozione": None},
    )
    out = build_purchasability_module_overview(
        MagicMock(), date_from=date(2026, 1, 1), date_to=date(2026, 1, 10)
    )
    assert out["coverage"] is None
    assert out["warnings"]


def _mock_fixture(
    *,
    output: dict | None,
    settled: bool = False,
):
    row = MagicMock()
    row.cecchino_output_json = output
    row.score_fulltime_home = 1 if settled else None
    row.score_fulltime_away = 0 if settled else None
    return row


def test_extract_balance_v5_canonical_and_legacy():
    from app.services.cecchino.cecchino_module_monitoring_exports import (
        extract_balance_v5_from_today_output,
    )

    assert extract_balance_v5_from_today_output(None) is None
    assert extract_balance_v5_from_today_output({}) is None
    assert (
        extract_balance_v5_from_today_output({"balance_v5": {"status": "unavailable"}})
        is None
    )
    ok = extract_balance_v5_from_today_output(
        {"balance_v5": {"status": "ok", "pillars": {}}}
    )
    assert ok is not None
    legacy = extract_balance_v5_from_today_output(
        {"balance_analysis": {"gap": 1.2, "status": "ok"}}
    )
    assert legacy is not None


def test_balance_overview_settled_subseteq_fixtures(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    rows = [
        _mock_fixture(output={"balance_v5": {"status": "ok", "x": 1}}, settled=True),
        _mock_fixture(output={"balance_v5": {"status": "ok", "x": 1}}, settled=False),
        _mock_fixture(output={}, settled=True),  # eleggibile FT ma senza balance
        _mock_fixture(
            output={"balance_v5": {"status": "unavailable"}}, settled=True
        ),
    ]

    class _Scalars:
        def all(self):
            return rows

    db = MagicMock()
    db.scalars.return_value = _Scalars()

    out = mon.build_balance_module_overview(
        db, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
    )
    assert out["eligible_fixtures"] == 4
    assert out["fixtures"] == 2
    assert out["settled"] == 1
    assert out["settled"] <= out["fixtures"]
    assert out["coverage"] == 0.5
    assert any("persistito" in w for w in out["warnings"]) is False


def test_balance_overview_zero_covered_warning(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    rows = [
        _mock_fixture(output={}, settled=True),
        _mock_fixture(output={}, settled=True),
    ]

    class _Scalars:
        def all(self):
            return rows

    db = MagicMock()
    db.scalars.return_value = _Scalars()
    out = mon.build_balance_module_overview(
        db, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
    )
    assert out["fixtures"] == 0
    assert out["settled"] == 0
    assert out["coverage"] == 0.0
    # Mai Fixture 0 + Settled > 0
    assert not (out["fixtures"] == 0 and (out["settled"] or 0) > 0)
    assert any("persistito" in w for w in out["warnings"])


def test_balance_coverage_null_when_no_eligible():
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    class _Scalars:
        def all(self):
            return []

    db = MagicMock()
    db.scalars.return_value = _Scalars()
    out = mon.build_balance_module_overview(
        db, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
    )
    assert out["coverage"] is None
    assert out["fixtures"] is None
    assert out["settled"] is None


@pytest.mark.parametrize(
    "module_key",
    ["purchasability", "balance-v5", "goal-intensity-v5", "signals"],
)
def test_build_module_rows_csv_bom_and_headers(module_key, monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "export_purchasability_validation_csv",
        lambda *a, **k: "id,market_key\n",
    )
    monkeypatch.setattr(
        mon,
        "build_balance_module_overview",
        lambda *a, **k: {
            "module_key": "balance-v5",
            "eligible_fixtures": 0,
            "covered_fixtures": 0,
            "settled_covered_fixtures": 0,
            "coverage": None,
            "status": "official_monitored",
            "version": "v",
        },
    )
    monkeypatch.setattr(
        mon,
        "build_goal_intensity_module_overview",
        lambda *a, **k: {
            "module_key": "goal-intensity-v5",
            "eligible_fixtures": 0,
            "fixtures": None,
            "settled": None,
            "coverage": None,
            "status": "preview_research",
            "version": "v",
        },
    )
    monkeypatch.setattr(
        mon,
        "build_signals_module_overview",
        lambda *a, **k: {
            "module_key": "signals",
            "fixtures": None,
            "activations": None,
            "settled": None,
            "coverage": None,
            "status": "operational",
            "version": "v",
        },
    )
    data, filename = mon.build_module_rows_csv(
        MagicMock(),
        module_key=module_key,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    assert data.startswith(b"\xef\xbb\xbf")
    assert filename.endswith("_rows.csv")
    assert module_key in filename
    text = data.decode("utf-8-sig")
    assert text.splitlines()[0]  # header presente anche se empty


def test_rows_csv_invalid_key():
    from app.services.cecchino.cecchino_module_monitoring_exports import (
        build_module_rows_csv,
    )

    with pytest.raises(ValueError):
        build_module_rows_csv(
            MagicMock(),
            module_key="nope",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 2),
        )