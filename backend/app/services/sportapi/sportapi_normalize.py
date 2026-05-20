"""Normalizzazione nomi squadra/giocatore per matching SportAPI."""

from __future__ import annotations

import re
import unicodedata

_TEAM_SUFFIXES = re.compile(
    r"\b(ac|afc|fc|sc|ssd|us|as|bc|cf|ud|cd|ss|calcio)\b",
    re.IGNORECASE,
)


def normalize_team_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = _TEAM_SUFFIXES.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def team_names_match(a: str, b: str) -> bool:
    na = normalize_team_name(a)
    nb = normalize_team_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False


def extract_round_number(round_str: str | None) -> int | None:
    if not round_str:
        return None
    m = re.search(r"(\d+)", str(round_str))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None
