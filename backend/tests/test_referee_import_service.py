"""Test import storico arbitro (mock API)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.referee_import_service import RefereeImportService
from app.services.referee_cards_parser import MatchCardsBySide


def test_import_season_history_counts_matches(monkeypatch):
    svc = RefereeImportService(client=MagicMock())
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []

    svc._get_or_create_referee = MagicMock(return_value=MagicMock(id=1))
    svc._upsert_card_summary = MagicMock()

    svc._client.get_fixtures.return_value = [
        {
            "fixture": {"id": 1001, "referee": "M. Guida", "date": "2025-01-01T15:00:00+00:00"},
            "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
            "league": {"id": 135, "season": 2025},
        },
        {
            "fixture": {"id": 1002, "referee": "Other Ref", "date": "2025-01-02T15:00:00+00:00"},
            "teams": {"home": {"id": 3, "name": "C"}, "away": {"id": 4, "name": "D"}},
            "league": {"id": 135, "season": 2025},
        },
    ]

    cards = MatchCardsBySide(4, 0, 2, 0, 2, 0)
    monkeypatch.setattr(
        "app.services.referee_import_service.resolve_cards_for_api_fixture",
        lambda *a, **k: (cards, "events"),
    )

    out = svc.import_season_history(db, referee_name="M. Guida", league_id=135, season=2025)
    assert out["status"] == "success"
    assert out["fixtures_scanned"] == 2
    assert out["referee_matches_found"] == 1
