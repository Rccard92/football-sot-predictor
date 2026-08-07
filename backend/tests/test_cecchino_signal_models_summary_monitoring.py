"""SIGNALS-MON-02.1 — models-summary segue coorte Monitoraggio V1/V2."""

from __future__ import annotations

import inspect
import os
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON, CecchinoSignalActivation
from app.routes import cecchino_signals as signals_routes
from app.services.cecchino.cecchino_signal_consensus import (
    ACQ_ACQUIRED_CONSENSUS,
    ACQ_REJECTED_INSUFFICIENT,
    ACQ_SINGLE_FORMULA_EXEMPT,
    CURRENT_SIGNAL_FORMULA_VERSION,
    compute_signal_group_consensus,
)
from app.services.cecchino.cecchino_signal_model_backtest import (
    _load_model_activations,
    _model_bucket_from_activations,
    build_models_summary,
)


def _act(
    *,
    model_key: str = "A",
    fixture_id: int = 1,
    signal_group: str = "DRAW",
    signal_label: str = "SEGNO X",
    source_column: str = "EXCEL_D",
    yes_count: int = 1,
    evaluation_status: str = EVAL_WON,
    quota_book: float = 3.40,
    signal_value: bool = True,
    is_current: bool = True,
) -> CecchinoSignalActivation:
    signals: dict[str, str] = {}
    cols = ["excel_d", "excel_e", "excel_f", "excel_g"]
    available = 4
    if signal_group in ("HOME", "AWAY"):
        cols = ["excel_d"]
        available = 1
    for i, col in enumerate(cols):
        signals[col] = "SI" if i < yes_count else "NO"

    cons = compute_signal_group_consensus(signal_group=signal_group, signals=signals)
    row = CecchinoSignalActivation(
        id=fixture_id * 1000 + yes_count + ord(model_key[0]),
        today_fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        scan_date=date(2026, 6, 8),
        home_team_name=f"Home{fixture_id}",
        away_team_name=f"Away{fixture_id}",
        model_key=model_key,
        model_label=f"Modello {model_key}",
        signal_group=signal_group,
        signal_label=signal_label,
        source_column=source_column,
        signal_value=signal_value,
        raw_signal_value="SI",
        evaluation_status=evaluation_status,
        is_current=is_current,
        signal_formula_version=CURRENT_SIGNAL_FORMULA_VERSION,
        quota_book=Decimal(str(quota_book)),
        quota_cecchino=Decimal("3.20"),
        consensus_yes_count=int(cons["consensus_yes_count"]),
        consensus_available_count=int(cons["consensus_available_count"]),
        consensus_required_count=int(cons["consensus_required_count"]),
        consensus_yes_columns_json=list(cons["consensus_yes_columns"]),
        consensus_passed=bool(cons["consensus_passed"]),
        is_acquired=bool(cons["is_acquired"]),
        acquisition_status=str(cons["acquisition_status"]),
        target_market_key=signal_group,
    )
    return row


def _model_from_payload(payload: dict, key: str) -> dict:
    return next(m for m in payload["models"] if m["model_key"] == key)


def _patch_load(rows_by_model: dict[str, list[CecchinoSignalActivation]]):
    def _load(_db, *, date_from, date_to, model_key, formula_version=CURRENT_SIGNAL_FORMULA_VERSION):
        return list(rows_by_model.get(model_key, []))

    return patch(
        "app.services.cecchino.cecchino_signal_model_backtest._load_model_activations",
        side_effect=_load,
    )


# ---------------------------------------------------------------------------
# Load contract: value-gated, not raw SI
# ---------------------------------------------------------------------------


def test_load_model_activations_is_value_gated_and_current():
    src = inspect.getsource(_load_model_activations)
    assert "signal_value.is_(True)" in src
    assert "is_current.is_(True)" in src


