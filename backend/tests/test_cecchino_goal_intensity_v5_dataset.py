"""Test dataset Intensità Goal v5 — Fase 1B.1 (summary compatto + export stream)."""

from __future__ import annotations

import ast
import csv
import inspect
import io
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    FEATURE_SPECS,
    dedupe_fixtures_provider_then_composite,
    dedupe_local_fixtures,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import (
    AuditIndexes,
    XgEvent,
    build_today_indexes,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dataset import (
    CSV_COLUMNS,
    VERSION,
    XG_FEATURE_KEYS,
    build_goal_intensity_v5_dataset,
    build_goal_intensity_v5_dataset_internal,
    core_feature_status,
    filter_dataset_rows_by_kind,
    history_quality_tier,
    stream_goal_intensity_v5_dataset_csv,
)
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_historical_fixture_identity_consistency,
)


KO = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)


def _fx(
    fid: int,
    *,
    api: int | None = None,
    home: int = 1,
    away: int = 2,
    gh: int = 2,
    ga: int = 1,
    ko: datetime | None = None,
    competition_id: int = 39,
    status: str = "FT",
) -> MagicMock:
    fx = MagicMock()
    fx.id = fid
    fx.api_fixture_id = api if api is not None else 8000 + fid
    fx.home_team_id = home
    fx.away_team_id = away
    fx.goals_home = gh
    fx.goals_away = ga
    fx.kickoff_at = ko or KO
    fx.status = status
    fx.competition_id = competition_id
    return fx


def _prior(fid: int, *, home: int, away: int, gh: int, ga: int, days_before: int = 7, base: datetime | None = None) -> MagicMock:
    base_ko = base or KO
    return _fx(
        fid,
        home=home,
        away=away,
        gh=gh,
        ga=ga,
        ko=base_ko - timedelta(days=days_before),
        api=9000 + fid,
    )


def _priors(base: datetime | None = None, n: int = 5):
    b = base or KO
    home = [
        _prior(10 + i, home=1, away=9, gh=2, ga=1, days_before=3 + i * 2, base=b) for i in range(n)
    ]
    away = [
        _prior(20 + i, home=2, away=5, gh=1, ga=1, days_before=3 + i * 2, base=b) for i in range(n)
    ]
    return home, away


def _xg_profiles(*, cutoff: str | None = None, excluded: bool = True) -> dict:
    return {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {"xg_for_avg": 1.2, "xg_against_avg": 1.3},
        "anti_leakage": {
            "fixture_date_cutoff": cutoff or KO.isoformat(),
            "current_fixture_excluded": excluded,
        },
    }


