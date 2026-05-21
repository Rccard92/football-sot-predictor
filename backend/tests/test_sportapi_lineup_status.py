"""Test etichette stato formazione SportAPI per report rapido."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.sportapi.sportapi_lineup_status import formation_status_label


def test_formation_status_missing():
    assert formation_status_label(has_lineup=False, confirmed=None, fetched_at=None) == "Mancante"


def test_formation_status_official():
    assert formation_status_label(has_lineup=True, confirmed=True, fetched_at=None) == "Ufficiale"


def test_formation_status_updated_within_6h():
    recent = datetime.now(timezone.utc) - timedelta(hours=3)
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=recent) == "Aggiornata"


def test_formation_status_stale_over_6h():
    old = datetime.now(timezone.utc) - timedelta(hours=8)
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=old) == "Da aggiornare"


def test_formation_status_no_fetched_at():
    assert formation_status_label(has_lineup=True, confirmed=False, fetched_at=None) == "Da aggiornare"
