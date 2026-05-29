"""Normalizzazione nomi giocatore per matching SportAPI ↔ API-Football."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_MULTI_SPACE = re.compile(r"\s+")

_NAME_ALIASES = (
    (re.compile(r"\bsao\b"), "sao"),
    (re.compile(r"\bsão\b"), "sao"),
    (re.compile(r"\batletico\b"), "atletico"),
    (re.compile(r"\batlético\b"), "atletico"),
    (re.compile(r"\batl\b"), "atletico"),
)


def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = s.replace("'", "'").replace("`", "'").replace("'", "'")
    s = re.sub(r"[^\w\s']", " ", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    for pattern, repl in _NAME_ALIASES:
        s = pattern.sub(repl, s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s


def _name_tokens(name: str) -> list[str]:
    norm = normalize_player_name(name)
    if not norm:
        return []
    return [t for t in norm.split() if len(t) >= 2]


def fuzzy_player_name_score(a: str, b: str, *, extra: str | None = None) -> float:
    """Score 0-1 per fuzzy match controllato su nomi giocatore."""
    if player_names_match(a, b, extra=extra):
        return 1.0
    na = normalize_player_name(a)
    nb = normalize_player_name(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta = set(_name_tokens(a))
    tb = set(_name_tokens(b))
    if ta and tb:
        overlap = len(ta & tb) / max(len(ta), len(tb))
        ratio = max(ratio, overlap)
        if ta & tb and (ta <= tb or tb <= ta):
            ratio = max(ratio, 0.9)
    if extra:
        ne = normalize_player_name(extra)
        if ne:
            ratio = max(ratio, SequenceMatcher(None, ne, nb).ratio())
    return ratio


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
    ta = _name_tokens(a)
    tb = _name_tokens(b)
    if ta and tb and ta[-1] == tb[-1] and len(ta[-1]) >= 4:
        if len(ta) == 1 or len(tb) == 1:
            return True
    if na in nb or nb in na:
        return len(min(na, nb, key=len)) >= 4
    return False
