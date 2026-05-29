"""Test import lineups SportAPI multi-campionato."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.services.competition_sportapi_lineup_service import CompetitionSportApiLineupService
from app.services.model_operating_context import build_v20_operating_context

client = TestClient(app)


def _future_fx(fx_id: int = 201, *, competition_id: int = 2) -> MagicMock:
    future = datetime.now(timezone.utc) + timedelta(days=3)
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.api_fixture_id = 9000 + fx_id
    fx.status = "NS"
    fx.kickoff_at = future
    fx.competition_id = competition_id
    fx.round = "Regular Season - 18"
    fx.home_team_id = 10
    fx.away_team_id = 11
    fx.raw_json = None
    return fx


def _comp(comp_id: int = 2) -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = comp_id
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.country = "Brazil"
    comp.season = 2026
    return comp


def test_dry_run_brasileirao_no_db_writes():
    comp = _comp(2)
    fixtures = [_future_fx(i) for i in range(201, 211)]

    db = MagicMock()
    svc = CompetitionSportApiLineupService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    match_debug = {
        "status": "ok",
        "api_calls": 1,
        "recommendation": "AUTO_SAFE",
        "would_save": True,
        "best_candidate": {
            "provider_event_id": 555,
            "confidence_score": 95.0,
            "recommendation": "AUTO_SAFE",
            "raw_event": {"id": 555},
        },
        "best_match": "Flamengo – Palmeiras",
        "sportapi_event_id": 555,
        "confidence_score": 95.0,
        "match_reason": "timestamp_exact, home_team, away_team",
        "raw_candidates": [],
        "candidates": [],
    }

    with patch.object(svc, "_resolve_fixtures", return_value=(fixtures, "Regular Season - 18", [], None)), patch.object(
        svc, "_has_mapping", return_value=False
    ), patch(
        "app.services.competition_sportapi_lineup_service.SportApiMatchingService"
    ) as mock_match_cls, patch(
        "app.services.competition_sportapi_lineup_service.sportapi_configured",
        return_value=True,
    ):
        mock_match_cls.return_value.match_fixture_for_competition.return_value = match_debug
        result = svc.ingest(db, 2, scope="next_round", dry_run=True)

    assert result["status"] == "dry_run"
    assert result["competition_id"] == 2
    assert result["fixtures_checked"] == 10
    assert result["mappings_found"] == 10
    assert result["dry_run"] is True
    db.commit.assert_not_called()


def test_fixture_ids_rejects_other_competition():
    comp = _comp(2)
    fx_ok = _future_fx(201, competition_id=2)
    fx_bad = _future_fx(999, competition_id=1)

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fx_ok, fx_bad]

    svc = CompetitionSportApiLineupService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    with patch(
        "app.services.competition_sportapi_lineup_service.sportapi_configured",
        return_value=True,
    ):
        result = svc.ingest(db, 2, scope="fixture_ids", fixture_ids=[201, 999], dry_run=True)

    assert result["status"] == "error"
    assert result["code"] == "fixture_competition_mismatch"


def test_confirm_mapping_sets_competition_id():
    from app.services.sportapi.sportapi_lineup_service import SportApiLineupService

    fx = _future_fx(201)
    fx.league = None
    fx.home_team = MagicMock(name="Flamengo")
    fx.away_team = MagicMock(name="Palmeiras")

    db = MagicMock()
    db.scalar.return_value = None

    with patch(
        "app.services.sportapi.sportapi_lineup_service.resolve_fixture_or_error",
        return_value=(fx, {}),
    ):
        svc = SportApiLineupService()
        out = svc.confirm_mapping(
            db,
            201,
            provider_event_id=12345,
            confidence_score=95.0,
            matched_by="auto_timestamp_teams",
            raw_payload={"id": 12345, "startTimestamp": int(fx.kickoff_at.timestamp())},
            expected_competition_id=2,
        )

    assert out["status"] == "success"
    added = db.add.call_args[0][0]
    assert added.competition_id == 2


def test_model_operating_context_lineups_ready_uses_sportapi_tables():
    comp = _comp(2)
    db = MagicMock()
    db.scalar.side_effect = [334, 597, 0, 5, 3, 380, 0, 0]

    ctx = build_v20_operating_context(db, comp)

    assert ctx["lineups_ready"] is True
    assert ctx["operating_mode"] == "complete"


def test_ingest_route_dry_run_mocked():
    with patch(
        "app.routes.admin_competition_ingest.CompetitionSportApiLineupService"
    ) as mock_cls, patch(
        "app.routes.admin_competition_ingest.sportapi_configured",
        return_value=True,
    ), patch("app.routes.admin_competition_ingest.CompetitionService") as comp_svc:
        comp_svc.return_value.get_by_id_or_raise.return_value = _comp(2)
        mock_cls.return_value.ingest.return_value = {
            "status": "dry_run",
            "competition_id": 2,
            "fixtures_checked": 10,
            "mappings_found": 8,
            "mappings_uncertain": 2,
            "dry_run": True,
            "results": [],
        }
        response = client.post(
            "/api/admin/competitions/2/ingest/sportapi-lineups",
            json={"scope": "next_round", "dry_run": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["competition_id"] == 2
    assert body["fixtures_checked"] == 10


def test_pre_match_run_all_enabled_skips_cron_disabled():
    from app.services.jobs.pre_match_lineup_refresh_job import PreMatchOfficialLineupRefreshJob

    comp_enabled = MagicMock(spec=Competition)
    comp_enabled.id = 1
    comp_enabled.pre_match_cron_enabled = True
    comp_enabled.season = 2025
    comp_enabled.name = "Serie A"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [comp_enabled]

    job = PreMatchOfficialLineupRefreshJob()
    with patch.object(job, "run", return_value={"status": "ok", "refreshed": 0}) as mock_run:
        out = job.run_all_enabled(db)

    mock_run.assert_called_once_with(db, 2025, force=False, minutes_before=None, window_minutes=None)
    assert out["competitions_processed"] == 1
    assert out["results"][0]["competition_id"] == 1
