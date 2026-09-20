"""Letture per le rotte V4 (docs/v4/API.md). Solo database e file degli esami: nessun calcolo pesante."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cecchino_v4 import (
    CecchinoV4Challenger,
    CecchinoV4Exam,
    CecchinoV4Explanation,
    CecchinoV4Fixture,
    CecchinoV4Job,
    CecchinoV4OddsSnapshot,
    CecchinoV4Shortlist,
    CecchinoV4ShortlistItem,
)
from app.services.cecchino_v4.constants import LEAGUES, VERDICT_LABELS
from app.services.cecchino_v4.measure.metrics import summary as measure_summary_fn
from app.services.cecchino_v4.pipeline.day import FINISHED_STATUSES, default_days, kickoff_iso
from app.services.cecchino_v4.selection.labels import market_family
from app.services.cecchino_v4.selection.shortlist import shortlist_payload

DOCS_V4 = Path(__file__).resolve().parents[4] / "docs" / "v4"
EXAMS_DIR = DOCS_V4 / "esami"

EXAM_TITLES = {
    "E1": "Motore gol V4 contro V3 Fase 4",
    "E2": "Motore statistiche: precisione e informazione oltre il mercato",
    "E4": "Selezione sui mercati classici con quote di chiusura",
    "G3": "Pipeline live: copertura dati",
    "G6": "Paper trading prospettico (CLV)",
}


class NotFound(Exception):
    pass


def _explanations(db: Session, fixture_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not fixture_ids:
        return {}
    rows = db.execute(select(CecchinoV4Explanation).where(CecchinoV4Explanation.fixture_id.in_(fixture_ids))).scalars()
    return {r.fixture_id: r.payload_json for r in rows}


def _card_fallback(f: CecchinoV4Fixture) -> dict[str, Any]:
    """Scheda minima quando il calcolo del giorno non e' ancora passato."""
    return {
        "id": f.id,
        "api_fixture_id": f.api_fixture_id,
        "league_code": f.league_code,
        "competition": f.competition,
        "season_label": f.season_label,
        "kickoff_at": kickoff_iso(f.kickoff_at),
        "home_team": f.home_team,
        "away_team": f.away_team,
        "status": f.status,
        "most_likely": None,
        "expected_goals": None,
        "uncertainty": None,
        "lineups_status": f.lineups_status,
        "best_play": None,
        "no_play_reason": "in_attesa_calcolo",
        "result": (
            {"ft_home": f.ft_home, "ft_away": f.ft_away, "ht_home": f.ht_home, "ht_away": f.ht_away}
            if f.ft_home is not None
            else None
        ),
    }


def _card(f: CecchinoV4Fixture, expl: dict[str, Any] | None) -> dict[str, Any]:
    card = dict((expl or {}).get("card") or _card_fallback(f))
    # stato e risultato sempre aggiornati dalla tabella partite
    card["status"] = f.status
    card["lineups_status"] = f.lineups_status
    if f.ft_home is not None:
        card["result"] = {"ft_home": f.ft_home, "ft_away": f.ft_away, "ht_home": f.ht_home, "ht_away": f.ht_away}
    return card


def days(db: Session, start: date | None = None, n: int = 7) -> dict[str, Any]:
    start = start or default_days()[0]
    wanted = [start + timedelta(days=i) for i in range(max(1, min(n, 14)))]
    fixtures = list(db.execute(select(CecchinoV4Fixture).where(CecchinoV4Fixture.match_date.in_(wanted))).scalars())
    expl = _explanations(db, [f.id for f in fixtures])
    out = []
    for d in wanted:
        todays = [f for f in fixtures if f.match_date == d]
        plays = sum(1 for f in todays if ((expl.get(f.id) or {}).get("card") or {}).get("best_play"))
        out.append(
            {
                "date": d.isoformat(),
                "fixtures": len(todays),
                "plays": plays,
                "finished": sum(1 for f in todays if f.status in FINISHED_STATUSES),
            }
        )
    return {"days": out}


