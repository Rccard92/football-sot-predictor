"""Statistiche xG senza sprechi: tag permanente dei campionati senza xG, richieste a gruppi da 20,
partite gia' risposte mai richieste di nuovo, contatori del job e residuo reale API-Football."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_xg_league_tag import XG_TAG_HAS_XG, XG_TAG_NO_XG, XG_TAG_PENDING, CecchinoXgLeagueTag
from app.services.api_football_client import ApiFootballQuotaExhausted
from app.services.api_usage_service import read_provider_quota
from app.services.cecchino import cecchino_xg_statistics_fetch as mod
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics

KICKOFF = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)
NO_XG_STATS = [
    {"team": {"id": 1}, "statistics": [{"type": "Shots on Goal", "value": 4}]},
    {"team": {"id": 2}, "statistics": [{"type": "Shots on Goal", "value": 2}]},
]
XG_STATS = [
    {"team": {"id": 1}, "statistics": [{"type": "expected_goals", "value": "1.40"}]},
    {"team": {"id": 2}, "statistics": [{"type": "expected_goals", "value": "0.70"}]},
]


def _fx(i: int, league: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=i,
        api_fixture_id=10_000 + i,
        home_team_id=1,
        away_team_id=2,
        home_team=SimpleNamespace(api_team_id=1),
        away_team=SimpleNamespace(api_team_id=2),
        kickoff_at=KICKOFF - timedelta(days=i),
        league_id=league,
        competition_id=league,
    )


class FakeDB:
    def __init__(self) -> None:
        self.added: list = []
        self.merged: list = []

    def get(self, model, pk):  # noqa: ANN001
        return None

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)

    def merge(self, obj):  # noqa: ANN001
        self.merged.append(obj)
        return obj

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def begin_nested(self):
        from contextlib import nullcontext

        return nullcontext()


class FakeClient:
    def __init__(self, stats_by_api: dict[int, list] | None = None, *, missing: set[int] | None = None, quota_after: int | None = None):
        self.stats_by_api = stats_by_api or {}
        self.missing = missing or set()
        self.quota_after = quota_after
        self.calls: list[list[int]] = []

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        assert endpoint == "fixtures"
        ids = [int(x) for x in str((params or {})["ids"]).split("-")]
        assert len(ids) <= mod.BATCH_SIZE
        self.calls.append(ids)
        if self.quota_after is not None and len(self.calls) > self.quota_after:
            raise ApiFootballQuotaExhausted("finita", endpoint="fixtures")
        return {
            "response": [
                {"fixture": {"id": i, "status": {"short": "FT"}}, "statistics": self.stats_by_api.get(i, [])}
                for i in ids
                if i not in self.missing
            ]
        }


def _run(fixtures, client, *, tags=None, stats_map=None, answered=None, force=False, on_call=None):
    tags = {} if tags is None else tags
    db = FakeDB()
    with (
        patch.object(mod, "load_league_tags", lambda _db, ids: {k: v for k, v in tags.items() if k in set(ids)}),
        patch.object(mod, "_answered_fetches", lambda _db, fx: set(answered or ())),
        patch.object(mod, "_team_stats_map", lambda _db, ids: dict(stats_map or {})),
        patch.object(mod._LeagueResolver, "provider_league", lambda self, fx: (fx.league_id, f"L{fx.league_id}", "X")),
        patch("app.services.cecchino.cecchino_current_season_xg._persist_fixture_statistics", return_value=2),
    ):
        out = mod.fetch_prior_statistics(db, fixtures, client=client, force_refresh=force, on_call=on_call)
    created = {t.provider_league_id: t for t in db.added if isinstance(t, CecchinoXgLeagueTag)}
    return out, {**tags, **created}, db


def test_league_without_xg_is_tagged_after_one_batch_and_never_asked_again():
    fixtures = [_fx(i, 500) for i in range(1, 26)]
    client = FakeClient({f.api_fixture_id: NO_XG_STATS for f in fixtures})
    seen: list[int] = []
    out, tags, _ = _run(fixtures, client, on_call=seen.append)

    assert len(client.calls) == 1 and len(client.calls[0]) == 20  # un solo gruppo di prova
    assert out.calls == 1 and seen == [1]
    assert tags[500].status == XG_TAG_NO_XG
    assert tags[500].fixtures_answered == 20 and tags[500].fixtures_with_xg == 0
    assert out.skipped_league_without_xg == 5
    assert out.leagues_tagged_no_xg == [500]

    # settimana dopo: il campionato ha gia' risposto, zero chiamate
    client2 = FakeClient()
    out2, _, _ = _run([_fx(i, 500) for i in range(30, 60)], client2, tags={500: tags[500]})
    assert client2.calls == [] and out2.calls == 0
    assert out2.skipped_league_without_xg == 30


def test_league_with_xg_downloads_all_missing_in_groups_of_20():
    fixtures = [_fx(i, 600) for i in range(1, 46)]
    client = FakeClient({f.api_fixture_id: XG_STATS for f in fixtures})
    out, tags, db = _run(fixtures, client)

    assert [len(c) for c in client.calls] == [20, 20, 5]
    assert tags[600].status == XG_TAG_HAS_XG
    assert out.fixtures_with_xg == 45 and out.fixtures_with_stats == 45
    # ogni risposta resta registrata: la partita non si richiede piu'
    assert len(db.merged) == 45


def test_tagged_has_xg_leagues_share_the_same_batch():
    tags = {
        700: CecchinoXgLeagueTag(provider_league_id=700, status=XG_TAG_HAS_XG, fixtures_answered=9, fixtures_with_xg=9),
        701: CecchinoXgLeagueTag(provider_league_id=701, status=XG_TAG_HAS_XG, fixtures_answered=9, fixtures_with_xg=9),
    }
    fixtures = [_fx(i, 700) for i in range(1, 11)] + [_fx(i, 701) for i in range(11, 21)]
    client = FakeClient({f.api_fixture_id: XG_STATS for f in fixtures})
    out, _, _ = _run(fixtures, client, tags=tags)
    assert len(client.calls) == 1 and len(client.calls[0]) == 20
    assert out.calls == 1


def test_fixtures_already_answered_are_not_requested_and_seed_the_tag():
    fixtures = [_fx(i, 800) for i in range(1, 8)]
    row = SimpleNamespace(raw_json={"statistics": NO_XG_STATS[0]["statistics"]}, expected_goals=None)
    stats_map = {(f.id, t): row for f in fixtures for t in (1, 2)}
    client = FakeClient()
    out, tags, _ = _run(fixtures, client, stats_map=stats_map)

    assert client.calls == []  # tutto gia' in archivio, nessuna chiamata
    assert out.skipped_already_answered == 7
    assert tags[800].status == XG_TAG_NO_XG  # 7 risposte senza xG: deciso senza spendere


def test_fixture_with_xg_in_archive_is_skipped():
    fixtures = [_fx(1, 900)]
    row_h = SimpleNamespace(raw_json={"statistics": XG_STATS[0]["statistics"]}, expected_goals=1.4)
    row_a = SimpleNamespace(raw_json={"statistics": XG_STATS[1]["statistics"]}, expected_goals=0.7)
    client = FakeClient()
    out, tags, _ = _run(fixtures, client, stats_map={(1, 1): row_h, (1, 2): row_a})
    assert client.calls == [] and out.skipped_has_xg == 1
    assert tags[900].status == XG_TAG_HAS_XG


def test_recorded_fetch_counts_as_an_answer():
    fixtures = [_fx(i, 950) for i in range(1, 4)]
    client = FakeClient()
    out, _, _ = _run(fixtures, client, answered={f.api_fixture_id for f in fixtures})
    assert client.calls == [] and out.skipped_already_answered == 3


def test_fixtures_not_returned_count_as_answers_without_xg():
    fixtures = [_fx(i, 960) for i in range(1, 7)]
    client = FakeClient(missing={f.api_fixture_id for f in fixtures})
    out, tags, _ = _run(fixtures, client)
    assert out.fixtures_answered == 6 and out.fixtures_with_stats == 0
    assert tags[960].status == XG_TAG_NO_XG


def test_few_answers_keep_the_league_pending():
    fixtures = [_fx(i, 970) for i in range(1, 4)]
    client = FakeClient({f.api_fixture_id: NO_XG_STATS for f in fixtures})
    _, tags, _ = _run(fixtures, client)
    assert tags[970].status == XG_TAG_PENDING and tags[970].fixtures_answered == 3


def test_quota_exhausted_stops_and_is_counted():
    tags = {980: CecchinoXgLeagueTag(provider_league_id=980, status=XG_TAG_HAS_XG, fixtures_answered=5, fixtures_with_xg=5)}
    fixtures = [_fx(i, 980) for i in range(1, 61)]
    client = FakeClient({f.api_fixture_id: XG_STATS for f in fixtures}, quota_after=1)
    seen: list[int] = []
    out, _, _ = _run(fixtures, client, tags=tags, on_call=seen.append)
    assert out.quota_exhausted is True
    assert len(client.calls) == 2 and out.calls == 2 and seen == [1, 1]


def test_force_refresh_ignores_tags_and_archive():
    tags = {990: CecchinoXgLeagueTag(provider_league_id=990, status=XG_TAG_NO_XG, fixtures_answered=9, fixtures_with_xg=0)}
    fixtures = [_fx(i, 990) for i in range(1, 4)]
    client = FakeClient({f.api_fixture_id: NO_XG_STATS for f in fixtures})
    out, _, _ = _run(fixtures, client, tags=tags, force=True)
    assert len(client.calls) == 1 and out.fixtures_requested == 3


def test_has_xg_tag_never_goes_back():
    tag = CecchinoXgLeagueTag(provider_league_id=1, status=XG_TAG_HAS_XG, fixtures_answered=50, fixtures_with_xg=1)
    assert mod._decide(tag, KICKOFF) is None and tag.status == XG_TAG_HAS_XG


def test_statistics_blocks_have_xg():
    assert mod.statistics_blocks_have_xg(XG_STATS)
    assert not mod.statistics_blocks_have_xg(NO_XG_STATS)
    assert not mod.statistics_blocks_have_xg([])


# --- contatori del job -----------------------------------------------------------------------


def test_statistics_calls_enter_the_job_total():
    m = ScanRunMetrics(started_at=1.0)
    m.api_calls["odds"] = 10
    m.count_statistics_call()
    m.count_statistics_call(2)
    assert m.api_calls["statistics"] == 3 and m.api_calls_total == 13
    m.xg_phase = {"status": "ok"}
    m.provider_quota = {"remaining": 4200, "limit_day": 7500}
    summary = m.to_result_summary(
        fixtures_found=1,
        after_competition_filter=1,
        odds_checked=1,
        eligible_count=0,
        excluded_count=1,
        excluded_summary={},
        duration_seconds=1.0,
    )
    assert summary["api_calls"]["statistics"] == 3
    assert summary["api_calls_total"] == 13
    assert summary["xg_phase"] == {"status": "ok"}
    assert summary["provider_quota"]["remaining"] == 4200


def test_deferred_xg_runs_after_the_scan_and_counts_calls():
    from app.services.cecchino import cecchino_today_service as svc

    m = ScanRunMetrics(started_at=1.0)
    m.deferred_xg_row_ids = [11, 12]
    warnings: list[str] = []

    def fake_phase(db, ids, *, client, on_call):  # noqa: ANN001
        assert ids == [11, 12]
        on_call(1)
        on_call(1)
        return {"status": "ok", "rows": 2}

    client = SimpleNamespace(set_usage_context=lambda ctx: None)
    with patch("app.services.cecchino.cecchino_xg_statistics_fetch.run_deferred_xg_phase", fake_phase):
        svc._run_deferred_xg(
            object(), m, client=client, usage_ctx=None, provider_quota_stopped=False, progress=None, warnings=warnings
        )
    assert m.xg_phase == {"status": "ok", "rows": 2}
    assert m.api_calls["statistics"] == 2 and m.api_calls_total == 2


def test_deferred_xg_is_skipped_when_quota_already_finished():
    from app.services.cecchino import cecchino_today_service as svc

    m = ScanRunMetrics(started_at=1.0)
    m.deferred_xg_row_ids = [11]
    with patch("app.services.cecchino.cecchino_xg_statistics_fetch.run_deferred_xg_phase") as phase:
        svc._run_deferred_xg(
            object(), m, client=None, usage_ctx=None, provider_quota_stopped=True, progress=None, warnings=[]
        )
    phase.assert_not_called()
    assert m.xg_phase == {"status": "skipped_quota_exhausted", "rows": 1}


def test_deferred_xg_phase_skips_profiles_when_quota_finishes_during_statistics():
    outcome = mod.StatisticsFetchOutcome(calls=3, quota_exhausted=True)
    with (
        patch.object(mod, "fetch_prior_statistics", return_value=outcome),
        patch("app.services.cecchino.cecchino_current_season_xg.ensure_current_season_xg_profile_for_fixture") as ensure,
    ):
        out = mod.run_deferred_xg_phase(FakeDB(), [1, 2], client=object())
    ensure.assert_not_called()
    assert out["status"] == "quota_exhausted" and out["statistics"]["calls"] == 3


# --- residuo reale -------------------------------------------------------------------------


class _StatusClient:
    def __init__(self, body=None, exc: Exception | None = None):
        self.body, self.exc = body, exc

    def get(self, endpoint, params=None):  # noqa: ANN001
        assert endpoint == "status"
        if self.exc:
            raise self.exc
        return self.body


def test_read_provider_quota_reports_real_remaining():
    q = read_provider_quota(_StatusClient({"response": {"requests": {"current": 7000, "limit_day": 7500}}}))
    assert q["remaining"] == 500 and q["limit_day"] == 7500 and q["current"] == 7000
    q2 = read_provider_quota(_StatusClient({"response": [{"requests": {"current": 10, "limit_day": 7500}}]}))
    assert q2["remaining"] == 7490


def test_read_provider_quota_when_exhausted_or_unreadable():
    q = read_provider_quota(_StatusClient(exc=ApiFootballQuotaExhausted("finita")))
    assert q["remaining"] == 0
    assert read_provider_quota(_StatusClient(exc=RuntimeError("rete"))) is None
    assert read_provider_quota(_StatusClient({"response": {}})) is None


@pytest.mark.parametrize("fetched_hours_after, counted", [(1, False), (4, True)])
def test_answered_fetch_needs_closed_match(fetched_hours_after: int, counted: bool):
    fx = _fx(1, 1)
    rec = SimpleNamespace(api_fixture_id=fx.api_fixture_id, fetched_at=fx.kickoff_at + timedelta(hours=fetched_hours_after))

    class _DB:
        def scalars(self, _stmt):  # noqa: ANN001
            return SimpleNamespace(all=lambda: [rec])

    assert (fx.api_fixture_id in mod._answered_fetches(_DB(), [fx])) is counted