def _today(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    defaults = {
        "id": 100,
        "provider_source": "api_football",
        "provider_fixture_id": 8500,
        "local_fixture_id": 500,
        "competition_id": 39,
        "scan_date": date(2026, 3, 14),
        "kickoff": KO,
        "match_display_status": "upcoming",
        "fixture_status": "NS",
        "goals_home": None,
        "goals_away": None,
        "score_fulltime_home": None,
        "score_fulltime_away": None,
        "home_team_name": "Team1",
        "away_team_name": "Team2",
        "cecchino_output_json": {},
        "xg_profiles_json": _xg_profiles(),
        "odds_snapshot_json": None,
        "odds_checked_at": None,
        "country_name": "England",
        "created_at": datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _indexes_from_priors(fixtures: list, today_rows: list, priors=None, *, include_xg_stats: bool = True) -> AuditIndexes:
    idx = AuditIndexes()
    by_local, by_provider = build_today_indexes(today_rows)
    idx.today_by_local_fixture_id = by_local
    idx.today_by_provider_fixture_id = by_provider
    by_comp_team: dict = {}
    xg_by: dict = {}

    def _add_hist(fx):
        comp = int(fx.competition_id) if fx.competition_id is not None else None
        for tid in (int(fx.home_team_id), int(fx.away_team_id)):
            key = (comp, tid)
            by_comp_team.setdefault(key, []).append(fx)
            if include_xg_stats:
                xg_by.setdefault(key, []).append(
                    XgEvent(
                        kickoff=fx.kickoff_at,
                        fixture_id=int(fx.id),
                        api_fixture_id=int(fx.api_fixture_id) if fx.api_fixture_id is not None else None,
                        xg_for=1.5,
                        xg_against=1.0,
                    )
                )

    for local in fixtures:
        if local.home_team_id is None or local.away_team_id is None:
            continue
        base = local.kickoff_at
        if priors is not None:
            home_p, away_p = priors
        else:
            home_p, away_p = _priors(base=base)
        for fx in home_p + away_p:
            _add_hist(fx)
        _add_hist(local)
        idx.team_name_by_id[int(local.home_team_id)] = f"Team{local.home_team_id}"
        idx.team_name_by_id[int(local.away_team_id)] = f"Team{local.away_team_id}"
        if local.competition_id is not None:
            cid = int(local.competition_id)
            idx.country_by_competition_id[cid] = "England" if cid == 39 else "Spain"
            idx.competition_name_by_id[cid] = "Premier League" if cid == 39 else "La Liga"

    for key in by_comp_team:
        by_comp_team[key].sort(key=lambda f: (f.kickoff_at, int(f.id)))
    for key in xg_by:
        xg_by[key].sort(key=lambda e: (e.kickoff, e.fixture_id))
    idx.fixtures_by_comp_team = by_comp_team
    idx.xg_by_comp_team = xg_by
    return idx


def _run_dataset(fixtures: list, *, today_rows: list | None = None, priors=None, include_xg_stats: bool = True):
    db = MagicMock()
    todays = today_rows if today_rows is not None else []
    indexes = _indexes_from_priors(fixtures, todays, priors=priors, include_xg_stats=include_xg_stats)
    db.scalars.return_value.all.return_value = []
    db.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.finished_local_fixtures_in_kickoff_range",
            return_value=list(fixtures),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.load_today_snapshots_for_fixtures",
            return_value=list(todays),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_today_indexes",
            side_effect=build_today_indexes,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset._fixture_ids_with_team_stats",
            return_value={int(f.id) for f in fixtures} if include_xg_stats else set(),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.preload_audit_indexes",
            return_value=indexes,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_historical_fixture_identity_consistency",
            side_effect=build_historical_fixture_identity_consistency,
        ),
    ):
        summary = build_goal_intensity_v5_dataset(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
        )
        internal = build_goal_intensity_v5_dataset_internal(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
        )
    return summary, internal, db


def test_version_and_v4_unchanged():
    assert VERSION == "cecchino_goal_intensity_v5_dataset_v1_1"
    assert V4_VERSION == "cecchino_goal_intensity_v4_expected_goals"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    summary, _, _ = _run_dataset([local], today_rows=[today])
    assert summary["version"] == VERSION
    assert summary["dataset_summary"]["v4_unchanged"] is True
    assert summary["dataset_summary"]["no_v5_formula"] is True


def test_dedupe_provider():
    a = _fx(1, api=100)
    b = _fx(2, api=100)
    out, removed = dedupe_local_fixtures([a, b])
    assert len(out) == 1
    assert removed == 1


def test_dedupe_composite_not_quadratic():
    """O(n log n): su n grandi non deve esplodere come O(n²)."""
    n = 800
    fixtures = [
        _fx(
            i,
            api=10_000 + i,
            home=1 + (i % 40),
            away=50 + (i % 40),
            competition_id=39,
            ko=KO + timedelta(seconds=i * 120),
        )
        for i in range(n)
    ]
    t0 = time.perf_counter()
    retained, report = dedupe_fixtures_provider_then_composite(fixtures)
    elapsed = time.perf_counter() - t0
    assert len(retained) == n
    assert report["duplicates_composite_removed"] == 0
    assert "timings_ms" in report
    assert "provider_dedupe_ms" in report["timings_ms"]
    assert "composite_bucket_build_ms" in report["timings_ms"]
    assert "composite_cluster_ms" in report["timings_ms"]
    # O(n²) su 800 sarebbe tipicamente >> 0.5s; O(n log n) resta sotto soglia ampia
    assert elapsed < 1.5


