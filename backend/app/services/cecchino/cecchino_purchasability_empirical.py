"""Acquistabilità empirica v1.1 — copertura operativa Pannello KPI.

Versione: cecchino_purchasability_empirical_rating_v1_1
Formula score invariata rispetto a v1. Current rows da kpi_panel_json.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import (
    DATASET_VERSION,
    _load_fixtures,
    _panel_rows,
    build_purchasability_rows,
    make_json_safe,
)

EMPIRICAL_VERSION = "cecchino_purchasability_empirical_rating_v1_1"
MIN_SAMPLE = 30
MIN_PERIOD_ROWS = 10
MAX_PERIODS = 4

# Mercati panel con settlement deterministico (allineati a KPI_V2_ROW_DEFS).
SUPPORTED_SELECTIONS = frozenset(PANEL_MARKET_KEYS)

RATING_BANDS: tuple[tuple[int, int, str], ...] = (
    (50, 59, "50–59"),
    (60, 69, "60–69"),
    (70, 79, "70–79"),
    (80, 89, "80–89"),
    (90, 100, "90–100"),
)

SCOPE_LOCAL = "same_competition"
SCOPE_GLOBAL = "all_competitions_fallback"


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def get_rating_band(rating: Any) -> dict[str, Any] | None:
    try:
        r = int(rating)
    except (TypeError, ValueError):
        return None
    if r < 50:
        return None
    for lo, hi, label in RATING_BANDS:
        if lo <= r <= hi:
            return {"min": lo, "max": hi, "label": label}
    return None


def is_market_settlement_supported(market_key: str) -> bool:
    """True se il mercato è nel panel e ha settlement deterministico."""
    return bool(market_key) and market_key in SUPPORTED_SELECTIONS


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _selection(row: dict[str, Any]) -> str:
    return str(
        row.get("market_key")
        or row.get("raw_market_code")
        or row.get("selection")
        or ""
    )


def _is_valid_history_row(row: dict[str, Any]) -> bool:
    if not row.get("is_settled_core"):
        return False
    if not row.get("snapshot_timestamp_verified") or not row.get("snapshot_before_kickoff"):
        return False
    if not row.get("no_post_match_data_in_features"):
        return False
    if row.get("leakage_status") == "excluded_leakage":
        return False
    status = row.get("settlement_status")
    if status not in ("won", "lost", "void"):
        return False
    odds = _num(row.get("odds"))
    if odds is None or odds <= 1.0:
        return False
    if _num(row.get("rating")) is None:
        return False
    sel = _selection(row)
    if not is_market_settlement_supported(sel):
        return False
    if not row.get("canonical_row_key"):
        return False
    if _parse_dt(row.get("kickoff")) is None:
        return False
    return True


def _dedupe_unique_keys(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = str(r.get("canonical_row_key"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def build_empirical_history_index(
    rows: list[dict[str, Any]],
) -> dict[tuple[Any, str, str], list[dict[str, Any]]]:
    """Indice locale (competition_id, selection, band) → rows per kickoff."""
    valid = _dedupe_unique_keys([r for r in rows if _is_valid_history_row(r)])
    buckets: dict[tuple[Any, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in valid:
        band = get_rating_band(r.get("rating"))
        if not band:
            continue
        key = (r.get("competition_id"), _selection(r), band["label"])
        buckets[key].append(r)
    for key in buckets:
        buckets[key].sort(key=lambda x: _parse_dt(x.get("kickoff")) or datetime.min)
    return dict(buckets)


def build_empirical_global_history_index(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Indice globale (selection, band) → rows per kickoff."""
    valid = _dedupe_unique_keys([r for r in rows if _is_valid_history_row(r)])
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in valid:
        band = get_rating_band(r.get("rating"))
        if not band:
            continue
        key = (_selection(r), band["label"])
        buckets[key].append(r)
    for key in buckets:
        buckets[key].sort(key=lambda x: _parse_dt(x.get("kickoff")) or datetime.min)
    return dict(buckets)


def _cohort_before_kickoff(
    rows: list[dict[str, Any]],
    kickoff: datetime,
) -> list[dict[str, Any]]:
    return [
        h
        for h in rows
        if (_parse_dt(h.get("kickoff")) or datetime.max) < kickoff
    ]


