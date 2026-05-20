"""Normalizzazione nomi giocatore per matching SportAPI ↔ API-Football."""

from __future__ import annotations

import re
import unicodedata

_MULTI_SPACE = re.compile(r"\s+")


def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = s.replace("'", "'").replace("`", "'").replace("'", "'")
    s = re.sub(r"[^\w\s']", " ", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s


def player_names_match(a: str, b: str, *, extra: str | None = None) -> bool:
    na = normalize_player_name(a)
    nb = normalize_player_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if extra:
        ne = normalize_player_name(extra)
        if ne and (ne == na or ne == nb):
            return True
    if na in nb or nb in na:
        return len(min(na, nb, key=len)) >= 4
    return False
