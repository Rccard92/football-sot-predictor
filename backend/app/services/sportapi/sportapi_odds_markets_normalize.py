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

_MARKET_LEVEL_NAME_KEYS = ("marketName", "market_name", "betName", "bet_name")
_MARKET_ID_KEYS = ("marketId", "market_id", "betId", "bet_id")
_GROUP_KEYS = ("group", "category", "marketGroup", "market_group", "section")
_LINE_KEYS = ("line", "handicap", "hdp", "total", "parameter", "value")
_CHOICE_GROUP_KEYS = ("choiceGroup", "choice_group", "groupName", "group_name", "handicap")

_STANDALONE_OUTCOME_NAMES = frozenset(
    {"over", "under", "yes", "no", "1", "x", "2", "home", "away", "draw"},
)

NON_SOT_MARKET_KEYS = frozenset(
    {
        "match_1x2",
        "double_chance",
        "btts",
        "draw_no_bet",
        "match_goals",
        "corners_total",
        "half_1x2",
        "half_goals",
        "half_other",
        "unknown",
    },
)

_SOT_KEYWORDS = (
    "shot on target",
    "shots on target",
    "total shots on target",
    "team shots on target",
    "player shots on target",
    "on target",
    "tiri in porta",
    "tiri nello specchio",
    "conclusioni in porta",
)


