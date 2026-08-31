"""Builder + reader League Pattern Analysis — snapshot aggregato READ-ONLY sulle run lockate.

Usa solo helper pubblici real_only di pattern_lab_preset_metrics.
Non modifica P01–P12, Historical Scan, né 2025/26.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_match_snapshot import (
    CecchinoLabHistoricalMatchSnapshot,
)
from app.models.cecchino_lab_historical_scan_run import CecchinoLabHistoricalScanRun
from app.models.cecchino_lab_league_pattern_analysis_snapshot import (
    STATUS_READY,
    CecchinoLabLeaguePatternAnalysisSnapshot,
)
from app.services.cecchino_data_lab.competition_catalog import list_competitions
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.league_pattern_analysis_registry import (
    ANALYSIS_REVISION,
    ANALYSIS_VERSION,
    FUTURE_OOS_SEASON,
    INCOMPATIBILITY_HYPOTHESES,
    LEAGUE_NATIVE_PATTERNS,
    LOCKED_SEASONS,
    LOCKED_SOURCE_RUN_IDS,
    LOW_SAMPLE_N,
    MARKET_UNIVERSE_VERSION,
    MIN_SAMPLE_TOP_INSIGHTS,
    SEASON_BY_RUN,
    SPECIALIZATION_HYPOTHESES,
    FROZEN_LN_SCIENTIFIC_FILTERS_SHA256,
    get_league_native_pattern,
    humanize_filters,
    ln_scientific_filters,
)
from app.services.cecchino_data_lab.pattern_lab_filters import (
    parse_pattern_lab_filters,
    row_passes_filters,
)
from app.services.cecchino_data_lab.pattern_lab_preset_metrics import (
    bump_pattern_selection,
    bump_real_only_econ,
    empty_econ_bucket,
    finalize_real_only_econ,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PATTERN_LAB_PRESETS,
    PRESET_REGISTRY_VERSION,
    preset_scientific_filters,
    scientific_filters_sha256,
)
from app.services.cecchino_data_lab.historical_analytics_agg import as_dict


def _resolve_git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return (out or "").strip() or None
    except Exception:
        return None


def _season_short(season: str) -> str:
    parts = season.split("/")
    if len(parts) == 2 and len(parts[0]) >= 4 and len(parts[1]) >= 4:
        return f"{parts[0][-2:]}/{parts[1][-2:]}"
    return season


def _ui_metrics(econ: dict[str, Any]) -> dict[str, Any]:
    """Mapping display: N = real_quote_count (real_only)."""
    n = int(econ.get("real_quote_count") or 0)
    roi = econ.get("roi")
    return {
        "n": n,
        "selections": int(econ.get("selections") or 0),
        "wins": int(econ.get("wins") or 0),
        "losses": int(econ.get("losses") or 0),
        "void": int(econ.get("void") or 0),
        "win_rate": econ.get("win_rate"),
        "avg_odds": econ.get("avg_real_odds"),
        "profit_1u": float(econ.get("profit_1u") or 0.0),
        "roi": roi,
        "roi_pct": (float(roi) * 100.0) if roi is not None else None,
    }


def _ensure_bucket(store: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    if key not in store:
        store[key] = empty_econ_bucket()
    return store[key]


def _season_stability(by_season: dict[str, dict[str, Any]]) -> dict[str, Any]:
    seasons_with_bets = 0
    positive = 0
    rois: list[float] = []
    for season in LOCKED_SEASONS:
        econ = by_season.get(season) or empty_econ_bucket()
        fin = finalize_real_only_econ(econ)
        n = int(fin["real_quote_count"])
        if n <= 0:
            continue
        seasons_with_bets += 1
        roi = fin.get("roi")
        if roi is not None:
            rois.append(float(roi))
            if float(roi) > 0:
                positive += 1
    return {
        "positive_seasons": positive,
        "seasons_with_bets": seasons_with_bets,
        "stability_label": f"{positive}/{seasons_with_bets} stagioni positive"
        if seasons_with_bets
        else "0/0",
        "best_season_roi": max(rois) if rois else None,
        "worst_season_roi": min(rois) if rois else None,
        "best_season_roi_pct": (max(rois) * 100.0) if rois else None,
        "worst_season_roi_pct": (min(rois) * 100.0) if rois else None,
    }


def _finalize_pattern_block(
    *,
    pattern_id: str,
    total: dict[str, Any],
    by_season: dict[str, dict[str, Any]],
    by_competition_season: dict[str, dict[str, dict[str, Any]]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    season_map: dict[str, Any] = {}
    for season in LOCKED_SEASONS:
        fin = finalize_real_only_econ(by_season.get(season) or empty_econ_bucket())
        season_map[season] = {
            **_ui_metrics(fin),
            "season": season,
            "season_short": _season_short(season),
        }
    stab = _season_stability(by_season)
    total_fin = finalize_real_only_econ(total)
    total_ui = _ui_metrics(total_fin)

    competitions: dict[str, Any] = {}
    for comp, seasons in sorted(by_competition_season.items()):
        comp_total = empty_econ_bucket()
        season_ui: dict[str, Any] = {}
        for season in LOCKED_SEASONS:
            b = seasons.get(season) or empty_econ_bucket()
            for k in ("selections", "real_quote_count", "wins", "losses", "void", "quota_n"):
                comp_total[k] += int(b[k])
            comp_total["profit_1u"] += float(b["profit_1u"])
            comp_total["quota_sum"] += float(b["quota_sum"])
            season_ui[season] = {
                **_ui_metrics(finalize_real_only_econ(b)),
                "season": season,
                "season_short": _season_short(season),
            }
        competitions[comp] = {
            "competition": comp,
            "by_season": season_ui,
            "total": {
                **_ui_metrics(finalize_real_only_econ(comp_total)),
                **_season_stability(seasons),
            },
        }

    return {
        **meta,
        "pattern_id": pattern_id,
        "by_season": season_map,
        "total": {**total_ui, **stab},
        "by_competition": competitions,
    }


def _parse_ft_goals(result_json: Any) -> tuple[int | None, int | None]:
    result = as_dict(result_json)
    ft = as_dict(result.get("fulltime") or result.get("ft"))
    home = ft.get("home")
    away = ft.get("away")
    try:
        h = int(home) if home is not None else None
    except (TypeError, ValueError):
        h = None
    try:
        a = int(away) if away is not None else None
    except (TypeError, ValueError):
        a = None
    return h, a


def compute_competition_regimes_from_snapshots(
    snapshots: list[Any],
) -> dict[str, Any]:
    """Baseline a livello MATCH (una riga snapshot = una partita), non market-row."""
    by_comp_season: dict[str, dict[str, dict[str, Any]]] = {}
    catalog = [c.display_name for c in list_competitions()]

    def empty_reg() -> dict[str, Any]:
        return {
            "matches": 0,
            "home_wins": 0,
            "draws": 0,
            "away_wins": 0,
            "over_25": 0,
            "under_25": 0,
            "goals_sum": 0.0,
            "goals_n": 0,
        }

    for snap in snapshots:
        comp = str(getattr(snap, "competition_name", None) or "unknown")
        season = str(getattr(snap, "season_label", None) or "unknown")
        if comp not in by_comp_season:
            by_comp_season[comp] = {}
        if season not in by_comp_season[comp]:
            by_comp_season[comp][season] = empty_reg()
        bucket = by_comp_season[comp][season]
        bucket["matches"] += 1
        h, a = _parse_ft_goals(getattr(snap, "result_json", None))
        if h is None or a is None:
            continue
        if h > a:
            bucket["home_wins"] += 1
        elif h == a:
            bucket["draws"] += 1
        else:
            bucket["away_wins"] += 1
        total_goals = h + a
        bucket["goals_sum"] += float(total_goals)
        bucket["goals_n"] += 1
        if total_goals > 2:
            bucket["over_25"] += 1
        else:
            bucket["under_25"] += 1

    def finalize_reg(b: dict[str, Any]) -> dict[str, Any]:
        m = int(b["matches"]) or 0
        decided = int(b["home_wins"]) + int(b["draws"]) + int(b["away_wins"])
        gn = int(b["goals_n"])

        def pct(num: int, den: int) -> float | None:
            return (float(num) / float(den) * 100.0) if den else None

        return {
            "matches": m,
            "home_pct": pct(int(b["home_wins"]), decided),
            "draw_pct": pct(int(b["draws"]), decided),
            "away_pct": pct(int(b["away_wins"]), decided),
            "over_25_pct": pct(int(b["over_25"]), gn),
            "under_25_pct": pct(int(b["under_25"]), gn),
            "avg_ft_goals": (float(b["goals_sum"]) / float(gn)) if gn else None,
        }

    leagues: list[dict[str, Any]] = []
    for comp in catalog:
        seasons = by_comp_season.get(comp) or {}
        pooled = empty_reg()
        by_season_ui: dict[str, Any] = {}
        for season in LOCKED_SEASONS:
            raw = seasons.get(season) or empty_reg()
            by_season_ui[season] = {
                "season": season,
                "season_short": _season_short(season),
                **finalize_reg(raw),
            }
            for k in (
                "matches",
                "home_wins",
                "draws",
                "away_wins",
                "over_25",
                "under_25",
                "goals_n",
            ):
                pooled[k] += int(raw[k])
            pooled["goals_sum"] += float(raw["goals_sum"])
        leagues.append(
            {
                "competition": comp,
                "by_season": by_season_ui,
                "total": finalize_reg(pooled),
            }
        )

    return {
        "competitions_count": len(leagues),
        "leagues": leagues,
    }


def _validate_locked_runs(db: Session, run_ids: list[int]) -> list[CecchinoLabHistoricalScanRun]:
    if list(run_ids) != list(LOCKED_SOURCE_RUN_IDS):
        raise CecchinoLabImportError(
            "lpa_locked_runs",
            f"Source run bloccate: attese {LOCKED_SOURCE_RUN_IDS}, ricevute {run_ids}",
            status_code=400,
        )
    runs = (
        db.execute(
            select(CecchinoLabHistoricalScanRun).where(
                CecchinoLabHistoricalScanRun.id.in_(run_ids)
            )
        )
        .scalars()
        .all()
    )
    by_id = {int(r.id): r for r in runs}
    missing = [rid for rid in run_ids if rid not in by_id]
    if missing:
        raise CecchinoLabImportError(
            "lpa_runs_missing",
            f"Run non trovate: {missing}",
            status_code=404,
        )
    ordered = [by_id[rid] for rid in run_ids]
    for run in ordered:
        season = str(run.season_label or "")
        expected = SEASON_BY_RUN.get(int(run.id))
        if expected and season != expected:
            raise CecchinoLabImportError(
                "lpa_season_mismatch",
                f"Run #{run.id}: season_label={season!r} attesa {expected!r}",
                status_code=400,
            )
        if "2025/2026" in season or season == FUTURE_OOS_SEASON:
            raise CecchinoLabImportError(
                "lpa_future_oos_forbidden",
                "2025/2026 non ammessa nel dataset League Pattern Analysis",
                status_code=400,
            )
    return ordered


def build_league_pattern_analysis_snapshot(
    db: Session,
    *,
    source_run_ids: list[int] | None = None,
) -> CecchinoLabLeaguePatternAnalysisSnapshot:
    """Costruisce e persiste uno snapshot aggregato (append-only)."""
    from app.services.cecchino_data_lab.pattern_lab_service import iter_pattern_lab_rows

    run_ids = list(source_run_ids or LOCKED_SOURCE_RUN_IDS)
    runs = _validate_locked_runs(db, run_ids)

    # Verifica hash LN congelati prima del build.
    for p in LEAGUE_NATIVE_PATTERNS:
        h = scientific_filters_sha256(ln_scientific_filters(p))
        frozen = FROZEN_LN_SCIENTIFIC_FILTERS_SHA256[p["id"]]
        if h != frozen:
            raise CecchinoLabImportError(
                "lpa_ln_hash_drift",
                f"Hash LN {p['id']} drift: computed={h} frozen={frozen}",
                status_code=500,
            )

    parsed_presets = [
        (p, parse_pattern_lab_filters(preset_scientific_filters(p)))
        for p in PATTERN_LAB_PRESETS
    ]
    parsed_ln = [
        (p, parse_pattern_lab_filters(ln_scientific_filters(p)))
        for p in LEAGUE_NATIVE_PATTERNS
    ]

    p_totals: dict[str, dict[str, Any]] = {
        p["id"]: empty_econ_bucket() for p, _ in parsed_presets
    }
    p_by_season: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }
    p_by_comp_season: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
        p["id"]: {} for p, _ in parsed_presets
    }

    ln_totals: dict[str, dict[str, Any]] = {
        p["id"]: empty_econ_bucket() for p, _ in parsed_ln
    }
    ln_by_season: dict[str, dict[str, dict[str, Any]]] = {
        p["id"]: {} for p, _ in parsed_ln
    }

    market_rows = 0
    snapshot_ids: set[int] = set()
    base_filters = parse_pattern_lab_filters(
        {"eligibility": "eligible_core", "market_informative": True}
    )

    for row in iter_pattern_lab_rows(
        db, run_ids, filters=base_filters, apply_filters=True
    ):
        market_rows += 1
        sid = row.get("snapshot_id")
        if sid is not None:
            snapshot_ids.add(int(sid))
        season = str(row.get("season") or "unknown")
        comp = str(row.get("competition") or "unknown")

        for preset, filt in parsed_presets:
            if not row_passes_filters(row, filt):
                continue
            pid = preset["id"]
            bump_pattern_selection(p_totals[pid], row)
            bump_real_only_econ(p_totals[pid], row)
            bump_pattern_selection(_ensure_bucket(p_by_season[pid], season), row)
            bump_real_only_econ(p_by_season[pid][season], row)
            if comp not in p_by_comp_season[pid]:
                p_by_comp_season[pid][comp] = {}
            bump_pattern_selection(
                _ensure_bucket(p_by_comp_season[pid][comp], season), row
            )
            bump_real_only_econ(p_by_comp_season[pid][comp][season], row)

        for pattern, filt in parsed_ln:
            if not row_passes_filters(row, filt):
                continue
            lid = pattern["id"]
            bump_pattern_selection(ln_totals[lid], row)
            bump_real_only_econ(ln_totals[lid], row)
            bump_pattern_selection(_ensure_bucket(ln_by_season[lid], season), row)
            bump_real_only_econ(ln_by_season[lid][season], row)

    # Competition regimes: snapshot eligible unici (match-level).
    snaps = (
        db.execute(
            select(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id.in_(run_ids),
                CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status
                == "eligible_core",
            )
        )
        .scalars()
        .all()
    )
    regimes = compute_competition_regimes_from_snapshots(list(snaps))

    global_patterns: list[dict[str, Any]] = []
    for preset, _ in parsed_presets:
        pid = preset["id"]
        filters = preset_scientific_filters(preset)
        human = humanize_filters(
            filters,
            pattern_id=pid,
            human_title=None,
        )
        # Titolo umano sintetico da label preset + lessico
        label = str(preset.get("label") or pid)
        human["human_title"] = label.split("·", 1)[-1].strip() if "·" in label else label
        meta = {
            "label": preset.get("label"),
            "status": preset.get("status"),
            "ui_badge": preset.get("ui_badge"),
            "filters": filters,
            "scientific_filters_sha256": scientific_filters_sha256(filters),
            "performance_quote_policy": preset.get("performance_quote_policy"),
            "human": human,
        }
        global_patterns.append(
            _finalize_pattern_block(
                pattern_id=pid,
                total=p_totals[pid],
                by_season=p_by_season[pid],
                by_competition_season=p_by_comp_season[pid],
                meta=meta,
            )
        )

    league_native: list[dict[str, Any]] = []
    for pattern, _ in parsed_ln:
        lid = pattern["id"]
        filters = ln_scientific_filters(pattern)
        human = humanize_filters(
            filters,
            pattern_id=lid,
            human_title=pattern.get("human_title"),
        )
        block = _finalize_pattern_block(
            pattern_id=lid,
            total=ln_totals[lid],
            by_season=ln_by_season[lid],
            by_competition_season={},
            meta={
                "human_title": pattern.get("human_title"),
                "competition": pattern.get("competition"),
                "status": pattern.get("status"),
                "discovery_seasons": list(pattern.get("discovery_seasons") or []),
                "internal_validation_seasons": list(
                    pattern.get("internal_validation_seasons") or []
                ),
                "first_true_oos_season": pattern.get("first_true_oos_season"),
                "filters": filters,
                "scientific_filters_sha256": FROZEN_LN_SCIENTIFIC_FILTERS_SHA256[lid],
                "performance_quote_policy": pattern.get("performance_quote_policy"),
                "human": human,
            },
        )
        league_native.append(block)

    # Heatmap Pattern × League (pooled 4 stagioni)
    heatmap_cells: list[dict[str, Any]] = []
    for gp in global_patterns:
        pid = gp["pattern_id"]
        for comp, cdata in (gp.get("by_competition") or {}).items():
            tot = cdata.get("total") or {}
            n = int(tot.get("n") or 0)
            heatmap_cells.append(
                {
                    "pattern_id": pid,
                    "competition": comp,
                    "n": n,
                    "roi": tot.get("roi"),
                    "roi_pct": tot.get("roi_pct"),
                    "profit_1u": tot.get("profit_1u"),
                    "positive_seasons": tot.get("positive_seasons"),
                    "seasons_with_bets": tot.get("seasons_with_bets"),
                    "worst_season_roi_pct": tot.get("worst_season_roi_pct"),
                    "best_season_roi_pct": tot.get("best_season_roi_pct"),
                    "low_sample": n > 0 and n < LOW_SAMPLE_N,
                }
            )

    def _hyp_metrics(pattern_id: str, competition: str) -> dict[str, Any]:
        gp = next((x for x in global_patterns if x["pattern_id"] == pattern_id), None)
        if not gp:
            return _ui_metrics(finalize_real_only_econ(empty_econ_bucket()))
        cdata = (gp.get("by_competition") or {}).get(competition) or {}
        tot = cdata.get("total") or {}
        return {
            **{k: tot.get(k) for k in (
                "n",
                "wins",
                "losses",
                "void",
                "win_rate",
                "avg_odds",
                "profit_1u",
                "roi",
                "roi_pct",
                "positive_seasons",
                "seasons_with_bets",
                "stability_label",
                "best_season_roi_pct",
                "worst_season_roi_pct",
            )},
            "by_season": cdata.get("by_season") or {},
        }

    specializations = []
    for hyp in SPECIALIZATION_HYPOTHESES:
        specializations.append(
            {
                **hyp,
                "metrics": _hyp_metrics(hyp["pattern_id"], hyp["competition"]),
            }
        )
    incompatibilities = []
    for hyp in INCOMPATIBILITY_HYPOTHESES:
        metrics = _hyp_metrics(hyp["pattern_id"], hyp["competition"])
        neg = 0
        bets = int(metrics.get("seasons_with_bets") or 0)
        for season in LOCKED_SEASONS:
            s = (metrics.get("by_season") or {}).get(season) or {}
            if int(s.get("n") or 0) > 0 and (s.get("roi") is not None) and float(s["roi"]) < 0:
                neg += 1
        incompatibilities.append(
            {
                **hyp,
                "metrics": metrics,
                "negative_seasons": neg,
                "negative_label": f"{neg}/{bets} stagioni negative" if bets else "0/0",
            }
        )

    # Top insights
    candidates = []
    for gp in global_patterns:
        tot = gp.get("total") or {}
        n = int(tot.get("n") or 0)
        if n < MIN_SAMPLE_TOP_INSIGHTS:
            continue
        candidates.append(
            {
                "pattern_id": gp["pattern_id"],
                "human_title": (gp.get("human") or {}).get("human_title"),
                "n": n,
                "roi_pct": tot.get("roi_pct"),
                "profit_1u": tot.get("profit_1u"),
                "positive_seasons": tot.get("positive_seasons"),
                "seasons_with_bets": tot.get("seasons_with_bets"),
                "worst_season_roi_pct": tot.get("worst_season_roi_pct"),
            }
        )

    def _pick(key: str, reverse: bool = True):
        ranked = [c for c in candidates if c.get(key) is not None]
        ranked.sort(key=lambda x: (x.get(key) is None, x.get(key)), reverse=reverse)
        return ranked[0] if ranked else None

    four_of_four = [
        c
        for c in candidates
        if int(c.get("positive_seasons") or 0) == 4
        and int(c.get("seasons_with_bets") or 0) == 4
    ]
    four_of_four.sort(key=lambda x: float(x.get("roi_pct") or 0), reverse=True)

    top_insights = {
        "min_sample": MIN_SAMPLE_TOP_INSIGHTS,
        "best_pooled_roi": _pick("roi_pct", reverse=True),
        "most_profit": _pick("profit_1u", reverse=True),
        "most_selections": _pick("n", reverse=True),
        "four_of_four_positive": four_of_four[:5],
        "best_worst_season_roi": _pick("worst_season_roi_pct", reverse=True),
    }

    summary = {
        "seasons_count": len(LOCKED_SEASONS),
        "competitions_count": len(list_competitions()),
        "eligible_matches_analyzed": len(snaps),
        "informative_market_rows_analyzed": market_rows,
        "global_patterns_count": len(global_patterns),
        "league_native_count": len(league_native),
        "source_run_ids": list(run_ids),
        "source_seasons": list(LOCKED_SEASONS),
        "analysis_dataset_locked": True,
        "future_oos_season": FUTURE_OOS_SEASON,
        "future_oos_included": False,
        "top_insights": top_insights,
    }

    methodology = {
        "dataset": "2021/22 - 2024/25",
        "source_run_ids": list(run_ids),
        "global_patterns": "P01-P12",
        "league_native": "LN01-LN10",
        "league_native_discovery": "21/22 - 23/24",
        "internal_validation": "24/25",
        "first_true_oos": "25/26",
        "future_oos_season": FUTURE_OOS_SEASON,
        "future_oos_used": False,
        "economic_unit": "1u flat stake",
        "performance_quote_policy": "real_only",
        "preset_registry_version": PRESET_REGISTRY_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_revision": ANALYSIS_REVISION,
        "market_universe_version": MARKET_UNIVERSE_VERSION,
        "source_enrichment_batch_ids": [],
        "min_sample_top_insights": MIN_SAMPLE_TOP_INSIGHTS,
        "low_sample_n": LOW_SAMPLE_N,
    }

    scan_versions = {
        str(r.id): {
            "season_label": r.season_label,
            "scan_version": getattr(r, "scan_version", None),
            "status": r.status,
            "source_git_commit": getattr(r, "source_git_commit", None),
        }
        for r in runs
    }

    snap = CecchinoLabLeaguePatternAnalysisSnapshot(
        analysis_version=ANALYSIS_VERSION,
        analysis_revision=ANALYSIS_REVISION,
        status=STATUS_READY,
        generated_at=datetime.now(timezone.utc),
        source_run_ids=list(run_ids),
        source_seasons=list(LOCKED_SEASONS),
        scan_versions=scan_versions,
        preset_registry_version=PRESET_REGISTRY_VERSION,
        source_git_commit=_resolve_git_commit(),
        analysis_dataset_locked=True,
        future_oos_season=FUTURE_OOS_SEASON,
        future_oos_included=False,
        source_enrichment_batch_ids=[],
        market_universe_version=MARKET_UNIVERSE_VERSION,
        summary_json=summary,
        competition_regimes_json=regimes,
        global_patterns_json={"patterns": global_patterns},
        pattern_league_matrix_json={
            "pattern_ids": [f"P{i:02d}" for i in range(1, 13)],
            "competitions": [c.display_name for c in list_competitions()],
            "cells": heatmap_cells,
            "low_sample_n": LOW_SAMPLE_N,
        },
        specializations_json={"items": specializations},
        incompatibilities_json={"items": incompatibilities},
        league_native_json={"patterns": league_native},
        methodology_json=methodology,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def get_latest_league_pattern_analysis_snapshot(
    db: Session,
    *,
    analysis_version: str = ANALYSIS_VERSION,
) -> CecchinoLabLeaguePatternAnalysisSnapshot | None:
    """Ultimo snapshot status=ready per analysis_version (non ultima riga grezza)."""
    return db.execute(
        select(CecchinoLabLeaguePatternAnalysisSnapshot)
        .where(
            CecchinoLabLeaguePatternAnalysisSnapshot.analysis_version
            == analysis_version,
            CecchinoLabLeaguePatternAnalysisSnapshot.status == STATUS_READY,
        )
        .order_by(
            CecchinoLabLeaguePatternAnalysisSnapshot.generated_at.desc(),
            CecchinoLabLeaguePatternAnalysisSnapshot.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def _snapshot_meta(snap: CecchinoLabLeaguePatternAnalysisSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": int(snap.id),
        "analysis_version": snap.analysis_version,
        "analysis_revision": snap.analysis_revision,
        "status": snap.status,
        "generated_at": snap.generated_at.isoformat() if snap.generated_at else None,
        "source_run_ids": snap.source_run_ids,
        "source_seasons": snap.source_seasons,
        "scan_versions": snap.scan_versions,
        "preset_registry_version": snap.preset_registry_version,
        "source_git_commit": snap.source_git_commit,
        "analysis_dataset_locked": snap.analysis_dataset_locked,
        "future_oos_season": snap.future_oos_season,
        "future_oos_included": snap.future_oos_included,
        "source_enrichment_batch_ids": snap.source_enrichment_batch_ids or [],
        "market_universe_version": snap.market_universe_version,
    }


def serialize_latest_payload(
    snap: CecchinoLabLeaguePatternAnalysisSnapshot,
) -> dict[str, Any]:
    """Payload GET /latest — aggregati, senza raw matches."""
    global_patterns = (snap.global_patterns_json or {}).get("patterns") or []
    # Strip by_competition pesante dalla lista globale (lazy su detail).
    global_compact = []
    for gp in global_patterns:
        global_compact.append(
            {
                "pattern_id": gp.get("pattern_id"),
                "label": gp.get("label"),
                "status": gp.get("status"),
                "ui_badge": gp.get("ui_badge"),
                "human": gp.get("human"),
                "scientific_filters_sha256": gp.get("scientific_filters_sha256"),
                "by_season": gp.get("by_season"),
                "total": gp.get("total"),
            }
        )
    ln_patterns = (snap.league_native_json or {}).get("patterns") or []
    ln_compact = [
        {
            "pattern_id": p.get("pattern_id"),
            "human_title": p.get("human_title"),
            "competition": p.get("competition"),
            "status": p.get("status"),
            "human": p.get("human"),
            "scientific_filters_sha256": p.get("scientific_filters_sha256"),
            "by_season": p.get("by_season"),
            "total": p.get("total"),
            "discovery_seasons": p.get("discovery_seasons"),
            "internal_validation_seasons": p.get("internal_validation_seasons"),
            "first_true_oos_season": p.get("first_true_oos_season"),
        }
        for p in ln_patterns
    ]
    regimes = snap.competition_regimes_json or {}
    regimes_overview = [
        {
            "competition": L.get("competition"),
            "total": L.get("total"),
        }
        for L in (regimes.get("leagues") or [])
    ]
    return {
        "metadata": _snapshot_meta(snap),
        "summary": snap.summary_json,
        "global_patterns": global_compact,
        "competition_regimes_overview": regimes_overview,
        "heatmap": snap.pattern_league_matrix_json,
        "specializations": (snap.specializations_json or {}).get("items") or [],
        "incompatibilities": (snap.incompatibilities_json or {}).get("items") or [],
        "league_native": ln_compact,
        "methodology": snap.methodology_json,
    }


def serialize_league_detail(
    snap: CecchinoLabLeaguePatternAnalysisSnapshot,
    competition: str,
) -> dict[str, Any]:
    regimes = snap.competition_regimes_json or {}
    league = next(
        (
            L
            for L in (regimes.get("leagues") or [])
            if L.get("competition") == competition
        ),
        None,
    )
    if league is None:
        raise CecchinoLabImportError(
            "lpa_league_not_found",
            f"Campionato non trovato nello snapshot: {competition}",
            status_code=404,
        )
    patterns = []
    for gp in (snap.global_patterns_json or {}).get("patterns") or []:
        cdata = (gp.get("by_competition") or {}).get(competition)
        if not cdata:
            patterns.append(
                {
                    "pattern_id": gp.get("pattern_id"),
                    "human": gp.get("human"),
                    "by_season": {
                        s: {
                            "n": 0,
                            "roi_pct": None,
                            "profit_1u": 0.0,
                            "win_rate": None,
                            "avg_odds": None,
                        }
                        for s in LOCKED_SEASONS
                    },
                    "total": {
                        "n": 0,
                        "profit_1u": 0.0,
                        "roi_pct": None,
                        "positive_seasons": 0,
                    },
                }
            )
            continue
        patterns.append(
            {
                "pattern_id": gp.get("pattern_id"),
                "label": gp.get("label"),
                "human": gp.get("human"),
                "by_season": cdata.get("by_season"),
                "total": cdata.get("total"),
            }
        )
    return {
        "metadata": _snapshot_meta(snap),
        "competition": competition,
        "league_overview": league,
        "patterns": patterns,
    }


def serialize_pattern_detail(
    snap: CecchinoLabLeaguePatternAnalysisSnapshot,
    pattern_id: str,
) -> dict[str, Any]:
    gp = next(
        (
            x
            for x in (snap.global_patterns_json or {}).get("patterns") or []
            if x.get("pattern_id") == pattern_id
        ),
        None,
    )
    if gp is None:
        raise CecchinoLabImportError(
            "lpa_pattern_not_found",
            f"Pattern non trovato: {pattern_id}",
            status_code=404,
        )
    return {"metadata": _snapshot_meta(snap), "pattern": gp}


def serialize_native_detail(
    snap: CecchinoLabLeaguePatternAnalysisSnapshot,
    pattern_id: str,
) -> dict[str, Any]:
    p = next(
        (
            x
            for x in (snap.league_native_json or {}).get("patterns") or []
            if x.get("pattern_id") == pattern_id
        ),
        None,
    )
    if p is None:
        # Fallback registry meta se assente nello snapshot
        reg = get_league_native_pattern(pattern_id)
        if not reg:
            raise CecchinoLabImportError(
                "lpa_native_not_found",
                f"League-native non trovato: {pattern_id}",
                status_code=404,
            )
        raise CecchinoLabImportError(
            "lpa_native_missing_in_snapshot",
            f"League-native {pattern_id} assente nello snapshot",
            status_code=404,
        )
    return {"metadata": _snapshot_meta(snap), "pattern": p}
