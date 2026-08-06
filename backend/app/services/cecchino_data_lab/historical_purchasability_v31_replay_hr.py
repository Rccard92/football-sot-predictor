"""Affidabilità storica walk-forward per replay Lab V3.1 (anti-leakage).

Per ogni valutazione a kickoff T usa soltanto eventi conclusi con kickoff < T.
Partite con stesso kickoff condividono lo stesso prior set; i risultati del
gruppo vengono aggiunti allo storico solo dopo il calcolo completo del gruppo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.cecchino.cecchino_historical_reliability import (
    MIN_SAMPLE,
    SCOPE_GLOBAL,
    SCOPE_LOCAL,
    _cohort_before_kickoff,
    _num,
    _parse_dt,
    build_historical_reliability_global_index,
    build_historical_reliability_index,
    calculate_historical_reliability,
    calculate_historical_reliability_cohort_metrics,
    get_rating_band,
    is_market_settlement_supported,
)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class WalkForwardHREvent:
    """Evento settled usabile come storia HR (solo quote reali)."""

    market_key: str
    competition_id: Any
    competition_name: str | None
    kickoff: datetime
    rating: int
    odds: float
    settlement_status: str  # won | lost | void
    unit_stake_profit: float
    snapshot_id: int
    market_result_id: int
    lab_match_id: Any = None

    @property
    def profit(self) -> float:
        """Alias di unit_stake_profit (contratto walk-forward)."""
        return self.unit_stake_profit

    @property
    def canonical_row_key(self) -> str:
        return f"lab:{self.snapshot_id}:{self.market_key}:{self.market_result_id}"


@dataclass
class WalkForwardHRStore:
    """Accumulo cronologico di eventi settled (mutabile, per-replay)."""

    events: list[WalkForwardHREvent] = field(default_factory=list)

    def append_many(self, new_events: list[WalkForwardHREvent]) -> None:
        self.events.extend(new_events)

    @property
    def count(self) -> int:
        return len(self.events)


def market_result_to_hr_event(
    snap: Any,
    market: Any,
) -> WalkForwardHREvent | None:
    """Converte MarketResult Lab in evento HR; None se non idoneo."""
    if market is None or snap is None:
        return None
    is_real = bool(getattr(market, "is_real_book_quote", False))
    is_derived = bool(getattr(market, "is_derived_quote", False))
    if not is_real or is_derived:
        return None

    mk = str(getattr(market, "market_key", "") or "")
    if not is_market_settlement_supported(mk):
        return None

    won = getattr(market, "won", None)
    result_reason = str(getattr(market, "result_reason", "") or "").lower()
    if won is None and "void" not in result_reason:
        return None
    if "void" in result_reason:
        settlement = "void"
        profit = 0.0
    elif won is True:
        settlement = "won"
        profit_raw = getattr(market, "profit_1u_real", None)
        odds = _num(getattr(market, "quota_book", None))
        if profit_raw is not None:
            profit = float(profit_raw)
        elif odds is not None:
            profit = float(odds) - 1.0
        else:
            return None
    elif won is False:
        settlement = "lost"
        profit = -1.0
    else:
        return None

    odds = _num(getattr(market, "quota_book", None))
    if odds is None or odds <= 1.0:
        return None

    rating_raw = getattr(market, "rating", None)
    try:
        rating = int(rating_raw)
    except (TypeError, ValueError):
        return None
    if get_rating_band(rating) is None:
        # Rating < 50 non entra nelle bande HR
        return None

    kickoff = _ensure_aware(getattr(snap, "kickoff_at", None))
    if kickoff is None:
        return None

    competition_id = (
        getattr(snap, "competition_id", None)
        or getattr(snap, "competition_name", None)
        or "unknown"
    )

    return WalkForwardHREvent(
        market_key=mk,
        competition_id=competition_id,
        competition_name=getattr(snap, "competition_name", None),
        kickoff=kickoff,
        rating=rating,
        odds=float(odds),
        settlement_status=settlement,
        unit_stake_profit=float(profit),
        snapshot_id=int(getattr(snap, "id", 0) or 0),
        market_result_id=int(getattr(market, "id", 0) or 0),
        lab_match_id=getattr(snap, "lab_match_id", None),
    )


def events_to_history_rows(events: list[WalkForwardHREvent]) -> list[dict[str, Any]]:
    """Righe compatibili con build_historical_reliability_index / _is_valid_history_row."""
    out: list[dict[str, Any]] = []
    for ev in events:
        out.append(
            {
                "canonical_row_key": ev.canonical_row_key,
                "market_key": ev.market_key,
                "selection": ev.market_key,
                "raw_market_code": ev.market_key,
                "competition_id": ev.competition_id,
                "competition_name": ev.competition_name,
                "kickoff": ev.kickoff.isoformat(),
                "rating": ev.rating,
                "odds": ev.odds,
                "unit_stake_profit": ev.unit_stake_profit,
                "settlement_status": ev.settlement_status,
                "is_settled_core": True,
                "snapshot_timestamp_verified": True,
                "snapshot_before_kickoff": True,
                "no_post_match_data_in_features": True,
                "leakage_status": "ok",
                "lab_match_id": ev.lab_match_id,
                "snapshot_id": ev.snapshot_id,
            }
        )
    return out


def _score_panel_row_from_indexes(
    row: dict[str, Any],
    local_index: dict[tuple[Any, str, str], list[dict[str, Any]]],
    global_index: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    kickoff: datetime,
    prior_events_count: int,
    same_kickoff_group_size: int,
) -> dict[str, Any]:
    sel = str(row.get("market_key") or "")
    rating = row.get("rating")
    competition_id = row.get("competition_id")
    band = get_rating_band(rating)

    audit_base = {
        "historical_cutoff": kickoff.isoformat(),
        "prior_events_count": prior_events_count,
        "same_kickoff_group_size": same_kickoff_group_size,
        "same_kickoff_results_excluded": True,
        "future_events_excluded": True,
        "walk_forward": True,
    }

    if not is_market_settlement_supported(sel):
        result = calculate_historical_reliability(
            {"sample_size": 0},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            status_override="unsupported_market",
            cohort_meta={
                "local_sample_size": 0,
                "global_sample_size": 0,
                "selected_sample_size": 0,
                "fallback_used": False,
                "unsupported_reason": "no_deterministic_settlement",
            },
        )
        result.update(audit_base)
        result["historical_factor"] = None
        return result

    if band is None:
        result = calculate_historical_reliability(
            {"sample_size": 0},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            status_override="rating_below_scope",
            cohort_meta={
                "local_sample_size": 0,
                "global_sample_size": 0,
                "selected_sample_size": 0,
                "fallback_used": False,
            },
        )
        result.update(audit_base)
        result["historical_factor"] = None
        result["rating_band"] = None
        return result

    local_all = local_index.get((competition_id, sel, band["label"])) or []
    local_cohort = _cohort_before_kickoff(local_all, kickoff)
    global_all = global_index.get((sel, band["label"])) or []
    global_cohort = _cohort_before_kickoff(global_all, kickoff)
    local_n = len(local_cohort)
    global_n = len(global_cohort)

    if local_n >= MIN_SAMPLE:
        cohort = local_cohort
        cohort_meta = {
            "cohort_scope": SCOPE_LOCAL,
            "local_sample_size": local_n,
            "global_sample_size": global_n,
            "selected_sample_size": local_n,
            "fallback_used": False,
            "fallback_reason": None,
        }
    elif global_n >= MIN_SAMPLE:
        cohort = global_cohort
        probe = calculate_historical_reliability_cohort_metrics(cohort)
        cohort_meta = {
            "cohort_scope": SCOPE_GLOBAL,
            "local_sample_size": local_n,
            "global_sample_size": global_n,
            "selected_sample_size": global_n,
            "fallback_used": True,
            "fallback_reason": "same_competition_below_minimum",
            "competitions_in_cohort": probe.get("competitions_in_cohort"),
            "competition_count": probe.get("competition_count"),
        }
    else:
        result = calculate_historical_reliability(
            {"sample_size": global_n},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            rating_band=band,
            status_override="insufficient_data",
            cohort_meta={
                "cohort_scope": None,
                "local_sample_size": local_n,
                "global_sample_size": global_n,
                "selected_sample_size": global_n,
                "fallback_used": False,
                "fallback_reason": "global_below_minimum",
            },
        )
        result.update(audit_base)
        result["historical_factor"] = None
        result["hr_score"] = None
        return result

    metrics = calculate_historical_reliability_cohort_metrics(cohort)
    result = calculate_historical_reliability(
        metrics,
        competition_id=competition_id,
        selection=sel,
        rating=rating,
        rating_band=band,
        cohort_meta=cohort_meta,
    )
    result.update(audit_base)
    score = result.get("score")
    result["hr_score"] = score
    result["historical_factor"] = (float(score) / 100.0) if score is not None else None
    return result


def resolve_hr_as_of(
    *,
    panel_rows: list[dict[str, Any]],
    competition_id: Any,
    kickoff: datetime | None,
    prior_events: list[WalkForwardHREvent],
    same_kickoff_group_size: int = 1,
) -> dict[str, dict[str, Any]]:
    """Mappa market_key → item HR walk-forward (solo prior_events con kickoff < T)."""
    if kickoff is None:
        return {}
    kickoff = _ensure_aware(kickoff)
    assert kickoff is not None

    # Strict: escludi stesso kickoff e futuro
    filtered = [
        e
        for e in prior_events
        if _ensure_aware(e.kickoff) is not None and _ensure_aware(e.kickoff) < kickoff  # type: ignore[operator]
    ]
    history_rows = events_to_history_rows(filtered)
    local_index = build_historical_reliability_index(history_rows)
    global_index = build_historical_reliability_global_index(history_rows)
    prior_n = len(filtered)

    out: dict[str, dict[str, Any]] = {}
    for prow in panel_rows:
        mk = str(prow.get("market_key") or "")
        if not mk:
            continue
        row = {
            **prow,
            "competition_id": prow.get("competition_id")
            if prow.get("competition_id") is not None
            else competition_id,
            "kickoff": kickoff.isoformat(),
            "market_key": mk,
            "selection": mk,
        }
        out[mk] = _score_panel_row_from_indexes(
            row,
            local_index,
            global_index,
            kickoff=kickoff,
            prior_events_count=prior_n,
            same_kickoff_group_size=same_kickoff_group_size,
        )
    return out


def collect_settled_events_for_snapshot(
    snap: Any,
    markets: list[Any],
) -> list[WalkForwardHREvent]:
    """Raccoglie eventi settled da uno snapshot (da aggiungere DOPO il gruppo)."""
    out: list[WalkForwardHREvent] = []
    for m in markets:
        ev = market_result_to_hr_event(snap, m)
        if ev is not None:
            out.append(ev)
    return out


def append_settled_events(
    store: WalkForwardHRStore,
    events: list[WalkForwardHREvent] | None,
) -> int:
    """Aggiunge eventi settled allo store dopo il gruppo kickoff (dedupe per key)."""
    if not events:
        return 0
    seen = {e.canonical_row_key for e in store.events}
    added = 0
    for ev in events:
        if not isinstance(ev, WalkForwardHREvent):
            continue
        if ev.canonical_row_key in seen:
            continue
        seen.add(ev.canonical_row_key)
        store.events.append(ev)
        added += 1
    return added