def _has_sot_keyword(n: str) -> bool:
    if any(kw in n for kw in _SOT_KEYWORDS):
        return True
    return "on target" in n and ("shot" in n or "shots" in n)


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _parse_line_value(node: dict[str, Any]) -> float | None:
    for k in _LINE_KEYS + _CHOICE_GROUP_KEYS:
        if k in node and node[k] is not None:
            raw = node[k]
            if isinstance(raw, str):
                raw = raw.replace(",", ".")
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _parse_choice_group_line(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _extract_markets_array(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("markets", "market", "bets"):
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    for wrap in ("response", "data", "event", "odds"):
        inner = payload.get(wrap)
        if isinstance(inner, dict):
            found = _extract_markets_array(inner)
            if found:
                return found
    return []


def _is_market_object(node: dict[str, Any]) -> bool:
    return any(node.get(k) is not None for k in _MARKET_LEVEL_NAME_KEYS)


def _extract_market_level_name(node: dict[str, Any]) -> str | None:
    for k in _MARKET_LEVEL_NAME_KEYS:
        if node.get(k) is not None:
            return _str_or_none(node[k])
    return None


def _extract_market_id(node: dict[str, Any]) -> str | None:
    for k in _MARKET_ID_KEYS:
        if node.get(k) is not None:
            return _str_or_none(node[k])
    return None


def _infer_period(market_name: str, node: dict[str, Any]) -> str:
    for k in ("period", "phase", "half", "scope"):
        if node.get(k) is not None:
            return _str_or_none(node[k]) or "Full match"
    n = _norm(market_name)
    if "1st half" in n or "first half" in n or "primo tempo" in n:
        return "1st half"
    if "2nd half" in n or "second half" in n or "secondo tempo" in n:
        return "2nd half"
    return "Full match"


def _guess_market_key(name: str | None) -> str:
    if not name:
        return "unknown"
    n = _norm(re.sub(r"[^\w\s]", " ", name))

    if any(x in n for x in ("corner", "corners")):
        return "corners_total"
    if "double chance" in n:
        return "double_chance"
    if "both teams to score" in n or n == "btts":
        return "btts"
    if "draw no bet" in n:
        return "draw_no_bet"
    if "match goals" in n or (n.startswith("match goal")):
        return "match_goals"
    if any(x in n for x in ("1x2", "1 x 2", "match winner", "full time", "fulltime")):
        if "1st half" in n or "first half" in n:
            return "half_1x2"
        if "2nd half" in n or "second half" in n:
            return "half_1x2"
        return "match_1x2"
    if "1st half" in n or "first half" in n:
        if "goal" in n:
            return "half_goals"
        return "half_1x2"
    if "2nd half" in n or "second half" in n:
        if "goal" in n:
            return "half_goals"
        return "half_1x2"

    if "player" in n and _has_sot_keyword(n):
        return "player_sot"
    if ("home" in n or "casa" in n) and _has_sot_keyword(n):
        return "home_team_sot"
    if ("away" in n or "ospite" in n or "trasferta" in n) and _has_sot_keyword(n):
        return "away_team_sot"
    if _has_sot_keyword(n):
        return "match_total_sot"

    return "unknown"


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


def _outcomes_from_node(node: dict[str, Any]) -> list[dict[str, Any]]:
    flat = _flatten_choices(node)
    if not flat:
        for k in _CHOICE_CONTAINER_KEYS:
            child = node.get(k)
            if child is not None:
                flat = _flatten_choices(child)
                if flat:
                    break
    return [_normalize_outcome(c) for c in flat if isinstance(c, dict)]


def _market_status(outcomes: list[dict[str, Any]]) -> str:
    statuses = [o.get("status") for o in outcomes if o.get("status")]
    suspended = any(str(s).lower() in ("suspended", "false", "0") for s in statuses)
    return "suspended" if suspended else "active"


def _extract_market_group(node: dict[str, Any]) -> str | None:
    for k in _GROUP_KEYS:
        if node.get(k) is not None:
            return _str_or_none(node[k])
    return None


def _choice_group_label(node: dict[str, Any]) -> str | None:
    for k in _CHOICE_GROUP_KEYS:
        if node.get(k) is not None:
            return _str_or_none(node[k])
    return None


def _build_market_row(
    market_name: str,
    market_node: dict[str, Any],
    *,
    choice_group: str | None = None,
    group_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = group_node if group_node is not None else market_node
    outcomes = _outcomes_from_node(source)
    cg_line = _parse_choice_group_line(choice_group) if choice_group else None
    market_line = _parse_line_value(market_node) or _parse_line_value(source)
    line = cg_line if cg_line is not None else market_line
    if line is None:
        lines_from_outcomes = sorted({o["line"] for o in outcomes if o.get("line") is not None})
        line = lines_from_outcomes[0] if len(lines_from_outcomes) == 1 else None
    period = _infer_period(market_name, market_node)
    key_guess = _guess_market_key(market_name)
    raw = {"market": market_node}
    if group_node is not None:
        raw["choice_group"] = group_node
    return {
        "market_name": market_name,
        "market_id": _extract_market_id(market_node),
        "market_group": _extract_market_group(market_node),
        "choice_group": choice_group,
        "period": period,
        "market_key_guess": key_guess,
        "line": line,
        "lines": [line] if line is not None else [],
        "outcomes": outcomes,
        "outcomes_count": len(outcomes),
        "status": _market_status(outcomes),
        "raw_market": raw,
    }


def _normalize_single_market(market_node: dict[str, Any]) -> list[dict[str, Any]]:
    name = _extract_market_level_name(market_node)
    if not name:
        return []
    if _norm(name) in _STANDALONE_OUTCOME_NAMES:
        return []

    rows: list[dict[str, Any]] = []
    choice_groups = market_node.get("choiceGroups") or market_node.get("choice_groups")
    if isinstance(choice_groups, list) and choice_groups:
        for grp in choice_groups:
            if not isinstance(grp, dict):
                continue
            cg = _choice_group_label(grp) or _choice_group_label(market_node)
            rows.append(
                _build_market_row(name, market_node, choice_group=cg, group_node=grp),
            )
        return rows

    cg_top = _choice_group_label(market_node)
    has_choices = any(
        isinstance(market_node.get(k), list) and market_node.get(k)
        for k in _CHOICE_CONTAINER_KEYS
    )
    if has_choices or cg_top:
        rows.append(_build_market_row(name, market_node, choice_group=cg_top))
    return rows


def normalize_all_markets_from_event_odds(payload: Any) -> list[dict[str, Any]]:
    """Estrae mercati solo da payload.markets (un mercato = marketName + choices/choiceGroups)."""
    market_nodes = _extract_markets_array(payload)
    seen: set[str] = set()
    markets: list[dict[str, Any]] = []
    for node in market_nodes:
        if not _is_market_object(node):
            continue
        for row in _normalize_single_market(node):
            dedupe = "|".join(
                [
                    str(row.get("market_name") or ""),
                    str(row.get("market_id") or ""),
                    str(row.get("choice_group") or ""),
                ],
            )
            if dedupe in seen:
                continue
            seen.add(dedupe)
            markets.append(row)
    markets.sort(
        key=lambda m: (
            (m.get("market_name") or "").lower(),
            str(m.get("choice_group") or ""),
        ),
    )
    return markets
