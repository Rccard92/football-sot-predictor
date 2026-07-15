"""Helper condivisi audit e dataset Credibilità X — Fase 1A/1B."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_FINISHED,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_betfair_odds_payload import build_betfair_payload_from_snapshot
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_goal_formulas import goal_market_kpi_entry
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import normalize_kpi_panel_rows
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)
from app.services.cecchino.cecchino_signal_goal_refs import resolve_under_2_5_cecchino_odd
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta

COHORT_ELIGIBLE_PRIMARY = "eligible_primary"
COHORT_ALL_USABLE_SENSITIVITY = "all_usable_sensitivity"
COHORT_MARKET_SUBSET = "market_subset"

COHORTS = (
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_ALL_USABLE_SENSITIVITY,
    COHORT_MARKET_SUBSET,
)

LEAKAGE_SAFE = "safe"
LEAKAGE_UNKNOWN = "unknown"
LEAKAGE_UNSAFE = "unsafe"


def num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def valid_cecchino_odd(odd: float | None) -> bool:
    return odd is not None and math.isfinite(odd) and odd > 0


def valid_book_odd(odd: float | None) -> bool:
    return odd is not None and math.isfinite(odd) and odd > 1


def pct(n: int | float, d: int | float) -> float:
    if d <= 0:
        return 0.0
    return round(100.0 * float(n) / float(d), 2)


def prob_to_percent(prob: float | None, prob_pct: float | None = None) -> float | None:
    if prob_pct is not None:
        p = num(prob_pct)
        if p is None or not math.isfinite(p):
            return None
        return p
    if prob is None:
        return None
    p = float(prob)
    if not math.isfinite(p) or p < 0:
        return None
    if p <= 1.0:
        return round(p * 100.0, 4)
    return round(p, 4)


def normalize_prob_triple(
    *,
    prob_1: float | None,
    prob_x: float | None,
    prob_2: float | None,
    prob_1_pct: float | None = None,
    prob_x_pct: float | None = None,
    prob_2_pct: float | None = None,
) -> dict[str, Any]:
    p1 = prob_to_percent(prob_1, prob_1_pct)
    px = prob_to_percent(prob_x, prob_x_pct)
    p2 = prob_to_percent(prob_2, prob_2_pct)
    if None in (p1, px, p2):
        return {
            "prob_1_raw": prob_1,
            "prob_x_raw": prob_x,
            "prob_2_raw": prob_2,
            "prob_1_pct": None,
            "prob_x_pct": None,
            "prob_2_pct": None,
            "prob_1_norm": None,
            "prob_x_norm": None,
            "prob_2_norm": None,
            "probability_sum_before_normalization": None,
            "probability_normalization_applied": False,
        }
    total = p1 + px + p2
    if total <= 0:
        return {
            "prob_1_raw": prob_1,
            "prob_x_raw": prob_x,
            "prob_2_raw": prob_2,
            "prob_1_pct": round(p1, 2),
            "prob_x_pct": round(px, 2),
            "prob_2_pct": round(p2, 2),
            "prob_1_norm": None,
            "prob_x_norm": None,
            "prob_2_norm": None,
            "probability_sum_before_normalization": round(total, 2),
            "probability_normalization_applied": False,
        }
    applied = abs(total - 100.0) > 0.01
    return {
        "prob_1_raw": prob_1,
        "prob_x_raw": prob_x,
        "prob_2_raw": prob_2,
        "prob_1_pct": round(p1, 2),
        "prob_x_pct": round(px, 2),
        "prob_2_pct": round(p2, 2),
        "prob_1_norm": round(100.0 * p1 / total, 2),
        "prob_x_norm": round(100.0 * px / total, 2),
        "prob_2_norm": round(100.0 * p2 / total, 2),
        "probability_sum_before_normalization": round(total, 2),
        "probability_normalization_applied": applied,
    }


def normalize_implied_pair(
    odd_a: float | None,
    odd_b: float | None,
) -> tuple[float | None, float | None, float | None]:
    raw_a = 1.0 / odd_a if valid_cecchino_odd(odd_a) else None
    raw_b = 1.0 / odd_b if valid_cecchino_odd(odd_b) else None
    if raw_a is None or raw_b is None:
        return None, None, None
    total = raw_a + raw_b
    if total <= 0:
        return None, None, None
    overround = round((raw_a + raw_b - 1.0) * 100.0, 2)
    return (
        round(100.0 * raw_a / total, 2),
        round(100.0 * raw_b / total, 2),
        overround,
    )


def normalize_implied_triple(
    odd_1: float | None,
    odd_x: float | None,
    odd_2: float | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    raw_1 = 1.0 / odd_1 if valid_book_odd(odd_1) else None
    raw_x = 1.0 / odd_x if valid_book_odd(odd_x) else None
    raw_2 = 1.0 / odd_2 if valid_book_odd(odd_2) else None
    if None in (raw_1, raw_x, raw_2):
        return None, None, None, None
    total = raw_1 + raw_x + raw_2
    if total <= 0:
        return None, None, None, None
    overround = round((total - 1.0) * 100.0, 2)
    return (
        round(100.0 * raw_1 / total, 2),
        round(100.0 * raw_x / total, 2),
        round(100.0 * raw_2 / total, 2),
        overround,
    )


def resolve_fulltime_score(row: CecchinoTodayFixture) -> tuple[int | None, int | None]:
    if row.match_display_status != MATCH_FINISHED:
        return None, None
    home = row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home
    away = row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away
    if home is None or away is None:
        return None, None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None, None


def resolve_result_1x2(home: int, away: int) -> str:
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def cecchino_final(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return None
    final = output.get("final")
    if not isinstance(final, dict):
        return None
    return final


def cecchino_output(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    output = row.cecchino_output_json
    return output if isinstance(output, dict) else None


def is_supported_payload(row: CecchinoTodayFixture) -> bool:
    return cecchino_final(row) is not None


def normalized_kpi_panel(row: CecchinoTodayFixture) -> dict[str, Any] | None:
    kpi_raw = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    return normalize_kpi_panel_rows(kpi_raw) if kpi_raw else None


def _kpi_panel_cecchino_odd(kpi_panel: dict | None, market_key: str, labels: tuple[str, ...]) -> float | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key:
            odd = num(row.get("quota_cecchino"))
            if valid_cecchino_odd(odd):
                return odd
        label = str(row.get("segno") or row.get("label") or "").strip().lower()
        if label in labels:
            odd = num(row.get("quota_cecchino"))
            if valid_cecchino_odd(odd):
                return odd
    return None


def resolve_over_2_5_cecchino_odd(
    *,
    kpi_panel: dict | None = None,
    goal_markets: dict | None = None,
) -> float | None:
    odd = _kpi_panel_cecchino_odd(
        kpi_panel,
        SEL_OVER_2_5,
        ("over 2.5", "over2.5", "o2.5"),
    )
    if valid_cecchino_odd(odd):
        return odd
    if isinstance(goal_markets, dict):
        q, _, _ = goal_market_kpi_entry(goal_markets, SEL_OVER_2_5)
        if valid_cecchino_odd(q):
            return q
    return None


def _kpi_panel_book_odd(kpi_panel: dict | None, market_key: str) -> float | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == market_key:
            odd = num(row.get("quota_book"))
            if valid_book_odd(odd):
                return odd
    return None


def snapshot_book_odds(
    odds_snapshot: dict[str, Any] | None,
    *,
    home_team_name: str | None,
    away_team_name: str | None,
) -> dict[str, float | None]:
    payload = build_betfair_payload_from_snapshot(
        odds_snapshot,
        source="cached_betfair_odds",
        home_team_name=home_team_name,
        away_team_name=away_team_name,
    )
    out: dict[str, float | None] = {
        SEL_HOME: None,
        SEL_DRAW: None,
        SEL_AWAY: None,
        SEL_UNDER_2_5: None,
        SEL_OVER_2_5: None,
    }
    for bm in payload.get("bookmakers") or []:
        if not isinstance(bm, dict) or bm.get("status") != "available":
            continue
        markets = bm.get("markets") or {}
        m1x2 = markets.get(MARKET_1X2) or {}
        ou = markets.get(MARKET_OU) or {}
        if isinstance(m1x2, dict):
            for sk in (SEL_HOME, SEL_DRAW, SEL_AWAY):
                if out[sk] is None:
                    out[sk] = num(m1x2.get(sk))
        if isinstance(ou, dict):
            for sk in (SEL_UNDER_2_5, SEL_OVER_2_5):
                if out[sk] is None:
                    out[sk] = num(ou.get(sk))
    return out


def resolve_book_odd(
    *,
    market_key: str,
    kpi_panel: dict | None,
    odds_snapshot: dict[str, Any] | None,
    home_team_name: str | None,
    away_team_name: str | None,
    snapshot_cache: dict[str, float | None] | None,
) -> tuple[float | None, str]:
    odd = _kpi_panel_book_odd(kpi_panel, market_key)
    if valid_book_odd(odd):
        return odd, "kpi_panel"
    snap = snapshot_cache
    if snap is None:
        snap = snapshot_book_odds(
            odds_snapshot,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )
    odd = snap.get(market_key)
    if valid_book_odd(odd):
        return odd, "odds_snapshot"
    return None, "missing"


def resolve_book_odds_bundle(row: CecchinoTodayFixture) -> dict[str, Any]:
    kpi_panel = normalized_kpi_panel(row)
    odds_snapshot = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None
    snapshot_cache = snapshot_book_odds(
        odds_snapshot,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )
    keys = (SEL_HOME, SEL_DRAW, SEL_AWAY, SEL_UNDER_2_5, SEL_OVER_2_5)
    odds: dict[str, float | None] = {}
    sources: dict[str, str] = {}
    for key in keys:
        odd, src = resolve_book_odd(
            market_key=key,
            kpi_panel=kpi_panel,
            odds_snapshot=odds_snapshot,
            home_team_name=row.home_team_name,
            away_team_name=row.away_team_name,
            snapshot_cache=snapshot_cache,
        )
        odds[key] = odd
        sources[key] = src
    book_1x2_sources = {sources[k] for k in (SEL_HOME, SEL_DRAW, SEL_AWAY) if odds[k] is not None}
    book_goal_sources = {sources[k] for k in (SEL_UNDER_2_5, SEL_OVER_2_5) if odds[k] is not None}
    book_1x2_source = "kpi_panel" if "kpi_panel" in book_1x2_sources else (
        "odds_snapshot" if "odds_snapshot" in book_1x2_sources else "missing"
    )
    book_goal_source = "kpi_panel" if "kpi_panel" in book_goal_sources else (
        "odds_snapshot" if "odds_snapshot" in book_goal_sources else "missing"
    )
    return {
        "odds": odds,
        "book_1x2_source": book_1x2_source,
        "book_goal_source": book_goal_source,
        "has_book_1x2": all(valid_book_odd(odds[k]) for k in (SEL_HOME, SEL_DRAW, SEL_AWAY)),
        "has_book_goal_pair": valid_book_odd(odds[SEL_UNDER_2_5]) and valid_book_odd(odds[SEL_OVER_2_5]),
    }


def evaluate_internal_features(row: CecchinoTodayFixture) -> dict[str, Any]:
    kpi_panel = normalized_kpi_panel(row)
    output = cecchino_output(row)
    goal_markets = (output or {}).get("goal_markets") if isinstance(output, dict) else None
    final = cecchino_final(row)

    has_invalid_numeric = False
    if final is not None:
        for key in ("quota_1", "quota_x", "quota_2", "prob_1", "prob_x", "prob_2"):
            raw = final.get(key)
            if raw is not None:
                val = num(raw)
                if val is None or not math.isfinite(val):
                    has_invalid_numeric = True
                    break

    has_cecchino_final = final is not None and final.get("status") == STATUS_AVAILABLE
    q1 = num(final.get("quota_1")) if final else None
    qx = num(final.get("quota_x")) if final else None
    q2 = num(final.get("quota_2")) if final else None
    p1 = num(final.get("prob_1")) if final else None
    px = num(final.get("prob_x")) if final else None
    p2 = num(final.get("prob_2")) if final else None

    has_1x2_odds = valid_cecchino_odd(q1) and valid_cecchino_odd(qx) and valid_cecchino_odd(q2)
    has_1x2_prob = valid_cecchino_odd(p1) and valid_cecchino_odd(px) and valid_cecchino_odd(p2)
    has_complete_1x2 = has_1x2_odds and has_1x2_prob

    under_odd = resolve_under_2_5_cecchino_odd(kpi_panel=kpi_panel, goal_markets=goal_markets)
    over_odd = resolve_over_2_5_cecchino_odd(kpi_panel=kpi_panel, goal_markets=goal_markets)
    has_under = valid_cecchino_odd(under_odd)
    has_over = valid_cecchino_odd(over_odd)
    has_complete_goal_pair = has_under and has_over
    has_internal = (
        is_supported_payload(row)
        and has_cecchino_final
        and has_complete_1x2
        and has_complete_goal_pair
        and not has_invalid_numeric
    )

    book = resolve_book_odds_bundle(row)
    odds = book["odds"]
    return {
        "kpi_panel": kpi_panel,
        "output": output,
        "goal_markets": goal_markets,
        "final": final,
        "has_invalid_numeric": has_invalid_numeric,
        "has_cecchino_final": has_cecchino_final,
        "has_1x2_odds": has_1x2_odds,
        "has_1x2_prob": has_1x2_prob,
        "has_complete_1x2": has_complete_1x2,
        "has_under": has_under,
        "has_over": has_over,
        "has_complete_goal_pair": has_complete_goal_pair,
        "has_internal_features": has_internal,
        "under_odd": under_odd,
        "over_odd": over_odd,
        "quota_1": q1,
        "quota_x": qx,
        "quota_2": q2,
        "prob_1": p1,
        "prob_x": px,
        "prob_2": p2,
        "odds": odds,
        "has_book_1x2": book["has_book_1x2"],
        "has_book_under": valid_book_odd(odds[SEL_UNDER_2_5]),
        "has_book_over": valid_book_odd(odds[SEL_OVER_2_5]),
        "has_book_goal_pair": book["has_book_goal_pair"],
        "book_1x2_source": book["book_1x2_source"],
        "book_goal_source": book["book_goal_source"],
    }


def _parse_iso_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None
    return None


def feature_snapshot_at(row: CecchinoTodayFixture) -> datetime | None:
    candidates: list[datetime] = []
    if row.created_at is not None:
        dt = _parse_iso_dt(row.created_at)
        if dt is not None:
            candidates.append(dt)
    odds_snapshot = row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None
    meta = read_odds_meta(odds_snapshot)
    for key in ("odds_fetched_at", "odds_cached_at"):
        dt = _parse_iso_dt(meta.get(key))
        if dt is not None:
            candidates.append(dt)
    if not candidates:
        return None
    return min(candidates)


def target_snapshot_at(row: CecchinoTodayFixture) -> datetime | None:
    if row.created_at is not None:
        return _parse_iso_dt(row.created_at)
    if row.scan_date is not None:
        return datetime.combine(row.scan_date, datetime.min.time(), tzinfo=timezone.utc)
    return None


def classify_leakage(feature_at: datetime | None, kickoff: datetime | None) -> tuple[str, bool | None, str | None]:
    if feature_at is None or kickoff is None:
        return LEAKAGE_UNKNOWN, None, "timestamp_or_kickoff_missing"
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    if feature_at.tzinfo is None:
        feature_at = feature_at.replace(tzinfo=timezone.utc)
    before = feature_at < kickoff
    if before:
        return LEAKAGE_SAFE, True, None
    return LEAKAGE_UNSAFE, False, "feature_snapshot_not_before_kickoff"


def fixtures_in_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    only_eligible: bool | None = None,
) -> list[CecchinoTodayFixture]:
    clauses = [
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
    ]
    if competition_id is not None:
        clauses.append(CecchinoTodayFixture.competition_id == competition_id)
    if only_eligible is True:
        clauses.append(CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE)
    return list(db.scalars(select(CecchinoTodayFixture).where(*clauses)).all())


def payload_structure_key(output: dict[str, Any] | None) -> str | None:
    if not output or not isinstance(output, dict):
        return None
    keys = sorted(str(k) for k in output.keys())
    return "|".join(keys) if keys else "empty"


def resolve_cecchino_final_version(final: dict[str, Any] | None) -> str | None:
    """Legge un vero campo versione da final, mai il dict weights."""
    if not final or not isinstance(final, dict):
        return None
    for key in ("version", "formula_version", "model_version"):
        val = final.get(key)
        if val is not None and str(val).strip():
            return str(val)
    return None


def extract_final_weight_fields(final: dict[str, Any] | None) -> dict[str, float | None]:
    """Estrae pesi final noti; chiavi sconosciute ignorate."""
    out: dict[str, float | None] = {
        "final_weight_totals": None,
        "final_weight_home_away": None,
        "final_weight_last6_totals": None,
        "final_weight_last5_home_away": None,
    }
    if not final or not isinstance(final, dict):
        return out
    weights = final.get("weights")
    if not isinstance(weights, dict):
        return out
    mapping = {
        "totals": "final_weight_totals",
        "home_away": "final_weight_home_away",
        "last6_totals": "final_weight_last6_totals",
        "last5_home_away": "final_weight_last5_home_away",
    }
    for src, dst in mapping.items():
        val = num(weights.get(src))
        if val is not None and math.isfinite(val):
            out[dst] = val
    return out
