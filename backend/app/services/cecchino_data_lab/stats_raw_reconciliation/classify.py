"""Parse raw_json e classificazione cella (WOULD_WRITE / ALREADY_SAME / …)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.cecchino_data_lab.stats_raw_reconciliation.constants import (
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_INVALID_SOURCE_VALUE,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    DB_TO_RAW_FIELD_MAP,
    INT_FIELDS,
    STRING_FIELDS,
)


def blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_int_value(raw: Any) -> tuple[int | None, bool]:
    """Ritorna (value, invalid). blank -> (None, False); non numerico -> (None, True)."""
    text = blank_to_none(raw)
    if text is None:
        return None, False
    try:
        return int(text), False
    except ValueError:
        try:
            return int(Decimal(text.replace(",", "."))), False
        except (InvalidOperation, ValueError, OverflowError):
            return None, True


def parse_string_value(raw: Any) -> tuple[str | None, bool]:
    """Ritorna (value, invalid). blank -> (None, False)."""
    text = blank_to_none(raw)
    return text, False


def parse_source_for_field(field: str, raw_json: dict[str, Any] | None) -> tuple[Any, bool]:
    """Estrae e tipizza il valore source da raw_json per il campo DB.

    Returns:
        (parsed_value, invalid)
    """
    if not isinstance(raw_json, dict):
        return None, False
    csv_key = DB_TO_RAW_FIELD_MAP[field]
    raw_val = raw_json.get(csv_key)
    if field in INT_FIELDS:
        return parse_int_value(raw_val)
    if field in STRING_FIELDS:
        return parse_string_value(raw_val)
    return parse_string_value(raw_val)


def normalize_db_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = blank_to_none(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(Decimal(text.replace(",", ".")))
        except (InvalidOperation, ValueError, OverflowError):
            return None


def normalize_db_str(value: Any) -> str | None:
    return blank_to_none(value)


def classify_cell(
    *,
    field: str,
    db_value: Any,
    source_value: Any,
    source_invalid: bool,
) -> str:
    """Classifica una cella campo.

    WOULD_WRITE: DB NULL + source valorizzato (dato source disponibile).
    ALREADY_SAME / CONFLICT / NO_SOURCE_VALUE / INVALID_SOURCE_VALUE.
    """
    if source_invalid:
        return CELL_ACTION_INVALID_SOURCE_VALUE
    if source_value is None:
        return CELL_ACTION_NO_SOURCE_VALUE

    if field in INT_FIELDS:
        db_norm = normalize_db_int(db_value)
        src_norm = normalize_db_int(source_value)
        if src_norm is None:
            return CELL_ACTION_INVALID_SOURCE_VALUE
        if db_norm is None:
            return CELL_ACTION_WOULD_WRITE
        if db_norm == src_norm:
            return CELL_ACTION_ALREADY_SAME
        return CELL_ACTION_CONFLICT

    db_norm_s = normalize_db_str(db_value)
    src_norm_s = normalize_db_str(source_value)
    if src_norm_s is None:
        return CELL_ACTION_NO_SOURCE_VALUE
    if db_norm_s is None:
        return CELL_ACTION_WOULD_WRITE
    if db_norm_s == src_norm_s:
        return CELL_ACTION_ALREADY_SAME
    return CELL_ACTION_CONFLICT


def source_value_for_audit(source_value: Any, source_invalid: bool, raw_json: dict | None, field: str) -> str:
    """Rappresentazione stringa del valore source per l'audit CSV."""
    if isinstance(raw_json, dict):
        csv_key = DB_TO_RAW_FIELD_MAP[field]
        raw = raw_json.get(csv_key)
        if raw is None:
            return ""
        return str(raw)
    if source_invalid:
        return ""
    if source_value is None:
        return ""
    return str(source_value)


def db_value_for_audit(db_value: Any) -> str:
    if db_value is None:
        return ""
    return str(db_value)