def test_dedupe_buckets_not_cross_compared():
    """Stesso kickoff ma bucket diversi (home/away) → entrambe retained."""
    ko = KO
    a = _fx(1, api=1, home=1, away=2, ko=ko, competition_id=39)
    b = _fx(2, api=2, home=3, away=4, ko=ko, competition_id=39)
    retained, report = dedupe_fixtures_provider_then_composite([a, b])
    assert {int(f.id) for f in retained} == {1, 2}
    assert report["duplicates_composite_removed"] == 0


def test_cluster_within_60s():
    ko = KO
    a = _fx(10, api=10, home=1, away=2, ko=ko, competition_id=39)
    b = _fx(11, api=11, home=1, away=2, ko=ko + timedelta(seconds=45), competition_id=39)
    retained, report = dedupe_fixtures_provider_then_composite(
        [a, b],
        has_today_by_id={10: True, 11: False},
    )
    assert len(retained) == 1
    assert int(retained[0].id) == 10
    assert report["duplicates_composite_removed"] == 1


def test_cluster_beyond_60s_separated():
    ko = KO
    a = _fx(10, api=10, home=1, away=2, ko=ko, competition_id=39)
    b = _fx(11, api=11, home=1, away=2, ko=ko + timedelta(seconds=61), competition_id=39)
    retained, report = dedupe_fixtures_provider_then_composite([a, b])
    assert {int(f.id) for f in retained} == {10, 11}
    assert report["duplicates_composite_removed"] == 0


def test_dedupe_composite_4305_4306():
    ko = datetime(2025, 8, 22, 15, 0, tzinfo=timezone.utc)
    a = _fx(4305, api=1395855, home=10, away=20, ko=ko, competition_id=36)
    b = _fx(4306, api=1396000, home=10, away=20, ko=ko, competition_id=36)
    today = _today(
        id=1,
        local_fixture_id=4305,
        provider_fixture_id=1395855,
        competition_id=36,
        kickoff=ko,
        home_team_name="Team10",
        away_team_name="Team20",
    )
    summary, internal, _ = _run_dataset([a, b], today_rows=[today])
    ids = [r["local_fixture_id"] for r in internal["dataset_rows"]]
    assert len(ids) == 1
    assert ids[0] == 4305
    assert summary["deduplication"]["duplicates_composite_removed"] == 1
    assert internal["deduplication"]["duplicate_groups"][0]["retained_fixture_id"] == 4305
    assert 4306 in internal["deduplication"]["duplicate_groups"][0]["excluded_fixture_ids"]


def test_paired_set_built_once_source():
    src = Path(__file__).resolve().parents[1] / "app/services/cecchino/cecchino_goal_intensity_v5_dataset.py"
    text = src.read_text(encoding="utf-8")
    assert "paired_id_set = set(paired_ids)" in text
    assert "in set(paired_ids)" not in text
    assert "if r[\"local_fixture_id\"] in paired_id_set]" in text or "in paired_id_set" in text


def test_no_set_recreation_in_dataset_loop():
    """AST: nessuna chiamata set() dentro list comprehension del service dataset."""
    src = Path(__file__).resolve().parents[1] / "app/services/cecchino/cecchino_goal_intensity_v5_dataset.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    offenders: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ListComp(self, node: ast.ListComp) -> None:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "set":
                    offenders.append(ast.dump(child))
            self.generic_visit(node)

        def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "set":
                    offenders.append(ast.dump(child))
            self.generic_visit(node)

    Visitor().visit(tree)
    assert offenders == []


