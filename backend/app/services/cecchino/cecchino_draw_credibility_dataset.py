"""Dataset storico analitico Credibilità X — deduplica, anti-leakage, export (Fase 1B)."""

from __future__ import annotations

import csv
import io
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_balance_analysis import build_balance_analysis_from_final
from app.services.cecchino.cecchino_draw_credibility_research import build_draw_credibility_coverage_audit
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ALL_USABLE_SENSITIVITY,
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_MARKET_SUBSET,
    LEAKAGE_SAFE,
    LEAKAGE_UNSAFE,
    LEAKAGE_UNKNOWN,
    classify_leakage,
    evaluate_internal_features,
    feature_snapshot_at,
    fixtures_in_range,
    normalize_implied_pair,
    normalize_implied_triple,
    normalize_prob_triple,
    num,
    payload_structure_key,
    pct,
    resolve_fulltime_score,
    resolve_result_1x2,
    target_snapshot_at,
    valid_cecchino_odd,
)
from app.services.cecchino.cecchino_goal_formulas import goal_market_kpi_entry
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME, SEL_OVER_2_5, SEL_UNDER_2_5

VERSION = "cecchino_draw_credibility_dataset_v1"

CSV_COLUMNS: tuple[str, ...] = (
    "provider_fixture_id",
    "local_fixture_id",
    "today_fixture_id_feature",
    "today_fixture_id_target",
    "scan_date_feature",
    "scan_date_target",
    "kickoff",
    "country_name",
    "league_name",
    "competition_id",
    "home_team_name",
    "away_team_name",
    "eligibility_status_feature",
    "cohort",
    "draw_ft",
    "ft_home",
    "ft_away",
    "ft_score",
    "result_1x2",
    "quota_cecchino_1",
    "quota_cecchino_x",
    "quota_cecchino_2",
    "prob_x_norm",
    "f36_signed",
    "f36_abs",
    "f36_score_existing",
    "dominant_sign",
    "dominance_pp",
    "conviction_index_candidate",
    "probability_gap_1_2_pp",
    "gap_coherence_index_candidate",
    "quota_under_2_5_cecchino",
    "quota_over_2_5_cecchino",
    "quota_book_x",
    "deviation_x_pp",
    "leakage_status",
    "feature_snapshot_at",
    "target_snapshot_at",
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, value)), 2)


