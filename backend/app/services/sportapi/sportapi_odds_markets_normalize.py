"""Normalizzazione generica mercati odds SportAPI da payload evento."""

from __future__ import annotations

import re
from typing import Any

from app.services.sportapi.sportapi_odds_1x2_normalize import (
    _CHOICE_CONTAINER_KEYS,
    _flatten_choices,
    _norm,
    _parse_odd_value,
)

MAX_DEPTH = 12

_MARKET_NAME_KEYS = (
    "marketName",
    "market_name",
    "name",
    "betName",
    "bet_name",
    "market",
    "type",
    "title",
)
_MARKET_ID_KEYS = ("marketId", "market_id", "id", "betId", "bet_id")
_GROUP_KEYS = ("group", "category", "marketGroup", "market_group", "section")
_LINE_KEYS = ("line", "handicap", "hdp", "total", "parameter", "value")


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _parse_line_value(node: dict[str, Any]) -> float | None:
    for k in _LINE_KEYS:
        if k in node and node[k] is not None:
            try:
                return float(node[k])
            except (TypeError, ValueError):
                continue
    return None


def _guess_market_key(name: str | None) -> str | None:
    if not name:
        return None
    n = _norm(re.sub(r"[^\w\s]", " ", name))
    if any(x in n for x in ("1x2", "1 x 2", "match winner", "full time", "winner")):
        return "match_1x2"
    if "player" in n and ("shot" in n or "target" in n or "tiri" in n):
        return "player_sot"
    if ("home" in n or "casa" in n) and ("shot" in n or "target" in n or "tiri" in n):
        return "home_team_sot"
    if ("away" in n or "ospite" in n or "trasferta" in n) and ("shot" in n or "target" in n or "tiri" in n):
        return "away_team_sot"
    if any(
        kw in n
        for kw in (
            "total shot",
            "shots on target",
            "shot on target",
            "tiri in porta",
            "match shot",
            "team shot",
        )
    ):
        return "match_total_sot"
    return None


def _extract_market_name(node: dict[str, Any]) -> str | None:
    for k in _MARKET_NAME_KEYS:
        if node.get(k) is not None:
            return _str_or_none(node[k])
    return None


def _extract_market_id(node: dict[str, Any]) -> str | None:
    for k in _MARKET_ID_KEYS:
        if node.get(k) is not None and k != "id":
            return _str_or_none(node[k])
    return None


def _normalize_outcome(choice: dict[str, Any]) -> dict[str, Any]:
    label = None
    for k in ("name", "label", "outcome", "outcomeName", "selection", "title"):
        if choice.get(k) is not None:
            label = _str_or_none(choice[k])
            break
    price, price_raw = _parse_odd_value(choice)
    line = _parse_line_value(choice)
    status = None
    for k in ("status", "suspended", "active", "isActive"):
        if choice.get(k) is not None:
            status = _str_or_none(choice[k])
            break
    return {
        "name": label,
        "price": price,
        "price_raw": price_raw,
        "line": line,
        "status": status,
        "raw": choice,
    }


def _collect_market_nodes(node: Any, depth: int, out: list[tuple[str, dict[str, Any]]]) -> None:
    if depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        name = _extract_market_name(node)
        flat = _flatten_choices(node)
        if name and flat:
            out.append((name, node))
        elif name:
            for k in _CHOICE_CONTAINER_KEYS:
                if isinstance(node.get(k), list) and node[k]:
                    out.append((name, node))
                    break
        for v in node.values():
            _collect_market_nodes(v, depth + 1, out)
    elif isinstance(node, list):
        for item in node:
            _collect_market_nodes(item, depth + 1, out)


def _build_market_row(name: str, node: dict[str, Any]) -> dict[str, Any]:
    flat = _flatten_choices(node)
    if not flat:
        for k in _CHOICE_CONTAINER_KEYS:
            if isinstance(node.get(k), list):
                flat = _flatten_choices(node[k])
                break
    outcomes = [_normalize_outcome(c) for c in flat if isinstance(c, dict)]
    lines = sorted({o["line"] for o in outcomes if o.get("line") is not None})
    market_line = _parse_line_value(node)
    if market_line is not None and market_line not in lines:
        lines.insert(0, market_line)
    statuses = [o.get("status") for o in outcomes if o.get("status")]
    suspended = any(str(s).lower() in ("suspended", "false", "0") for s in statuses)
    group = None
    for k in _GROUP_KEYS:
        if node.get(k) is not None:
            group = _str_or_none(node[k])
            break
    return {
        "market_name": name,
        "market_id": _extract_market_id(node),
        "market_group": group,
        "market_key_guess": _guess_market_key(name),
        "line": lines[0] if len(lines) == 1 else None,
        "lines": lines,
        "outcomes": outcomes,
        "outcomes_count": len(outcomes),
        "status": "suspended" if suspended else "active",
        "raw_market": node,
    }


def normalize_all_markets_from_event_odds(payload: Any) -> list[dict[str, Any]]:
    """Estrae tutti i mercati dal payload event odds (non solo 1X2)."""
    raw_nodes: list[tuple[str, dict[str, Any]]] = []
    _collect_market_nodes(payload, 0, raw_nodes)
    seen: set[str] = set()
    markets: list[dict[str, Any]] = []
    for name, node in raw_nodes:
        key = f"{name}|{_extract_market_id(node) or ''}"
        if key in seen:
            continue
        seen.add(key)
        markets.append(_build_market_row(name, node))
    markets.sort(key=lambda m: (m.get("market_name") or "").lower())
    return markets