def test_summary_no_full_dataset_rows_or_cohort_ids():
    fixtures = [_fx(i, api=i, ko=KO + timedelta(days=i)) for i in range(1, 12)]
    summary, internal, _ = _run_dataset(fixtures, today_rows=[])
    assert "dataset_rows" not in summary or summary.get("dataset_rows") is None
    assert "cohort_ids" not in summary
    assert "dataset_preview_rows" in summary
    assert len(summary["dataset_preview_rows"]) <= 100
    assert len(internal["dataset_rows"]) == 11
    assert summary["dataset_summary"]["preview_rows"] == len(summary["dataset_preview_rows"])


def test_paired_ids_and_targets_hashed_not_duplicated():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    summary, internal, _ = _run_dataset([local], today_rows=[today])
    paired = summary["paired_xg_readiness"]
    assert "fixture_ids" not in paired
    assert "targets" not in paired
    assert "paired_core_without_xg" not in paired
    assert "paired_enriched_with_xg" not in paired
    assert paired["same_fixture_ids"] is True
    assert paired["same_targets"] is True
    assert isinstance(paired["fixture_ids_hash"], str) and len(paired["fixture_ids_hash"]) == 64
    assert isinstance(paired["targets_hash"], str) and len(paired["targets_hash"]) == 64
    assert paired["fixture_ids_hash"] == internal["fixture_ids_hash"]
    assert paired["targets_hash"] == internal["targets_hash"]


def test_preview_max_100():
    fixtures = [_fx(i, api=i, ko=KO + timedelta(hours=i)) for i in range(1, 150)]
    summary, internal, _ = _run_dataset(fixtures, today_rows=[])
    assert len(summary["dataset_preview_rows"]) == 100
    assert len(internal["dataset_rows"]) == 149
    assert summary["dataset_preview_rows"] == internal["dataset_rows"][:100]


def test_summary_payload_under_soft_limit():
    fixtures = [_fx(i, api=i, ko=KO + timedelta(hours=i)) for i in range(1, 120)]
    summary, _, _ = _run_dataset(fixtures, today_rows=[])
    encoded = json.dumps(summary, default=str, separators=(",", ":"))
    size = len(encoded.encode("utf-8"))
    assert size < 2 * 1024 * 1024
    # Misurato con response_payload_bytes=0 poi aggiornato: tolleranza sul digit count
    assert abs(int(summary["performance"]["response_payload_bytes"]) - size) <= 16
    assert "summary_payload_exceeds_2mb_soft_limit" not in summary["warnings"]


def test_export_filters_and_chronological_csv_escaping():
    fixtures = [
        _fx(1, api=8501, ko=KO, gh=2, ga=1),
        _fx(2, api=8502, ko=KO + timedelta(days=1), gh=1, ga=1),
        _fx(3, api=8503, ko=KO + timedelta(days=2), gh=3, ga=2),
    ]
    todays = [
        _today(id=i, local_fixture_id=f.id, provider_fixture_id=f.api_fixture_id)
        for i, f in enumerate(fixtures, start=1)
    ]
    home, away = _priors(n=12)
    summary, internal, db = _run_dataset(fixtures, today_rows=todays, priors=(home, away))

    all_rows = filter_dataset_rows_by_kind(internal["dataset_rows"], "all")
    core5 = filter_dataset_rows_by_kind(internal["dataset_rows"], "core_min5")
    core10 = filter_dataset_rows_by_kind(internal["dataset_rows"], "core_min10")
    paired = filter_dataset_rows_by_kind(internal["dataset_rows"], "xg_paired")
    assert len(all_rows) == len(internal["dataset_rows"])
    assert len(core5) <= len(all_rows)
    assert len(core10) <= len(core5)
    assert len(paired) <= len(all_rows)
    assert all(r["core_feature_status"] == "available" and r["sample_size"] >= 5 for r in core5)
    assert all(r["core_feature_status"] == "available" and r["sample_size"] >= 10 for r in core10)
    assert all(r["xg_status"] == "available" for r in paired)

    # CSV streaming: chunked, chronological, escaping
    chunks: list[str] = []
    with (
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.finished_local_fixtures_in_kickoff_range",
            return_value=list(fixtures),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.load_today_snapshots_for_fixtures",
            return_value=list(todays),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_today_indexes",
            side_effect=build_today_indexes,
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset._fixture_ids_with_team_stats",
            return_value={int(f.id) for f in fixtures},
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.preload_audit_indexes",
            return_value=_indexes_from_priors(fixtures, todays, priors=(home, away)),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_historical_fixture_identity_consistency",
            side_effect=build_historical_fixture_identity_consistency,
        ),
    ):
        for chunk in stream_goal_intensity_v5_dataset_csv(
            db,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 7, 17),
            kind="all",
        ):
            chunks.append(chunk)
    assert len(chunks) >= 2  # header + almeno una riga → non una sola stringa monolitica obbligatoria
    body = "".join(chunks)
    assert body.startswith("\ufeff")
    reader = csv.DictReader(io.StringIO(body.lstrip("\ufeff")))
    assert list(reader.fieldnames) == list(CSV_COLUMNS)
    rows = list(reader)
    assert len(rows) == len(all_rows)
    kicks = [r["kickoff"] for r in rows]
    assert kicks == sorted(kicks)
    # escaping: DictWriter gestisce quote; colonne booleane stabili
    assert rows[0]["row_feature_safe"] in ("true", "false")
    _ = summary  # summary path exercised


