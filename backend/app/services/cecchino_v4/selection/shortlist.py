"""Shortlist del giorno V4: costruzione (pura), impronta sigillata, persistenza (SQLAlchemy).

Regole (docs/v4/PREREGISTRAZIONE_FASE_4.md): una giocata per partita, ordinamento per profitto atteso,
massimo `MAX_PLAYS_PER_DAY`, le prime `TOP_PLAYS` marcate `top`. Stati: provvisoria -> confermata (sigillo)
-> regolata; una voce può essere ritirata con motivo.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_v4 import CecchinoV4Shortlist, CecchinoV4ShortlistItem
from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    MAX_PLAYS_PER_DAY,
    PLAYS_PER_MATCH,
    SHORTLIST_CONFIRMED,
    SHORTLIST_PROVISIONAL,
    SHORTLIST_SETTLED,
    SHORTLIST_WITHDRAWN,
    TOP_PLAYS,
    VERDICT_LABELS,
    VERDICT_PLAYABLE,
)
from app.services.cecchino_v4.measure.metrics import clv as clv_value
from app.services.cecchino_v4.selection.rules import MarketRow
from app.services.cecchino_v4.selection.settlement import profit_units

E4_FAILED_BANNER = "Esame E4 non superato: giocate classiche in osservazione, non consigliate"


@dataclass
class ShortlistItem:
    fixture_id: int
    home_team: str
    away_team: str
    kickoff_at: str | None
    league_code: str | None
    rank: int
    top: bool
    status: str
    row: MarketRow
    withdraw_reason: str | None = None
    result: str | None = None
    clv: float | None = None
    profit_units: float | None = None
    closing_quota: float | None = None
    reason: dict[str, Any] | None = None  # frasi del perché (blocco 5), se già calcolate

    def to_dict(self) -> dict[str, Any]:
        data = self.row.to_dict()
        data.update(
            {
                "fixture_id": self.fixture_id,
                "home_team": self.home_team,
                "away_team": self.away_team,
                "kickoff_at": self.kickoff_at,
                "league_code": self.league_code,
                "rank": self.rank,
                "top": self.top,
                "status": self.status,
                "withdraw_reason": self.withdraw_reason,
                "result": self.result,
                "clv": self.clv,
                "profit_units": self.profit_units,
                "closing_quota": self.closing_quota,
            }
        )
        return data


@dataclass
class Shortlist:
    day: date
    status: str
    items: list[ShortlistItem]
    sealed_at: datetime | None = None
    digest: str | None = None
    advised: bool = True
    banner: str | None = None
    abstentions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day.isoformat(),
            "status": self.status,
            "sealed_at": None if self.sealed_at is None else self.sealed_at.isoformat(),
            "digest": self.digest,
            "advised": self.advised,
            "banner": self.banner,
            "items": [i.to_dict() for i in self.items],
            "abstentions": list(self.abstentions),
        }


def _sort_key(pair: tuple[dict[str, Any], MarketRow]) -> tuple[float, float, int]:
    meta, row = pair
    return (-(row.expected_profit or 0.0), -row.p_prudent, int(meta.get("fixture_id") or 0))


def build_shortlist(
    day: date,
    candidates: Iterable[tuple[dict[str, Any], MarketRow]],
    advised: bool = True,
    abstentions: list[dict[str, Any]] | None = None,
) -> Shortlist:
    """Lista del giorno dalle coppie (meta partita, riga). Prende solo le righe `giocabile`, una per partita
    (la migliore per profitto atteso), ordina per profitto atteso, taglia a `MAX_PLAYS_PER_DAY`, marca `top`.

    `meta` deve avere `fixture_id`, `home_team`, `away_team`; opzionali `kickoff_at`, `league_code`, `reason`.
    `advised=False` (esame E4 non superato) marca ogni voce `advised=False` e aggiunge il banner.
    """
    best_by_fixture: dict[int, tuple[dict[str, Any], MarketRow]] = {}
    for meta, row in candidates:
        if row.verdict != VERDICT_PLAYABLE or row.expected_profit is None:
            continue
        fixture_id = int(meta["fixture_id"])
        current = best_by_fixture.get(fixture_id)
        if current is None or _sort_key((meta, row)) < _sort_key(current):
            best_by_fixture[fixture_id] = (meta, row)

    ordered = sorted(best_by_fixture.values(), key=_sort_key)[: MAX_PLAYS_PER_DAY * PLAYS_PER_MATCH]
    items: list[ShortlistItem] = []
    for rank, (meta, row) in enumerate(ordered, start=1):
        row.advised = bool(advised) and row.advised
        kickoff = meta.get("kickoff_at")
        items.append(
            ShortlistItem(
                fixture_id=int(meta["fixture_id"]),
                home_team=str(meta.get("home_team") or ""),
                away_team=str(meta.get("away_team") or ""),
                kickoff_at=kickoff.isoformat() if isinstance(kickoff, datetime) else kickoff,
                league_code=meta.get("league_code"),
                rank=rank,
                top=rank <= TOP_PLAYS,
                status=SHORTLIST_PROVISIONAL,
                row=row,
                reason=meta.get("reason"),
            )
        )
    return Shortlist(
        day=day,
        status=SHORTLIST_PROVISIONAL,
        items=items,
        advised=bool(advised),
        banner=None if advised else E4_FAILED_BANNER,
        abstentions=list(abstentions or []),
    )


def seal_digest(items: Iterable[Any], sealed_at: datetime) -> str:
    """Impronta sha256 del contenuto sigillato: id partita, chiave, quota, probabilità e orario, in JSON canonico."""
    payload = []
    for item in items:
        if isinstance(item, ShortlistItem):
            fixture_id, key, quota, p, p_prudent = item.fixture_id, item.row.market_key, item.row.quota_used, item.row.p, item.row.p_prudent
        elif isinstance(item, CecchinoV4ShortlistItem):
            fixture_id, key, quota, p, p_prudent = item.fixture_id, item.market_key, item.quota, item.probability, item.prob_prudent
        else:
            fixture_id, key, quota, p, p_prudent = (
                item["fixture_id"],
                item["market_key"],
                item.get("quota_used", item.get("quota")),
                item["p"],
                item["p_prudent"],
            )
        payload.append(
            {
                "fixture_id": int(fixture_id),
                "market_key": str(key),
                "quota": None if quota is None else round(float(quota), 3),
                "p": round(float(p), 4),
                "p_prudent": round(float(p_prudent), 4),
            }
        )
    payload.sort(key=lambda d: (d["fixture_id"], d["market_key"]))
    canonical = json.dumps({"items": payload, "sealed_at": sealed_at.isoformat()}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def abstention_summary(fixtures_without_play: Iterable[dict[str, Any]], max_examples: int = 3) -> list[dict[str, Any]]:
    """Partite analizzate senza giocata raggruppate per motivo: [{"reason","label","count","examples"}], per conteggio.
    Ogni elemento: `{"home_team","away_team","no_play_reason"}`."""
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for fx in fixtures_without_play:
        reason = fx.get("no_play_reason") or "nessun_mercato"
        counts[reason] += 1
        if len(examples[reason]) < max_examples:
            examples[reason].append(f"{fx.get('home_team', '?')} - {fx.get('away_team', '?')}")
    return [
        {"reason": reason, "label": VERDICT_LABELS.get(reason, "Nessun mercato calcolato"), "count": count, "examples": examples[reason]}
        for reason, count in counts.most_common()
    ]


# --- Persistenza -------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_shortlist(db: Session, day: date) -> CecchinoV4Shortlist | None:
    return db.execute(select(CecchinoV4Shortlist).where(CecchinoV4Shortlist.day == day)).scalar_one_or_none()


def list_items(db: Session, shortlist_id: int) -> list[CecchinoV4ShortlistItem]:
    return list(
        db.execute(
            select(CecchinoV4ShortlistItem)
            .where(CecchinoV4ShortlistItem.shortlist_id == shortlist_id)
            .order_by(CecchinoV4ShortlistItem.rank)
        ).scalars()
    )


def save_provisional(db: Session, shortlist: Shortlist, now: datetime | None = None) -> CecchinoV4Shortlist:
    """Crea o sostituisce la lista provvisoria del giorno. Una lista già sigillata non si tocca (ValueError)."""
    now = now or _now()
    record = get_shortlist(db, shortlist.day)
    if record is None:
        record = CecchinoV4Shortlist(day=shortlist.day, status=SHORTLIST_PROVISIONAL, created_at=now, updated_at=now)
        db.add(record)
        db.flush()
    elif record.status != SHORTLIST_PROVISIONAL:
        raise ValueError(f"shortlist del {shortlist.day.isoformat()} già {record.status}: non si sostituisce")
    else:
        for old in list_items(db, record.id):
            db.delete(old)
        db.flush()

    for item in shortlist.items:
        row = item.row
        db.add(
            CecchinoV4ShortlistItem(
                shortlist_id=record.id,
                fixture_id=item.fixture_id,
                market_key=row.market_key,
                label=row.label,
                probability=row.p,
                prob_low=row.lo if row.lo is not None else row.p,
                prob_high=row.hi if row.hi is not None else row.p,
                prob_prudent=row.p_prudent,
                quota=float(row.quota_used or 0.0),
                bookmaker_id=row.bookmaker_id or BOOKMAKER_BET365_ID,
                expected_profit=float(row.expected_profit or 0.0),
                rank=item.rank,
                status=SHORTLIST_PROVISIONAL,
                reason_json=item.reason,
                created_at=now,
            )
        )
    record.status = SHORTLIST_PROVISIONAL
    record.sealed_at = None
    record.digest = None
    record.summary_json = {
        "advised": shortlist.advised,
        "banner": shortlist.banner,
        "plays": len(shortlist.items),
        "top": min(TOP_PLAYS, len(shortlist.items)),
        "abstentions": shortlist.abstentions,
        "meta": {
            str(i.fixture_id): {"home_team": i.home_team, "away_team": i.away_team, "kickoff_at": i.kickoff_at, "league_code": i.league_code}
            for i in shortlist.items
        },
    }
    record.updated_at = now
    db.commit()
    return record


def seal_shortlist(db: Session, day: date, sealed_at: datetime | None = None) -> CecchinoV4Shortlist:
    """Sigilla la lista del giorno: impronta, stato confermata sulla lista e sulle voci non ritirate."""
    record = get_shortlist(db, day)
    if record is None:
        raise ValueError(f"nessuna shortlist per il {day.isoformat()}")
    if record.status != SHORTLIST_PROVISIONAL:
        raise ValueError(f"shortlist del {day.isoformat()} già {record.status}")
    sealed_at = sealed_at or _now()
    items = list_items(db, record.id)
    for item in items:
        if item.status == SHORTLIST_PROVISIONAL:
            item.status = SHORTLIST_CONFIRMED
    record.digest = seal_digest([i for i in items if i.status != SHORTLIST_WITHDRAWN], sealed_at)
    record.sealed_at = sealed_at
    record.status = SHORTLIST_CONFIRMED
    record.updated_at = sealed_at
    db.commit()
    return record


def withdraw_item(db: Session, item_id: int, reason: str, now: datetime | None = None) -> CecchinoV4ShortlistItem:
    """Ritira una voce (es. alle formazioni ufficiali) con motivo. Una voce regolata non si ritira."""
    item = db.get(CecchinoV4ShortlistItem, item_id)
    if item is None:
        raise ValueError(f"voce {item_id} inesistente")
    if item.status == SHORTLIST_SETTLED:
        raise ValueError(f"voce {item_id} già regolata")
    item.status = SHORTLIST_WITHDRAWN
    item.withdraw_reason = str(reason)[:160]
    parent = db.get(CecchinoV4Shortlist, item.shortlist_id)
    if parent is not None:
        parent.updated_at = now or _now()
    db.commit()
    return item


def settle_item(
    db: Session,
    item_id: int,
    outcome: str | None,
    closing_quota: float | None = None,
    now: datetime | None = None,
) -> CecchinoV4ShortlistItem:
    """Regola una voce con l'esito di `settlement.settle`; calcola profitto e CLV; se tutte le voci della lista
    sono regolate o ritirate, la lista passa a `regolata`. Voci ritirate: solo la quota di chiusura (CLV)."""
    item = db.get(CecchinoV4ShortlistItem, item_id)
    if item is None:
        raise ValueError(f"voce {item_id} inesistente")
    now = now or _now()
    if closing_quota is not None:
        item.closing_quota = float(closing_quota)
        item.clv = clv_value(item.quota, float(closing_quota))
    if item.status != SHORTLIST_WITHDRAWN and outcome is not None:
        item.result = outcome
        item.profit_units = profit_units(outcome, item.quota)
        item.status = SHORTLIST_SETTLED
        item.settled_at = now

    parent = db.get(CecchinoV4Shortlist, item.shortlist_id)
    if parent is not None:
        siblings = list_items(db, parent.id)
        if siblings and all(s.status in (SHORTLIST_SETTLED, SHORTLIST_WITHDRAWN) for s in siblings):
            parent.status = SHORTLIST_SETTLED
        parent.updated_at = now
    db.commit()
    return item


def shortlist_payload(db: Session, day: date) -> dict[str, Any] | None:
    """Risposta di `GET /shortlist?date=` dal database (docs/v4/API.md). None se il giorno non ha lista."""
    record = get_shortlist(db, day)
    if record is None:
        return None
    summary = record.summary_json or {}
    meta = summary.get("meta") or {}
    advised = bool(summary.get("advised", True))
    items = []
    for it in list_items(db, record.id):
        fx_meta = meta.get(str(it.fixture_id)) or {}
        items.append(
            {
                "id": it.id,
                "fixture_id": it.fixture_id,
                "home_team": fx_meta.get("home_team"),
                "away_team": fx_meta.get("away_team"),
                "kickoff_at": fx_meta.get("kickoff_at"),
                "league_code": fx_meta.get("league_code"),
                "market_key": it.market_key,
                "label": it.label,
                "p": it.probability,
                "lo": it.prob_low,
                "hi": it.prob_high,
                "p_prudent": it.prob_prudent,
                "quota_used": it.quota,
                "bookmaker_id": it.bookmaker_id,
                "expected_profit": it.expected_profit,
                "rank": it.rank,
                "top": it.rank <= TOP_PLAYS,
                "status": it.status,
                "advised": advised,
                "withdraw_reason": it.withdraw_reason,
                "result": it.result,
                "profit_units": it.profit_units,
                "closing_quota": it.closing_quota,
                "clv": it.clv,
                "reason": it.reason_json,
            }
        )
    return {
        "date": record.day.isoformat(),
        "status": record.status,
        "sealed_at": None if record.sealed_at is None else record.sealed_at.isoformat(),
        "digest": record.digest,
        "advised": advised,
        "banner": summary.get("banner"),
        "items": items,
        "abstentions": summary.get("abstentions") or [],
    }


__all__ = [
    "E4_FAILED_BANNER",
    "Shortlist",
    "ShortlistItem",
    "abstention_summary",
    "build_shortlist",
    "get_shortlist",
    "list_items",
    "save_provisional",
    "seal_digest",
    "seal_shortlist",
    "settle_item",
    "shortlist_payload",
    "withdraw_item",
]