def fixtures(
    db: Session,
    day: date,
    *,
    league: str | None = None,
    only_plays: bool = False,
    only_lineups: bool = False,
    sort: str = "kickoff",
) -> dict[str, Any]:
    q = select(CecchinoV4Fixture).where(CecchinoV4Fixture.match_date == day)
    if league:
        q = q.where(CecchinoV4Fixture.league_code == league)
    rows = list(db.execute(q.order_by(CecchinoV4Fixture.kickoff_at)).scalars())
    expl = _explanations(db, [f.id for f in rows])
    cards = [_card(f, expl.get(f.id)) for f in rows]
    abstentions: Counter[str] = Counter()
    for c in cards:
        if not c.get("best_play") and c.get("no_play_reason"):
            abstentions[c["no_play_reason"]] += 1
    if only_plays:
        cards = [c for c in cards if c.get("best_play")]
    if only_lineups:
        cards = [c for c in cards if c.get("lineups_status") == "ufficiali"]
    if sort == "profit":
        cards.sort(key=lambda c: -float(((c.get("best_play") or {}).get("expected_profit") or -9)))
    return {
        "date": day.isoformat(),
        "items": cards,
        "abstentions": dict(abstentions),
        "abstention_labels": {k: VERDICT_LABELS.get(k, k) for k in abstentions},
    }


def fixture_detail(db: Session, fixture_id: int) -> dict[str, Any]:
    f = db.get(CecchinoV4Fixture, fixture_id)
    if f is None:
        raise NotFound(f"partita {fixture_id} non trovata")
    expl = _explanations(db, [f.id]).get(f.id)
    return {
        "fixture": _card(f, expl),
        "blocks": (expl or {}).get("blocks"),
        "rows": (expl or {}).get("rows") or [],
        "computed_at": (expl or {}).get("computed_at"),
    }


def shortlist(db: Session, day: date) -> dict[str, Any]:
    payload = shortlist_payload(db, day)
    if payload is None:
        return {"date": day.isoformat(), "status": None, "sealed_at": None, "digest": None, "items": [], "abstentions": [], "advised": True, "banner": None}
    return payload


def _settled_items(db: Session, start: date | None, end: date | None) -> list[dict[str, Any]]:
    q = (
        select(CecchinoV4ShortlistItem, CecchinoV4Shortlist.day, CecchinoV4Fixture.league_code, CecchinoV4Fixture.kickoff_at)
        .join(CecchinoV4Shortlist, CecchinoV4Shortlist.id == CecchinoV4ShortlistItem.shortlist_id)
        .join(CecchinoV4Fixture, CecchinoV4Fixture.id == CecchinoV4ShortlistItem.fixture_id)
        .where(CecchinoV4ShortlistItem.status != "provvisoria")
    )
    if start:
        q = q.where(CecchinoV4Shortlist.day >= start)
    if end:
        q = q.where(CecchinoV4Shortlist.day <= end)
    out = []
    for item, day, league_code, kickoff_at in db.execute(q).all():
        out.append(
            {
                "fixture_id": item.fixture_id,
                "day": day,
                "match_date": day,
                "kickoff_at": kickoff_iso(kickoff_at),
                "league_code": league_code,
                "market_key": item.market_key,
                "market_family": market_family(item.market_key),
                "quota_used": item.quota,
                "closing_quota": item.closing_quota,
                "clv": item.clv,
                "profit_units": item.profit_units,
                "result": item.result,
                "status": item.status,
            }
        )
    return out