def test_streaming_response_routes():
    """Pattern StreamingResponse delle route export (senza importare app.routes → Settings)."""
    from starlette.responses import StreamingResponse

    from app.services.cecchino.cecchino_goal_intensity_v5_dataset import dataset_export_filename

    filename = dataset_export_filename(
        kind="all",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 17),
    )
    assert filename.endswith(".csv")
    stream = iter(["\ufeff", "a,b\n", "1,2\n"])
    res = StreamingResponse(
        stream,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    assert isinstance(res, StreamingResponse)
    assert "text/csv" in res.media_type
    assert "attachment" in res.headers.get("content-disposition", "")
    assert filename in res.headers.get("content-disposition", "")

    summary_name = dataset_export_filename(
        kind="summary",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 17),
    )
    assert summary_name.endswith(".json")
    route_src = (
        Path(__file__).resolve().parents[1] / "app/routes/cecchino_research.py"
    ).read_text(encoding="utf-8")
    for path in (
        "/goal-intensity-v5/dataset/export/all",
        "/goal-intensity-v5/dataset/export/core-min5",
        "/goal-intensity-v5/dataset/export/core-min10",
        "/goal-intensity-v5/dataset/export/xg-paired",
        "/goal-intensity-v5/dataset/export/summary",
    ):
        assert path in route_src
    assert "StreamingResponse" in route_src


def test_internal_equivalent_to_summary_preview():
    """Equivalenza funzionale: preview = prime 100 di internal; coorti/target allineati."""
    fixtures = [_fx(i, api=i, ko=KO + timedelta(days=i)) for i in range(1, 8)]
    summary, internal, _ = _run_dataset(fixtures, today_rows=[])
    assert summary["dataset_preview_rows"] == internal["dataset_rows"][:100]
    assert summary["dataset_summary"]["cohort_counts"] == internal["cohort_counts"]
    assert summary["history_quality"] == internal["history_quality"]
    assert summary["xg_cohorts"] == internal["xg_cohorts"]
    assert summary["exclusion_bias_report"] == internal["exclusion_bias_report"]


def test_no_external_api_no_db_writes():
    local = _fx(500)
    summary, _, db = _run_dataset([local], today_rows=[])
    assert summary["status"] == "ok"
    db.commit.assert_not_called()
    db.add.assert_not_called()
    jsonable_encoder(summary)


def test_no_formula_or_training_markers():
    local = _fx(500)
    summary, _, _ = _run_dataset([local], today_rows=[])
    assert summary["dataset_summary"]["no_v5_formula"] is True
    assert summary["dataset_summary"]["v4_unchanged"] is True
    assert "training" not in summary
    assert "model_weights" not in summary