def test_v1_does_not_include_non_value_rows_outside_load():
    """only_acquired=False non espone raw SI: il load esclude già signal_value=False."""
    non_value = _act(model_key="A", yes_count=1, signal_value=False, fixture_id=1)
    value_rejected = _act(model_key="A", yes_count=1, signal_value=True, fixture_id=2)
    assert non_value.acquisition_status == ACQ_REJECTED_INSUFFICIENT
    # Simula contratto persistenza: load restituisce solo value-gated
    with _patch_load({"A": [value_rejected]}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
    card = _model_from_payload(v1, "A")
    assert card["activations"] == 1
    assert non_value not in [value_rejected]


# ---------------------------------------------------------------------------
# Cohort A/B/C
# ---------------------------------------------------------------------------


def test_rejected_1_of_4_counted_in_v1_not_v2():
    rejected = _act(model_key="A", yes_count=1, evaluation_status=EVAL_WON)
    assert rejected.acquisition_status == ACQ_REJECTED_INSUFFICIENT
    assert rejected.is_acquired is False

    with _patch_load({"A": [rejected]}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )

    assert _model_from_payload(v1, "A")["activations"] == 1
    assert _model_from_payload(v1, "A")["won"] == 1
    assert _model_from_payload(v2, "A")["activations"] == 0
    assert _model_from_payload(v2, "A")["won"] == 0


def test_acquired_2_of_4_counted_in_v1_and_v2():
    acquired = _act(model_key="A", yes_count=2, evaluation_status=EVAL_LOST)
    assert acquired.acquisition_status == ACQ_ACQUIRED_CONSENSUS
    assert acquired.is_acquired is True

    with _patch_load({"A": [acquired]}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )

    assert _model_from_payload(v1, "A")["activations"] == 1
    assert _model_from_payload(v2, "A")["activations"] == 1
    assert _model_from_payload(v1, "A")["lost"] == 1
    assert _model_from_payload(v2, "A")["lost"] == 1


def test_home_single_formula_in_v1_and_v2():
    home = _act(
        model_key="A",
        signal_group="HOME",
        signal_label="1",
        yes_count=1,
        evaluation_status=EVAL_WON,
        quota_book=2.10,
    )
    assert home.acquisition_status == ACQ_SINGLE_FORMULA_EXEMPT
    assert home.is_acquired is True

    with _patch_load({"A": [home]}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )

    assert _model_from_payload(v1, "A")["activations"] == 1
    assert _model_from_payload(v2, "A")["activations"] == 1
    assert _model_from_payload(v1, "A")["won"] == 1
    assert _model_from_payload(v2, "A")["won"] == 1


# ---------------------------------------------------------------------------
# V2 regression + metrics diff + isolation
# ---------------------------------------------------------------------------


def test_v2_equals_pre_task_only_acquired_true():
    rows = [
        _act(model_key="E", fixture_id=1, yes_count=1, evaluation_status=EVAL_WON),
        _act(model_key="E", fixture_id=2, yes_count=2, evaluation_status=EVAL_LOST),
        _act(
            model_key="E",
            fixture_id=3,
            signal_group="HOME",
            signal_label="1",
            yes_count=1,
            evaluation_status=EVAL_WON,
            quota_book=2.0,
        ),
    ]
    db = MagicMock()
    with _patch_load({"E": rows}):
        legacy = _model_bucket_from_activations(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            model_key="E",
            only_acquired=True,
        )
        v2 = build_models_summary(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )
        default = build_models_summary(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )

    card_v2 = _model_from_payload(v2, "E")
    card_default = _model_from_payload(default, "E")
    assert card_v2["activations"] == legacy["activations"]
    assert card_v2["won"] == legacy["won"]
    assert card_v2["lost"] == legacy["lost"]
    assert card_v2["settled"] == legacy["settled"]
    assert card_v2["win_rate"] == legacy["success_rate"]
    assert card_v2["taken_profit_indicator"] == legacy["taken_profit_indicator"]
    assert card_default == card_v2
    assert default["monitoring_version"] == "v2"
    assert default["acquisition_filter"] == "acquired"


def test_metrics_difference_model_e_v1_vs_v2():
    """A: X 1/4 WON; B: X 2/4 LOST; C: HOME WON → V1=A+B+C, V2=B+C."""
    rows = [
        _act(
            model_key="E",
            fixture_id=10,
            yes_count=1,
            evaluation_status=EVAL_WON,
            quota_book=3.0,
        ),
        _act(
            model_key="E",
            fixture_id=11,
            yes_count=2,
            evaluation_status=EVAL_LOST,
            quota_book=3.5,
        ),
        _act(
            model_key="E",
            fixture_id=12,
            signal_group="HOME",
            signal_label="1",
            yes_count=1,
            evaluation_status=EVAL_WON,
            quota_book=2.0,
        ),
    ]
    with _patch_load({"E": rows}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )

    c1 = _model_from_payload(v1, "E")
    c2 = _model_from_payload(v2, "E")
    assert c1["activations"] == 3
    assert c1["won"] == 2
    assert c1["lost"] == 1
    assert c1["settled"] == 3
    assert c2["activations"] == 2
    assert c2["won"] == 1
    assert c2["lost"] == 1
    assert c2["settled"] == 2
    assert c1["win_rate"] != c2["win_rate"]
    assert c1["taken_profit_indicator"] != c2["taken_profit_indicator"]
    # unique_acquired_signs resta acquired-canonical anche in V1 (strategia A)
    assert c1["unique_acquired_signs"] == c2["unique_acquired_signs"] == 2


def test_model_isolation_a_rejected_f_acquired_v2():
    a_row = _act(model_key="A", fixture_id=1, yes_count=1)
    f_row = _act(model_key="F", fixture_id=1, yes_count=2)
    with _patch_load({"A": [a_row], "F": [f_row]}):
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )
    assert _model_from_payload(v2, "A")["activations"] == 0
    assert _model_from_payload(v2, "F")["activations"] == 1


