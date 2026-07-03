"""Normalizzazione datetime condivisa (Cecchino, predictions_v10, ingestion)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from app.services.sot_feature_math import fixture_key_before

logger = logging.getLogger(__name__)

_DATETIME_ERROR_MARKERS = (
    "has no attribute 'utc'",
    "kickoff",
    "datetime",
    "isoformat",
    "tzinfo",
    "offset",
    "timezone",
)


def utc_now() -> datetime:
    """Ora corrente UTC-aware (sicuro anche con param `timezone: str` in scope)."""
    return datetime.now(timezone.utc)


def ensure_datetime_utc(value: Any, *, field_name: str = "datetime") -> datetime | None:
    """Converte value in datetime UTC-aware; None/invalid -> None senza eccezione."""
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            logger.warning("datetime_utils invalid empty string field=%s", field_name)
            return None
        normalized = s.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except (TypeError, ValueError):
            logger.warning("datetime_utils unparseable field=%s value=%r", field_name, value)
            return None
        logger.debug("datetime_utils normalized string field=%s value=%r", field_name, value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    logger.warning(
        "datetime_utils unsupported type field=%s type=%s",
        field_name,
        type(value).__name__,
    )
    return None


def ensure_datetime(value: Any, *, field_name: str = "datetime") -> datetime | None:
    """Alias di ensure_datetime_utc."""
    return ensure_datetime_utc(value, field_name=field_name)


def safe_isoformat(value: Any, *, field_name: str = "datetime") -> str | None:
    dt = ensure_datetime_utc(value, field_name=field_name)
    return dt.isoformat() if dt is not None else None


def fixture_key_before_safe(
    kickoff_a: Any,
    id_a: int,
    kickoff_b: Any,
    id_b: int,
    *,
    field_name_a: str = "kickoff_a",
    field_name_b: str = "kickoff_b",
) -> bool | None:
    """
    Wrapper anti-crash per fixture_key_before.
    True/False se confronto valido; None se una delle date non è parsabile.
    """
    ko_a = ensure_datetime_utc(kickoff_a, field_name=field_name_a)
    ko_b = ensure_datetime_utc(kickoff_b, field_name=field_name_b)
    if ko_a is None or ko_b is None:
        return None
    return fixture_key_before(ko_a, int(id_a), ko_b, int(id_b))


def is_datetime_error_message(message: str | None) -> bool:
    if not message:
        return False
    lower = str(message).lower()
    return any(marker in lower for marker in _DATETIME_ERROR_MARKERS)


def build_datetime_debug(
    kickoff: Any,
    *,
    raw_fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_api = (raw_fixture or {}).get("fixture") or {}
    raw_date = raw_api.get("date")
    normalized = ensure_datetime_utc(kickoff, field_name="kickoff")
    normalized_api = ensure_datetime_utc(raw_date, field_name="fixture.date") if raw_date else None
    return {
        "kickoff_raw": kickoff if isinstance(kickoff, str) else raw_date,
        "kickoff_normalized": normalized.isoformat() if normalized else None,
        "api_date_raw": raw_date,
        "api_date_normalized": normalized_api.isoformat() if normalized_api else None,
    }


def classify_datetime_blocking_reason(message: str | None) -> str:
    if not message:
        return "datetime_normalization_error"
    lower = str(message).lower()
    if "has no attribute 'utc'" in lower:
        return "datetime_normalization_error"
    if "target_kickoff_missing" in lower or "missing_kickoff" in lower:
        return "target_kickoff_missing"
    if "target_kickoff_invalid" in lower:
        return "target_kickoff_invalid"
    if "prior_fixture_kickoff_invalid" in lower:
        return "prior_fixture_kickoff_invalid"
    return "datetime_normalization_error"
