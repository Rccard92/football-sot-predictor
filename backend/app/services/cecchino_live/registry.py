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
from datetime import date, datetime, timedelta, timezone
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
MODEL_V3 = "V3"
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
    goals = pre.get("goals")
    modules = {
        "balance_classes": pre["balance"].get("pillar_classes"),
        "goal_intensity_classes": {k: v.get("class_key") for k, v in (gi.get("pillars") or {}).items()},
        "goal_intensity_final": (gi.get("final_class") or {}).get("key"),
        # dettaglio per le schede (indice 0-100, valore grezzo, lato) — solo lettura
        "balance_pillars": {
            k: {f: v.get(f) for f in ("title", "index", "raw_value", "class_key", "class_label", "direction")}
            for k, v in (pre["balance"].get("pillars") or {}).items()
        },
        "goal_intensity_pillars": {
            k: {f: v.get(f) for f in ("title", "score", "raw_value", "class_key", "label")}
            for k, v in (gi.get("pillars") or {}).items()
        },
        "goal_intensity_final_detail": gi.get("final_class"),
        "expected_goals": (
            {"home": _round(goals.lambda_home, 3), "away": _round(goals.lambda_away, 3)}
            if goals is not None and getattr(goals, "lambda_home", None) is not None
            else None
        ),
        "eligibility": pre["eligibility"].get("status"),
        "history_matches": pre.get("history_matches"),
        "league_reference": pre.get("league_reference"),
    }
    return markets, modules


def v2_live_modules(
    db: Session, fixture: Fixture, row: CecchinoTodayFixture, markets: dict[str, Any]
) -> dict[str, Any]:
    """Moduli V2 ricalcolati come nella RUN V2 + Pattern Master V2 accesi."""
    from app.services.cecchino_live.v2_live import compute_v2_live, v2_modules, v2_pattern_signals

    pre = compute_v2_live(db, fixture, row.kpi_panel_json)
    modules = v2_modules(pre)
    modules["patterns"] = v2_pattern_signals(db, fixture, markets, modules)
    return modules


