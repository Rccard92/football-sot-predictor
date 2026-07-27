"""Ricostruzione contesti PIT pre-match da partite Cecchino Lab (anti-leakage)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino.cecchino_constants import (
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    TARGET_RECENT_CONTEXT,
    TARGET_RECENT_TOTAL,
)
from app.services.cecchino.cecchino_engine import (
    CecchinoCalculationInput,
    WDLRecord,
    build_full_cecchino_output,
)
from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    CONTEXT_KEY_LAST6_TOTALS,
    CONTEXT_KEY_TOTALS,
    CONTEXT_LABELS,
    CONTEXT_TARGETS,
    GoalContextSlice,
    GoalFixtureSlices,
    GoalMarketContexts,
    GoalTotals,
    TARGET_GOAL_HOME_AWAY,
    TARGET_GOAL_HT,
    TARGET_GOAL_TOTAL,
    aggregate_goal_totals,
    aggregate_halftime_goal_totals,
    wdl_from_fixtures,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import (
    _FT_MARKETS,
    _PT_MARKETS,
    calculate_first_half_draw_market_v1,
    calculate_goal_market_v2,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT
from app.services.cecchino.cecchino_today_constants import (
    MIN_AWAY_CONTEXT,
    MIN_AWAY_TOTAL,
    MIN_HOME_CONTEXT,
    MIN_HOME_TOTAL,
    MIN_RECENT_CONTEXT_5,
    MIN_RECENT_TOTAL_6,
)


def stable_team_id(name: str) -> int:
    """ID stabile positivo da nome squadra (hash)."""
    h = hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()
    return int(h[:12], 16) % (10**12) + 1


def match_sort_key(m: CecchinoLabMatch) -> tuple:
    return (
        m.kickoff_at is None,
        m.kickoff_at or datetime.min,
        m.match_date is None,
        m.match_date or datetime.min.date(),
        m.match_time is None,
        str(m.match_time) if m.match_time else "",
        int(m.source_row_number or 0),
        int(m.id),
    )


def lab_match_to_proxy(m: CecchinoLabMatch, *, competition_id: int) -> SimpleNamespace:
    home = m.home_team or ""
    away = m.away_team or ""
    ht_home = m.ht_home_goals
    ht_away = m.ht_away_goals
    raw = {
        "score": {
            "halftime": {
                "home": ht_home,
                "away": ht_away,
            }
            if ht_home is not None and ht_away is not None
            else {}
        },
        "lab_match_id": int(m.id),
    }
    return SimpleNamespace(
        id=int(m.id),
        home_team_id=stable_team_id(home) if home else 0,
        away_team_id=stable_team_id(away) if away else 0,
        home_team_name=home,
        away_team_name=away,
        goals_home=m.ft_home_goals,
        goals_away=m.ft_away_goals,
        kickoff_at=m.kickoff_at,
        match_date=m.match_date,
        match_time=m.match_time,
        source_row_number=m.source_row_number,
        status="FT",
        competition_id=competition_id,
        raw_json=raw,
        lab_match=m,
    )


def _proxy_sort_key(p: SimpleNamespace) -> tuple:
    return (
        p.kickoff_at is None,
        p.kickoff_at or datetime.min,
        p.match_date is None,
        p.match_date or datetime.min.date(),
        p.match_time is None,
        str(p.match_time) if p.match_time else "",
        int(p.source_row_number or 0),
        int(p.id),
    )


def sort_proxies(proxies: list[SimpleNamespace]) -> list[SimpleNamespace]:
    return sorted(proxies, key=_proxy_sort_key)


def prior_proxies_strict(
    ordered: list[SimpleNamespace],
    target: SimpleNamespace,
) -> list[SimpleNamespace]:
    """Partite strettamente precedenti (stesso kickoff escluso)."""
    out: list[SimpleNamespace] = []
    for p in ordered:
        if int(p.id) == int(target.id):
            continue
        if p.kickoff_at is None or target.kickoff_at is None:
            continue
        if p.kickoff_at < target.kickoff_at:
            out.append(p)
    return out


def team_priors(priors: list[SimpleNamespace], team_id: int) -> list[SimpleNamespace]:
    tid = int(team_id)
    return [
        p
        for p in priors
        if int(p.home_team_id) == tid or int(p.away_team_id) == tid
    ]


def split_home_away_proxies(
    fixtures: list[SimpleNamespace],
    team_id: int,
    *,
    is_home: bool,
) -> list[SimpleNamespace]:
    tid = int(team_id)
    if is_home:
        return [p for p in fixtures if int(p.home_team_id) == tid]
    return [p for p in fixtures if int(p.away_team_id) == tid]


def take_last_n_proxies(fixtures: list[SimpleNamespace], n: int) -> list[SimpleNamespace]:
    if n <= 0:
        return []
    return list(fixtures[-n:]) if len(fixtures) > n else list(fixtures)


def filter_halftime_proxies(
    fixtures: list[SimpleNamespace],
) -> tuple[list[SimpleNamespace], int]:
    valid: list[SimpleNamespace] = []
    skipped = 0
    for p in fixtures:
        ht = (p.raw_json or {}).get("score", {}).get("halftime", {})
        if ht.get("home") is None or ht.get("away") is None:
            skipped += 1
        else:
            valid.append(p)
    return valid, skipped


def _make_slice(
    *,
    name: str,
    home_fixtures: list,
    away_fixtures: list,
    home_team_id: int,
    away_team_id: int,
    use_halftime: bool = False,
) -> GoalContextSlice:
    target, min_s = CONTEXT_TARGETS[name]
    agg = aggregate_halftime_goal_totals if use_halftime else aggregate_goal_totals
    return GoalContextSlice(
        name=name,
        label=CONTEXT_LABELS[name],
        home_fixtures=home_fixtures,
        away_fixtures=away_fixtures,
        home_totals=agg(home_fixtures, home_team_id),
        away_totals=agg(away_fixtures, away_team_id),
        target_sample=target,
        min_sample=min_s,
    )


@dataclass
class LabPreMatchContexts:
    home_context: WDLRecord
    away_context: WDLRecord
    home_total: WDLRecord
    away_total: WDLRecord
    home_recent_context_5: WDLRecord
    away_recent_context_5: WDLRecord
    home_recent_total_6: WDLRecord
    away_recent_total_6: WDLRecord
    sample_meta: dict[str, dict[str, int | None]] = field(default_factory=dict)
    fixture_ids: dict[str, list[int]] = field(default_factory=dict)
    goal_contexts: GoalMarketContexts | None = None
    goal_slices: GoalFixtureSlices | None = None
    league_probs: dict[str, float | None] = field(default_factory=dict)
    prior_count: int = 0
    leakage_ok: bool = True


def build_lab_prematch_contexts(
    *,
    competition_ordered: list[SimpleNamespace],
    target: SimpleNamespace,
) -> LabPreMatchContexts:
    priors = prior_proxies_strict(competition_ordered, target)
    hid = int(target.home_team_id)
    aid = int(target.away_team_id)

    home_prior = team_priors(priors, hid)
    away_prior = team_priors(priors, aid)
    home_split = split_home_away_proxies(home_prior, hid, is_home=True)
    away_split = split_home_away_proxies(away_prior, aid, is_home=False)
    home_last5 = take_last_n_proxies(home_split, TARGET_RECENT_CONTEXT)
    away_last5 = take_last_n_proxies(away_split, TARGET_RECENT_CONTEXT)
    home_last6 = take_last_n_proxies(home_prior, TARGET_RECENT_TOTAL)
    away_last6 = take_last_n_proxies(away_prior, TARGET_RECENT_TOTAL)

    # Leakage check: no target / future / same kickoff in priors
    leakage_ok = True
    for p in priors:
        if int(p.id) == int(target.id):
            leakage_ok = False
        if p.kickoff_at is not None and target.kickoff_at is not None:
            if p.kickoff_at >= target.kickoff_at:
                leakage_ok = False

    ht_home_prior, s1 = filter_halftime_proxies(home_prior)
    ht_away_prior, s2 = filter_halftime_proxies(away_prior)
    ht_home_split, s3 = filter_halftime_proxies(home_split)
    ht_away_split, s4 = filter_halftime_proxies(away_split)
    ht_home_last6, s5 = filter_halftime_proxies(home_last6)
    ht_away_last6, s6 = filter_halftime_proxies(away_last6)
    ht_home_last5, s7 = filter_halftime_proxies(home_last5)
    ht_away_last5, s8 = filter_halftime_proxies(away_last5)
    ht_skip = s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8

    goal_contexts = GoalMarketContexts(
        totals=_make_slice(
            name=CONTEXT_KEY_TOTALS,
            home_fixtures=home_prior,
            away_fixtures=away_prior,
            home_team_id=hid,
            away_team_id=aid,
        ),
        home_away=_make_slice(
            name=CONTEXT_KEY_HOME_AWAY,
            home_fixtures=home_split,
            away_fixtures=away_split,
            home_team_id=hid,
            away_team_id=aid,
        ),
        last6_totals=_make_slice(
            name=CONTEXT_KEY_LAST6_TOTALS,
            home_fixtures=home_last6,
            away_fixtures=away_last6,
            home_team_id=hid,
            away_team_id=aid,
        ),
        last5_home_away=_make_slice(
            name=CONTEXT_KEY_LAST5_HOME_AWAY,
            home_fixtures=home_last5,
            away_fixtures=away_last5,
            home_team_id=hid,
            away_team_id=aid,
        ),
        ht_totals=_make_slice(
            name=CONTEXT_KEY_TOTALS,
            home_fixtures=ht_home_prior,
            away_fixtures=ht_away_prior,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_home_away=_make_slice(
            name=CONTEXT_KEY_HOME_AWAY,
            home_fixtures=ht_home_split,
            away_fixtures=ht_away_split,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_last6_totals=_make_slice(
            name=CONTEXT_KEY_LAST6_TOTALS,
            home_fixtures=ht_home_last6,
            away_fixtures=ht_away_last6,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        ht_last5_home_away=_make_slice(
            name=CONTEXT_KEY_LAST5_HOME_AWAY,
            home_fixtures=ht_home_last5,
            away_fixtures=ht_away_last5,
            home_team_id=hid,
            away_team_id=aid,
            use_halftime=True,
        ),
        skipped_missing_halftime_score=ht_skip,
        home_team_id=hid,
        away_team_id=aid,
    )

    home_home_5 = take_last_n_proxies(home_split, TARGET_GOAL_HOME_AWAY)
    away_away_5 = take_last_n_proxies(away_split, TARGET_GOAL_HOME_AWAY)
    home_total_10 = take_last_n_proxies(home_prior, TARGET_GOAL_TOTAL)
    away_total_10 = take_last_n_proxies(away_prior, TARGET_GOAL_TOTAL)
    home_ht_fx = take_last_n_proxies(ht_home_split, TARGET_GOAL_HT)
    away_ht_fx = take_last_n_proxies(ht_away_split, TARGET_GOAL_HT)
    goal_slices = GoalFixtureSlices(
        home_home_5=aggregate_goal_totals(home_home_5, hid),
        away_away_5=aggregate_goal_totals(away_away_5, aid),
        home_total_10=aggregate_goal_totals(home_total_10, hid),
        away_total_10=aggregate_goal_totals(away_total_10, aid),
        home_home_ht_5=aggregate_halftime_goal_totals(home_ht_fx, hid),
        away_away_ht_5=aggregate_halftime_goal_totals(away_ht_fx, aid),
        skipped_missing_halftime_score=ht_skip,
    )

    league_probs = _league_event_probabilities_from_proxies(priors)

    sample_meta = {
        PICCHETTO_KEY_HOME_AWAY: {
            "home_sample_count": len(home_split),
            "away_sample_count": len(away_split),
            "home_target_sample": TARGET_RECENT_CONTEXT,
            "away_target_sample": TARGET_RECENT_CONTEXT,
        },
        PICCHETTO_KEY_TOTALS: {
            "home_sample_count": len(home_prior),
            "away_sample_count": len(away_prior),
            "home_target_sample": 10,
            "away_target_sample": 10,
        },
        PICCHETTO_KEY_LAST5_HOME_AWAY: {
            "home_sample_count": len(home_last5),
            "away_sample_count": len(away_last5),
            "home_target_sample": TARGET_RECENT_CONTEXT,
            "away_target_sample": TARGET_RECENT_CONTEXT,
        },
        PICCHETTO_KEY_LAST6_TOTALS: {
            "home_sample_count": len(home_last6),
            "away_sample_count": len(away_last6),
            "home_target_sample": TARGET_RECENT_TOTAL,
            "away_target_sample": TARGET_RECENT_TOTAL,
        },
    }

    return LabPreMatchContexts(
        home_context=wdl_from_fixtures(home_split, hid),
        away_context=wdl_from_fixtures(away_split, aid),
        home_total=wdl_from_fixtures(home_prior, hid),
        away_total=wdl_from_fixtures(away_prior, aid),
        home_recent_context_5=wdl_from_fixtures(home_last5, hid),
        away_recent_context_5=wdl_from_fixtures(away_last5, aid),
        home_recent_total_6=wdl_from_fixtures(home_last6, hid),
        away_recent_total_6=wdl_from_fixtures(away_last6, aid),
        sample_meta=sample_meta,
        fixture_ids={
            "home_context": [int(p.id) for p in home_split],
            "away_context": [int(p.id) for p in away_split],
            "home_total": [int(p.id) for p in home_prior],
            "away_total": [int(p.id) for p in away_prior],
            "home_recent_context_5": [int(p.id) for p in home_last5],
            "away_recent_context_5": [int(p.id) for p in away_last5],
            "home_recent_total_6": [int(p.id) for p in home_last6],
            "away_recent_total_6": [int(p.id) for p in away_last6],
        },
        goal_contexts=goal_contexts,
        goal_slices=goal_slices,
        league_probs=league_probs,
        prior_count=len(priors),
        leakage_ok=leakage_ok,
    )


def contexts_to_input(ctx: LabPreMatchContexts) -> CecchinoCalculationInput:
    return CecchinoCalculationInput(
        home_away=(ctx.home_context, ctx.away_context),
        totals=(ctx.home_total, ctx.away_total),
        last5_home_away=(ctx.home_recent_context_5, ctx.away_recent_context_5),
        last6_totals=(ctx.home_recent_total_6, ctx.away_recent_total_6),
    )


def compute_cecchino_from_contexts(ctx: LabPreMatchContexts) -> dict[str, Any]:
    inp = contexts_to_input(ctx)
    out = build_full_cecchino_output(inp, picchetto_sample_meta=ctx.sample_meta)
    return out.to_dict()


def compute_goal_markets_from_contexts(ctx: LabPreMatchContexts) -> dict[str, Any]:
    if ctx.goal_contexts is None or ctx.goal_slices is None:
        return {}
    markets: dict[str, Any] = {}
    markets[SEL_DRAW_PT] = calculate_first_half_draw_market_v1(
        ctx.goal_contexts, ctx.league_probs
    )
    for mk in _FT_MARKETS + _PT_MARKETS:
        markets[mk] = calculate_goal_market_v2(
            mk,
            ctx.goal_contexts,
            ctx.league_probs,
            legacy_slices=ctx.goal_slices,
        )
    return markets


def build_input_snapshot(ctx: LabPreMatchContexts) -> dict[str, Any]:
    def _wdl(w: WDLRecord) -> dict[str, int]:
        return w.to_dict()

    return {
        "home_context": {
            "wdl": _wdl(ctx.home_context),
            "sample": ctx.home_context.total,
            "min_required": MIN_HOME_CONTEXT,
        },
        "away_context": {
            "wdl": _wdl(ctx.away_context),
            "sample": ctx.away_context.total,
            "min_required": MIN_AWAY_CONTEXT,
        },
        "home_total": {
            "wdl": _wdl(ctx.home_total),
            "sample": ctx.home_total.total,
            "min_required": MIN_HOME_TOTAL,
        },
        "away_total": {
            "wdl": _wdl(ctx.away_total),
            "sample": ctx.away_total.total,
            "min_required": MIN_AWAY_TOTAL,
        },
        "home_recent_context_5": {
            "wdl": _wdl(ctx.home_recent_context_5),
            "sample": ctx.home_recent_context_5.total,
            "min_required": MIN_RECENT_CONTEXT_5,
        },
        "away_recent_context_5": {
            "wdl": _wdl(ctx.away_recent_context_5),
            "sample": ctx.away_recent_context_5.total,
            "min_required": MIN_RECENT_CONTEXT_5,
        },
        "home_recent_total_6": {
            "wdl": _wdl(ctx.home_recent_total_6),
            "sample": ctx.home_recent_total_6.total,
            "min_required": MIN_RECENT_TOTAL_6,
        },
        "away_recent_total_6": {
            "wdl": _wdl(ctx.away_recent_total_6),
            "sample": ctx.away_recent_total_6.total,
            "min_required": MIN_RECENT_TOTAL_6,
        },
        "fixture_ids": ctx.fixture_ids,
        "prior_count": ctx.prior_count,
        "leakage_ok": ctx.leakage_ok,
        "sample_meta": ctx.sample_meta,
    }


def sha256_prematch_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _league_event_probabilities_from_proxies(
    league_fixtures: list[SimpleNamespace],
) -> dict[str, float | None]:
    """Stessa semantica di league_event_probabilities, su proxy Lab."""
    from app.services.cecchino.cecchino_goal_poisson_v2 import (
        _ft_event_hit,
    )

    all_markets = _FT_MARKETS + _PT_MARKETS + (SEL_DRAW_PT,)
    if not league_fixtures:
        return {m: None for m in all_markets}

    ft_totals: dict[str, int] = {m: 0 for m in _FT_MARKETS}
    pt_totals: dict[str, int] = {m: 0 for m in _PT_MARKETS}
    ft_n = pt_n = 0
    ht_draw_n = 0

    for f in league_fixtures:
        if f.goals_home is None or f.goals_away is None:
            continue
        gh, ga = int(f.goals_home), int(f.goals_away)
        ft_n += 1
        for m in _FT_MARKETS:
            if _ft_event_hit(gh, ga, m):
                ft_totals[m] += 1

        raw = f.raw_json if isinstance(f.raw_json, dict) else {}
        score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
        ht = score.get("halftime") if isinstance(score.get("halftime"), dict) else {}
        hh, ha = ht.get("home"), ht.get("away")
        if hh is not None and ha is not None:
            try:
                ht_home, ht_away = int(hh), int(ha)
            except (TypeError, ValueError):
                continue
            pt_n += 1
            ht_total = ht_home + ht_away
            if ht_total >= 1:
                pt_totals["OVER_PT_0_5"] += 1
            if ht_total >= 2:
                pt_totals["OVER_PT_1_5"] += 1
            if ht_total <= 1:
                pt_totals["UNDER_PT_1_5"] += 1
            if ht_home == ht_away:
                ht_draw_n += 1

    out: dict[str, float | None] = {}
    for m in _FT_MARKETS:
        out[m] = round(ft_totals[m] / ft_n, 4) if ft_n > 0 else None
    for m in _PT_MARKETS:
        out[m] = round(pt_totals[m] / pt_n, 4) if pt_n > 0 else None
    out[SEL_DRAW_PT] = round(ht_draw_n / pt_n, 4) if pt_n > 0 else None
    return out
