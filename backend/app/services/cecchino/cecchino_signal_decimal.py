"""Canonicalizzazione Decimal a due cifre per formule Segnali Cecchino (DRAW only)."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

SIGNAL_FORMULA_DECIMAL_QUANTUM = Decimal("0.01")
SIGNAL_FORMULA_DECIMAL_ROUNDING = ROUND_HALF_UP


def canonical_signal_decimal(value: Any) -> Decimal | None:
    """Converte un valore numerico in Decimal quantizzato a 0.01 con ROUND_HALF_UP.

    Rifiuta None, bool, stringhe non numeriche, NaN e Infinity.
    Usa Decimal(str(value)) — nessun round() nativo, nessuna tolleranza float.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, Decimal) and (not value.is_finite()):
        return None
    try:
        if isinstance(value, Decimal):
            dec = value
        else:
            text = str(value).strip()
            if not text:
                return None
            lower = text.lower()
            if lower in ("nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"):
                return None
            dec = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not dec.is_finite():
        return None
    return dec.quantize(SIGNAL_FORMULA_DECIMAL_QUANTUM, rounding=SIGNAL_FORMULA_DECIMAL_ROUNDING)


def format_canonical_decimal(value: Decimal | None) -> str | None:
    """Serializza un Decimal canonico come stringa stabile JSON-safe."""
    if value is None:
        return None
    return format(value, "f")