def test_metadata_monitoring_version_in_payload():
    with _patch_load({}):
        v1 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v1",
        )
        v2 = build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="v2",
        )
    assert v1["monitoring_version"] == "v1"
    assert v1["acquisition_filter"] == "all"
    assert v2["monitoring_version"] == "v2"
    assert v2["acquisition_filter"] == "acquired"


def test_invalid_monitoring_version_raises():
    from app.services.cecchino.cecchino_signal_aggregation import MonitoringVersionNotAllowed

    with pytest.raises(MonitoringVersionNotAllowed):
        build_models_summary(
            MagicMock(),
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            monitoring_version="foo",
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def signals_client():
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


def test_api_models_summary_versions_and_default(signals_client):
    c, _db = signals_client
    with patch(
        "app.services.cecchino.cecchino_signal_model_backtest._load_model_activations",
        return_value=[],
    ):
        r_default = c.get(
            "/api/admin/cecchino/signals/models-summary",
            params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
        )
        r_v1 = c.get(
            "/api/admin/cecchino/signals/models-summary",
            params={
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "monitoring_version": "v1",
            },
        )
        r_v2 = c.get(
            "/api/admin/cecchino/signals/models-summary",
            params={
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "monitoring_version": "v2",
            },
        )
        r_bad = c.get(
            "/api/admin/cecchino/signals/models-summary",
            params={
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "monitoring_version": "foo",
            },
        )

    assert r_default.status_code == 200
    assert r_default.json()["monitoring_version"] == "v2"
    assert r_default.json()["acquisition_filter"] == "acquired"
    assert r_v1.status_code == 200
    assert r_v1.json()["monitoring_version"] == "v1"
    assert r_v1.json()["acquisition_filter"] == "all"
    assert r_v2.status_code == 200
    assert r_v2.json()["monitoring_version"] == "v2"
    assert r_bad.status_code == 422


def test_backtest_models_does_not_accept_monitoring_version_in_generation():
    """Generazione backtest resta unica/neutrale — nessun param monitoring_version sul POST body schema."""
    from app.schemas.cecchino_signals import CecchinoSignalsBacktestModelsBody

    fields = set(CecchinoSignalsBacktestModelsBody.model_fields.keys())
    assert "monitoring_version" not in fields
