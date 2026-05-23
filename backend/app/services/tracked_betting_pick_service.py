"""Persistenza e regole anti-duplicato per tracked_betting_picks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import TrackedBettingPick
from app.models.tracked_betting_pick import (
    BACKFILL_WARNING_RECONSTRUCTED,
    PICK_TYPE_CAUTIOUS,
    PICK_TYPE_STATISTICAL,
    SOURCE_AUTO_PRE_MATCH,
    SOURCE_BACKFILL_ROUND,
    STATUS_PENDING,
)

MARKET_MATCH_TOTAL = "match_total_sot"
MARKET_LABEL_MATCH_TOTAL = "SOT Totale"

_OVER_LINE_RE = re.compile(r"over\s+([\d.]+)", re.I)


def parse_line_value_from_pick(suggested_pick: str | None) -> float | None:
    if not suggested_pick:
        return None
    m = _OVER_LINE_RE.search(suggested_pick)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def formation_snapshot_label(lineup_confirmed: bool) -> str:
    if lineup_confirmed:
        return "Pronostico con formazione ufficiale"
    return "Pronostico con probabile formazione aggiornata 30' prima"


def _confidence_to_reliability(label: str | None) -> float | None:
    lc = (label or "").strip().lower()
    if lc == "alta":
        return 80.0
    if lc == "media":
        return 50.0
    if lc == "bassa":
        return 20.0
    return None


def _pick_unchanged(existing: TrackedBettingPick, data: dict[str, Any]) -> bool:
    if existing.suggested_pick != data.get("suggested_pick"):
        return False
    if existing.lineup_confirmed and data.get("lineup_confirmed"):
        pt = existing.predicted_total_sot
        nt = data.get("predicted_total_sot")
        if pt is not None and nt is not None and abs(float(pt) - float(nt)) > 0.01:
            return False
    return True


class TrackedBettingPickService:
    def get_auto_pre_match(
        self,
        db: Session,
        fixture_id: int,
        *,
        model_id: str,
        market_id: str,
        pick_type: str,
    ) -> TrackedBettingPick | None:
        return db.scalar(
            select(TrackedBettingPick).where(
                TrackedBettingPick.fixture_id == int(fixture_id),
                TrackedBettingPick.model_id == model_id,
                TrackedBettingPick.market_id == market_id,
                TrackedBettingPick.pick_type == pick_type,
                TrackedBettingPick.source == SOURCE_AUTO_PRE_MATCH,
            ),
        )

    def load_auto_pre_match_by_fixture_ids(
        self,
        db: Session,
        fixture_ids: list[int],
        *,
        model_id: str | None = None,
    ) -> dict[int, list[TrackedBettingPick]]:
        if not fixture_ids:
            return {}
        q = select(TrackedBettingPick).where(
            TrackedBettingPick.fixture_id.in_([int(x) for x in fixture_ids]),
            TrackedBettingPick.source == SOURCE_AUTO_PRE_MATCH,
        )
        if model_id:
            q = q.where(TrackedBettingPick.model_id == model_id)
        rows = list(db.scalars(q).all())
        out: dict[int, list[TrackedBettingPick]] = {}
        for r in rows:
            out.setdefault(int(r.fixture_id), []).append(r)
        return out

    def get_backfill_pick(
        self,
        db: Session,
        fixture_id: int,
        *,
        model_id: str,
        market_id: str,
        pick_type: str,
    ) -> TrackedBettingPick | None:
        return db.scalar(
            select(TrackedBettingPick).where(
                TrackedBettingPick.fixture_id == int(fixture_id),
                TrackedBettingPick.model_id == model_id,
                TrackedBettingPick.market_id == market_id,
                TrackedBettingPick.pick_type == pick_type,
                TrackedBettingPick.source == SOURCE_BACKFILL_ROUND,
            ),
        )

    def upsert_backfill_round(
        self,
        db: Session,
        *,
        fixture_id: int,
        model_id: str,
        market_id: str = MARKET_MATCH_TOTAL,
        market_label: str = MARKET_LABEL_MATCH_TOTAL,
        pick_type: str,
        suggested_pick: str | None,
        line_value: float | None,
        predicted_home_sot: float | None,
        predicted_away_sot: float | None,
        predicted_total_sot: float | None,
        confidence_label: str | None,
        lineup_confirmed: bool,
        lineup_fetched_at: datetime | None,
        raw_prediction_payload: dict[str, Any] | None,
        raw_betting_advice_payload: dict[str, Any] | None,
        is_backfilled: bool,
        prediction_source: str | None,
        backfill_warning: str | None,
        force: bool = False,
    ) -> Literal["created", "updated", "skipped"]:
        if not suggested_pick:
            return "skipped"

        now = datetime.now(timezone.utc)
        data = {
            "suggested_pick": suggested_pick,
            "line_value": line_value if line_value is not None else parse_line_value_from_pick(suggested_pick),
            "predicted_home_sot": predicted_home_sot,
            "predicted_away_sot": predicted_away_sot,
            "predicted_total_sot": predicted_total_sot,
            "confidence_label": confidence_label,
            "reliability_score": _confidence_to_reliability(confidence_label),
            "lineup_confirmed": bool(lineup_confirmed),
            "lineup_fetched_at": lineup_fetched_at,
            "prediction_generated_at": now,
            "raw_prediction_payload": raw_prediction_payload,
            "raw_betting_advice_payload": raw_betting_advice_payload,
            "is_backfilled": bool(is_backfilled),
            "prediction_source": prediction_source,
            "backfill_warning": backfill_warning,
        }

        existing = self.get_backfill_pick(
            db,
            fixture_id,
            model_id=model_id,
            market_id=market_id,
            pick_type=pick_type,
        )
        if existing is not None:
            if not force and _pick_unchanged(existing, data):
                return "skipped"
            for k, v in data.items():
                setattr(existing, k, v)
            if existing.status in (STATUS_PENDING,):
                pass
            db.add(existing)
            return "updated"

        row = TrackedBettingPick(
            fixture_id=int(fixture_id),
            model_id=model_id,
            source=SOURCE_BACKFILL_ROUND,
            market_id=market_id,
            market_label=market_label,
            pick_type=pick_type,
            status=STATUS_PENDING,
            auto_generated_at=None,
            **data,
        )
        db.add(row)
        return "created"

    def upsert_auto_pre_match(
        self,
        db: Session,
        *,
        fixture_id: int,
        model_id: str = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        market_id: str = MARKET_MATCH_TOTAL,
        market_label: str = MARKET_LABEL_MATCH_TOTAL,
        pick_type: str,
        suggested_pick: str | None,
        line_value: float | None,
        predicted_home_sot: float | None,
        predicted_away_sot: float | None,
        predicted_total_sot: float | None,
        confidence_label: str | None,
        lineup_confirmed: bool,
        lineup_fetched_at: datetime | None,
        raw_prediction_payload: dict[str, Any] | None,
        raw_betting_advice_payload: dict[str, Any] | None,
        force: bool = False,
    ) -> Literal["created", "updated", "skipped"]:
        if not suggested_pick:
            return "skipped"

        now = datetime.now(timezone.utc)
        data = {
            "suggested_pick": suggested_pick,
            "line_value": line_value if line_value is not None else parse_line_value_from_pick(suggested_pick),
            "predicted_home_sot": predicted_home_sot,
            "predicted_away_sot": predicted_away_sot,
            "predicted_total_sot": predicted_total_sot,
            "confidence_label": confidence_label,
            "reliability_score": _confidence_to_reliability(confidence_label),
            "lineup_confirmed": bool(lineup_confirmed),
            "lineup_fetched_at": lineup_fetched_at,
            "prediction_generated_at": now,
            "raw_prediction_payload": raw_prediction_payload,
            "raw_betting_advice_payload": raw_betting_advice_payload,
        }

        existing = self.get_auto_pre_match(
            db,
            fixture_id,
            model_id=model_id,
            market_id=market_id,
            pick_type=pick_type,
        )

        if existing is not None:
            if existing.lineup_confirmed and not force:
                return "skipped"
            if not force and _pick_unchanged(existing, data):
                return "skipped"

            for k, v in data.items():
                setattr(existing, k, v)
            existing.auto_generated_at = now
            if existing.status == STATUS_PENDING:
                pass
            db.add(existing)
            return "updated"

        row = TrackedBettingPick(
            fixture_id=int(fixture_id),
            model_id=model_id,
            source=SOURCE_AUTO_PRE_MATCH,
            market_id=market_id,
            market_label=market_label,
            pick_type=pick_type,
            status=STATUS_PENDING,
            auto_generated_at=now,
            **data,
        )
        db.add(row)
        return "created"

    def persist_from_betting_advice(
        self,
        db: Session,
        *,
        fixture_id: int,
        home_sot: float,
        away_sot: float,
        advice: dict[str, Any],
        lineup_confirmed: bool,
        lineup_fetched_at: datetime | None,
        raw_prediction_payload: dict[str, Any] | None,
        force: bool = False,
    ) -> dict[str, int]:
        totals = round(float(home_sot) + float(away_sot), 2)
        created = updated = skipped = 0
        match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
        conf = match.get("confidence_label")

        for pick_type, key in (
            (PICK_TYPE_CAUTIOUS, "cautious_pick"),
            (PICK_TYPE_STATISTICAL, "statistical_pick"),
        ):
            suggested = match.get(key)
            if pick_type == PICK_TYPE_STATISTICAL and not suggested:
                continue
            if pick_type == PICK_TYPE_CAUTIOUS and not suggested:
                continue
            line_ln = match.get("cautious_line") if pick_type == PICK_TYPE_CAUTIOUS else match.get("statistical_line")
            action = self.upsert_auto_pre_match(
                db,
                fixture_id=fixture_id,
                pick_type=pick_type,
                suggested_pick=str(suggested) if suggested else None,
                line_value=float(line_ln) if line_ln is not None else None,
                predicted_home_sot=round(float(home_sot), 2),
                predicted_away_sot=round(float(away_sot), 2),
                predicted_total_sot=totals,
                confidence_label=conf,
                lineup_confirmed=lineup_confirmed,
                lineup_fetched_at=lineup_fetched_at,
                raw_prediction_payload=raw_prediction_payload,
                raw_betting_advice_payload=advice,
                force=force,
            )
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        return {"created": created, "updated": updated, "skipped": skipped}
