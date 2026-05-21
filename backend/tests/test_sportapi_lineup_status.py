"""Test etichette stato formazione SportAPI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.sportapi.sportapi_lineup_status import formation_status_label


def test_formation_status_missing():
    assert formation_status_label(has_lineup=False, confirmed=None, fetched_at=None) == "Mancante"


def test_formation_status_official():
    assert formation_status_label(has_lineup=True, confirmed=True, fetched_at=None) == "Ufficiale"


def test_formation_status_probable_updated():
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    assert (
        formation_status_label(has_lineup=True, confirmed=False, fetched_at=recent) == "Probabile aggiornata"
    )


def test_formation_status_probable_stale():
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=old) == "Probabile vecchia"


def test_formation_status_probable_fallback():
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=None) == "Probabile"
