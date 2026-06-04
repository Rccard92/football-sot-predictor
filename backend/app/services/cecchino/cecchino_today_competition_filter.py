"""Filtri competizione Cecchino Today."""

from __future__ import annotations

import re
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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _haystack_from_item(item: dict[str, Any]) -> str:
    league = item.get("league") or {}
    parts = [
        str(league.get("name") or ""),
        str(league.get("country") or ""),
        str(league.get("round") or ""),
        str(league.get("type") or ""),
    ]
    fx = item.get("fixture") or {}
    parts.append(str(fx.get("round") or ""))
    return _norm(" ".join(parts))


def _matches_keywords(text: str, keywords: frozenset[str]) -> bool:
    for kw in keywords:
        if kw in text:
            return True
    return False


def is_cecchino_allowed_competition(item: dict[str, Any]) -> tuple[bool, str | None]:
    """
    True se competizione ammessa (campionato maschile).
    Ritorna (allowed, eligibility_status_if_excluded).
    """
    league = item.get("league") or {}
    league_type = _norm(str(league.get("type") or ""))
    hay = _haystack_from_item(item)

    if _matches_keywords(hay, WOMEN_KEYWORDS):
        return False, ELIGIBILITY_EXCLUDED_WOMEN

    if league_type and league_type not in ("league", ""):
        if "cup" in league_type or "super" in league_type:
            return False, ELIGIBILITY_EXCLUDED_CUP

    if _matches_keywords(hay, CUP_KEYWORDS):
        return False, ELIGIBILITY_EXCLUDED_CUP

    if _matches_keywords(hay, FRIENDLY_KEYWORDS):
        return False, ELIGIBILITY_EXCLUDED_FRIENDLY

    if _matches_keywords(hay, YOUTH_KEYWORDS):
        return False, ELIGIBILITY_EXCLUDED_YOUTH

    return True, None
