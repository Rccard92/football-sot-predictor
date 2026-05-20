"""Unit test risoluzione fixture SportAPI (ID DB vs api_fixture_id)."""

from unittest.mock import MagicMock

from app.services.sportapi.sportapi_fixture_resolve import (
    FIXTURE_NOT_FOUND_MSG,
    resolve_fixture,
    resolve_fixture_or_error,
)


def _fixture(id_: int, api_fixture_id: int) -> MagicMock:
    fx = MagicMock()
    fx.id = id_
    fx.api_fixture_id = api_fixture_id
    return fx


def test_resolve_fixture_by_db_id():
    db = MagicMock()
    fx = _fixture(375, 1378236)
    db.scalar.side_effect = [fx]

    result, via = resolve_fixture(db, 375)

    assert result is fx
    assert via == "db_id"
    assert db.scalar.call_count == 1


def test_resolve_fixture_by_api_fixture_id():
    db = MagicMock()
    fx = _fixture(375, 1378236)
    db.scalar.side_effect = [None, fx]

    result, via = resolve_fixture(db, 1378236)

    assert result is fx
    assert via == "api_fixture_id"
    assert db.scalar.call_count == 2


def test_resolve_fixture_not_found():
    db = MagicMock()
    db.scalar.side_effect = [None, None]

    result, via = resolve_fixture(db, 999)

    assert result is None
    assert via is None


def test_resolve_fixture_or_error_not_found():
    db = MagicMock()
    db.scalar.side_effect = [None, None]

    fx, err = resolve_fixture_or_error(db, 999)

    assert fx is None
    assert err is not None
    assert err["status"] == "error"
    assert err["message"] == FIXTURE_NOT_FOUND_MSG
    assert err["input_id"] == 999


def test_resolve_fixture_or_error_success():
    db = MagicMock()
    fx = _fixture(375, 1378236)
    db.scalar.side_effect = [None, fx]

    result, meta = resolve_fixture_or_error(db, 1378236)

    assert result is fx
    assert meta == {"resolved_via": "api_fixture_id", "internal_fixture_id": 375}
