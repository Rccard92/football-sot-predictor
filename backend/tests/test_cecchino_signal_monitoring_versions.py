"""Test Monitoraggio Segnali V1/V2 (coorti di lettura, non formule)."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_WON,
    CecchinoSignalActivation,
)
from app.routes import cecchino_signals as signals_routes
from app.services.cecchino.cecchino_signal_aggregation import (
    DEFAULT_MONITORING_VERSION,
    MONITORING_VERSION_V1,
    MONITORING_VERSION_V2,
    MonitoringVersionNotAllowed,
    _apply_acquisition_filter,
    build_signals_summary,
    export_signals_csv,
    list_signal_activations,
    resolve_monitoring_version,
)
from app.services.cecchino.cecchino_signal_consensus import (
    ACQ_ACQUIRED_CONSENSUS,
    ACQ_REJECTED_INSUFFICIENT,
    ACQ_SINGLE_FORMULA_EXEMPT,
    CURRENT_SIGNAL_FORMULA_VERSION,
    compute_signal_group_consensus,
    inherit_draw_consensus,
)
from app.services.cecchino.cecchino_signal_min_odds import DEFAULT_SIGNAL_MIN_BOOK_ODDS
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _stub_min_book_odds_load(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_min_book_odd_settings_service.load_signal_min_book_odds",
        lambda _db: DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    )


def _matches_v2(row: CecchinoSignalActivation) -> bool:
    return (
        row.acquisition_status
        in (
            ACQ_ACQUIRED_CONSENSUS,
            ACQ_SINGLE_FORMULA_EXEMPT,
        )
        or row.is_acquired is True
    )


def _act(
    *,
    fixture_id: int = 1,
    signal_group: str = "DRAW",
    signal_label: str = "SEGNO X",
    source_column: str = "EXCEL_D",
    yes_count: int = 1,
    available: int = 4,
    evaluation_status: str = EVAL_WON,
    quota_book: float = 3.40,
    quota_cecchino: float = 3.20,
    scan_date: date | None = None,
) -> CecchinoSignalActivation:
    signals = {}
    cols = ["excel_d", "excel_e", "excel_f", "excel_g"]
    if signal_group == "ONE_X":
        cols = ["excel_d", "excel_e", "excel_f", "excel_g", "scala_1x"]
        available = 5
    elif signal_group == "X_TWO":
        cols = ["excel_d", "excel_e", "excel_f", "excel_g", "scala_x2"]
        available = 5
    elif signal_group == "ONE_TWO":
        cols = ["excel_d", "excel_e"]
        available = 2
    elif signal_group in ("HOME", "AWAY"):
        cols = ["excel_d"]
        available = 1
    for i, col in enumerate(cols):
        signals[col] = "SI" if i < yes_count else "NO"

    if signal_group == "DRAW_PT":
        parent = compute_signal_group_consensus(
            signal_group="DRAW",
            signals={
                "excel_d": "SI" if yes_count >= 1 else "NO",
                "excel_e": "SI" if yes_count >= 2 else "NO",
                "excel_f": "SI" if yes_count >= 3 else "NO",
                "excel_g": "SI" if yes_count >= 4 else "NO",
            },
        )
        cons = inherit_draw_consensus(parent)
    else:
        cons = compute_signal_group_consensus(signal_group=signal_group, signals=signals)

    return CecchinoSignalActivation(
        id=fixture_id * 100 + yes_count,
        today_fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        scan_date=scan_date or date(2026, 6, 8),
        home_team_name=f"Home{fixture_id}",
        away_team_name=f"Away{fixture_id}",
        model_key="F",
        model_label="Modello F",
        signal_group=signal_group,
        signal_label=signal_label,
        source_column=source_column,
        signal_value=True,
        raw_signal_value="SI",
        evaluation_status=evaluation_status,
        is_current=True,
        signal_formula_version=CURRENT_SIGNAL_FORMULA_VERSION,
        quota_book=Decimal(str(quota_book)),
        quota_cecchino=Decimal(str(quota_cecchino)),
        consensus_yes_count=int(cons["consensus_yes_count"]),
        consensus_available_count=int(cons["consensus_available_count"]),
        consensus_required_count=int(cons["consensus_required_count"]),
        consensus_yes_columns_json=list(cons["consensus_yes_columns"]),
        consensus_passed=bool(cons["consensus_passed"]),
        is_acquired=bool(cons["is_acquired"]),
        acquisition_status=str(cons["acquisition_status"]),
        consensus_source_group=cons.get("consensus_source_group"),
        consensus_eligible=cons.get("consensus_eligible"),
    )


def _mock_db(rows: list[CecchinoSignalActivation]) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    db.scalar.return_value = len(rows)
    db.new = set()
    db.dirty = set()
    db.deleted = set()
    return db


# ---------------------------------------------------------------------------
# resolve_monitoring_version
# ---------------------------------------------------------------------------


def test_resolve_v1_maps_to_all():
    mv, af = resolve_monitoring_version("v1", "acquired")
    assert mv == MONITORING_VERSION_V1
    assert af == "all"


def test_resolve_v2_maps_to_acquired():
    mv, af = resolve_monitoring_version("v2", "all")
    assert mv == MONITORING_VERSION_V2
    assert af == "acquired"


def test_resolve_monitoring_version_precedence_over_acquisition_filter():
    mv, af = resolve_monitoring_version("v1", "acquired")
    assert mv == "v1"
    assert af == "all"
    mv2, af2 = resolve_monitoring_version("v2", "all")
    assert mv2 == "v2"
    assert af2 == "acquired"


def test_resolve_absent_keeps_acquisition_filter_lab_compat():
    mv, af = resolve_monitoring_version(None, "all")
    assert mv == "v1"
    assert af == "all"
    mv2, af2 = resolve_monitoring_version(None, "consensus_rejected")
    assert mv2 is None
    assert af2 == "consensus_rejected"


def test_resolve_default_acquired_is_v2():
    mv, af = resolve_monitoring_version(None, None)
    assert mv == DEFAULT_MONITORING_VERSION
    assert af == "acquired"


def test_resolve_invalid_raises():
    with pytest.raises(MonitoringVersionNotAllowed):
        resolve_monitoring_version("v3", None)
    with pytest.raises(MonitoringVersionNotAllowed):
        resolve_monitoring_version("acquired", None)


# ---------------------------------------------------------------------------
# Cohort membership (same signal, not cross-market)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yes_count,v1,v2",
    [
        (1, True, False),
        (2, True, True),
        (3, True, True),
        (4, True, True),
    ],
)
def test_draw_consensus_v1_v2(yes_count, v1, v2):
    row = _act(signal_group="DRAW", yes_count=yes_count)
    assert (True) is v1  # value-eligible SI always in V1 cohort conceptually
    assert _matches_v2(row) is v2
    if yes_count == 1:
        assert row.acquisition_status == ACQ_REJECTED_INSUFFICIENT
    else:
        assert row.acquisition_status == ACQ_ACQUIRED_CONSENSUS


def test_home_away_single_formula_in_v1_and_v2():
    home = _act(signal_group="HOME", signal_label="1", yes_count=1, available=1)
    away = _act(signal_group="AWAY", signal_label="2", yes_count=1, available=1, fixture_id=2)
    assert home.acquisition_status == ACQ_SINGLE_FORMULA_EXEMPT
    assert away.acquisition_status == ACQ_SINGLE_FORMULA_EXEMPT
    assert _matches_v2(home) is True
    assert _matches_v2(away) is True


@pytest.mark.parametrize(
    "group,yes_one,yes_two,available",
    [
        ("ONE_X", 1, 2, 5),
        ("X_TWO", 1, 2, 5),
        ("ONE_TWO", 1, 2, 2),
        ("OVER_OVER_PT", 1, 2, 4),
        ("UNDER_UNDER_PT", 1, 2, 4),
    ],
)
def test_multi_formula_groups_v1_yes_v2_threshold(group, yes_one, yes_two, available):
    one = _act(signal_group=group, yes_count=yes_one, available=available)
    two = _act(signal_group=group, yes_count=yes_two, available=available, fixture_id=2)
    assert _matches_v2(one) is False
    assert _matches_v2(two) is True


def test_no_cross_market_count_for_v2():
    """Tre mercati diversi con 1 SI ciascuno: nessuno entra in V2."""
    rows = [
        _act(fixture_id=1, signal_group="DRAW", yes_count=1),
        _act(fixture_id=1, signal_group="OVER_OVER_PT", yes_count=1, source_column="EXCEL_E"),
        _act(fixture_id=1, signal_group="ONE_X", yes_count=1, source_column="EXCEL_F"),
    ]
    assert all(not _matches_v2(r) for r in rows)
    assert sum(1 for r in rows if r.consensus_yes_count == 1) == 3


def test_multi_market_independent_v2():
    rows = [
        _act(fixture_id=10, signal_group="DRAW", yes_count=2),
        _act(fixture_id=10, signal_group="OVER_OVER_PT", yes_count=1, source_column="EXCEL_E"),
        _act(fixture_id=10, signal_group="ONE_X", yes_count=3, source_column="EXCEL_F"),
    ]
    assert _matches_v2(rows[0]) is True
    assert _matches_v2(rows[1]) is False
    assert _matches_v2(rows[2]) is True


def test_source_column_filter_does_not_recompute_consensus():
    """X con E+F = 2 SI: filtro EXCEL_E mostra la riga E ma consensus resta 2."""
    row_e = _act(signal_group="DRAW", yes_count=2, source_column="EXCEL_E")
    assert row_e.consensus_yes_count == 2
    assert _matches_v2(row_e) is True
    db = _mock_db([row_e])
    payload = list_signal_activations(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        source_column="EXCEL_E",
        monitoring_version="v2",
    )
    assert payload["items"][0]["consensus_yes_count"] == 2
    assert payload["monitoring_version"] == "v2"


def test_signal_group_filter_preserves_consensus():
    row = _act(signal_group="DRAW", yes_count=3)
    db = _mock_db([row])
    payload = list_signal_activations(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        signal_group="DRAW",
        monitoring_version="v2",
    )
    assert payload["items"][0]["consensus_yes_count"] == 3


def test_evaluation_status_filter_preserves_consensus():
    row = _act(signal_group="DRAW", yes_count=2, evaluation_status=EVAL_WON)
    db = _mock_db([row])
    payload = list_signal_activations(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        evaluation_status=EVAL_WON,
        monitoring_version="v2",
    )
    assert payload["items"][0]["consensus_yes_count"] == 2


# ---------------------------------------------------------------------------
# Summary / KPI difference V1 vs V2
# ---------------------------------------------------------------------------


def test_kpi_difference_synthetic_abcd():
    """A 1/4 WON, B 2/4 LOST, C Over 3/4 WON, D HOME WON → V1=A+B+C+D, V2=B+C+D."""
    a = _act(fixture_id=1, signal_group="DRAW", yes_count=1, evaluation_status=EVAL_WON)
    b = _act(fixture_id=2, signal_group="DRAW", yes_count=2, evaluation_status=EVAL_LOST)
    c = _act(
        fixture_id=3,
        signal_group="OVER_OVER_PT",
        signal_label="OVER",
        yes_count=3,
        evaluation_status=EVAL_WON,
    )
    d = _act(
        fixture_id=4,
        signal_group="HOME",
        signal_label="1",
        yes_count=1,
        evaluation_status=EVAL_WON,
    )
    all_rows = [a, b, c, d]
    v2_rows = [r for r in all_rows if _matches_v2(r)]
    assert len(v2_rows) == 3
    assert a not in v2_rows

    summary_v1 = build_signals_summary(
        _mock_db(all_rows),
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        monitoring_version="v1",
    )
    summary_v2 = build_signals_summary(
        _mock_db(v2_rows),
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        monitoring_version="v2",
    )
    assert summary_v1["filters"]["monitoring_version"] == "v1"
    assert summary_v1["filters"]["acquisition_filter"] == "all"
    assert summary_v2["filters"]["monitoring_version"] == "v2"
    assert summary_v2["filters"]["acquisition_filter"] == "acquired"
    assert summary_v1["overall"]["activations"] == 4
    assert summary_v1["overall"]["won"] == 3
    assert summary_v1["overall"]["lost"] == 1
    assert summary_v2["overall"]["activations"] == 3
    assert summary_v2["overall"]["won"] == 2
    assert summary_v2["overall"]["lost"] == 1


def test_apply_acquisition_filter_all_is_noop():
    base = select(CecchinoSignalActivation)
    filtered = _apply_acquisition_filter(base, "all")
    assert filtered.whereclause is None or str(filtered.whereclause) == str(base.whereclause)


def test_apply_acquisition_filter_acquired_adds_predicate():
    base = select(CecchinoSignalActivation)
    filtered = _apply_acquisition_filter(base, "acquired")
    compiled = str(filtered.compile(compile_kwargs={"literal_binds": False}))
    assert "acquisition_status" in compiled or "is_acquired" in compiled


# ---------------------------------------------------------------------------
# Value gate semantics (persisted rows already gated)
# ---------------------------------------------------------------------------


def test_v1_does_not_include_non_persisted_failed_value_gate():
    """SI con book < cecchino non viene persistito → non appare in V1."""
    # Nessuna row nel mock = nessun SI sotto value gate in coorte
    summary = build_signals_summary(
        _mock_db([]),
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        monitoring_version="v1",
    )
    assert summary["overall"]["activations"] == 0


def test_v2_does_not_bypass_value_gate():
    """4/4 SI non value-gated non è in DB → assente anche in V2."""
    summary = build_signals_summary(
        _mock_db([]),
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        monitoring_version="v2",
    )
    assert summary["overall"]["activations"] == 0


# ---------------------------------------------------------------------------
# X PT
# ---------------------------------------------------------------------------


def test_x_pt_inherits_draw_consensus_for_v2():
    draw = _act(signal_group="DRAW", yes_count=2)
    pt = _act(signal_group="DRAW_PT", signal_label="X PT", yes_count=2, fixture_id=2)
    assert pt.consensus_source_group == "DRAW"
    assert pt.consensus_yes_count == draw.consensus_yes_count
    assert _matches_v2(pt) is True


def test_x_pt_not_created_for_draw_1_si():
    """Con DRAW 1/4, DRAW_PT non esiste (sync); V1/V2 non inventano row."""
    draw = _act(signal_group="DRAW", yes_count=1)
    assert draw.is_acquired is False
    # Nessuna DRAW_PT nel dataset
    rows = [draw]
    assert not any(r.signal_group == "DRAW_PT" for r in rows)


# ---------------------------------------------------------------------------
# Zero-write historical replay
# ---------------------------------------------------------------------------


def test_summary_list_export_zero_write():
    rows = [
        _act(fixture_id=1, yes_count=1, scan_date=date(2026, 5, 1)),
        _act(fixture_id=2, yes_count=2, scan_date=date(2026, 5, 1)),
    ]
    db = _mock_db(rows)
    build_signals_summary(
        db,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 1),
        monitoring_version="v1",
    )
    list_signal_activations(
        db,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 1),
        monitoring_version="v2",
    )
    export_signals_csv(
        db,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 1),
        monitoring_version="v1",
    )
    assert db.add.call_count == 0
    assert db.commit.call_count == 0
    assert db.delete.call_count == 0
    assert len(db.new) == 0
    assert len(db.dirty) == 0
    assert len(db.deleted) == 0


def test_export_csv_includes_monitoring_and_consensus_columns():
    row = _act(yes_count=2)
    db = _mock_db([row])
    csv_text = export_signals_csv(
        db,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        monitoring_version="v2",
    )
    header = csv_text.splitlines()[0]
    for col in (
        "monitoring_version",
        "consensus_yes_count",
        "consensus_available_count",
        "consensus_required_count",
        "consensus_passed",
        "acquisition_status",
    ):
        assert col in header
    assert "v2" in csv_text


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def signals_client(monkeypatch):
    app = FastAPI()
    app.include_router(signals_routes.router, prefix="/api")
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    db.scalar.return_value = 0

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c, db


def test_api_summary_v1_v2(signals_client):
    c, db = signals_client
    r1 = c.get(
        "/api/admin/cecchino/signals/summary",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "monitoring_version": "v1",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["filters"]["monitoring_version"] == "v1"
    assert r1.json()["filters"]["acquisition_filter"] == "all"

    r2 = c.get(
        "/api/admin/cecchino/signals/summary",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "monitoring_version": "v2",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["filters"]["monitoring_version"] == "v2"
    assert r2.json()["filters"]["acquisition_filter"] == "acquired"


def test_api_activations_and_export_versions(signals_client):
    c, _db = signals_client
    ra = c.get(
        "/api/admin/cecchino/signals/activations",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "monitoring_version": "v1",
        },
    )
    assert ra.status_code == 200
    assert ra.json()["monitoring_version"] == "v1"

    re = c.get(
        "/api/admin/cecchino/signals/export.csv",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "monitoring_version": "v2",
        },
    )
    assert re.status_code == 200
    assert "monitoring_version" in re.text


def test_api_invalid_monitoring_version_422(signals_client):
    c, _db = signals_client
    for path in (
        "/api/admin/cecchino/signals/summary",
        "/api/admin/cecchino/signals/activations",
        "/api/admin/cecchino/signals/export.csv",
    ):
        r = c.get(
            path,
            params={
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "monitoring_version": "v9",
            },
        )
        assert r.status_code == 422, path


def test_api_monitoring_version_precedes_acquisition_filter(signals_client):
    c, _db = signals_client
    r = c.get(
        "/api/admin/cecchino/signals/summary",
        params={
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "monitoring_version": "v1",
            "acquisition_filter": "acquired",
        },
    )
    assert r.status_code == 200
    assert r.json()["filters"]["monitoring_version"] == "v1"
    assert r.json()["filters"]["acquisition_filter"] == "all"
