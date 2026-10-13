"""Aggiornamento automatico risultati Cecchino Today: quali giornate, e mai bloccante."""

from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino import cecchino_today_auto_results as mod


def test_recent_days_first_then_stale_newest_first_capped():
    out = mod.dates_to_refresh(
        local_date=date(2026, 10, 14),
        days_back=3,
        stale=[date(2026, 9, 26), date(2026, 10, 9), date(2026, 10, 12)],
        max_days=5,
    )
    assert out == [
        date(2026, 10, 13),
        date(2026, 10, 12),
        date(2026, 10, 11),
        date(2026, 10, 9),
        date(2026, 9, 26),
    ]
    assert mod.dates_to_refresh(local_date=date(2026, 10, 14), days_back=3, stale=[], max_days=2) == [
        date(2026, 10, 13),
        date(2026, 10, 12),
    ]


def test_never_today_or_future():
    out = mod.dates_to_refresh(
        local_date=date(2026, 10, 14), days_back=1, stale=[date(2026, 10, 14), date(2026, 10, 15)], max_days=10
    )
    assert out == [date(2026, 10, 13)]


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, _stmt):  # noqa: ANN001
        raise RuntimeError("db non raggiungibile")

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_one_failing_day_does_not_stop_the_others():
    calls: list[date] = []

    def update(db, *, scan_date, timezone):  # noqa: ANN001
        calls.append(scan_date)
        if scan_date == date(2026, 10, 12):
            raise RuntimeError("boom")
        return {"status": "ok", "still_upcoming": 0, "live": 0, "api_calls": 1}

    summary = mod.refresh_recent_results(
        session_factory=_Session,
        local_date=date(2026, 10, 14),
        timezone="Europe/Rome",
        days_back=3,
        update_fn=update,
        settle_fn=lambda db: {"settled": 0},
    )
    assert calls == [date(2026, 10, 13), date(2026, 10, 12), date(2026, 10, 11)]
    assert summary["errors"] == 1
    assert [d["date"] for d in summary["days"]] == ["2026-10-13", "2026-10-11"]
    assert summary["stale_found"] == []  # lettura giornate ferme fallita: si prosegue con i giorni recenti
    assert summary["live_registry_settlement"] == {"settled": 0}