def v3_payload(result: dict[str, Any], kpi_panel: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mercati (probabilita' V3 contro quote reali Bet365 del pannello KPI) e dettaglio del modello."""
    from app.services.cecchino_live.v25_live import strict_quotes_from_kpi
    from app.services.cecchino_v25.kpi import build_kpi_panel_v25

    panel = build_kpi_panel_v25(probabilities=result["probabilities"], strict_by_market=strict_quotes_from_kpi(kpi_panel))
    markets = {
        r["market_key"]: {
            "probability": r.get("prob_cecchino"),
            "quota_cecchino": r.get("quota_cecchino"),
            "quota_book": r.get("quota_book"),
            "prob_book_fair": r.get("prob_book_fair"),
            "rating": r.get("rating"),
            "vantaggio_prob": r.get("vantaggio_prob"),
            "edge_pct": r.get("edge_pct"),
            "buyability_score": None,
            "buyability_class": None,
            "signal_active": False,
        }
        for r in panel["rows"]
    }
    modules = {
        "engine_label": "V3 estesa",
        "expected_goals": {"home": result.get("lambda_home"), "away": result.get("lambda_away")},
        "rho": result.get("rho"),
        "ht_share": result.get("ht_share"),
        "phase": result.get("phase"),
        "played": {"home": result.get("played_home"), "away": result.get("played_away")},
        "evidence": {"home": result.get("home_evidence"), "away": result.get("away_evidence")},
        "specialists": result.get("specialists"),
        "indices": result.get("indices"),
        "history": result.get("history"),
        "params": result.get("params"),
        "eligibility": "ok" if result.get("eligible") else "early_season",
    }
    return markets, modules


def v25_pattern_signals(
    db: Session, fixture: Fixture, markets: dict[str, Any], modules: dict[str, Any]
) -> dict[str, Any]:
    """Pattern Master V2.5 accesi sulla partita (statistiche extra dove disponibili)."""
    from app.services.cecchino_live.live_extra_stats import delta_classes, live_extra_features
    from app.services.cecchino_live.pattern_signals import evaluate_patterns, load_winners, v25_features

    build_id, patterns, discovery_run = load_winners(db, MODEL_V25)
    if build_id is None or discovery_run is None:
        return {"status": "master_pattern_missing"}
    extra = live_extra_features(db, fixture)
    delta = delta_classes(extra, discovery_run_id=discovery_run)
    result = evaluate_patterns(patterns, features=v25_features(modules, delta), markets=markets)
    return {
        "status": "ok",
        "master_build_id": build_id,
        "extra_stats": {
            "prior_matches": extra.get("prior_matches"),
            "prior_matches_with_stats": extra.get("prior_matches_with_stats"),
            "delta_classes_available": sum(1 for v in delta.values() if v is not None),
        },
        **result,
    }


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
        fixture = db.get(Fixture, int(row.local_fixture_id))
        v2_mods: dict[str, Any] | None = None
        markets_v2 = v2_markets(row)
        if fixture is not None:
            try:
                with db.begin_nested():
                    v2_mods = v2_live_modules(db, fixture, row, markets_v2)
            except Exception as exc:  # noqa: BLE001 - i pattern V2 non bloccano la previsione V2
                logger.exception("live registry moduli V2 falliti today_fixture_id=%s", row.id)
                errors.append(f"{row.id} V2 moduli: {exc!s}"[:200])
                v2_mods = None
        if v2_mods is not None:
            for key in v2_mods.get("signal_markets") or []:
                if key in markets_v2:
                    markets_v2[key]["signal_active"] = True
        state = _upsert(
            db, row, model=MODEL_V2, engine_version=V2_ENGINE_VERSION,
            markets=markets_v2, modules=v2_mods, eligible=True, now=now,
        )
        counts[f"v2_{state}"] = counts.get(f"v2_{state}", 0) + 1
        if fixture is None:
            continue
        try:
            with db.begin_nested():
                pre = compute_v25_live(db, fixture, row.kpi_panel_json)
                markets, modules = v25_payload(pre)
                modules["patterns"] = v25_pattern_signals(db, fixture, markets, modules)
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
    _record_v3(db, rows, now=now, counts=counts, errors=errors)
    db.commit()
    return {"scan_date": scan_date.isoformat(), "fixtures": len(rows), "counts": counts, "errors": errors[:20]}


def _record_v3(
    db: Session, rows: list[CecchinoTodayFixture], *, now: datetime, counts: dict[str, int], errors: list[str]
) -> None:
    """V3 estesa sulle partite non iniziate dei campionati con statistiche (un campionato alla volta)."""
    from app.services.cecchino_v3_live.engine import compute_for_fixtures
    from app.services.cecchino_v3_live.params import ENGINE_VERSION as V3_ENGINE_VERSION
    from app.services.cecchino_v3_live.patterns import v3_pattern_signals

    upcoming = [r for r in rows if (_aware(r.kickoff) or now) > now and r.local_fixture_id]
    fixtures = [f for f in (db.get(Fixture, int(r.local_fixture_id)) for r in upcoming) if f is not None]
    if not fixtures:
        return
    try:
        results = compute_for_fixtures(db, fixtures)
    except Exception as exc:  # noqa: BLE001
        logger.exception("live registry V3 fallita")
        errors.append(f"V3: {exc!s}"[:200])
        return
    for row in upcoming:
        res = results.get(int(row.local_fixture_id)) or {}
        status = str(res.get("status") or "missing")
        if status != "ok":
            counts[f"v3_{status}"] = counts.get(f"v3_{status}", 0) + 1
            continue
        try:
            with db.begin_nested():
                markets, modules = v3_payload(res, row.kpi_panel_json)
                modules["patterns"] = v3_pattern_signals(db, res, markets)
                state = _upsert(
                    db, row, model=MODEL_V3, engine_version=V3_ENGINE_VERSION,
                    markets=markets, modules=modules, eligible=bool(res.get("eligible")), now=now,
                )
            counts[f"v3_{state}"] = counts.get(f"v3_{state}", 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("live registry V3 fallita today_fixture_id=%s", row.id)
            errors.append(f"{row.id} V3: {exc!s}"[:200])


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


def _score_from_fixture(fixture: Fixture | None) -> SimpleNamespace | None:
    """Risultato dalla fixture locale (aggiornata dal collegamento dati notturno)."""
    if fixture is None or (fixture.status or "") not in FINISHED_STATUSES:
        return None
    if fixture.goals_home is None or fixture.goals_away is None:
        return None
    ht = (((fixture.raw_json or {}).get("score") or {}).get("halftime")) or {}
    return SimpleNamespace(
        ft_home_goals=fixture.goals_home,
        ft_away_goals=fixture.goals_away,
        ht_home_goals=ht.get("home"),
        ht_away_goals=ht.get("away"),
    )


_STAT_FIELDS = {
    "shots": ("total_shots", "shots"),
    "sot": ("shots_on_target",),
    "corners": ("corner_kicks",),
    "yellow_cards": ("yellow_cards",),
}


def _actual_stats(db: Session, fixture: Fixture | None) -> dict[str, float] | None:
    """Statistiche reali della partita (stesse chiavi dei bersagli senza quota), se disponibili."""
    if fixture is None:
        return None
    from app.models.fixture_team_stat import FixtureTeamStat

    rows = {int(s.team_id): s for s in db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == fixture.id)).all()}
    home, away = rows.get(int(fixture.home_team_id)), rows.get(int(fixture.away_team_id))
    if home is None or away is None:
        return None
    out: dict[str, float] = {}
    for name, columns in _STAT_FIELDS.items():
        h = next((getattr(home, c) for c in columns if getattr(home, c, None) is not None), None)
        a = next((getattr(away, c) for c in columns if getattr(away, c, None) is not None), None)
        if h is None or a is None:
            continue
        out[f"home_{name}"] = float(h)
        out[f"away_{name}"] = float(a)
        out[f"total_{name}"] = float(h) + float(a)
    return out or None


def _synthetic_pattern_outcomes(pred: CecchinoLivePrediction, actuals: dict[str, float] | None) -> dict[str, Any]:
    """Esito dei pattern senza quota accesi: valore reale sopra/sotto la soglia nella direzione del pattern."""
    out: dict[str, Any] = {}
    active = (((pred.modules_json or {}).get("patterns") or {}).get("active")) or []
    for p in active:
        if p.get("target_type") != "synthetic":
            continue
        value = (actuals or {}).get(str(p.get("target_key")))
        if value is None or p.get("threshold") is None:
            out[str(p["id"])] = {"won": None, "actual": None}
            continue
        over = value > float(p["threshold"])
        out[str(p["id"])] = {"won": over if int(p.get("direction") or 1) >= 0 else not over, "actual": value}
    return out


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
        fixture = db.get(Fixture, int(pred.local_fixture_id)) if pred.local_fixture_id else None
        score = (_final_score(row) if row is not None else None) or _score_from_fixture(fixture)
        if score is None:
            continue
        result = match_result_from_lab_match(score)
        markets: dict[str, Any] = {}
        for key, m in (pred.markets_json or {}).items():
            outcome = evaluate_market_outcome_v2(key, result)
            won = outcome.get("won")
            markets[key] = {"won": won, "profit": flat_stake_profit(won=won, quota=m.get("quota_book"))}
        actuals = _actual_stats(db, fixture)
        pred.result_json = {
            "score": {
                "ft_home": score.ft_home_goals, "ft_away": score.ft_away_goals,
                "ht_home": score.ht_home_goals, "ht_away": score.ht_away_goals,
            },
            "markets": markets,
            "stats": actuals,
            "patterns": _synthetic_pattern_outcomes(pred, actuals),
        }
        pred.status = LIVE_STATUS_SETTLED
        pred.settled_at = now
        settled += 1

    # statistiche arrivate dopo la chiusura (es. risultati aggiornati a mano prima della notte)
    late = 0
    recent = db.scalars(
        select(CecchinoLivePrediction).where(
            CecchinoLivePrediction.status == LIVE_STATUS_SETTLED,
            CecchinoLivePrediction.kickoff > now - timedelta(days=4),
        )
    ).all()
    for pred in recent:
        result = dict(pred.result_json or {})
        if result.get("stats") is not None or not pred.local_fixture_id:
            continue
        actuals = _actual_stats(db, db.get(Fixture, int(pred.local_fixture_id)))
        if actuals is None:
            continue
        result["stats"] = actuals
        result["patterns"] = _synthetic_pattern_outcomes(pred, actuals)
        pred.result_json = result
        late += 1
    db.commit()
    return {"open_checked": len(open_rows), "settled": settled, "stats_completed_later": late}