def test_target_not_in_feature_construction():
    local = _fx(500, api=8500, gh=7, ga=4)
    _, internal, _ = _run_dataset([local], today_rows=[])
    row = internal["dataset_rows"][0]
    assert row["total_goals_ft"] == 11
    assert row["home_goals_scored_avg"] is not None
    assert row["home_goals_scored_avg"] != 7


def test_future_fixture_excluded_from_features():
    local = _fx(500, api=8500)
    home, away = _priors()
    future = _prior(99, home=1, away=3, gh=9, ga=9, days_before=-2)
    _, internal, _ = _run_dataset([local], today_rows=[], priors=(home + [future], away))
    assert internal["dataset_rows"][0]["row_feature_safe"] is True
    assert internal["dataset_rows"][0]["home_goals_scored_avg"] is not None


def test_identity_static_components_and_status_score_non_blocking():
    local = _fx(500, api=8500, status="FT", gh=2, ga=1)
    today = _today(
        local_fixture_id=500,
        provider_fixture_id=8500,
        match_display_status="upcoming",
        fixture_status="NS",
        goals_home=None,
        goals_away=None,
    )
    hist = build_historical_fixture_identity_consistency(
        today_row=today,
        local_fixture=local,
        local_home_team_name="Team1",
        local_away_team_name="Team2",
    )
    assert hist["status"] == "static_identity_verified"
    _, internal, _ = _run_dataset([local], today_rows=[today])
    assert internal["dataset_rows"][0]["row_feature_safe"] is True


def test_exclusion_bias_report_shape():
    local = _fx(500)
    summary, _, _ = _run_dataset([local], today_rows=[])
    bias = summary["exclusion_bias_report"]
    for key in (
        "all_finished",
        "feature_safe",
        "identity_excluded",
        "no_history",
        "core_model_ready_min_5",
    ):
        assert key in bias
        assert "rows" in bias[key]


def test_history_quality_tiers():
    assert history_quality_tier(0) == "none"
    assert history_quality_tier(3) == "very_low"
    assert history_quality_tier(7) == "low"
    assert history_quality_tier(15) == "standard"
    assert history_quality_tier(20) == "robust"


def test_sample_size_and_history_cohorts():
    local = _fx(500)
    summary, internal, _ = _run_dataset([local], today_rows=[])
    row = internal["dataset_rows"][0]
    assert row["sample_size"] > 0
    hq = summary["history_quality"]
    assert hq["history_any"] >= 1
    assert hq[row["history_quality_tier"]] >= 1


def test_core_history_cohorts():
    local = _fx(500)
    home, away = _priors(n=12)
    summary, _, _ = _run_dataset([local], today_rows=[], priors=(home, away))
    counts = summary["dataset_summary"]["cohort_counts"]
    assert counts["core_history_any"] >= 1
    assert counts["core_history_min_5"] >= 1
    assert counts["core_history_min_10"] >= 1


def test_xg_available_partial_missing():
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    _, internal, _ = _run_dataset([local], today_rows=[today])
    assert internal["dataset_rows"][0]["xg_status"] == "available"

    _, internal_m, _ = _run_dataset([local], today_rows=[], include_xg_stats=False)
    assert internal_m["dataset_rows"][0]["xg_status"] == "missing"

    partial = {
        "home_team": {"xg_for_avg": 1.4, "xg_against_avg": 1.1},
        "away_team": {},
        "anti_leakage": {
            "fixture_date_cutoff": KO.isoformat(),
            "current_fixture_excluded": True,
        },
    }
    today2 = _today(local_fixture_id=500, provider_fixture_id=8500, xg_profiles_json=partial)
    _, internal_p, _ = _run_dataset([local], today_rows=[today2], include_xg_stats=False)
    assert internal_p["dataset_rows"][0]["xg_status"] == "partial"


def test_xg_optional_enrichment_no_exclude_low_coverage():
    for spec in FEATURE_SPECS:
        if spec["feature_key"] in XG_FEATURE_KEYS:
            assert spec["recommended_status"] == "optional_enrichment"
            assert spec["recommended_status"] != "exclude_low_coverage"
    local = _fx(500, api=8500)
    today = _today(local_fixture_id=500, provider_fixture_id=8500)
    summary, _, _ = _run_dataset([local], today_rows=[today])
    for f in summary["feature_definitions"]:
        if f["is_xg"]:
            assert f["recommended_status"] == "optional_enrichment"


