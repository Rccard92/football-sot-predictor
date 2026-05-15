"""Parser nullable per API-Football: None = dato assente, mai confuso con 0."""

from __future__ import annotations

import re
from typing import Any


def parse_int_nullable(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if val != val:  # NaN
            return None
        return int(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-", "n/a"):
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def parse_float_nullable(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, float):
        if val != val:
            return None
        return val
    if isinstance(val, int):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-", "n/a"):
        return None
    m = re.match(r"^([\d.,]+)\s*%$", s)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def parse_percent_nullable(val: Any) -> float | None:
    """Percentuale API (es. \"84%\", 84, \"84\") → valore numerico 0–100 o None."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and val != val:
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "-", "n/a"):
        return None
    m = re.match(r"^([\d.,]+)\s*%$", s)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def parse_bool_nullable(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "yes", "1", "y"):
        return True
    if s in ("false", "no", "0", "n"):
        return False
    return None
