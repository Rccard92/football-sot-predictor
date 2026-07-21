"""Test integrazione export pack Balance v11 — readiness packaging."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_MONITORING_KEY,
    BALANCE_MONITORING_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_readiness import (
    BALANCE_GOVERNANCE_CSV_FIELDS,
    BALANCE_READINESS_GATES_CSV_FIELDS,
    BALANCE_READINESS_HISTORY_CSV_FIELDS,
    build_balance_readiness_dossier_files,
    build_balance_readiness_forensic_file_payload,
    build_balance_readiness_gate_csv_rows,
    build_balance_readiness_pack_payload,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    SCHEMA_CONTRACTS,
    _build_balance_readiness_export_files,
    _build_balance_readiness_export_placeholders,
    build_module_analysis_pack_zip,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_PROSPECTIVE,
)

DATE_FROM = date(2026, 6, 19)
DATE_TO = date(2026, 7, 20)


def _readiness_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.having.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    q.count.return_value = 0
    q.scalar.return_value = 0
    db.query.return_value = q
    db.scalars.return_value.all.return_value = []
    return db


def _empty_eval_query(*args, **kwargs):
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = []
    q.count.return_value = 0
    q.scalar.return_value = 0
    return q


def _readiness_db_patch_context():
    return patch.multiple(
        "app.services.cecchino.cecchino_balance_v5_readiness",
        _base_q=_empty_eval_query,
        _prospective_settled_q=_empty_eval_query,
        _count=MagicMock(return_value=0),
        _max_updated_at=MagicMock(return_value=None),
    )


def test_gate_csv_rows_join_non_string_reason_codes():
    report = {
        "technical_gates": {
            "gates": [
                {
                    "key": "k1",
                    "reason_codes": [123, "ok"],
                }
            ]
        },
        "scientific_gates": {"gates": []},
    }
    rows = build_balance_readiness_gate_csv_rows(report)
    assert rows[0]["reason_codes"] == "123|ok"


def test_pack_payload_uses_parse_filters():
    db = _readiness_db()
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_pillar_readiness",
        return_value={"pillars": {}},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._count",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._max_updated_at",
        return_value=None,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_readiness_history",
        return_value={"items": [], "count": 0},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_governance_decisions",
        return_value={"items": [], "count": 0},
    ):
        pack = build_balance_readiness_pack_payload(
            db, date_from=DATE_FROM, date_to=DATE_TO
        )
    assert pack["filters"]["date_from"] == DATE_FROM.isoformat()
    assert pack["filters"]["date_to"] == DATE_TO.isoformat()
    assert "report" in pack


def test_readiness_export_placeholders_include_all_schema_csv():
    files = _build_balance_readiness_export_placeholders(
        date_from=DATE_FROM,
        date_to=DATE_TO,
        competition_id=None,
        error="TypeError",
    )
    required = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    for name in required:
        if name.startswith("balance_readiness") or name.startswith("balance_governance"):
            if name.endswith(".csv") or name.endswith(".json"):
                assert name in files or name.replace(".csv", ".json") in files
    assert "balance_readiness_history.csv" in files
    assert "balance_governance_decisions.csv" in files
    hist_header = files["balance_readiness_history.csv"].decode("utf-8-sig").splitlines()[0]
    assert hist_header == ",".join(BALANCE_READINESS_HISTORY_CSV_FIELDS)
    gov_header = files["balance_governance_decisions.csv"].decode("utf-8-sig").splitlines()[0]
    assert gov_header == ",".join(BALANCE_GOVERNANCE_CSV_FIELDS)
    gates_header = files["balance_readiness_gates.csv"].decode("utf-8-sig").splitlines()[0]
    assert gates_header == ",".join(BALANCE_READINESS_GATES_CSV_FIELDS)


def test_readiness_export_files_no_typeerror_with_real_builders():
    db = _readiness_db()
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_pillar_readiness",
        return_value={"pillars": {"f36": {"status": "descriptive_only"}}},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._count",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._max_updated_at",
        return_value=None,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_readiness_history",
        return_value={
            "items": [
                {
                    "snapshot_date": "2026-07-20",
                    "prospective_settled": 0,
                    "prospective_days": 1,
                    "temporal_folds": 0,
                    "scientific_maturity": "prospective_collecting",
                    "current_decision": "continue_monitoring",
                    "readiness_hash": "abc",
                }
            ],
            "count": 1,
        },
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_governance_decisions",
        return_value={"items": [], "count": 0},
    ):
        files, meta = _build_balance_readiness_export_files(
            db,
            date_from=DATE_FROM,
            date_to=DATE_TO,
            competition_id=None,
        )
    overview = json.loads(files["balance_readiness_overview.json"].decode("utf-8"))
    assert overview.get("error") != "TypeError"
    assert "TypeError" not in files["balance_pillar_readiness.json"].decode("utf-8")
    assert "balance_readiness_history.csv" in files
    assert "balance_governance_decisions.csv" in files
    assert meta.get("readiness_scientific_maturity") is not None or overview.get("status")


def test_forensic_payload_matches_dossier_report_shape():
    db = MagicMock()
    db.query.return_value = _empty_eval_query()
    fake_report = {
        "overview": {"status": "ok", "current_decision": "continue_monitoring"},
        "technical_gates": {"gates": []},
        "scientific_gates": {"gates": []},
        "pillars": {},
        "prospective_progress": {},
        "current_decision": {"decision": "continue_monitoring"},
        "decision_contract": {"version": "v"},
        "prospective_collection_health": {"status": "collecting"},
        "policy": {"immutable": True},
    }
    pack = {
        "filters": {"date_from": DATE_FROM, "date_to": DATE_TO, "competition_id": None},
        "report": fake_report,
        "history": {"items": [], "count": 0},
        "governance": {"items": [], "count": 0},
    }
    forensic = build_balance_readiness_forensic_file_payload(pack)
    assert forensic["balance_readiness_overview.json"]["status"] == "ok"
    assert isinstance(forensic["balance_readiness_gates.csv"], list)


def _minimal_balance_export_stubs(monkeypatch):
    """Stub layer non-readiness per ZIP completo."""
    from app.services.cecchino import cecchino_module_monitoring_exports as mon
    from app.services.cecchino.cecchino_balance_v5_monitoring import BALANCE_ROW_FIELDS

    header = ("\ufeff" + ",".join(BALANCE_ROW_FIELDS) + "\n").encode("utf-8")
    row = ("1," + ",".join("x" for _ in BALANCE_ROW_FIELDS[1:]) + "\n").encode("utf-8")

    monitoring_files = {
        "balance_rows.csv": header + row,
        "f36_distribution.csv": b"\xef\xbb\xbfclass,count\n",
        "dominance_distribution.csv": b"\xef\xbb\xbfclass,count\n",
        "draw_credibility_distribution.csv": b"\xef\xbb\xbfclass,count\n",
        "gap_distribution.csv": b"\xef\xbb\xbfclass,count\n",
        "monthly_timeseries.csv": b"\xef\xbb\xbfmonth\n",
        "snapshot_health.json": b"{}",
        "source_cohort_distribution.json": b"{}",
        "version_definition.json": b"{}",
        "draw_credibility_research.json": b"{}",
    }
    required = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    empirical_names = {
        "empirical_dataset_rows.csv",
        "empirical_dataset_health.json",
        "empirical_target_contract.json",
        "empirical_cardinality.json",
        "empirical_source_cohorts.csv",
        "empirical_evaluation_status.csv",
    }
    readiness_names = {
        n
        for n in required
        if n.startswith("balance_readiness")
        or n.startswith("balance_pillar")
        or n.startswith("balance_prospective")
        or n.startswith("balance_current")
        or n.startswith("balance_decision")
        or n.startswith("balance_governance")
    }

    def _stub(name: str) -> bytes:
        return b"\xef\xbb\xbfcol\n" if name.endswith(".csv") else b"{}"

    analysis_files = {
        name: _stub(name)
        for name in required
        if name not in monitoring_files
        and name not in empirical_names
        and name not in readiness_names
        and name != "balance_empirical_reconciliation.json"
    }
    empirical_files = {name: _stub(name) for name in empirical_names}

    monkeypatch.setattr(mon, "build_balance_export_files", lambda *a, **k: monitoring_files)
    monkeypatch.setattr(mon, "_build_balance_empirical_export_files", lambda *a, **k: empirical_files)
    monkeypatch.setattr(mon, "_build_balance_analysis_export_files", lambda *a, **k: analysis_files)
    monkeypatch.setattr(
        mon,
        "build_balance_monitoring_rows",
        lambda *a, **k: [
            {"today_fixture_id": i, "source_cohort": COHORT_PROSPECTIVE, "snapshot_timestamp": "2026-06-20T10:00:00+00:00", "pre_match_verified": True}
            for i in range(978)
        ],
    )
    monkeypatch.setattr(
        mon,
        "build_balance_module_overview",
        lambda *a, **k: {
            "version": "cecchino_balance_v5_v2",
            "warnings": [],
            "eligible_fixtures": 978,
            "prospective_persisted": 14,
            "legacy_derived_diagnostic": 5,
            "last_snapshot_at": "2026-06-20T10:00:00+00:00",
            "source_cohorts": {COHORT_PROSPECTIVE: 14, COHORT_HISTORICAL_DIAGNOSTIC: 5},
        },
    )
    import app.services.cecchino.cecchino_draw_credibility_research as draw_research

    monkeypatch.setattr(
        draw_research,
        "build_draw_credibility_coverage_audit",
        lambda *a, **k: {"status": "unavailable", "counts": {}},
    )


def test_balance_zip_readiness_files_present_without_typeerror(monkeypatch):
    db = _readiness_db()
    _minimal_balance_export_stubs(monkeypatch)

    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_pillar_readiness",
        return_value={"pillars": {}},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._count",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._max_updated_at",
        return_value=None,
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_prospective_progress",
        return_value={
            "prospective_pending": 14,
            "ratios": {"prospective_settled": {"numerator": 0, "denominator": 1500}},
        },
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_readiness_history",
        return_value={"items": [], "count": 0},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_governance_decisions",
        return_value={"items": [], "count": 0},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_empirical_reconciliation",
        return_value={
            "status": "ok",
            "balance_monitoring_rows": 978,
            "empirical_current_rows": 983,
            "intersection_rows": 978,
            "only_monitoring_count": 0,
            "only_empirical_count": 5,
            "counts_by_reason": {"only_empirical_historical_diagnostic": 5},
            "reconciliation_status": "explained",
        },
    ):
        data, _ = build_module_analysis_pack_zip(
            db,
            module_key="balance-v5",
            date_from=DATE_FROM,
            date_to=DATE_TO,
            include_rows=True,
        )

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "balance_readiness_history.csv" in names
        assert "balance_governance_decisions.csv" in names
        for fname in (
            "balance_readiness_overview.json",
            "balance_current_decision.json",
            "balance_pillar_readiness.json",
            "balance_prospective_progress.json",
            "balance_prospective_collection_health.json",
        ):
            body = json.loads(zf.read(fname).decode("utf-8"))
            assert body.get("error") != "TypeError"
        audit = json.loads(zf.read("export_audit.json").decode("utf-8"))
        assert audit.get("missing_files") == []
        assert audit.get("technical_status") == "pass"
        assert audit.get("scientific_status") in {"partial_collecting", "partial", "exploratory"}
        recon = json.loads(zf.read("balance_empirical_reconciliation.json").decode("utf-8"))
        assert recon.get("reconciliation_status") == "explained"