def iter_current_kpi_panel_rows(
    fixtures: list[CecchinoTodayFixture],
) -> list[dict[str, Any]]:
    """Righe correnti = esattamente le rows del Pannello KPI mostrate in FE."""
    out: list[dict[str, Any]] = []
    for fx in fixtures:
        panel_rows = _panel_rows(fx)
        for prow in panel_rows:
            market_key = str(prow.get("market_key") or "")
            if not market_key:
                continue
            rating = prow.get("rating")
            try:
                rating_i = int(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating_i = None
            odds = _num(prow.get("quota_book") or prow.get("odds"))
            out.append({
                "today_fixture_id": fx.id,
                "provider_fixture_id": getattr(fx, "provider_fixture_id", None),
                "competition_id": fx.competition_id,
                "scan_date": fx.scan_date.isoformat() if fx.scan_date else None,
                "kickoff": fx.kickoff.isoformat() if fx.kickoff else None,
                "market_key": market_key,
                "selection": market_key,
                "raw_market_code": market_key,
                "label": prow.get("segno") or prow.get("label") or market_key,
                "rating": rating_i,
                "odds": odds,
                "quota_book": odds,
                "snapshot_at": None,
            })
    return out


def _period_rois(rows: list[dict[str, Any]]) -> list[float]:
    n = len(rows)
    if n < 2 * MIN_PERIOD_ROWS:
        return []
    n_periods = min(MAX_PERIODS, n // MIN_PERIOD_ROWS)
    if n_periods < 2:
        return []
    base, rem = divmod(n, n_periods)
    rois: list[float] = []
    start = 0
    for i in range(n_periods):
        size = base + (1 if i < rem else 0)
        chunk = rows[start : start + size]
        start += size
        if len(chunk) < MIN_PERIOD_ROWS:
            return []
        profits = [_num(r.get("unit_stake_profit")) or 0.0 for r in chunk]
        rois.append(sum(profits) / len(chunk))
    return rois


def calculate_empirical_cohort_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for r in rows if r.get("settlement_status") == "won")
    losses = sum(1 for r in rows if r.get("settlement_status") == "lost")
    voids = sum(1 for r in rows if r.get("settlement_status") == "void")
    decided = wins + losses
    win_rate = (wins / decided) if decided else None

    be_probs: list[float] = []
    odds_list: list[float] = []
    profits: list[float] = []
    for r in rows:
        odds = _num(r.get("odds"))
        if odds is None or odds <= 1.0:
            continue
        odds_list.append(odds)
        status = r.get("settlement_status")
        if status != "void":
            be_probs.append(1.0 / odds)
        profit = _num(r.get("unit_stake_profit"))
        if profit is None:
            if status == "won":
                profit = odds - 1.0
            elif status == "lost":
                profit = -1.0
            else:
                profit = 0.0
        profits.append(profit)

    n = len(rows)
    avg_odds = sum(odds_list) / len(odds_list) if odds_list else None
    avg_be = sum(be_probs) / len(be_probs) if be_probs else None
    realized_margin = (
        (win_rate - avg_be) if win_rate is not None and avg_be is not None else None
    )
    total_profit = sum(profits) if profits else 0.0
    roi = (total_profit / n) if n else None

    dates = [_parse_dt(r.get("kickoff")) for r in rows]
    dates_ok = [d for d in dates if d is not None]
    period_rois = _period_rois(rows)
    positive_periods = sum(1 for x in period_rois if x > 0)
    total_periods = len(period_rois)
    stability_ratio = (positive_periods / total_periods) if total_periods >= 2 else None
    comps = sorted({r.get("competition_id") for r in rows if r.get("competition_id") is not None})

    return {
        "sample_size": n,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "win_rate": win_rate,
        "average_odds": avg_odds,
        "average_break_even_probability": avg_be,
        "realized_margin": realized_margin,
        "total_profit": total_profit,
        "roi": roi,
        "positive_periods": positive_periods if total_periods else None,
        "total_periods": total_periods if total_periods else None,
        "stability_ratio": stability_ratio,
        "historical_date_from": min(dates_ok).date().isoformat() if dates_ok else None,
        "historical_date_to": max(dates_ok).date().isoformat() if dates_ok else None,
        "period_rois": period_rois,
        "competitions_in_cohort": comps,
        "competition_count": len(comps),
    }


def _class_for_score(score: int | None, status: str) -> str:
    if status == "insufficient_data":
        return "Dati insufficienti"
    if status == "rating_below_scope":
        return "Non valutato"
    if status == "unsupported_market":
        return "Non disponibile"
    if status == "history_unavailable":
        return "Storico non disponibile"
    if score is None:
        return "Dati insufficienti"
    if score <= 34:
        return "Bassa"
    if score <= 49:
        return "Debole"
    if score <= 64:
        return "Incerta"
    if score <= 79:
        return "Buona"
    return "Alta"


def _explanation(
    status: str,
    metrics: dict[str, Any],
    band: dict[str, Any] | None,
    *,
    cohort_meta: dict[str, Any] | None = None,
    selection: str | None = None,
) -> str:
    meta = cohort_meta or {}
    if status == "rating_below_scope":
        return "L’Acquistabilità viene calcolata per Rating almeno pari a 50."
    if status == "unsupported_market":
        reason = meta.get("unsupported_reason") or "settlement non affidabile"
        return f"Mercato non storicizzabile: {reason}."
    if status == "history_unavailable":
        return "Storico non disponibile per questa combinazione."
    if status == "insufficient_data":
        g = meta.get("global_sample_size") or metrics.get("sample_size") or 0
        label = (band or {}).get("label") or "?"
        sel = selection or "?"
        return (
            f"{g} casi globali per {sel} nella fascia {label}. "
            f"Servono almeno {MIN_SAMPLE} casi."
        )
    if meta.get("fallback_used"):
        n_comp = meta.get("competition_count") or 0
        local_n = meta.get("local_sample_size") or 0
        return (
            f"Storico globale: stessa fascia Rating e stesso mercato su "
            f"{n_comp} competizioni. La competizione corrente disponeva di "
            f"{local_n} solo precedente{'i' if local_n != 1 else ''}."
        )
    roi = metrics.get("roi")
    margin = metrics.get("realized_margin")
    pos = metrics.get("positive_periods")
    tot = metrics.get("total_periods")
    if roi is not None and margin is not None and roi > 0 and margin > 0:
        parts = [
            f"Storico positivo: ROI {roi * 100:+.1f}%",
            f"margine sul break-even {margin * 100:+.1f} pp",
        ]
        if pos is not None and tot:
            parts.append(f"{pos} periodi positivi su {tot}")
        return ", ".join(parts) + "."
    if roi is not None and margin is not None and (roi <= 0 or margin <= 0):
        return (
            f"Storico debole: ROI {roi * 100:+.1f}% e rendimento "
            f"{'inferiore' if (margin or 0) <= 0 else 'misto'} al break-even."
        )
    return "Valutazione empirica basata sullo storico della fascia Rating."


def calculate_empirical_purchasability(
    metrics: dict[str, Any],
    *,
    competition_id: Any = None,
    selection: str | None = None,
    rating: Any = None,
    rating_band: dict[str, Any] | None = None,
    status_override: str | None = None,
    cohort_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Applica formula empirica v1 (invariata) alle metriche di coorte."""
    meta = dict(cohort_meta or {})
    if status_override:
        status = status_override
        score = None
        reason_codes = [status_override]
    elif (metrics.get("sample_size") or 0) < MIN_SAMPLE:
        status = "insufficient_data"
        score = None
        reason_codes = ["insufficient_data"]
    else:
        status = "ok"
        reason_codes = []
        roi = float(metrics["roi"] or 0.0)
        margin = float(metrics["realized_margin"] or 0.0)
        stability = metrics.get("stability_ratio")
        roi_c = clamp(50.0 + roi * 500.0)
        margin_c = clamp(50.0 + margin * 500.0)
        stab_c = (float(stability) * 100.0) if stability is not None else 50.0
        raw = (roi_c + margin_c + stab_c) / 3.0
        n = int(metrics["sample_size"])
        confidence = min(1.0, n / 100.0)
        score_f = clamp(50.0 + confidence * (raw - 50.0))
        score = int(round(score_f))
        if roi <= 0 and margin <= 0:
            score = min(score, 49)
            reason_codes.append("negative_roi_and_margin_cap")
        metrics = {
            **metrics,
            "roi_component": roi_c,
            "margin_component": margin_c,
            "stability_component": stab_c,
            "raw_evidence_score": raw,
            "sample_confidence": confidence,
        }

    sample_confidence = metrics.get("sample_confidence")
    if sample_confidence is None and metrics.get("sample_size"):
        sample_confidence = min(1.0, int(metrics["sample_size"]) / 100.0)

    klass = _class_for_score(score, status)
    out = {
        "version": EMPIRICAL_VERSION,
        "status": status,
        "score": score,
        "class": klass,
        "competition_id": competition_id,
        "selection": selection,
        "market_key": selection,
        "rating": int(rating) if rating is not None and _num(rating) is not None else rating,
        "rating_band": rating_band,
        "sample_size": metrics.get("sample_size") or 0,
        "wins": metrics.get("wins") or 0,
        "losses": metrics.get("losses") or 0,
        "voids": metrics.get("voids") or 0,
        "win_rate": metrics.get("win_rate"),
        "average_odds": metrics.get("average_odds"),
        "average_break_even_probability": metrics.get("average_break_even_probability"),
        "realized_margin": metrics.get("realized_margin"),
        "total_profit": metrics.get("total_profit"),
        "roi": metrics.get("roi"),
        "positive_periods": metrics.get("positive_periods"),
        "total_periods": metrics.get("total_periods"),
        "stability_ratio": metrics.get("stability_ratio"),
        "sample_confidence": sample_confidence,
        "historical_date_from": metrics.get("historical_date_from"),
        "historical_date_to": metrics.get("historical_date_to"),
        "reason_codes": reason_codes,
        "explanation": _explanation(
            status, metrics, rating_band, cohort_meta=meta, selection=selection
        ),
        "dataset_version": DATASET_VERSION,
        "cohort_scope": meta.get("cohort_scope"),
        "local_sample_size": meta.get("local_sample_size"),
        "global_sample_size": meta.get("global_sample_size"),
        "selected_sample_size": meta.get("selected_sample_size") or metrics.get("sample_size") or 0,
        "competitions_in_cohort": meta.get("competitions_in_cohort")
        or metrics.get("competitions_in_cohort")
        or [],
        "competition_count": meta.get("competition_count")
        if meta.get("competition_count") is not None
        else metrics.get("competition_count"),
        "fallback_used": bool(meta.get("fallback_used")),
        "fallback_reason": meta.get("fallback_reason"),
        "raw_market_key": meta.get("raw_market_key"),
        "unsupported_reason": meta.get("unsupported_reason"),
    }
    return out


def panel_item_key(*, today_fixture_id: Any, market_key: str) -> str:
    return f"{today_fixture_id}:{market_key}"


def _score_current_panel_row(
    row: dict[str, Any],
    local_index: dict[tuple[Any, str, str], list[dict[str, Any]]],
    global_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    sel = _selection(row)
    rating = row.get("rating")
    competition_id = row.get("competition_id")
    kickoff = _parse_dt(row.get("kickoff"))
    today_fixture_id = row.get("today_fixture_id")

    base_meta = {
        "today_fixture_id": today_fixture_id,
        "provider_fixture_id": row.get("provider_fixture_id"),
        "selection": sel,
        "market_key": sel,
        "label": row.get("label"),
        "competition_id": competition_id,
        "rating": rating,
        "scan_date": row.get("scan_date"),
    }

    if not is_market_settlement_supported(sel):
        cohort_meta = {
            "raw_market_key": sel,
            "unsupported_reason": "no_deterministic_settlement",
            "local_sample_size": 0,
            "global_sample_size": 0,
            "selected_sample_size": 0,
            "fallback_used": False,
        }
        result = calculate_empirical_purchasability(
            {"sample_size": 0},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            status_override="unsupported_market",
            cohort_meta=cohort_meta,
        )
        result.update(base_meta)
        return result

    band = get_rating_band(rating)
    if band is None:
        result = calculate_empirical_purchasability(
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
        result.update(base_meta)
        result["rating_band"] = None
        result["class"] = "Non valutato"
        return result

    if kickoff is None:
        result = calculate_empirical_purchasability(
            {"sample_size": 0},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            rating_band=band,
            status_override="history_unavailable",
            cohort_meta={
                "local_sample_size": 0,
                "global_sample_size": 0,
                "selected_sample_size": 0,
                "fallback_used": False,
            },
        )
        result.update(base_meta)
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
        metrics_probe = calculate_empirical_cohort_metrics(cohort)
        cohort_meta = {
            "cohort_scope": SCOPE_GLOBAL,
            "local_sample_size": local_n,
            "global_sample_size": global_n,
            "selected_sample_size": global_n,
            "fallback_used": True,
            "fallback_reason": "same_competition_below_minimum",
            "competitions_in_cohort": metrics_probe.get("competitions_in_cohort"),
            "competition_count": metrics_probe.get("competition_count"),
        }
    else:
        cohort_meta = {
            "cohort_scope": None,
            "local_sample_size": local_n,
            "global_sample_size": global_n,
            "selected_sample_size": global_n,
            "fallback_used": False,
            "fallback_reason": "global_below_minimum",
        }
        result = calculate_empirical_purchasability(
            {"sample_size": global_n},
            competition_id=competition_id,
            selection=sel,
            rating=rating,
            rating_band=band,
            status_override="insufficient_data",
            cohort_meta=cohort_meta,
        )
        result.update(base_meta)
        return result

    metrics = calculate_empirical_cohort_metrics(cohort)
    if "competitions_in_cohort" not in cohort_meta or cohort_meta.get("competitions_in_cohort") is None:
        cohort_meta["competitions_in_cohort"] = metrics.get("competitions_in_cohort")
        cohort_meta["competition_count"] = metrics.get("competition_count")
    result = calculate_empirical_purchasability(
        metrics,
        competition_id=competition_id,
        selection=sel,
        rating=rating,
        rating_band=band,
        cohort_meta=cohort_meta,
    )
    result.update(base_meta)
    return result


def build_empirical_purchasability_for_panel(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    history_rows: list[dict[str, Any]] | None = None,
    current_rows: list[dict[str, Any]] | None = None,
    fixtures: list[CecchinoTodayFixture] | None = None,
) -> dict[str, Any]:
    """Calcola Acquistabilità empirica v1.1 per le righe visibili del Pannello KPI."""
    started = time.perf_counter()

    if fixtures is None and current_rows is None:
        fixtures = _load_fixtures(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )

    if current_rows is None:
        current_rows = iter_current_kpi_panel_rows(fixtures or [])

    # History ampia (tutte le competizioni) per abilitare fallback globale.
    if history_rows is None:
        history_rows = build_purchasability_rows(db, date_to=date_to)

    local_index = build_empirical_history_index(history_rows)
    global_index = build_empirical_global_history_index(history_rows)

    items: dict[str, Any] = {}
    scored_local = 0
    scored_global = 0
    insufficient = 0
    below_scope = 0
    unsupported = 0
    unavailable = 0
    market_dist: Counter[str] = Counter()

    for row in current_rows:
        market_key = _selection(row)
        if not market_key:
            continue
        key = panel_item_key(
            today_fixture_id=row.get("today_fixture_id"),
            market_key=market_key,
        )
        result = _score_current_panel_row(row, local_index, global_index)
        items[key] = result
        market_dist[market_key] += 1
        st = result.get("status")
        if st == "ok":
            if result.get("cohort_scope") == SCOPE_GLOBAL:
                scored_global += 1
            else:
                scored_local += 1
        elif st == "insufficient_data":
            insufficient += 1
        elif st == "rating_below_scope":
            below_scope += 1
        elif st == "unsupported_market":
            unsupported += 1
        else:
            unavailable += 1

    payload = {
        "version": EMPIRICAL_VERSION,
        "dataset_version": DATASET_VERSION,
        "status": "ok",
        "items": items,
        "summary": {
            "rows_requested": len(items),
            "rows_scored": scored_local + scored_global,
            "scored_same_competition": scored_local,
            "scored_global_fallback": scored_global,
            "below_scope": below_scope,
            "insufficient_data": insufficient,
            "insufficient_after_global_fallback": insufficient,
            "unsupported_market": unsupported,
            "unsupported": unsupported,
            "history_unavailable": unavailable,
            "market_distribution": dict(sorted(market_dist.items())),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "no_db_writes": True,
        },
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
        },
    }
    safe = make_json_safe(payload)
    json.dumps(safe, allow_nan=False)
    return safe
