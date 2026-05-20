"""Smoke import route admin SportAPI."""

from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG


def test_admin_sportapi_route_imports():
    from app.routes.admin_sportapi import router, _fixture_not_found_message

    assert router.prefix == "/admin/sportapi"
    assert _fixture_not_found_message({"status": "error", "message": FIXTURE_NOT_FOUND_MSG}) == FIXTURE_NOT_FOUND_MSG
    assert _fixture_not_found_message({"status": "ok"}) is None


def test_admin_sportapi_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.routes.admin_sportapi")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
