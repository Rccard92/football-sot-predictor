"""STEP 3C.2 — Acquistabilità V3 ufficiale per Run storiche (resolver, no fallback)."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_lab_purchasability_v3_replay_run import (
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_RUNNING,
)
from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_export import (
    PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver import (
    LEGACY_PURCHASABILITY_FALLBACK_ALLOWED,
    PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE,
    REPLAY_ENGINE_VERSION,
    REPLAY_SCHEMA_VERSION,
    assert_legacy_fallback_forbidden,
    official_purchasability_unavailable_payload,
    resolve_official_purchasability_v3_replay,
    try_resolve_official_purchasability_v3_replay,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_official import (
    build_official_purchasability_section,
)
from app.services.cecchino_data_lab.historical_run_analytics_service import (
    dashboard_purchasability,
)


def _utcnow() -> datetime:
    return datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _replay(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        source_scan_run_id=3,
        status=STATUS_COMPLETED_WITH_WARNINGS,
        replay_schema_version=REPLAY_SCHEMA_VERSION,
        replay_engine_version=REPLAY_ENGINE_VERSION,
        candidate_version=PURCHASABILITY_V3_CANDIDATE_VERSION,
        formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
        audit_version="cecchino_purchasability_v3_audit_v1",
        preflight_schema_version="cecchino_lab_purchasability_v3_replay_preflight_v2",
        integrity_policy_version="integrity_v1",
        completed_at=_utcnow(),
        evaluations_total=36488,
        results_persisted=36488,
        scored_count=13534,
        gate_failed_count=22950,
        unavailable_count=4,
        error_count=0,
        unclassified_count=0,
        real_quote_count=100,
        derived_quote_count=50,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _db_with_replays(
    replays: list[SimpleNamespace], *, result_counts: dict[int, int] | None = None
):
    """Session mock + patch di _results_really_present per conteggi controllati."""
    db = MagicMock()
    result_counts = result_counts or {
        int(r.id): int(r.results_persisted) for r in replays
    }

    def execute(stmt):
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = list(replays)
        mock_res.scalar_one.return_value = 0
        return mock_res

    db.execute.side_effect = execute

    def _present(_db, replay_id: int, expected: int) -> bool:
        counted = result_counts.get(int(replay_id), -1)
        return int(counted) == int(expected) and int(expected) > 0

    # Attach patcher context for callers
    db._result_counts = result_counts
    db._present_fn = _present
    return db


@pytest.fixture
def _patch_results_present():
    """Attiva in ogni test che usa _db_with_replays via helper wrap."""
    yield


def _resolve(db, run_id: int = 3):
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver._results_really_present",
        side_effect=db._present_fn,
    ):
        return resolve_official_purchasability_v3_replay(db, run_id)


def _try_resolve(db, run_id: int = 3):
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_replay_resolver._results_really_present",
        side_effect=db._present_fn,
    ):
        return try_resolve_official_purchasability_v3_replay(db, run_id)


def test_legacy_fallback_constant_false():
    assert LEGACY_PURCHASABILITY_FALLBACK_ALLOWED is False


def test_assert_legacy_fallback_forbidden_raises():
    with pytest.raises(CecchinoLabImportError) as exc:
        assert_legacy_fallback_forbidden(context="test")
    assert exc.value.code == "legacy_purchasability_fallback_forbidden"
    assert exc.value.status_code == 409


def test_resolver_finds_completed_replay():
    r = _replay(status=STATUS_COMPLETED, id=5)
    db = _db_with_replays([r])
    got = _resolve(db, 3)
    assert got.id == 5


def test_resolver_accepts_completed_with_warnings():
    r = _replay(status=STATUS_COMPLETED_WITH_WARNINGS, id=1)
    db = _db_with_replays([r])
    got = _resolve(db, 3)
    assert got.id == 1


def test_resolver_ignores_running():
    r = _replay(status=STATUS_RUNNING, id=2)
    db = _db_with_replays([r])
    assert _try_resolve(db, 3) is None


def test_resolver_ignores_failed():
    r = _replay(status=STATUS_FAILED, id=2)
    db = _db_with_replays([r])
    assert _try_resolve(db, 3) is None


def test_resolver_ignores_incomplete_results():
    r = _replay(results_persisted=100, evaluations_total=36488, id=2)
    db = _db_with_replays([r], result_counts={2: 100})
    assert _try_resolve(db, 3) is None


def test_resolver_ignores_error_count():
    r = _replay(error_count=1, id=2)
    db = _db_with_replays([r])
    assert _try_resolve(db, 3) is None


def test_resolver_ignores_unclassified():
    r = _replay(unclassified_count=3, id=2)
    db = _db_with_replays([r])
    assert _try_resolve(db, 3) is None


def test_resolver_ignores_incompatible_formula():
    r = _replay(formula_version="other_formula", id=2)
    db = _db_with_replays([r])
    assert _try_resolve(db, 3) is None


def test_resolver_chooses_most_recent_completed_at():
    older = _replay(id=1, completed_at=_utcnow() - timedelta(days=2))
    newer = _replay(id=2, completed_at=_utcnow())
    db = _db_with_replays([older, newer])
    got = _resolve(db, 3)
    assert got.id == 2


def test_resolver_tie_break_higher_id():
    a = _replay(id=10, completed_at=_utcnow())
    b = _replay(id=20, completed_at=_utcnow())
    db = _db_with_replays([a, b])
    got = _resolve(db, 3)
    assert got.id == 20


def test_resolver_does_not_hardcode_id_1():
    r = _replay(id=99)
    db = _db_with_replays([r])
    got = _resolve(db, 3)
    assert got.id == 99


def test_resolver_absent_raises_409():
    db = _db_with_replays([])
    with pytest.raises(CecchinoLabImportError) as exc:
        _resolve(db, 3)
    assert exc.value.code == PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE
    assert exc.value.status_code == 409


def test_unavailable_payload_no_legacy():
    payload = official_purchasability_unavailable_payload(source_scan_run_id=3)
    assert payload["status"] == "unavailable"
    assert payload["legacy_fallback_used"] is False
    assert payload["cta"]["path"].endswith("run_id=3")


def test_dashboard_uses_v3_and_exposes_replay_id():
    replay = _replay(id=1)
    analytics = {
        "status": "ready_with_warnings",
        "schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
        "universes": {
            "SCORED_EVALUATIONS": 13534,
            "GATE_FAILED_EVALUATIONS": 22950,
            "UNAVAILABLE_EVALUATIONS": 4,
            "ALL_EVALUATIONS": 36488,
        },
        "reconciliation": {
            "status": "ok",
            "quote_buckets": {"real": 100, "derived": 50},
        },
        "performance_real": {"roi_pct": 1.2},
        "performance_synthetic": {"roi_pct": -0.5},
        "by_market": {},
        "family_decisions": {},
        "score_distribution": {},
        "gate_analysis": {},
        "metadata": {"formula_recomputed": False},
    }
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.try_resolve_official_purchasability_v3_replay",
        return_value=replay,
    ), patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.get_purchasability_v3_replay_analytics",
        return_value=analytics,
    ):
        out = dashboard_purchasability(MagicMock(), 3, {})
    assert out["official_version"] == "V3"
    assert out["replay_id"] == 1
    assert out["scored"] == 13534
    assert out["gate_failed"] == 22950
    assert out["unavailable"] == 4
    assert out["legacy_fallback_used"] is False
    blob = json.dumps(out)
    assert "diagnostic_ungated_score" not in blob
    assert "purchasability_v2" not in blob
    assert "purchasability_v1_1" not in blob


def test_dashboard_unavailable_no_legacy_fallback():
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.try_resolve_official_purchasability_v3_replay",
        return_value=None,
    ):
        out = dashboard_purchasability(MagicMock(), 3, {})
    assert out["status"] == "unavailable"
    assert out["legacy_fallback_used"] is False


def test_ai_summary_section_uses_v3():
    replay = _replay(id=1)
    analytics = {
        "status": "ready",
        "schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
        "universes": {
            "SCORED_EVALUATIONS": 10,
            "GATE_FAILED_EVALUATIONS": 5,
            "UNAVAILABLE_EVALUATIONS": 0,
        },
        "reconciliation": {
            "status": "ok",
            "quote_buckets": {"real": 8, "derived": 2},
        },
        "metadata": {},
    }
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.try_resolve_official_purchasability_v3_replay",
        return_value=replay,
    ), patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.get_purchasability_v3_replay_analytics",
        return_value=analytics,
    ):
        section = build_official_purchasability_section(MagicMock(), 3)
    assert section["official_purchasability_version"] == "V3"
    assert section["replay_id"] == 1
    assert section["formula_recomputed"] is False


def test_ai_summary_section_unavailable_without_legacy():
    with patch(
        "app.services.cecchino_data_lab.historical_purchasability_v3_official.try_resolve_official_purchasability_v3_replay",
        return_value=None,
    ):
        section = build_official_purchasability_section(MagicMock(), 9)
    assert section["status"] == "unavailable"
    assert section["reason"] == PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE


def test_analytics_schema_is_v2():
    assert PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION == (
        "cecchino_lab_purchasability_v3_analytics_v2"
    )


def test_export_schema_is_v2():
    assert PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION == (
        "cecchino_lab_purchasability_v3_export_v2"
    )


def test_analytics_source_has_no_v2_loader():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics as an

    src = open(an.__file__, encoding="utf-8").read()
    assert "_load_v2_markets_batched" not in src
    assert "v2_v3_comparison" not in src
    assert "purchasability_compatibility_json" not in src


def test_export_source_has_no_v2_comparison_file():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as ex

    src = open(ex.__file__, encoding="utf-8").read()
    assert "v2_v3_comparison.json" not in src
    assert "official_purchasability_version" in src


def test_ai_report_does_not_import_legacy_export():
    import app.services.cecchino_data_lab.historical_ai_report as ai_report

    src = open(ai_report.__file__, encoding="utf-8").read()
    assert "historical_purchasability_export" not in src


def test_module_purchasability_short_circuits_to_v3_export():
    from app.services.cecchino_data_lab.historical_ai_report import (
        write_historical_report_zip,
    )

    dest = io.BytesIO()
    replay = _replay(id=7)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=3)

    with patch(
        "app.services.cecchino_data_lab.historical_ai_report.resolve_official_purchasability_v3_replay",
        return_value=replay,
    ) as resolve_mock, patch(
        "app.services.cecchino_data_lab.historical_ai_report.write_purchasability_v3_replay_report_zip",
        return_value=("cecchino-run-3-purchasability-v3.zip", 123),
    ) as write_mock:
        filename, size = write_historical_report_zip(
            db, 3, dest, mode="module", module="purchasability"
        )
    assert filename == "cecchino-run-3-purchasability-v3.zip"
    assert size == 123
    resolve_mock.assert_called_once()
    write_mock.assert_called_once()
    assert write_mock.call_args.kwargs.get("filename_override") == (
        "cecchino-run-3-purchasability-v3.zip"
    )
    assert write_mock.call_args.args[1] == 7


def test_module_purchasability_absent_raises_409():
    from app.services.cecchino_data_lab.historical_ai_report import (
        write_historical_report_zip,
    )

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=3)
    with patch(
        "app.services.cecchino_data_lab.historical_ai_report.resolve_official_purchasability_v3_replay",
        side_effect=CecchinoLabImportError(
            PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE,
            "missing",
            status_code=409,
        ),
    ):
        with pytest.raises(CecchinoLabImportError) as exc:
            write_historical_report_zip(
                db, 3, io.BytesIO(), mode="module", module="purchasability"
            )
    assert exc.value.status_code == 409
    assert exc.value.code == PURCHASABILITY_V3_REPLAY_NOT_AVAILABLE


def test_run_centric_routes_exist():
    from app.routes import cecchino_lab

    paths = {getattr(r, "path", None) for r in cecchino_lab.router.routes}
    assert any(
        p and p.endswith("/historical-scans/{run_id}/purchasability") for p in paths
    )
    assert any(
        p and p.endswith("/historical-scans/{run_id}/purchasability/report")
        for p in paths
    )


def test_replay_direct_routes_unchanged():
    from app.routes import cecchino_lab

    paths = {getattr(r, "path", None) for r in cecchino_lab.router.routes}
    assert any(
        p and "/purchasability-v3-replays/{replay_id}/analytics" in p for p in paths
    )
    assert any(
        p and "/purchasability-v3-replays/{replay_id}/report" in p for p in paths
    )


def test_formula_and_counts_invariants_documented_in_fixture():
    r = _replay()
    assert r.id == 1
    assert r.results_persisted == 36488
    assert r.scored_count == 13534
    assert r.gate_failed_count == 22950
    assert r.unavailable_count == 4
    assert r.error_count == 0
    assert r.unclassified_count == 0
    assert r.formula_version == PURCHASABILITY_V3_FORMULA_VERSION
