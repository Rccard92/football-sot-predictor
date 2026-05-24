"""Persistenza e regole anti-duplicato per tracked_betting_picks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models import Fixture, TeamSotPrediction, TrackedBettingPick
from app.services.sot_betting_advice_service import build_fixture_betting_advice
from app.models.tracked_betting_pick import (
    PICK_TYPE_CAUTIOUS,
    PICK_TYPE_STATISTICAL,
    PREDICTION_SOURCE_CERTIFIED,
    SOURCE_AUTO_PRE_MATCH,
    SOURCE_BACKFILL_ROUND,
    SOURCE_MANUAL,
    STATUS_LIVE,
    STATUS_LOST,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
    STATUS_VOID,
    STATUS_WON,
)

MARKET_MATCH_TOTAL = "match_total_sot"
MARKET_LABEL_MATCH_TOTAL = "SOT Totale"

_OVER_LINE_RE = re.compile(r"over\s+([\d.]+)", re.I)

CONCLUDED_STATUSES = frozenset({STATUS_WON, STATUS_LOST, STATUS_VOID, STATUS_UNAVAILABLE})
OPEN_STATUSES = frozenset({STATUS_PENDING, STATUS_LIVE})


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


def formation_snapshot_label(lineup_confirmed: bool, *, lineup_fetched_at: datetime | None = None) -> str:
    if lineup_confirmed:
        return "Formazione ufficiale"
    if lineup_fetched_at is not None:
        return "Probabile aggiornata pre-match"
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
    pt = existing.predicted_total_sot
    nt = data.get("predicted_total_sot")
    if pt is not None and nt is not None and abs(float(pt) - float(nt)) > 0.01:
        return False
    if bool(existing.lineup_confirmed) != bool(data.get("lineup_confirmed")):
        return False
    return True


def is_pick_concluded(pick: TrackedBettingPick) -> bool:
    return pick.status in CONCLUDED_STATUSES


def _seed_initial_snapshot(
    pick: TrackedBettingPick,
    *,
    home_sot: float | None,
    away_sot: float | None,
    total_sot: float | None,
    suggested_pick: str | None,
    line_value: float | None,
) -> None:
    if pick.initial_predicted_total_sot is not None:
        return
    if total_sot is None and suggested_pick is None:
        return
    pick.initial_predicted_home_sot = home_sot
    pick.initial_predicted_away_sot = away_sot
    pick.initial_predicted_total_sot = total_sot
    pick.initial_suggested_pick = suggested_pick
    pick.initial_line_value = line_value if line_value is not None else parse_line_value_from_pick(suggested_pick)


def _apply_initial_from_before(
    pick: TrackedBettingPick,
    *,
    before_home_sot: float | None,
    before_away_sot: float | None,
    before_advice: dict[str, Any] | None = None,
) -> None:
    if pick.initial_predicted_total_sot is not None:
        return
    if before_home_sot is None or before_away_sot is None:
        return
    total = round(float(before_home_sot) + float(before_away_sot), 2)
    pick_s: str | None = None
    line: float | None = None
    if before_advice:
        match = before_advice.get("match_total") if isinstance(before_advice.get("match_total"), dict) else {}
        if pick.pick_type == PICK_TYPE_CAUTIOUS:
            pick_s = match.get("cautious_pick")
            line_ln = match.get("cautious_line")
            if pick_s:
                pick_s = str(pick_s)
                line = float(line_ln) if line_ln is not None else parse_line_value_from_pick(pick_s)
    if pick_s is None and pick.pick_type == PICK_TYPE_CAUTIOUS:
        advice = build_fixture_betting_advice(
            float(before_home_sot),
            float(before_away_sot),
            model_version=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        )
        match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
        pick_s = match.get("cautious_pick")
        line_ln = match.get("cautious_line")
        if pick_s:
            pick_s = str(pick_s)
            line = float(line_ln) if line_ln is not None else parse_line_value_from_pick(pick_s)
    _seed_initial_snapshot(
        pick,
        home_sot=round(float(before_home_sot), 2),
        away_sot=round(float(before_away_sot), 2),
        total_sot=total,
        suggested_pick=pick_s,
        line_value=line,
    )


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

    def get_open_pick(
        self,
        db: Session,
        fixture_id: int,
        *,
        model_id: str,
        market_id: str,
        pick_type: str,
    ) -> TrackedBettingPick | None:
        """Pick monitorata non conclusa (auto, backfill o manual)."""
        for src in (SOURCE_AUTO_PRE_MATCH, SOURCE_BACKFILL_ROUND, SOURCE_MANUAL):
            row = db.scalar(
                select(TrackedBettingPick).where(
                    TrackedBettingPick.fixture_id == int(fixture_id),
                    TrackedBettingPick.model_id == model_id,
                    TrackedBettingPick.market_id == market_id,
                    TrackedBettingPick.pick_type == pick_type,
                    TrackedBettingPick.source == src,
                ),
            )
            if row is not None and not is_pick_concluded(row):
                return row
        return None

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

    def load_open_picks_by_fixture_ids(
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
            TrackedBettingPick.status.in_(list(OPEN_STATUSES)),
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
        before_home_sot: float | None = None,
        before_away_sot: float | None = None,
        before_advice: dict[str, Any] | None = None,
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
            if is_pick_concluded(existing) and not force:
                return "skipped"
            if not force and _pick_unchanged(existing, data):
                return "skipped"
            _apply_initial_from_before(
                existing,
                before_home_sot=before_home_sot,
                before_away_sot=before_away_sot,
                before_advice=before_advice,
            )
            for k, v in data.items():
                setattr(existing, k, v)
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
        _seed_initial_snapshot(
            row,
            home_sot=predicted_home_sot,
            away_sot=predicted_away_sot,
            total_sot=predicted_total_sot,
            suggested_pick=suggested_pick,
            line_value=data["line_value"],
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
        before_home_sot: float | None = None,
        before_away_sot: float | None = None,
        before_advice: dict[str, Any] | None = None,
    ) -> Literal["created", "updated", "skipped"]:
        if not suggested_pick:
            return "skipped"

        now = datetime.now(timezone.utc)
        line_resolved = line_value if line_value is not None else parse_line_value_from_pick(suggested_pick)
        data = {
            "suggested_pick": suggested_pick,
            "line_value": line_resolved,
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
            "is_backfilled": False,
            "prediction_source": PREDICTION_SOURCE_CERTIFIED,
            "backfill_warning": None,
        }

        open_pick = self.get_open_pick(
            db,
            fixture_id,
            model_id=model_id,
            market_id=market_id,
            pick_type=pick_type,
        )
        if open_pick is not None and is_pick_concluded(open_pick) and not force:
            return "skipped"

        existing_auto = self.get_auto_pre_match(
            db,
            fixture_id,
            model_id=model_id,
            market_id=market_id,
            pick_type=pick_type,
        )

        if existing_auto is not None:
            if is_pick_concluded(existing_auto) and not force:
                return "skipped"
            if not force and _pick_unchanged(existing_auto, data):
                return "skipped"
            _apply_initial_from_before(
                existing_auto,
                before_home_sot=before_home_sot,
                before_away_sot=before_away_sot,
                before_advice=before_advice,
            )
            for k, v in data.items():
                setattr(existing_auto, k, v)
            existing_auto.auto_generated_at = now
            existing_auto.source = SOURCE_AUTO_PRE_MATCH
            db.add(existing_auto)
            return "updated"

        backfill = self.get_backfill_pick(
            db,
            fixture_id,
            model_id=model_id,
            market_id=market_id,
            pick_type=pick_type,
        )
        if backfill is not None and not is_pick_concluded(backfill):
            if not force and _pick_unchanged(backfill, data):
                return "skipped"
            _apply_initial_from_before(
                backfill,
                before_home_sot=before_home_sot,
                before_away_sot=before_away_sot,
                before_advice=before_advice,
            )
            for k, v in data.items():
                setattr(backfill, k, v)
            backfill.source = SOURCE_AUTO_PRE_MATCH
            backfill.auto_generated_at = now
            backfill.is_backfilled = False
            backfill.backfill_warning = None
            backfill.prediction_source = PREDICTION_SOURCE_CERTIFIED
            if backfill.status not in OPEN_STATUSES:
                backfill.status = STATUS_PENDING
            db.add(backfill)
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
        if before_home_sot is not None and before_away_sot is not None:
            _apply_initial_from_before(
                row,
                before_home_sot=before_home_sot,
                before_away_sot=before_away_sot,
                before_advice=before_advice,
            )
        _seed_initial_snapshot(
            row,
            home_sot=predicted_home_sot,
            away_sot=predicted_away_sot,
            total_sot=predicted_total_sot,
            suggested_pick=suggested_pick,
            line_value=line_resolved,
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
        before_home_sot: float | None = None,
        before_away_sot: float | None = None,
        before_advice: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        totals = round(float(home_sot) + float(away_sot), 2)
        created = updated = skipped = 0
        match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
        conf = match.get("confidence_label")
        if before_advice is None and before_home_sot is not None and before_away_sot is not None:
            before_advice = build_fixture_betting_advice(
                float(before_home_sot),
                float(before_away_sot),
                model_version=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            )

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
                before_home_sot=before_home_sot if pick_type == PICK_TYPE_CAUTIOUS else None,
                before_away_sot=before_away_sot if pick_type == PICK_TYPE_CAUTIOUS else None,
                before_advice=before_advice if pick_type == PICK_TYPE_CAUTIOUS else None,
            )
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        return {"created": created, "updated": updated, "skipped": skipped}

    def sync_official_from_v20(
        self,
        db: Session,
        fixture_id: int,
        *,
        before_snapshot: dict[str, Any] | None = None,
        lineup_confirmed: bool = False,
        lineup_fetched_at: datetime | None = None,
        advice_context: Any | None = None,
        force: bool = False,
    ) -> dict[str, int]:
        """Aggiorna pick monitorate da predizioni v2.0 correnti (post refresh formazioni)."""
        from app.services.sot_betting_advice_service import AdviceContext

        fx = db.get(Fixture, int(fixture_id))
        if fx is None:
            return {"created": 0, "updated": 0, "skipped": 0}

        mv = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
        home_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(fx.home_team_id),
                TeamSotPrediction.model_version == mv,
            ),
        )
        away_row = db.scalar(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id == int(fixture_id),
                TeamSotPrediction.team_id == int(fx.away_team_id),
                TeamSotPrediction.model_version == mv,
            ),
        )
        if home_row is None or away_row is None or home_row.predicted_sot is None or away_row.predicted_sot is None:
            return {"created": 0, "updated": 0, "skipped": 0}

        home_sot = round(float(home_row.predicted_sot), 2)
        away_sot = round(float(away_row.predicted_sot), 2)
        raw_pred: dict[str, Any] = {}
        if isinstance(home_row.raw_json, dict):
            raw_pred["home"] = home_row.raw_json
        if isinstance(away_row.raw_json, dict):
            raw_pred["away"] = away_row.raw_json

        before_h = before_a = None
        before_adv = None
        if before_snapshot and before_snapshot.get("v20_available"):
            bh = before_snapshot.get("predicted_home_sot")
            ba = before_snapshot.get("predicted_away_sot")
            if bh is not None and ba is not None:
                before_h = float(bh)
                before_a = float(ba)
                ctx = advice_context if isinstance(advice_context, AdviceContext) else AdviceContext()
                before_adv = build_fixture_betting_advice(
                    before_h,
                    before_a,
                    model_version=mv,
                    context=ctx,
                )

        ctx = advice_context
        if ctx is None:
            ctx = AdviceContext()
        advice = build_fixture_betting_advice(
            home_sot,
            away_sot,
            model_version=mv,
            context=ctx,
        )
        return self.persist_from_betting_advice(
            db,
            fixture_id=int(fixture_id),
            home_sot=home_sot,
            away_sot=away_sot,
            advice=advice,
            lineup_confirmed=lineup_confirmed,
            lineup_fetched_at=lineup_fetched_at,
            raw_prediction_payload=raw_pred,
            force=force,
            before_home_sot=before_h,
            before_away_sot=before_a,
            before_advice=before_adv,
        )