def _classify_conviction(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 20:
        return "Molto Debole"
    if value < 40:
        return "Debole"
    if value < 60:
        return "Moderata"
    if value < 80:
        return "Forte"
    return "Molto Forte"


def _classify_gap_coherence(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 20:
        return "Non Confermato"
    if value < 40:
        return "Debole"
    if value < 60:
        return "Parziale"
    if value < 80:
        return "Confermato"
    return "Fortemente Confermato"


def _x_rank(prob_norm: dict[str, float | None]) -> tuple[int | None, bool]:
    px = prob_norm.get("prob_x_norm")
    if px is None:
        return None, False
    items = [
        ("1", prob_norm.get("prob_1_norm")),
        ("X", px),
        ("2", prob_norm.get("prob_2_norm")),
    ]
    valid = [(k, v) for k, v in items if v is not None]
    if len(valid) < 3:
        return None, False
    ordered = sorted(valid, key=lambda x: x[1], reverse=True)
    max_prob = ordered[0][1]
    ranks = {k: i + 1 for i, (k, _) in enumerate(ordered)}
    tied_top = sum(1 for _, v in valid if v == max_prob) > 1 and px == max_prob
    return ranks.get("X"), tied_top


def _goal_probabilities(
    *,
    goal_markets: dict | None,
    under_odd: float | None,
    over_odd: float | None,
) -> dict[str, Any]:
    under_block = (goal_markets or {}).get(SEL_UNDER_2_5) if isinstance(goal_markets, dict) else None
    over_block = (goal_markets or {}).get(SEL_OVER_2_5) if isinstance(goal_markets, dict) else None
    p_under_direct = num(under_block.get("probability")) if isinstance(under_block, dict) else None
    p_over_direct = num(over_block.get("probability")) if isinstance(over_block, dict) else None

    if valid_cecchino_odd(p_under_direct) and valid_cecchino_odd(p_over_direct):
        pu = p_under_direct if p_under_direct <= 1 else p_under_direct / 100.0
        po = p_over_direct if p_over_direct <= 1 else p_over_direct / 100.0
        total = pu + po
        if total > 0:
            return {
                "prob_under_2_5_cecchino_pct": round(pu / total * 100.0, 2),
                "prob_over_2_5_cecchino_pct": round(po / total * 100.0, 2),
                "goal_probability_source": "direct_probability",
            }

    if valid_cecchino_odd(under_odd) and valid_cecchino_odd(over_odd):
        pu_raw = 1.0 / under_odd
        po_raw = 1.0 / over_odd
        total = pu_raw + po_raw
        if total > 0:
            return {
                "prob_under_2_5_cecchino_pct": round(100.0 * pu_raw / total, 2),
                "prob_over_2_5_cecchino_pct": round(100.0 * po_raw / total, 2),
                "goal_probability_source": "normalized_from_cecchino_odds",
            }

    return {
        "prob_under_2_5_cecchino_pct": None,
        "prob_over_2_5_cecchino_pct": None,
        "goal_probability_source": "missing",
    }


def _iso_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _feature_row_score(row: CecchinoTodayFixture, *, prefer_eligible: bool) -> tuple:
    ev = evaluate_internal_features(row)
    feat_at = feature_snapshot_at(row)
    kickoff = row.kickoff
    if kickoff is not None and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    before_kickoff = True
    if feat_at is not None and kickoff is not None:
        before_kickoff = feat_at < kickoff
    eligible = 1 if row.eligibility_status == ELIGIBILITY_ELIGIBLE else 0
    ts = feat_at or datetime.min.replace(tzinfo=timezone.utc)
    return (
        1 if ev["has_internal_features"] else 0,
        1 if before_kickoff else 0,
        ts.timestamp(),
        eligible if prefer_eligible else 0,
        row.scan_date.toordinal() if row.scan_date else 0,
    )


def _select_feature_row(rows: list[CecchinoTodayFixture], *, prefer_eligible: bool) -> CecchinoTodayFixture | None:
    candidates = [r for r in rows if evaluate_internal_features(r)["has_internal_features"]]
    if not candidates:
        return None
    pre_kickoff = []
    for r in candidates:
        feat_at = feature_snapshot_at(r)
        kickoff = r.kickoff
        if kickoff is not None and kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        if feat_at is not None and kickoff is not None and feat_at < kickoff:
            pre_kickoff.append(r)
    pool = pre_kickoff if pre_kickoff else candidates
    return max(pool, key=lambda r: _feature_row_score(r, prefer_eligible=prefer_eligible))


def _select_target_row(rows: list[CecchinoTodayFixture]) -> CecchinoTodayFixture | None:
    finished = []
    for r in rows:
        home, away = resolve_fulltime_score(r)
        if home is not None and away is not None:
            finished.append(r)
    if not finished:
        return None

    def _target_key(r: CecchinoTodayFixture) -> tuple:
        ts = target_snapshot_at(r) or datetime.min.replace(tzinfo=timezone.utc)
        return (r.scan_date.toordinal() if r.scan_date else 0, ts.timestamp())

    return max(finished, key=_target_key)


def _build_dataset_row(
    *,
    feature_row: CecchinoTodayFixture,
    target_row: CecchinoTodayFixture,
    cohort_label: str,
) -> dict[str, Any]:
    ev = evaluate_internal_features(feature_row)
    final = ev["final"] or {}
    output = ev["output"] or {}
    goal_markets = ev["goal_markets"]

    home, away = resolve_fulltime_score(target_row)
    assert home is not None and away is not None

    probs = normalize_prob_triple(
        prob_1=ev["prob_1"],
        prob_x=ev["prob_x"],
        prob_2=ev["prob_2"],
        prob_1_pct=num(final.get("prob_1_pct")),
        prob_x_pct=num(final.get("prob_x_pct")),
        prob_2_pct=num(final.get("prob_2_pct")),
    )

    balance = build_balance_analysis_from_final(final)
    f36 = balance.get("f36") or {}
    dominance = balance.get("dominance") or {}

    p1n = probs.get("prob_1_norm")
    pxn = probs.get("prob_x_norm")
    p2n = probs.get("prob_2_norm")
    x_rank, x_tied = _x_rank(probs)

    max_prob = None
    second_prob = None
    if p1n is not None and pxn is not None and p2n is not None:
        ordered = sorted([p1n, pxn, p2n], reverse=True)
        max_prob = ordered[0]
        second_prob = ordered[1]

    conviction = None
    if max_prob is not None and second_prob is not None and max_prob > 0:
        conviction = _clamp(100.0 * (max_prob - second_prob) / max_prob, 0, 100)

    gap_1_2 = abs(p1n - p2n) if p1n is not None and p2n is not None else None
    prob_balance = None
    if p1n is not None and p2n is not None and (p1n + p2n) > 0:
        prob_balance = _clamp(100.0 * (1.0 - abs(p1n - p2n) / (p1n + p2n)), 0, 100)

    f36_score = f36.get("score")
    gap_coherence = None
    if f36_score is not None and prob_balance is not None:
        gap_coherence = _clamp(100.0 - abs(float(f36_score) - prob_balance), 0, 100)

    lateral_max = max(p1n, p2n) if p1n is not None and p2n is not None else None
    x_vs_best = (pxn - lateral_max) if pxn is not None and lateral_max is not None else None

    goal_probs = _goal_probabilities(
        goal_markets=goal_markets if isinstance(goal_markets, dict) else None,
        under_odd=ev["under_odd"],
        over_odd=ev["over_odd"],
    )
    under_pct = goal_probs.get("prob_under_2_5_cecchino_pct")
    over_pct = goal_probs.get("prob_over_2_5_cecchino_pct")
    under_minus_over = (
        round(under_pct - over_pct, 2) if under_pct is not None and over_pct is not None else None
    )

    odds = ev["odds"]
    b1, bx, b2, book_1x2_overround = normalize_implied_triple(
        odds.get(SEL_HOME), odds.get(SEL_DRAW), odds.get(SEL_AWAY)
    )
    bu, bo, book_goal_overround = normalize_implied_pair(
        odds.get(SEL_UNDER_2_5), odds.get(SEL_OVER_2_5)
    )

    deviations: dict[str, float | None] = {
        "deviation_1_pp": abs(p1n - b1) if p1n is not None and b1 is not None else None,
        "deviation_x_pp": abs(pxn - bx) if pxn is not None and bx is not None else None,
        "deviation_2_pp": abs(p2n - b2) if p2n is not None and b2 is not None else None,
        "deviation_under_pp": abs(under_pct - bu) if under_pct is not None and bu is not None else None,
        "deviation_over_pp": abs(over_pct - bo) if over_pct is not None and bo is not None else None,
    }
    dev_values = [v for v in deviations.values() if v is not None]
    market_dev_mean = round(sum(dev_values) / len(dev_values), 2) if dev_values else None
    market_dev_max = round(max(dev_values), 2) if dev_values else None

    feat_at = feature_snapshot_at(feature_row)
    kickoff = feature_row.kickoff
    leakage_status, feature_before, leakage_warning = classify_leakage(feat_at, kickoff)
    tgt_at = target_snapshot_at(target_row)

    _, under_ver, _ = goal_market_kpi_entry(goal_markets or {}, SEL_UNDER_2_5)
    _, over_ver, _ = goal_market_kpi_entry(goal_markets or {}, SEL_OVER_2_5)

    draw_ft = 1 if home == away else 0

    return {
        "today_fixture_id_feature": feature_row.id,
        "today_fixture_id_target": target_row.id,
        "provider_fixture_id": feature_row.provider_fixture_id,
        "local_fixture_id": feature_row.local_fixture_id or target_row.local_fixture_id,
        "scan_date_feature": feature_row.scan_date.isoformat() if feature_row.scan_date else None,
        "scan_date_target": target_row.scan_date.isoformat() if target_row.scan_date else None,
        "kickoff": _iso_dt(kickoff),
        "country_name": feature_row.country_name or target_row.country_name,
        "league_name": feature_row.league_name or target_row.league_name,
        "competition_id": feature_row.competition_id or target_row.competition_id,
        "provider_league_id": feature_row.provider_league_id,
        "provider_season": feature_row.provider_season,
        "home_team_name": feature_row.home_team_name or target_row.home_team_name,
        "away_team_name": feature_row.away_team_name or target_row.away_team_name,
        "eligibility_status_feature": feature_row.eligibility_status,
        "cohort": cohort_label,
        "draw_ft": draw_ft,
        "ft_home": home,
        "ft_away": away,
        "ft_score": f"{home}-{away}",
        "result_1x2": resolve_result_1x2(home, away),
        "quota_cecchino_1": ev["quota_1"],
        "quota_cecchino_x": ev["quota_x"],
        "quota_cecchino_2": ev["quota_2"],
        **probs,
        "x_rank": x_rank,
        "x_tied_for_top": x_tied,
        "dominant_sign": dominance.get("best_side"),
        "dominant_probability": dominance.get("best_probability"),
        "second_sign": dominance.get("second_side"),
        "second_probability": dominance.get("second_probability"),
        "x_vs_best_lateral_pp": round(x_vs_best, 2) if x_vs_best is not None else None,
        "x_vs_second_probability_pp": (
            round(pxn - second_prob, 2) if pxn is not None and second_prob is not None else None
        ),
        "max_probability_pp": max_prob,
        "f36_signed": f36.get("signed"),
        "f36_abs": f36.get("abs"),
        "f36_score_existing": f36_score,
        "f36_class_existing": f36.get("class_key"),
        "dominance_pp": dominance.get("value"),
        "conviction_index_candidate": conviction,
        "conviction_class_candidate": _classify_conviction(conviction),
        "probability_gap_1_2_pp": round(gap_1_2, 2) if gap_1_2 is not None else None,
        "probability_balance_index": prob_balance,
        "gap_coherence_index_candidate": gap_coherence,
        "gap_coherence_class_candidate": _classify_gap_coherence(gap_coherence),
        "quota_under_2_5_cecchino": ev["under_odd"],
        "quota_over_2_5_cecchino": ev["over_odd"],
        **goal_probs,
        "under_minus_over_pp": under_minus_over,
        "quota_book_1": odds.get(SEL_HOME),
        "quota_book_x": odds.get(SEL_DRAW),
        "quota_book_2": odds.get(SEL_AWAY),
        "quota_book_under_2_5": odds.get(SEL_UNDER_2_5),
        "quota_book_over_2_5": odds.get(SEL_OVER_2_5),
        "book_1x2_source": ev["book_1x2_source"],
        "book_goal_source": ev["book_goal_source"],
        "prob_book_1_norm": b1,
        "prob_book_x_norm": bx,
        "prob_book_2_norm": b2,
        "prob_book_under_2_5_norm": bu,
        "prob_book_over_2_5_norm": bo,
        "book_1x2_overround": book_1x2_overround,
        "book_goal_overround": book_goal_overround,
        **deviations,
        "market_deviation_mean_pp": market_dev_mean,
        "market_deviation_max_pp": market_dev_max,
        "has_market_features": ev["has_book_1x2"] and ev["has_book_goal_pair"],
        "feature_snapshot_at": _iso_dt(feat_at),
        "target_snapshot_at": _iso_dt(tgt_at),
        "feature_before_kickoff": feature_before,
        "leakage_status": leakage_status,
        "leakage_warning": leakage_warning,
        "cecchino_output_version": output.get("version"),
        "cecchino_final_version": final.get("weights"),
        "balance_analysis_version": balance.get("version"),
        "goal_market_version_under": under_ver,
        "goal_market_version_over": over_ver,
        "kpi_panel_version": (feature_row.kpi_panel_json or {}).get("version") if isinstance(feature_row.kpi_panel_json, dict) else None,
        "payload_structure_key": payload_structure_key(output),
    }


def _cohort_membership(row: dict[str, Any]) -> set[str]:
    cohorts: set[str] = set()
    if row["leakage_status"] != LEAKAGE_SAFE:
        return cohorts
    eligible = row["eligibility_status_feature"] == ELIGIBILITY_ELIGIBLE
    if eligible:
        cohorts.add(COHORT_ELIGIBLE_PRIMARY)
    cohorts.add(COHORT_ALL_USABLE_SENSITIVITY)
    if row.get("has_market_features"):
        cohorts.add(COHORT_MARKET_SUBSET)
    return cohorts


def _summary_from_rows(rows: list[dict[str, Any]], *, raw_rows: int, unique: int) -> dict[str, Any]:
    draws = sum(1 for r in rows if r.get("draw_ft") == 1)
    non_draws = len(rows) - draws
    leakage_safe = sum(1 for r in rows if r.get("leakage_status") == LEAKAGE_SAFE)
    leakage_unknown = sum(1 for r in rows if r.get("leakage_status") == LEAKAGE_UNKNOWN)
    leakage_unsafe = sum(1 for r in rows if r.get("leakage_status") == LEAKAGE_UNSAFE)
    return {
        "raw_rows_found": raw_rows,
        "unique_provider_fixtures": unique,
        "duplicate_rows_collapsed": max(0, raw_rows - unique),
        "rows_with_valid_target": len(rows),
        "rows_with_internal_features": len(rows),
        "rows_with_market_features": sum(1 for r in rows if r.get("has_market_features")),
        "leakage_safe": leakage_safe,
        "leakage_unknown": leakage_unknown,
        "leakage_unsafe": leakage_unsafe,
        "final_dataset_rows": len(rows),
        "draws": draws,
        "non_draws": non_draws,
        "draw_rate_pct": pct(draws, len(rows)),
    }


def _version_distribution(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    fields = {
        "cecchino_output": "cecchino_output_version",
        "balance_analysis": "balance_analysis_version",
        "goal_markets": "goal_market_version_under",
        "kpi_panel": "kpi_panel_version",
        "payload_structure": "payload_structure_key",
    }
    out: dict[str, list[dict[str, Any]]] = {}
    total = len(rows) or 1
    for label, key in fields.items():
        counter = Counter(str(r.get(key)) if r.get(key) is not None else "null" for r in rows)
        out[label] = [
            {"version": ver, "count": cnt, "pct": pct(cnt, total)}
            for ver, cnt in counter.most_common()
        ]
    return out


def _build_all_rows(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_fixtures = fixtures_in_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        only_eligible=None,
    )
    raw_rows = len(raw_fixtures)
    groups: dict[int, list[CecchinoTodayFixture]] = defaultdict(list)
    for row in raw_fixtures:
        groups[int(row.provider_fixture_id)].append(row)

    built: list[dict[str, Any]] = []
    stats = {
        "excluded_no_pre_match_snapshot": 0,
        "excluded_no_target": 0,
        "excluded_unsupported": 0,
        "leakage_removed": 0,
        "version_removed": 0,
    }

    for _pid, group_rows in groups.items():
        if not any(evaluate_internal_features(r)["has_internal_features"] for r in group_rows):
            if all(not evaluate_internal_features(r)["has_cecchino_final"] for r in group_rows):
                stats["version_removed"] += 1
            continue

        feature_row = _select_feature_row(group_rows, prefer_eligible=True)
        if feature_row is None:
            stats["excluded_no_pre_match_snapshot"] += 1
            continue

        target_row = _select_target_row(group_rows)
        if target_row is None:
            stats["excluded_no_target"] += 1
            continue

        dataset_row = _build_dataset_row(
            feature_row=feature_row,
            target_row=target_row,
            cohort_label=COHORT_ALL_USABLE_SENSITIVITY,
        )
        if dataset_row["leakage_status"] != LEAKAGE_SAFE:
            stats["leakage_removed"] += 1
        built.append(dataset_row)

    meta = {
        "raw_rows": raw_rows,
        "unique_provider_fixtures": len(groups),
        "duplicates_collapsed": max(0, raw_rows - len(groups)),
        **stats,
    }
    return built, meta


def _consistency_checks(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    primary_rows: list[dict[str, Any]],
    sensitivity_rows: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    dedup_meta: dict[str, Any],
) -> dict[str, Any]:
    audit_primary = build_draw_credibility_coverage_audit(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id, only_eligible=True,
    )
    audit_all = build_draw_credibility_coverage_audit(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id, only_eligible=False,
    )
    expected_primary = audit_primary["summary"]["usable_internal_research"]
    expected_sensitivity = audit_all["summary"]["usable_internal_research"]
    expected_market = audit_all["summary"]["usable_market_comparison"]

    final_primary = len(primary_rows)
    final_sensitivity = len(sensitivity_rows)
    final_market = len(market_rows)

    diff_primary = final_primary - expected_primary
    diff_sensitivity = final_sensitivity - expected_sensitivity
    diff_market = final_market - expected_market

    reasons: list[str] = []
    if diff_primary != 0:
        reasons.append(
            f"Primary: deduplica (-{dedup_meta['duplicates_collapsed']}), "
            f"leakage (-{dedup_meta['leakage_removed']}), "
            f"no snapshot (-{dedup_meta['excluded_no_pre_match_snapshot']})"
        )
    if diff_sensitivity != 0:
        reasons.append(
            f"Sensitivity: stessi filtri deduplica/leakage rispetto audit row-level"
        )

    return {
        "expected_primary_from_audit": expected_primary,
        "expected_sensitivity_from_audit": expected_sensitivity,
        "expected_market_from_audit": expected_market,
        "actual_primary_rows": final_primary,
        "actual_sensitivity_rows": final_sensitivity,
        "actual_market_rows": final_market,
        "difference_primary_vs_audit": diff_primary,
        "difference_sensitivity_vs_audit": diff_sensitivity,
        "difference_market_vs_audit": diff_market,
        "difference_reason": "; ".join(reasons) if reasons else "Allineato con audit entro deduplica/leakage",
        "duplicates_removed": dedup_meta["duplicates_collapsed"],
        "leakage_removed": dedup_meta["leakage_removed"],
        "version_removed": dedup_meta["version_removed"],
        "invalid_features_removed": dedup_meta["excluded_no_pre_match_snapshot"] + dedup_meta["excluded_no_target"],
    }


def _filter_cohort(rows: list[dict[str, Any]], cohort: str) -> list[dict[str, Any]]:
    if cohort == COHORT_ELIGIBLE_PRIMARY:
        return [
            r for r in rows
            if r["eligibility_status_feature"] == ELIGIBILITY_ELIGIBLE
            and r["leakage_status"] == LEAKAGE_SAFE
        ]
    if cohort == COHORT_ALL_USABLE_SENSITIVITY:
        return [r for r in rows if r["leakage_status"] == LEAKAGE_SAFE]
    if cohort == COHORT_MARKET_SUBSET:
        return [
            r for r in rows
            if r["leakage_status"] == LEAKAGE_SAFE and r.get("has_market_features")
        ]
    return rows


def build_draw_credibility_historical_dataset(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    cohort: str = COHORT_ELIGIBLE_PRIMARY,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    all_rows, dedup_meta = _build_all_rows(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
    )

    primary_rows = _filter_cohort(all_rows, COHORT_ELIGIBLE_PRIMARY)
    sensitivity_rows = _filter_cohort(all_rows, COHORT_ALL_USABLE_SENSITIVITY)
    market_rows = _filter_cohort(all_rows, COHORT_MARKET_SUBSET)

    for r in all_rows:
        memberships = _cohort_membership(r)
        if COHORT_ELIGIBLE_PRIMARY in memberships:
            r["cohort"] = COHORT_ELIGIBLE_PRIMARY
        elif COHORT_ALL_USABLE_SENSITIVITY in memberships:
            r["cohort"] = COHORT_ALL_USABLE_SENSITIVITY

    selected = _filter_cohort(all_rows, cohort)
    total_rows = len(selected)
    total_pages = max(1, math.ceil(total_rows / page_size)) if page_size > 0 else 1
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    page_rows = selected[start : start + page_size]

    anti_leakage = {
        "safe": sum(1 for r in all_rows if r["leakage_status"] == LEAKAGE_SAFE),
        "unknown": sum(1 for r in all_rows if r["leakage_status"] == LEAKAGE_UNKNOWN),
        "unsafe": sum(1 for r in all_rows if r["leakage_status"] == LEAKAGE_UNSAFE),
        "excluded_no_pre_match_snapshot": dedup_meta["excluded_no_pre_match_snapshot"],
    }

    warnings: list[str] = []
    if total_rows == 0:
        warnings.append("Nessuna riga nel dataset per la coorte selezionata.")

    return {
        "status": "ok",
        "version": VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
            "cohort": cohort,
            "page": page,
            "page_size": page_size,
        },
        "primary_summary": _summary_from_rows(
            primary_rows,
            raw_rows=dedup_meta["raw_rows"],
            unique=dedup_meta["unique_provider_fixtures"],
        ),
        "sensitivity_summary": _summary_from_rows(
            sensitivity_rows,
            raw_rows=dedup_meta["raw_rows"],
            unique=dedup_meta["unique_provider_fixtures"],
        ),
        "market_summary": _summary_from_rows(
            market_rows,
            raw_rows=dedup_meta["raw_rows"],
            unique=dedup_meta["unique_provider_fixtures"],
        ),
        "deduplication": {
            "raw_rows": dedup_meta["raw_rows"],
            "unique_provider_fixtures": dedup_meta["unique_provider_fixtures"],
            "duplicates_collapsed": dedup_meta["duplicates_collapsed"],
        },
        "anti_leakage": anti_leakage,
        "target_distribution": {
            "rows": total_rows,
            "draws": sum(1 for r in selected if r.get("draw_ft") == 1),
            "non_draws": sum(1 for r in selected if r.get("draw_ft") == 0),
            "draw_rate_pct": pct(sum(1 for r in selected if r.get("draw_ft") == 1), total_rows),
        },
        "version_distribution": _version_distribution(all_rows),
        "consistency_checks": _consistency_checks(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            primary_rows=primary_rows,
            sensitivity_rows=sensitivity_rows,
            market_rows=market_rows,
            dedup_meta=dedup_meta,
        ),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
        },
        "rows": page_rows,
        "warnings": warnings,
    }


def _sanitize_csv_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _row_to_csv_dict(row: dict[str, Any]) -> dict[str, str]:
    return {col: _sanitize_csv_value(row.get(col)) for col in CSV_COLUMNS}


def stream_draw_credibility_dataset_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    cohort: str = COHORT_ELIGIBLE_PRIMARY,
) -> Iterator[str]:
    all_rows, _ = _build_all_rows(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id,
    )
    selected = _filter_cohort(all_rows, cohort)

    yield "\ufeff"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), delimiter=";", lineterminator="\n")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in selected:
        writer.writerow(_row_to_csv_dict(row))
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def dataset_csv_filename(
    *,
    cohort: str,
    date_from: date,
    date_to: date,
) -> str:
    return f"cecchino_draw_credibility_{cohort}_{date_from.isoformat()}_{date_to.isoformat()}.csv"
