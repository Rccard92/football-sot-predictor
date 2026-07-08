"""Test persistenza e API soglie minime quota book configurabili."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_signal_min_book_odd_setting import CecchinoSignalMinBookOddSetting
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_HOME, SEL_ONE_X
from app.services.cecchino.cecchino_signal_min_book_odd_settings_service import (
    SignalMinBookOddValidationError,
    load_signal_min_book_odds,
    list_signal_min_book_odds_settings,
    reset_signal_min_book_odds_defaults,
    save_signal_min_book_odds,
)
from app.services.cecchino.cecchino_signal_value_gate import signal_has_value_from_kpi_context


def _mock_db_with_rows(rows: list[CecchinoSignalMinBookOddSetting] | None = None) -> MagicMock:
    store = list(rows or [])
    db = MagicMock()

    def _all():
        return store

    db.scalars.return_value.all.side_effect = _all

    def _add(obj):
        existing = next((r for r in store if r.target_market_key == obj.target_market_key), None)
        if existing is None:
            obj.id = len(store) + 1
            store.append(obj)
        return None

    db.add.side_effect = _add

    def _delete(obj):
        if obj in store:
            store.remove(obj)

    db.delete.side_effect = _delete
    db.query.return_value.count.return_value = len(store)
    db.query.return_value.one.side_effect = lambda: store[0]
    return db


def test_list_settings_empty_db_returns_defaults():
    items = list_signal_min_book_odds_settings(_mock_db_with_rows())
    assert len(items) == 7
    draw = next(i for i in items if i["target_market_key"] == SEL_DRAW)
    assert draw["min_book_odd"] == 3.0
    assert draw["default_min_book_odd"] == 3.0
    assert draw["is_default"] is True


def test_save_updates_draw_threshold():
    db = _mock_db_with_rows()
    save_signal_min_book_odds(db, [{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}])
    items = list_signal_min_book_odds_settings(db)
    draw = next(i for i in items if i["target_market_key"] == SEL_DRAW)
    assert draw["min_book_odd"] == 2.8
    assert draw["is_default"] is False


def test_load_signal_min_book_odds_merges_db_and_defaults():
    db = _mock_db_with_rows()
    save_signal_min_book_odds(db, [{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}])
    loaded = load_signal_min_book_odds(db)
    assert loaded[SEL_DRAW] == Decimal("2.80")
    assert loaded[SEL_ONE_X] == Decimal("1.37")


def test_reset_defaults_removes_db_rows():
    db = _mock_db_with_rows()
    save_signal_min_book_odds(db, [{"target_market_key": SEL_DRAW, "min_book_odd": 2.80}])
    reset_signal_min_book_odds_defaults(db)
    draw = next(
        i for i in list_signal_min_book_odds_settings(db) if i["target_market_key"] == SEL_DRAW
    )
    assert draw["min_book_odd"] == 3.0
    assert draw["is_default"] is True


def test_save_rejects_unknown_target():
    with pytest.raises(SignalMinBookOddValidationError):
        save_signal_min_book_odds(_mock_db_with_rows(), [{"target_market_key": "INVALID", "min_book_odd": 2.0}])


def test_save_rejects_min_odd_at_or_below_one():
    with pytest.raises(SignalMinBookOddValidationError):
        save_signal_min_book_odds(_mock_db_with_rows(), [{"target_market_key": SEL_DRAW, "min_book_odd": 1.0}])


def test_save_rejects_min_odd_above_fifty():
    with pytest.raises(SignalMinBookOddValidationError):
        save_signal_min_book_odds(_mock_db_with_rows(), [{"target_market_key": SEL_DRAW, "min_book_odd": 50.01}])


def test_save_rounds_to_two_decimals():
    db = _mock_db_with_rows()
    save_signal_min_book_odds(db, [{"target_market_key": SEL_DRAW, "min_book_odd": 2.805}])
    row = db.scalars.return_value.all()[0]
    assert row.min_book_odd == Decimal("2.81")


def test_value_gate_uses_custom_min_book_odds_dict():
    custom = {SEL_DRAW: Decimal("2.80")}
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 2.90, "quota_cecchino": 2.70},
        target_market_key=SEL_DRAW,
        min_book_odds=custom,
    )
    assert passed is True
    assert reason == "value_ok"


def test_value_gate_default_x_rejects_below_three():
    passed, reason, _ = signal_has_value_from_kpi_context(
        {"quota_book": 2.90, "quota_cecchino": 2.70},
        target_market_key=SEL_DRAW,
    )
    assert passed is False
    assert reason == "book_odd_below_min_threshold"


def test_market_without_threshold_only_value_gate():
    passed, reason, meta = signal_has_value_from_kpi_context(
        {"quota_book": 1.50, "quota_cecchino": 1.40},
        target_market_key=SEL_HOME,
    )
    assert passed is True
    assert reason == "value_ok"
    assert meta["min_book_odd"] is None
