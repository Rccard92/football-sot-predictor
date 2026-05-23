"""Rilevamento mercati candidati SOT da nomi mercato SportAPI."""

from __future__ import annotations

import re
from typing import Any

from app.services.sportapi.sportapi_odds_markets_normalize import NON_SOT_MARKET_KEYS

_SOT_KEYWORDS_EN = (
    "shots on target",
    "shot on target",
    "total shots on target",
    "team shots on target",
    "player shots on target",
)

_SOT_KEYWORDS_IT = (
    "tiri in porta",
    "tiri nello specchio",
    "conclusioni in porta",
)

_EXCLUDE_PATTERNS = (
    r"\bmatch\s+goals?\b",
    r"\bboth\s+teams\s+to\s+score\b",
    r"\bbtts\b",
    r"\bcorners?\b",
    r"\bcards?\b",
    r"\bfouls?\b",
    r"\boffsides?\b",
    r"\bdouble\s+chance\b",
    r"\bdraw\s+no\s+bet\b",
    r"\b1x2\b",
    r"\bfull\s+time\b",
    r"\bfulltime\b",
    r"\bmatch\s+winner\b",
    r"\bgoalscorer\b",
    r"\banytime\s+scorer\b",
)

_SOT_MARKET_KEYS = frozenset(
    {"match_total_sot", "home_team_sot", "away_team_sot", "player_sot"},
)

_HOME_HINTS = ("home team", "home", "casa", "team 1", "team1")
_AWAY_HINTS = ("away team", "away", "ospite", "trasferta", "team 2", "team2")
_PLAYER_HINTS = ("player", "giocatore", "anytime player")


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _is_excluded_by_name(name: str) -> bool:
    n = _norm_name(name)
    for pat in _EXCLUDE_PATTERNS:
        if re.search(pat, n, re.I):
            return True
    return False


def _is_non_sot_market_key(key: str | None) -> bool:
    if not key:
        return True
    if key in NON_SOT_MARKET_KEYS:
        return True
    return key.startswith("half_")


def _matched_keywords(name: str) -> list[str]:
    n = _norm_name(name)
    found: list[str] = []
    for kw in _SOT_KEYWORDS_EN + _SOT_KEYWORDS_IT:
        if kw in n:
            found.append(kw)
    if "on target" in n and ("shot" in n or "shots" in n):
        if "on target" not in found:
            found.append("on target")
    return found


def _suggest_key(name: str, market_key_guess: str | None) -> str | None:
    if market_key_guess in _SOT_MARKET_KEYS:
        return market_key_guess
    n = _norm_name(name)
    if any(h in n for h in _PLAYER_HINTS):
        return "player_sot"
    if any(h in n for h in _HOME_HINTS):
        return "home_team_sot"
    if any(h in n for h in _AWAY_HINTS):
        return "away_team_sot"
    return "match_total_sot"


def _confidence(name: str, keywords: list[str], suggested: str | None) -> str:
    n = _norm_name(name)
    if not keywords:
        return "low"
    strong = (
        "shots on target",
        "shot on target",
        "tiri in porta",
        "total shots on target",
        "tiri nello specchio",
        "conclusioni in porta",
    )
    if any(k in n for k in strong):
        return "high"
    if suggested == "player_sot" and "player" not in n:
        return "low"
    if len(keywords) >= 2:
        return "medium"
    return "medium"


def _over_under_from_outcomes(outcomes: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
    over_odd = under_odd = line_val = None
    for o in outcomes:
        label = _norm_name(str(o.get("name") or ""))
        price = o.get("price")
        ln = o.get("line")
        if ln is not None and line_val is None:
            line_val = float(ln)
        if "over" in label and price is not None:
            over_odd = float(price)
        if "under" in label and price is not None:
            under_odd = float(price)
    return over_odd, under_odd, line_val


def find_sot_candidate_markets(normalized_markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for m in normalized_markets:
        name = str(m.get("market_name") or "")
        if not name or _is_excluded_by_name(name):
            continue
        key_guess = m.get("market_key_guess")
        if _is_non_sot_market_key(str(key_guess) if key_guess else None):
            continue
        keywords = _matched_keywords(name)
        if not keywords:
            continue
        suggested = _suggest_key(name, str(key_guess) if key_guess else None)
        if suggested not in _SOT_MARKET_KEYS:
            continue
        conf = _confidence(name, keywords, suggested)
        over_o, under_o, line_v = _over_under_from_outcomes(m.get("outcomes") or [])
        candidates.append(
            {
                "market_name": name,
                "market_id": m.get("market_id"),
                "market_group": m.get("market_group"),
                "choice_group": m.get("choice_group"),
                "period": m.get("period"),
                "match_reason": ", ".join(keywords[:3]),
                "mapping_confidence": conf,
                "suggested_market_key": suggested,
                "line": line_v or m.get("line"),
                "over_odd": over_o,
                "under_odd": under_o,
                "outcomes_count": m.get("outcomes_count"),
                "outcomes": m.get("outcomes"),
                "raw_market": m.get("raw_market"),
            },
        )
    order = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda c: (order.get(str(c.get("mapping_confidence")), 9), c.get("market_name") or ""))
    return candidates
