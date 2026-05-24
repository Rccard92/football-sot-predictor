"""Ricostruzione snapshot iniziale vs post ufficiali per Monitoraggio Giocate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture, TeamSotPrediction, TrackedBettingPick
from app.services.sot_betting_advice_service import build_fixture_betting_advice
from app.services.tracked_betting_pick_service import parse_line_value_from_pick

_CLOSE = 0.02


@dataclass
class ResolvedSnapshot:
    total: float | None
    home: float | None
    away: float | None
    suggested_pick: str | None
    line_value: float | None
    source: str
    reconstruction_note: str | None = None


def _round2(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 2)


def _approx_eq(a: float | None, b: float | None, tol: float = _CLOSE) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _totals_from_delta_dict(impact: dict[str, Any] | None, *, prefix: str) -> tuple[float | None, float | None, float | None]:
    if not impact:
        return None, None, None
    h = impact.get(f"{prefix}_home_sot")
    a = impact.get(f"{prefix}_away_sot")
    t = impact.get(f"{prefix}_total_sot")
    if t is None and h is not None and a is not None:
        t = round(float(h) + float(a), 2)
    return (
        _round2(float(h) if h is not None else None),
        _round2(float(a) if a is not None else None),
        _round2(float(t) if t is not None else None),
    )


def _totals_from_payload(payload: dict[str, Any] | None) -> tuple[float | None, float | None, float | None]:
    if not isinstance(payload, dict):
        return None, None, None
    h = payload.get("predicted_home_sot")
    a = payload.get("predicted_away_sot")
    t = payload.get("predicted_total_sot")
    if t is None and h is not None and a is not None:
        t = round(float(h) + float(a), 2)
    return (
        _round2(float(h) if h is not None else None),
        _round2(float(a) if a is not None else None),
        _round2(float(t) if t is not None else None),
    )


def _cautious_from_totals(home_sot: float | None, away_sot: float | None) -> tuple[str | None, float | None]:
    if home_sot is None or away_sot is None:
        return None, None
    advice = build_fixture_betting_advice(
        float(home_sot),
        float(away_sot),
        model_version=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    )
    match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
    pick = match.get("cautious_pick")
    line = match.get("cautious_line")
    if pick is None:
        return None, None
    line_f = float(line) if line is not None else parse_line_value_from_pick(str(pick))
    return str(pick), line_f


def _pick_line_coherent(
    total: float | None,
    suggested_pick: str | None,
    line_value: float | None,
    home: float | None,
    away: float | None,
) -> tuple[str | None, float | None]:
    if total is None:
        return None, None
    if suggested_pick and line_value is not None:
        return suggested_pick, line_value
    return _cautious_from_totals(home, away)


def _official_candidate_total(pick: TrackedBettingPick) -> float | None:
    return _round2(pick.predicted_total_sot)


def _load_v20_totals(
    db: Session,
    fixture_id: int,
    home_team_id: int,
    away_team_id: int,
) -> tuple[float | None, float | None, float | None]:
    mv = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    home_row = db.scalar(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id == int(fixture_id),
            TeamSotPrediction.team_id == int(home_team_id),
            TeamSotPrediction.model_version == mv,
        ),
    )
    away_row = db.scalar(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id == int(fixture_id),
            TeamSotPrediction.team_id == int(away_team_id),
            TeamSotPrediction.model_version == mv,
        ),
    )
    if home_row is None or away_row is None or home_row.predicted_sot is None or away_row.predicted_sot is None:
        return None, None, None
    h = round(float(home_row.predicted_sot), 2)
    a = round(float(away_row.predicted_sot), 2)
    return h, a, round(h + a, 2)


def _historical_from_pick_raw(pick: TrackedBettingPick) -> tuple[float | None, float | None, float | None]:
    raw = pick.raw_prediction_payload if isinstance(pick.raw_prediction_payload, dict) else {}
    h = raw.get("predicted_home_sot") or raw.get("home_sot")
    a = raw.get("predicted_away_sot") or raw.get("away_sot")
    t = raw.get("predicted_total_sot") or raw.get("total_sot")
    if t is None and h is not None and a is not None:
        t = round(float(h) + float(a), 2)
    return (
        _round2(float(h) if h is not None else None),
        _round2(float(a) if a is not None else None),
        _round2(float(t) if t is not None else None),
    )


def _initial_from_pick_columns(pick: TrackedBettingPick) -> ResolvedSnapshot | None:
    if pick.initial_predicted_total_sot is None:
        return None
    h = _round2(pick.initial_predicted_home_sot)
    a = _round2(pick.initial_predicted_away_sot)
    t = _round2(pick.initial_predicted_total_sot)
    pick_s, line = _pick_line_coherent(t, pick.initial_suggested_pick, pick.initial_line_value, h, a)
    return ResolvedSnapshot(
        total=t,
        home=h,
        away=a,
        suggested_pick=pick_s,
        line_value=line,
        source="pick_initial_columns",
    )


def _should_reject_initial_column(
    pick: TrackedBettingPick,
    official_total: float | None,
    first_impact: dict[str, Any] | None,
    latest_impact: dict[str, Any] | None,
) -> bool:
    init = pick.initial_predicted_total_sot
    if init is None:
        return False
    official = official_total if official_total is not None else _official_candidate_total(pick)
    if official is not None and _approx_eq(init, official):
        fh, fa, ft = _totals_from_delta_dict(first_impact, prefix="before")
        if ft is not None and not _approx_eq(init, ft):
            return True
        if first_impact is None and latest_impact:
            _, _, after_t = _totals_from_delta_dict(latest_impact, prefix="after")
            if after_t is not None and _approx_eq(init, after_t):
                return True
    return False


def resolve_initial_snapshot(
    pick: TrackedBettingPick,
    *,
    first_impact: dict[str, Any] | None,
    latest_impact: dict[str, Any] | None,
    db: Session,
    fx: Fixture,
    official_total_hint: float | None = None,
) -> ResolvedSnapshot:
    official_hint = official_total_hint if official_total_hint is not None else _official_candidate_total(pick)

    if pick.initial_predicted_total_sot is not None and not _should_reject_initial_column(
        pick, official_hint, first_impact, latest_impact
    ):
        snap = _initial_from_pick_columns(pick)
        if snap is not None:
            return snap

    if first_impact:
        bp = first_impact.get("before_payload")
        if isinstance(bp, dict):
            h, a, t = _totals_from_payload(bp)
            if t is not None:
                pick_s, line = _cautious_from_totals(h, a)
                return ResolvedSnapshot(
                    total=t,
                    home=h,
                    away=a,
                    suggested_pick=pick_s,
                    line_value=line,
                    source="first_impact_before_payload",
                )
        h, a, t = _totals_from_delta_dict(first_impact, prefix="before")
        if t is not None:
            pick_s, line = _cautious_from_totals(h, a)
            return ResolvedSnapshot(
                total=t,
                home=h,
                away=a,
                suggested_pick=pick_s,
                line_value=line,
                source="first_impact_before_total",
            )

    if latest_impact:
        _, _, after_t = _totals_from_delta_dict(latest_impact, prefix="after")
        delta = latest_impact.get("delta_total_sot")
        if after_t is not None and delta is not None:
            try:
                initial_t = _round2(float(after_t) - float(delta))
            except (TypeError, ValueError):
                initial_t = None
            if initial_t is not None:
                dh = latest_impact.get("delta_home_sot")
                da = latest_impact.get("delta_away_sot")
                h = a = None
                oh, oa, _ = _totals_from_delta_dict(latest_impact, prefix="after")
                if oh is not None and dh is not None:
                    h = _round2(float(oh) - float(dh))
                if oa is not None and da is not None:
                    a = _round2(float(oa) - float(da))
                if h is None or a is None:
                    h, a, _ = _historical_from_pick_raw(pick)
                pick_s, line = _cautious_from_totals(h, a)
                return ResolvedSnapshot(
                    total=initial_t,
                    home=h,
                    away=a,
                    suggested_pick=pick_s,
                    line_value=line,
                    source="latest_delta_reconstruction",
                    reconstruction_note="after_total_sot - delta_total_sot",
                )

    h, a, t = _historical_from_pick_raw(pick)
    if t is not None and (official_hint is None or not _approx_eq(t, official_hint)):
        pick_s, line = _cautious_from_totals(h, a)
        return ResolvedSnapshot(
            total=t,
            home=h,
            away=a,
            suggested_pick=pick_s,
            line_value=line,
            source="raw_prediction_payload",
        )

    if not pick.lineup_confirmed:
        total = _round2(pick.predicted_total_sot)
        if total is not None:
            h = _round2(pick.predicted_home_sot)
            a = _round2(pick.predicted_away_sot)
            pick_s, line = _pick_line_coherent(total, pick.suggested_pick, pick.line_value, h, a)
            return ResolvedSnapshot(
                total=total,
                home=h,
                away=a,
                suggested_pick=pick_s,
                line_value=line,
                source="pick_predicted_pre_lineup",
            )

    if _should_reject_initial_column(pick, official_hint, first_impact, latest_impact):
        return ResolvedSnapshot(
            total=None,
            home=None,
            away=None,
            suggested_pick=None,
            line_value=None,
            source="unavailable",
            reconstruction_note="initial_* duplica post ufficiali; nessun before snapshot",
        )

    return ResolvedSnapshot(
        total=None,
        home=None,
        away=None,
        suggested_pick=None,
        line_value=None,
        source="unavailable",
    )


def _impact_source_ok(impact: dict[str, Any] | None) -> bool:
    if not impact:
        return False
    src = str(impact.get("refresh_source") or impact.get("source") or "").lower()
    if src in ("auto_pre_match", "official", "manual", "manual_refresh", "sportapi"):
        return True
    return bool(impact.get("has_comparison"))


def resolve_official_snapshot(
    pick: TrackedBettingPick,
    *,
    latest_impact: dict[str, Any] | None,
    db: Session,
    fx: Fixture,
) -> ResolvedSnapshot:
    total_pick = _round2(pick.predicted_total_sot)
    pick_s = pick.suggested_pick
    line = pick.line_value

    if total_pick is not None:
        h = _round2(pick.predicted_home_sot)
        a = _round2(pick.predicted_away_sot)
        ps, ln = _pick_line_coherent(total_pick, pick_s, line, h, a)
        return ResolvedSnapshot(
            total=total_pick,
            home=h,
            away=a,
            suggested_pick=ps,
            line_value=ln,
            source="pick_predicted_total",
        )

    if latest_impact and _impact_source_ok(latest_impact):
        ap = latest_impact.get("after_payload")
        if isinstance(ap, dict):
            h, a, t = _totals_from_payload(ap)
            if t is not None:
                ps, ln = _cautious_from_totals(h, a)
                return ResolvedSnapshot(
                    total=t,
                    home=h,
                    away=a,
                    suggested_pick=ps,
                    line_value=ln,
                    source="latest_impact_after_payload",
                )

    if latest_impact:
        h, a, t = _totals_from_delta_dict(latest_impact, prefix="after")
        if t is not None:
            ps, ln = _pick_line_coherent(t, pick_s, line, h, a)
            if ps is None:
                ps, ln = _cautious_from_totals(h, a)
            return ResolvedSnapshot(
                total=t,
                home=h,
                away=a,
                suggested_pick=ps,
                line_value=ln,
                source="latest_impact_after_total",
            )

    if pick.lineup_confirmed:
        h, a, t = _load_v20_totals(db, int(fx.id), int(fx.home_team_id), int(fx.away_team_id))
        if t is not None:
            ps, ln = _cautious_from_totals(h, a)
            return ResolvedSnapshot(
                total=t,
                home=h,
                away=a,
                suggested_pick=ps,
                line_value=ln,
                source="db_v20_lineup_confirmed",
            )

    return ResolvedSnapshot(
        total=None,
        home=None,
        away=None,
        suggested_pick=pick_s,
        line_value=line,
        source="unavailable",
    )
