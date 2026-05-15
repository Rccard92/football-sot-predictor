"""Smoke import applicazione (no circular import)."""


def test_import_app_main():
    from app.main import app

    assert app.title
