"""Filtri competizione Cecchino Today (high-confidence, conservativi)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_EXCLUDED_CUP,
    ELIGIBILITY_EXCLUDED_FRIENDLY,
    ELIGIBILITY_EXCLUDED_WOMEN,
    ELIGIBILITY_EXCLUDED_YOUTH,
)
from app.services.cecchino.cecchino_today_constants import (
    CUP_KEYWORDS,
    FRIENDLY_KEYWORDS,
    WOMEN_KEYWORDS,
    YOUTH_KEYWORDS,
)

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")
_YOUTH_AGE_RE = re.compile(r"^(?:u|under|sub)[\s\-]?([1][7-9]|2[0-3])$", re.IGNORECASE)


def _normalize(s: str) -> str:
    """Lowercase, strip diacritics, map punctuation to spaces, collapse whitespace."""
    text = str(s or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = _PUNCT_RE.sub(" ", without_marks)
    return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


def _tokens(s: str) -> list[str]:
    norm = _normalize(s)
    return norm.split() if norm else []


def _keyword_phrases(keywords: frozenset[str]) -> tuple[tuple[str, ...], ...]:
    phrases: list[tuple[str, ...]] = []
    for kw in keywords:
        parts = _tokens(kw)
        if parts:
            phrases.append(tuple(parts))
    return tuple(phrases)


_WOMEN_PHRASES = _keyword_phrases(WOMEN_KEYWORDS)
_CUP_PHRASES = _keyword_phrases(CUP_KEYWORDS)
_FRIENDLY_PHRASES = _keyword_phrases(FRIENDLY_KEYWORDS)
_YOUTH_PHRASES = _keyword_phrases(YOUTH_KEYWORDS)

_YOUTH_AGE_CODES = frozenset(f"u{age}" for age in range(17, 24))


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    n = len(phrase)
    for i in range(len(tokens) - n + 1):
        if tuple(tokens[i : i + n]) == phrase:
            return True
    return False


def _matches_phrases(tokens: list[str], phrases: tuple[tuple[str, ...], ...]) -> bool:
    return any(_contains_phrase(tokens, phrase) for phrase in phrases)


def _youth_age_hit(tokens: list[str]) -> bool:
    """Detect U17–U23 / Under 17–23 / Sub-17–23 with token boundaries."""
    if not tokens:
        return False
    for tok in tokens:
        compact = tok.replace("-", "")
        if compact in _YOUTH_AGE_CODES:
            return True
        if _YOUTH_AGE_RE.match(tok):
            return True
    # u 21 / under 21 / sub 21 as consecutive tokens (after punct→space normalize)
    for i, tok in enumerate(tokens):
        if tok in ("u", "under", "sub") and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.isdigit() and 17 <= int(nxt) <= 23:
                return True
            if nxt in _YOUTH_AGE_CODES:
                return True
    return False


def _matches_youth(tokens: list[str]) -> bool:
    if _youth_age_hit(tokens):
        return True
    return _matches_phrases(tokens, _YOUTH_PHRASES)


def _competition_field_texts(item: dict[str, Any]) -> list[str]:
    league = item.get("league") or {}
    fx = item.get("fixture") or {}
    return [
        str(league.get("name") or ""),
        str(league.get("country") or ""),
        str(league.get("round") or ""),
        str(league.get("type") or ""),
        str(fx.get("round") or ""),
    ]


def _team_names(item: dict[str, Any]) -> tuple[str, str]:
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    return str(home.get("name") or ""), str(away.get("name") or "")


def _competition_tokens(item: dict[str, Any]) -> list[str]:
    parts = [t for t in (_tokens(field) for field in _competition_field_texts(item)) for t in t]
    return parts


def _ends_with_autonomous_w(name: str) -> bool:
    toks = _tokens(name)
    return bool(toks) and toks[-1] == "w"


def _team_has_explicit_women_marker(name: str) -> bool:
    """Explicit women keywords only — never the lone letter W."""
    return _matches_phrases(_tokens(name), _WOMEN_PHRASES)


def _is_women_excluded(item: dict[str, Any]) -> bool:
    if _matches_phrases(_competition_tokens(item), _WOMEN_PHRASES):
        return True
    home, away = _team_names(item)
    if not home or not away:
        return False
    if _ends_with_autonomous_w(home) and _ends_with_autonomous_w(away):
        return True
    if _team_has_explicit_women_marker(home) and _team_has_explicit_women_marker(away):
        return True
    return False


def _is_cup_type(league_type: str) -> bool:
    norm = _normalize(league_type)
    if not norm or norm == "league":
        return False
    type_tokens = _tokens(norm)
    if "cup" in type_tokens or "super" in type_tokens:
        return True
    # preserve previous substring behaviour for type values like "supercup"
    if "cup" in norm or "super" in norm:
        return True
    return False


def _is_youth_excluded(item: dict[str, Any]) -> bool:
    if _matches_youth(_competition_tokens(item)):
        return True
    home, away = _team_names(item)
    if not home or not away:
        return False
    # Team-only youth: require coherent evidence on BOTH sides (conservative).
    return _matches_youth(_tokens(home)) and _matches_youth(_tokens(away))


def is_cecchino_allowed_competition(item: dict[str, Any]) -> tuple[bool, str | None]:
    """
    True se competizione ammessa (campionato maschile regolare).

    Hard-exclude solo con indicatori ad alta confidenza: women / cup / friendly / youth.
    Non esclude campionati di livello inferiore (Serie B, Championship, Liga 2, …).
    Ritorna (allowed, eligibility_status_if_excluded).
    """
    league = item.get("league") or {}
    league_type = str(league.get("type") or "")
    comp_tokens = _competition_tokens(item)

    if _is_women_excluded(item):
        return False, ELIGIBILITY_EXCLUDED_WOMEN

    if _is_cup_type(league_type):
        return False, ELIGIBILITY_EXCLUDED_CUP

    if _matches_phrases(comp_tokens, _CUP_PHRASES):
        return False, ELIGIBILITY_EXCLUDED_CUP

    if _matches_phrases(comp_tokens, _FRIENDLY_PHRASES):
        return False, ELIGIBILITY_EXCLUDED_FRIENDLY

    if _is_youth_excluded(item):
        return False, ELIGIBILITY_EXCLUDED_YOUTH

    return True, None
