"""Estrazione mercato 1X2 da payload quote evento SportAPI."""

from __future__ import annotations

import re
from typing import Any

MAX_DEPTH = 10

_1X2_NAME_RE = re.compile(
    r"(?:^|\b)(?:1\s*x\s*2|1x2|match\s*winner|full\s*time|esito\s*finale|risultato\s*finale|esito\s*partita)(?:\b|$)",
    re.IGNORECASE,
)

_HOME_LABELS = frozenset({"1", "home", "casa", "team1", "team 1", "1 "})
_DRAW_LABELS = frozenset({"x", "draw", "pareggio", "n", "tie"})
_AWAY_LABELS = frozenset({"2", "away", "ospite", "trasferta", "team2", "team 2", "2 "})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _is_1x2_market_name(name: str | None) -> bool:
    if not name:
        return False
    return bool(_1X2_NAME_RE.search(name))


def _label_bucket(label: str | None) -> str | None:
    if not label:
        return None
    n = _norm(label)
    if n in _HOME_LABELS or n.startswith("1 "):
        return "home"
    if n in _DRAW_LABELS:
        return "draw"
    if n in _AWAY_LABELS or n.startswith("2 "):
        return "away"
    if n in {"1", "2"}:
        return "home" if n == "1" else "away"
    return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _collect_market_nodes(node: Any, depth: int, markets: list[tuple[str, Any]]) -> None:
    if depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        name = None
        for k in ("marketName", "market_name", "name", "betName", "bet_name", "market", "type"):
            if k in node and node[k] is not None:
                name = str(node[k]).strip()
                break
        choices = None
        for k in ("choices", "outcomes", "selections", "odds", "lines"):
            if isinstance(node.get(k), list):
                choices = node[k]
                break
        if name and choices:
            markets.append((name, node))
        for v in node.values():
            _collect_market_nodes(v, depth + 1, markets)
    elif isinstance(node, list):
        for item in node:
            _collect_market_nodes(item, depth + 1, markets)


def _extract_odds_from_choices(choices: list[Any]) -> dict[str, Any]:
    home_odd = draw_odd = away_odd = None
    home_label = draw_label = away_label = None
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        label = None
        for k in ("name", "label", "outcome", "outcomeName", "selection"):
            if ch.get(k) is not None:
                label = str(ch[k]).strip()
                break
        price = None
        for k in ("price", "odd", "odds", "value", "coefficient"):
            if ch.get(k) is not None:
                price = _to_float(ch[k])
                break
        if price is None:
            continue
        bucket = _label_bucket(label)
        if bucket == "home" and home_odd is None:
            home_odd, home_label = price, label
        elif bucket == "draw" and draw_odd is None:
            draw_odd, draw_label = price, label
        elif bucket == "away" and away_odd is None:
            away_odd, away_label = price, label
    return {
        "home_odd": home_odd,
        "draw_odd": draw_odd,
        "away_odd": away_odd,
        "home_label": home_label,
        "draw_label": draw_label,
        "away_label": away_label,
    }


def extract_1x2_from_event_odds(payload: Any) -> dict[str, Any]:
    """
    Ritorna dict con market_found, quote, available_markets, raw_market.
    """
    markets: list[tuple[str, Any]] = []
    _collect_market_nodes(payload, 0, markets)
    available = sorted({n for n, _ in markets if n})
    for name, node in markets:
        if not _is_1x2_market_name(name):
            continue
        choices = None
        for k in ("choices", "outcomes", "selections", "odds", "lines"):
            if isinstance(node.get(k), list):
                choices = node[k]
                break
        if not choices:
            continue
        odds = _extract_odds_from_choices(choices)
        if odds["home_odd"] is None and odds["draw_odd"] is None and odds["away_odd"] is None:
            continue
        return {
            "market_found": True,
            "market_key": "1x2",
            "market_name_original": name,
            "home_odd": odds["home_odd"],
            "draw_odd": odds["draw_odd"],
            "away_odd": odds["away_odd"],
            "home_label": odds["home_label"],
            "draw_label": odds["draw_label"],
            "away_label": odds["away_label"],
            "available_markets": available,
            "raw_market": node,
        }
    return {
        "market_found": False,
        "market_key": "1x2",
        "market_name_original": None,
        "home_odd": None,
        "draw_odd": None,
        "away_odd": None,
        "available_markets": available,
        "raw_market": None,
    }
