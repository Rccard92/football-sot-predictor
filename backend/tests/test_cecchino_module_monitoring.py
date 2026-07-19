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
