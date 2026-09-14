"""Registro previsioni live: congela V2 e V2.5 prima del calcio d'inizio, poi registra gli esiti.

Regole:
- si registrano solo le partite eleggibili di Cecchino Today con fixture locale;
- una previsione si aggiorna finche' il calcio d'inizio non e' passato; dopo resta congelata
  (nessuna scrittura sulle probabilita' dopo il kickoff);
- a partita finita (risultato finale presente) ogni mercato riceve vinta/persa e profitto a
  quota book congelata.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture
from app.models.cecchino_live_prediction import (
    LIVE_STATUS_OPEN,
    LIVE_STATUS_SETTLED,
    CecchinoLivePrediction,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino_data_lab.run_v2.settlement import (
    evaluate_market_outcome_v2,
    flat_stake_profit,
    match_result_from_lab_match,
)
from app.services.cecchino_v25.constants import ENGINE_VERSION as V25_ENGINE_VERSION

logger = logging.getLogger(__name__)

MODEL_V2 = "V2"
MODEL_V25 = "V2.5"
V2_ENGINE_VERSION = "cecchino_today_v2"
ELIGIBLE = "eligible"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _round(v: Any, places: int = 6) -> float | None:
    try:
        return round(float(v), places) if v is not None else None
    except (TypeError, ValueError):
        return None


def v2_markets(row: CecchinoTodayFixture) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in (row.kpi_panel_json or {}).get("rows") or []:
        key = r.get("market_key")
        if not key:
            continue
        out[str(key)] = {
            "probability": _round(r.get("prob_cecchino")),
            "quota_cecchino": _round(r.get("quota_cecchino"), 4),
            "quota_book": _round(r.get("quota_book"), 4),
            "rating": r.get("rating"),
            "vantaggio_prob": _round(r.get("vantaggio_prob")),
            "edge_pct": _round(r.get("edge_pct"), 3),
        }
    return out


def v25_payload(pre: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    purch = {m["market_key"]: m for m in (pre["purchasability"].get("markets") or [])}
    markets: dict[str, Any] = {}
    for r in pre["kpi"]["rows"]:
        key = r["market_key"]
        p = purch.get(key) or {}
        markets[key] = {
            "probability": r.get("prob_cecchino"),
            "quota_cecchino": r.get("quota_cecchino"),
            "quota_book": r.get("quota_book"),
            "prob_book_fair": r.get("prob_book_fair"),
            "rating": r.get("rating"),
            "vantaggio_prob": r.get("vantaggio_prob"),
            "edge_pct": r.get("edge_pct"),
            "buyability_score": p.get("score"),
            "buyability_class": p.get("class"),
            "signal_active": bool((pre["signal_index"].get(key) or {}).get("signal_active")),
        }
    gi = pre["gi"]
    modules = {
        "balance_classes": pre["balance"].get("pillar_classes"),
        "goal_intensity_classes": {k: v.get("class_key") for k, v in (gi.get("pillars") or {}).items()},
        "goal_intensity_final": (gi.get("final_class") or {}).get("key"),
        "eligibility": pre["eligibility"].get("status"),
        "history_matches": pre.get("history_matches"),
        "league_reference": pre.get("league_reference"),
    }
    return markets, modules


def _upsert(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    model: str,
    engine_version: str,
    markets: dict[str, Any],
    modules: dict[str, Any] | None,
    eligible: bool,
    now: datetime,
) -> str:
    existing = db.scalars(
        select(CecchinoLivePrediction).where(
            CecchinoLivePrediction.today_fixture_id == int(row.id),
            CecchinoLivePrediction.model == model,
        )
    ).first()
    kickoff = _aware(row.kickoff)
    if existing is not None and (existing.status != LIVE_STATUS_OPEN or (kickoff is not None and now >= kickoff)):
        return "frozen"
    target = existing or CecchinoLivePrediction(today_fixture_id=int(row.id), model=model)
    target.provider_fixture_id = int(row.provider_fixture_id)
    target.local_fixture_id = row.local_fixture_id
    target.scan_date = row.scan_date
    target.kickoff = kickoff
    target.country_name = row.country_name
    target.league_name = row.league_name
    target.home_team_name = row.home_team_name
    target.away_team_name = row.away_team_name
    target.engine_version = engine_version
    target.status = LIVE_STATUS_OPEN
    target.frozen_at = now
    target.eligible = eligible
    target.markets_json = markets
    target.modules_json = modules
    if existing is None:
        db.add(target)
    return "updated" if existing is not None else "created"


def record_predictions(db: Session, *, scan_date: date, now: datetime | None = None) -> dict[str, Any]:
    """V2 (dallo snapshot di Cecchino Today) e V2.5 (calcolata qui) per le partite non iniziate."""
    from app.services.cecchino_live.v25_live import compute_v25_live

    now = now or _now()
    rows = db.scalars(
        select(CecchinoTodayFixture).where(
            CecchinoTodayFixture.scan_date == scan_date,
            CecchinoTodayFixture.eligibility_status == ELIGIBLE,
            CecchinoTodayFixture.local_fixture_id.is_not(None),
        )
    ).all()
    counts: dict[str, int] = {}
    errors: list[str] = []
    for row in rows:
        kickoff = _aware(row.kickoff)
        if kickoff is None or now >= kickoff:
            counts["already_started"] = counts.get("already_started", 0) + 1
            continue
        state = _upsert(
            db, row, model=MODEL_V2, engine_version=V2_ENGINE_VERSION,
            markets=v2_markets(row), modules=None, eligible=True, now=now,
        )
        counts[f"v2_{state}"] = counts.get(f"v2_{state}", 0) + 1
        fixture = db.get(Fixture, int(row.local_fixture_id))
        if fixture is None:
            continue
        try:
            with db.begin_nested():
                pre = compute_v25_live(db, fixture, row.kpi_panel_json)
                markets, modules = v25_payload(pre)
                state = _upsert(
                    db, row, model=MODEL_V25, engine_version=V25_ENGINE_VERSION,
                    markets=markets, modules=modules,
                    eligible=bool(pre["eligibility"].get("core_eligible")), now=now,
                )
            counts[f"v25_{state}"] = counts.get(f"v25_{state}", 0) + 1
        except Exception as exc:  # noqa: BLE001 - una partita non blocca il registro
            logger.exception("live registry V2.5 fallita today_fixture_id=%s", row.id)
            errors.append(f"{row.id}: {exc!s}"[:200])
    db.commit()
    return {"scan_date": scan_date.isoformat(), "fixtures": len(rows), "counts": counts, "errors": errors[:20]}


def _final_score(row: CecchinoTodayFixture) -> SimpleNamespace | None:
    if (row.fixture_status or "") not in FINISHED_STATUSES:
        return None
    home = row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home
    away = row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away
    if home is None or away is None:
        return None
    return SimpleNamespace(
        ft_home_goals=home,
        ft_away_goals=away,
        ht_home_goals=row.score_halftime_home,
        ht_away_goals=row.score_halftime_away,
    )


def settle_predictions(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    open_rows = db.scalars(
        select(CecchinoLivePrediction).where(
            CecchinoLivePrediction.status == LIVE_STATUS_OPEN,
            CecchinoLivePrediction.kickoff < now,
        )
    ).all()
    settled = 0
    for pred in open_rows:
        row = db.get(CecchinoTodayFixture, int(pred.today_fixture_id))
        score = _final_score(row) if row is not None else None
        if score is None:
            continue
        result = match_result_from_lab_match(score)
        markets: dict[str, Any] = {}
        for key, m in (pred.markets_json or {}).items():
            outcome = evaluate_market_outcome_v2(key, result)
            won = outcome.get("won")
            markets[key] = {"won": won, "profit": flat_stake_profit(won=won, quota=m.get("quota_book"))}
        pred.result_json = {
            "score": {
                "ft_home": score.ft_home_goals, "ft_away": score.ft_away_goals,
                "ht_home": score.ht_home_goals, "ht_away": score.ht_away_goals,
            },
            "markets": markets,
        }
        pred.status = LIVE_STATUS_SETTLED
        pred.settled_at = now
        settled += 1
    db.commit()
    return {"open_checked": len(open_rows), "settled": settled}