def measure_summary(db: Session, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    items = _settled_items(db, start, end)
    out = measure_summary_fn(items)
    out["from"] = start.isoformat() if start else None
    out["to"] = end.isoformat() if end else None
    return out


def _json_safe(value: Any) -> Any:
    """NaN e infiniti (numpy negli esami) non sono JSON: diventano null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _exam_from_file(code: str) -> dict[str, Any] | None:
    path = EXAMS_DIR / f"{code}.json"
    if not path.exists():
        return None
    try:
        data = _json_safe(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
    passed = data.get("passed")
    if not isinstance(passed, bool):
        verdict = data.get("verdict") or data.get("verdetto")
        passed = verdict.lower() in {"superato", "passed"} if isinstance(verdict, str) else None
    prereg = data.get("preregistration") or f"docs/v4/PREREGISTRAZIONE_FASE_{code[1] if len(code) > 1 and code[1].isdigit() else 'N'}.md"
    return {
        "code": code,
        "title": data.get("title") or EXAM_TITLES.get(code, code),
        "passed": passed,
        "preregistration": prereg,
        "result": data,
        "computed_at": data.get("computed_at") or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "source": "file",
    }


def exams(db: Session | None = None) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    for code in ("E1", "E2", "E4", "G3", "G6"):
        e = _exam_from_file(code)
        if e:
            items[code] = e
    if db is not None:
        for row in db.execute(select(CecchinoV4Exam).order_by(CecchinoV4Exam.computed_at)).scalars():
            items[row.code] = {
                "code": row.code,
                "title": row.title,
                "passed": row.passed,
                "preregistration": row.preregistration_path,
                "result": row.result_json,
                "computed_at": row.computed_at.isoformat() if row.computed_at else None,
                "source": "db",
            }
    for code, title in EXAM_TITLES.items():
        items.setdefault(
            code,
            {"code": code, "title": title, "passed": None, "preregistration": None, "result": {}, "computed_at": None, "source": "attesa"},
        )
    order = list(EXAM_TITLES)
    return {"items": sorted(items.values(), key=lambda e: order.index(e["code"]) if e["code"] in order else 99)}


def challengers(db: Session) -> dict[str, Any]:
    rows = db.execute(select(CecchinoV4Challenger).order_by(CecchinoV4Challenger.created_at)).scalars()
    return {
        "items": [
            {"name": r.name, "description": r.description, "status": r.status, "exam": r.exam_json, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
            for r in rows
        ]
    }


def _try_live_helpers(db: Session) -> dict[str, Any]:
    """Copertura, qualita' dati e budget dalla pipeline live, se disponibile."""
    out: dict[str, Any] = {"coverage": [], "quality": [], "api_budget": None, "odds_registry": None}
    try:
        from app.services.cecchino_v4.live import jobs as live_jobs  # type: ignore
    except Exception:  # noqa: BLE001
        live_jobs = None
    if live_jobs is not None:
        for name, key in (("data_quality", "quality"), ("api_budget_today", "api_budget"), ("odds_registry_status", "odds_registry")):
            fn = getattr(live_jobs, name, None)
            if fn is None:
                continue
            try:
                out[key] = fn(db)
            except Exception:  # noqa: BLE001
                pass
        cov = getattr(live_jobs, "latest_coverage", None)
        if cov is not None:
            try:
                out["coverage"] = cov(db) or []
            except Exception:  # noqa: BLE001
                pass
    if not out["coverage"]:
        job = db.execute(
            select(CecchinoV4Job).where(CecchinoV4Job.name == "coverage_scan", CecchinoV4Job.status == "done").order_by(CecchinoV4Job.created_at.desc())
        ).scalars().first()
        if job and job.result_json:
            out["coverage"] = job.result_json.get("coverage") or []
    if out["odds_registry"] is None:
        today = default_days()[0]
        start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        n = db.scalar(select(func.count(CecchinoV4OddsSnapshot.id)).where(CecchinoV4OddsSnapshot.taken_at >= start)) or 0
        last = db.scalar(select(func.max(CecchinoV4OddsSnapshot.taken_at)))
        out["odds_registry"] = {"snapshots_today": int(n), "last_taken_at": last.isoformat() if last else None}
    if out["api_budget"] is None:
        out["api_budget"] = {"date": default_days()[0].isoformat(), "calls": None, "stop_at": 7000}
    if not out["quality"]:
        since = default_days()[0] - timedelta(days=14)
        rows = db.execute(select(CecchinoV4Fixture).where(CecchinoV4Fixture.match_date >= since)).scalars()
        per: dict[str, dict[str, int]] = {}
        for f in rows:
            p = per.setdefault(f.league_code, {"fixtures": 0, "no_stats": 0, "no_lineups": 0})
            p["fixtures"] += 1
            if f.status in FINISHED_STATUSES and not f.stats_json:
                p["no_stats"] += 1
            if f.status in FINISHED_STATUSES and f.lineups_status != "ufficiali":
                p["no_lineups"] += 1
        out["quality"] = [
            {
                "league_code": code,
                "fixtures": p["fixtures"],
                "missing_stats_pct": round(100.0 * p["no_stats"] / p["fixtures"], 1) if p["fixtures"] else 0.0,
                "missing_lineups_pct": round(100.0 * p["no_lineups"] / p["fixtures"], 1) if p["fixtures"] else 0.0,
                "missing_odds_pct": None,
            }
            for code, p in sorted(per.items())
        ]
    return out


def engine_data(db: Session) -> dict[str, Any]:
    data = _try_live_helpers(db)
    data["leagues"] = [{"code": lg.code, "competition": lg.competition, "tier": lg.tier} for lg in LEAGUES]
    return data


def jobs(db: Session, limit: int = 30) -> dict[str, Any]:
    rows = db.execute(select(CecchinoV4Job).order_by(CecchinoV4Job.created_at.desc()).limit(limit)).scalars()
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "progress_pct": r.progress_pct,
                "step": r.step,
                "api_calls": r.api_calls,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "result": r.result_json,
            }
            for r in rows
        ]
    }