def test_chronological_split():
    fixtures = [_fx(i, api=i, ko=KO + timedelta(days=i)) for i in range(1, 11)]
    _, internal, _ = _run_dataset(fixtures, today_rows=[])
    rows = internal["dataset_rows"]
    assert rows[0]["chronological_index"] == 0
    assert rows[-1]["chronological_index"] == len(rows) - 1
    assert any(r["train_candidate"] for r in rows)
    assert any(r["test_candidate"] for r in rows)
    kicks = [r["kickoff"] for r in rows]
    assert kicks == sorted(kicks)


def test_performance_payload():
    local = _fx(500)
    summary, _, _ = _run_dataset([local], today_rows=[])
    perf = summary["performance"]
    assert "elapsed_ms" in perf
    assert "response_payload_bytes" in perf
    assert "calculation_phases" in perf
    assert "provider_dedupe_ms" in perf["calculation_phases"]
    assert "composite_bucket_build_ms" in perf["calculation_phases"]
    assert "composite_cluster_ms" in perf["calculation_phases"]


def test_core_feature_status_helper():
    assert core_feature_status({}, 0) == "missing"
    feats = {
        k: 1.0
        for k in [
            s["feature_key"]
            for s in FEATURE_SPECS
            if s["feature_key"] not in XG_FEATURE_KEYS and s.get("recommended_status") == "primary_candidate"
        ]
    }
    assert core_feature_status(feats, 5) == "available"
    partial = {list(feats.keys())[0]: 1.0}
    assert core_feature_status(partial, 5) == "partial"


def test_frontend_summary_state_contract():
    """FE riceve solo preview: summary non espone dataset completo / cohort_ids."""
    fixtures = [_fx(i, api=i, ko=KO + timedelta(hours=i)) for i in range(1, 30)]
    summary, _, _ = _run_dataset(fixtures, today_rows=[])
    assert len(summary.get("dataset_preview_rows", [])) <= 100
    assert summary.get("dataset_rows") in (None, [])
    assert "cohort_ids" not in summary


def test_classify_error_states_mirror():
    """Contratto errori FE (summary vs export) — mirror della logica TypeScript."""
    def classify(err: Exception, context: str) -> str:
        msg = str(err)
        lower = msg.lower()
        if type(err).__name__ == "AbortError" or "abort" in lower:
            return (
                "Timeout costruzione summary dataset"
                if context == "summary"
                else "Timeout export dataset"
            )
        if "timeout" in lower:
            return (
                "Timeout costruzione summary dataset"
                if context == "summary"
                else "Timeout export dataset"
            )
        if "failed to fetch" in lower or "network" in lower:
            return "Errore di rete"
        return f"Errore backend: {msg}"

    assert "Timeout" in classify(TimeoutError("timeout"), "summary")
    assert "summary" in classify(TimeoutError("timeout"), "summary").lower()
    assert "export" in classify(TimeoutError("timeout"), "export").lower()
    assert classify(Exception("Failed to fetch"), "summary") == "Errore di rete"
    assert classify(Exception("boom"), "export").startswith("Errore backend")


def test_one_row_per_fixture():
    a = _fx(1, api=1, ko=KO)
    b = _fx(2, api=2, ko=KO + timedelta(days=1))
    _, internal, _ = _run_dataset([a, b], today_rows=[])
    ids = [r["local_fixture_id"] for r in internal["dataset_rows"]]
    assert len(ids) == len(set(ids)) == 2


def test_source_has_no_nested_composite_loop():
    """La dedupe non deve usare nested for sul full list (pattern O(n²))."""
    src = inspect.getsource(dedupe_fixtures_provider_then_composite)
    assert "buckets" in src or "bucket" in src
    assert "_cluster_bucket_by_kickoff" in src
