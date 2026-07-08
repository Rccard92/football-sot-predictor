"""Persistenza e validazione soglie minime quota book configurabili."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_min_book_odd_setting import CecchinoSignalMinBookOddSetting
from app.services.cecchino.cecchino_selection_keys import (
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_min_odds import (
    DEFAULT_SIGNAL_MIN_BOOK_ODDS,
    MIN_BOOK_ODD_LABELS,
)

ALLOWED_TARGET_MARKET_KEYS: frozenset[str] = frozenset(
    {
        SEL_DRAW,
        SEL_DRAW_PT,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
        SEL_UNDER_2_5,
        SEL_OVER_2_5,
    },
)

ORDERED_TARGET_MARKET_KEYS: tuple[str, ...] = (
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_UNDER_2_5,
    SEL_OVER_2_5,
)

_MIN_ODD_EXCLUSIVE = Decimal("1")
_MAX_ODD = Decimal("50")
_TWO_PLACES = Decimal("0.01")


class SignalMinBookOddValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


def _quantize_odd(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _parse_min_book_odd(value: Any) -> Decimal:
    try:
        odd = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SignalMinBookOddValidationError("min_book_odd non valido", field="min_book_odd") from exc
    odd = _quantize_odd(odd)
    if odd <= _MIN_ODD_EXCLUSIVE:
        raise SignalMinBookOddValidationError("min_book_odd deve essere > 1", field="min_book_odd")
    if odd > _MAX_ODD:
        raise SignalMinBookOddValidationError("min_book_odd deve essere <= 50", field="min_book_odd")
    return odd


def _default_for_key(target_market_key: str) -> Decimal:
    default = DEFAULT_SIGNAL_MIN_BOOK_ODDS.get(target_market_key)
    if default is None:
        raise SignalMinBookOddValidationError(
            f"target_market_key non supportata: {target_market_key}",
            field="target_market_key",
        )
    return default


def ensure_default_signal_min_book_odds(db: Session) -> None:
    """Bootstrap lazy: nessuna scrittura se la tabella ha già righe."""
    existing = db.scalar(select(CecchinoSignalMinBookOddSetting.id).limit(1))
    if existing is not None:
        return


def load_signal_min_book_odds(db: Session) -> dict[str, Decimal]:
    """Valori attivi: DB se presente, altrimenti default per ogni target ammesso."""
    rows = list(db.scalars(select(CecchinoSignalMinBookOddSetting)).all())
    by_key = {row.target_market_key: row.min_book_odd for row in rows if row.is_enabled}
    merged = dict(DEFAULT_SIGNAL_MIN_BOOK_ODDS)
    for key in ALLOWED_TARGET_MARKET_KEYS:
        if key in by_key:
            merged[key] = by_key[key]
    return merged


def _serialize_item(target_market_key: str, active_odd: Decimal, *, from_db: bool) -> dict[str, Any]:
    default_odd = _default_for_key(target_market_key)
    return {
        "target_market_key": target_market_key,
        "label": MIN_BOOK_ODD_LABELS.get(target_market_key, target_market_key),
        "min_book_odd": float(active_odd),
        "default_min_book_odd": float(default_odd),
        "is_default": active_odd == default_odd and not from_db if from_db else active_odd == default_odd,
        "is_enabled": True,
    }


def list_signal_min_book_odds_settings(db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(CecchinoSignalMinBookOddSetting)).all())
    by_key = {row.target_market_key: row for row in rows}
    items: list[dict[str, Any]] = []
    for key in ORDERED_TARGET_MARKET_KEYS:
        row = by_key.get(key)
        if row is not None:
            default_odd = _default_for_key(key)
            items.append(
                {
                    "target_market_key": key,
                    "label": row.label or MIN_BOOK_ODD_LABELS.get(key, key),
                    "min_book_odd": float(row.min_book_odd),
                    "default_min_book_odd": float(default_odd),
                    "is_default": row.min_book_odd == default_odd,
                    "is_enabled": bool(row.is_enabled),
                },
            )
        else:
            default_odd = _default_for_key(key)
            items.append(
                {
                    "target_market_key": key,
                    "label": MIN_BOOK_ODD_LABELS.get(key, key),
                    "min_book_odd": float(default_odd),
                    "default_min_book_odd": float(default_odd),
                    "is_default": True,
                    "is_enabled": True,
                },
            )
    return items


def save_signal_min_book_odds(
    db: Session,
    items: list[dict[str, Any]],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    if not items:
        raise SignalMinBookOddValidationError("items non può essere vuoto")

    existing = {
        row.target_market_key: row
        for row in db.scalars(select(CecchinoSignalMinBookOddSetting)).all()
    }
    seen_keys: set[str] = set()
    updated = 0

    for raw in items:
        key = str(raw.get("target_market_key") or "").strip()
        if not key:
            raise SignalMinBookOddValidationError("target_market_key obbligatoria", field="target_market_key")
        if key not in ALLOWED_TARGET_MARKET_KEYS:
            raise SignalMinBookOddValidationError(
                f"target_market_key non supportata: {key}",
                field="target_market_key",
            )
        if key in seen_keys:
            raise SignalMinBookOddValidationError(f"target_market_key duplicata: {key}", field="target_market_key")
        seen_keys.add(key)

        odd = _parse_min_book_odd(raw.get("min_book_odd"))
        label = MIN_BOOK_ODD_LABELS.get(key, key)
        row = existing.get(key)
        if row is None:
            row = CecchinoSignalMinBookOddSetting(
                target_market_key=key,
                label=label,
                min_book_odd=odd,
                is_enabled=True,
                updated_by=updated_by,
            )
            db.add(row)
            existing[key] = row
        else:
            row.label = label
            row.min_book_odd = odd
            row.is_enabled = True
            row.updated_by = updated_by
        updated += 1

    db.flush()
    return {
        "status": "ok",
        "items": list_signal_min_book_odds_settings(db),
        "updated": updated,
    }


def reset_signal_min_book_odds_defaults(db: Session) -> dict[str, Any]:
    for row in db.scalars(select(CecchinoSignalMinBookOddSetting)).all():
        db.delete(row)
    db.flush()
    return {
        "status": "ok",
        "items": list_signal_min_book_odds_settings(db),
    }
