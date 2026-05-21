"""Estrazione mercato 1X2 da payload quote evento SportAPI."""

from __future__ import annotations

import re
from typing import Any

MAX_DEPTH = 10

_1X2_ALIASES = frozenset(
    {
        "full time",
        "fulltime",
        "match winner",
        "winner",
        "1x2",
        "1 x 2",
        "regular time",
        "esito finale",
        "risultato finale",
        "esito partita",
    },
)

_1X2_NAME_RE = re.compile(
    r"(?:^|\b)(?:1\s*x\s*2|1x2|match\s*winner|full\s*time|fulltime|regular\s*time|"
    r"winner|esito\s*finale|risultato\s*finale|esito\s*partita)(?:\b|$)",
    re.IGNORECASE,
)

_HOME_LABELS = frozenset(
    {"1", "home", "casa", "squadra casa", "team1", "team 1", "team home", "h"},
)
_DRAW_LABELS = frozenset({"x", "draw", "pareggio", "n", "tie", "d"})
_AWAY_LABELS = frozenset(
    {"2", "away", "ospite", "trasferta", "squadra trasferta", "team2", "team 2", "team away", "a"},
)

_TYPE_HOME = frozenset({"home", "1", "h", "team1", "team_home"})
_TYPE_DRAW = frozenset({"draw", "x", "d", "tie", "n"})
_TYPE_AWAY = frozenset({"away", "2", "a", "team2", "team_away"})

_ODD_KEYS = (
    "decimalOdd",
    "decimal",
    "odd",
    "odds",
    "price",
    "value",
    "current",
    "fractionalValue",
    "fractional",
)

_CHOICE_CONTAINER_KEYS = ("choices", "outcomes", "selections", "odds", "lines", "choiceGroups", "groups")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _normalize_market_name(name: str | None) -> str:
    if not name:
        return ""
    return _norm(re.sub(r"[^\w\s]", " ", name))


def _is_1x2_market_name(name: str | None) -> bool:
    if not name:
        return False
    normalized = _normalize_market_name(name)
    if normalized in _1X2_ALIASES:
        return True
    return bool(_1X2_NAME_RE.search(name))


def _is_full_time_market_name(name: str | None) -> bool:
    if not name:
        return False
    n = _normalize_market_name(name)
    return n in ("full time", "fulltime")


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


def _type_bucket(choice: dict[str, Any]) -> str | None:
    for k in ("type", "outcomeType", "outcome_type", "group", "side"):
        v = choice.get(k)
        if v is None:
            continue
        t = _norm(str(v))
        if t in _TYPE_HOME:
            return "home"
        if t in _TYPE_DRAW:
            return "draw"
        if t in _TYPE_AWAY:
            return "away"
    return None


def _parse_fractional_string(s: str) -> float | None:
    s = s.strip()
    if "/" not in s:
        return None
    parts = s.split("/", 1)
    if len(parts) != 2:
        return None
    try:
        num = float(parts[0].strip())
        den = float(parts[1].strip())
        if den <= 0:
            return None
        dec = num / den
        # Convenzione bookmaker UK: quota decimale = frazionario + 1
        if dec >= 0.01:
            return round(dec + 1.0, 4)
    except (TypeError, ValueError):
        return None
    return None


def _parse_odd_value(choice: dict[str, Any]) -> tuple[float | None, Any | None]:
    """Ritorna (quota decimale, valore grezzo se non convertito)."""
    candidates: list[Any] = []
    for k in _ODD_KEYS:
        if k in choice and choice[k] is not None:
            candidates.append(choice[k])
    for nested_key in ("initial", "current", "live"):
        nested = choice.get(nested_key)
        if isinstance(nested, dict):
            for k in _ODD_KEYS:
                if k in nested and nested[k] is not None:
                    candidates.append(nested[k])

    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            f = float(raw)
            if f >= 1.01:
                return f, raw
            continue
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                continue
            frac = _parse_fractional_string(s)
            if frac is not None and frac >= 1.01:
                return frac, raw
            try:
                f = float(s.replace(",", "."))
                if f >= 1.01:
                    return f, raw
            except ValueError:
                pass
        if isinstance(raw, dict):
            for sub_k in ("decimal", "decimalOdd", "value", "price"):
                if sub_k in raw:
                    sub_val, _ = _parse_odd_value({sub_k: raw[sub_k]})
                    if sub_val is not None:
                        return sub_val, raw

    return None, candidates[0] if candidates else None


def _choice_label(choice: dict[str, Any]) -> str | None:
    for k in ("name", "label", "outcome", "outcomeName", "selection", "title"):
        if choice.get(k) is not None:
            return str(choice[k]).strip()
    return None


def _flatten_choices(node: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > MAX_DEPTH:
        return []
    out: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            out.extend(_flatten_choices(item, depth + 1))
        return out
    if not isinstance(node, dict):
        return out

    has_odd = any(node.get(k) is not None for k in _ODD_KEYS)
    if has_odd or _choice_label(node):
        out.append(node)

    for k in _CHOICE_CONTAINER_KEYS:
        child = node.get(k)
        if child is not None:
            out.extend(_flatten_choices(child, depth + 1))

    return out


def _collect_market_nodes(node: Any, depth: int, markets: list[tuple[str, Any]]) -> None:
    if depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        name = None
        for k in ("marketName", "market_name", "name", "betName", "bet_name", "market", "type"):
            if k in node and node[k] is not None:
                name = str(node[k]).strip()
                break
        flat = _flatten_choices(node, depth)
        if name and flat:
            markets.append((name, node))
        elif name:
            for k in _CHOICE_CONTAINER_KEYS:
                if node.get(k) is not None:
                    markets.append((name, node))
                    break
        for v in node.values():
            _collect_market_nodes(v, depth + 1, markets)
    elif isinstance(node, list):
        for item in node:
            _collect_market_nodes(item, depth + 1, markets)


def _extract_odds_from_choices(choices: list[Any], *, allow_positional: bool) -> dict[str, Any]:
    home_odd = draw_odd = away_odd = None
    home_label = draw_label = away_label = None
    home_raw = draw_raw = away_raw = None
    flat: list[dict[str, Any]] = []
    for ch in choices:
        if isinstance(ch, dict):
            flat.extend(_flatten_choices(ch))
        else:
            flat.extend(_flatten_choices(ch))

    unmatched: list[tuple[dict[str, Any], float | None, Any | None, str | None]] = []

    for ch in flat:
        label = _choice_label(ch)
        price, raw_val = _parse_odd_value(ch)
        bucket = _type_bucket(ch) or _label_bucket(label)
        if bucket == "home" and home_odd is None and price is not None:
            home_odd, home_label, home_raw = price, label, raw_val
        elif bucket == "draw" and draw_odd is None and price is not None:
            draw_odd, draw_label, draw_raw = price, label, raw_val
        elif bucket == "away" and away_odd is None and price is not None:
            away_odd, away_label, away_raw = price, label, raw_val
        elif price is not None:
            unmatched.append((ch, price, raw_val, label))

    if allow_positional and len(flat) == 3 and home_odd is None and draw_odd is None and away_odd is None:
        labels = [_choice_label(flat[i]) for i in range(3)]
        prices = [_parse_odd_value(flat[i])[0] for i in range(3)]
        if all(p is not None for p in prices):
            home_odd, draw_odd, away_odd = prices[0], prices[1], prices[2]
            home_label, draw_label, away_label = labels[0], labels[1], labels[2]
            home_raw, draw_raw, away_raw = (
                _parse_odd_value(flat[0])[1],
                _parse_odd_value(flat[1])[1],
                _parse_odd_value(flat[2])[1],
            )

    elif allow_positional and unmatched and (home_odd is None or draw_odd is None or away_odd is None):
        remaining = [u for u in unmatched if u[1] is not None]
        order = ["home", "draw", "away"]
        idx = 0
        for bucket in order:
            if bucket == "home" and home_odd is not None:
                continue
            if bucket == "draw" and draw_odd is not None:
                continue
            if bucket == "away" and away_odd is not None:
                continue
            if idx < len(remaining):
                _, price, raw_val, label = remaining[idx]
                idx += 1
                if bucket == "home":
                    home_odd, home_label, home_raw = price, label, raw_val
                elif bucket == "draw":
                    draw_odd, draw_label, draw_raw = price, label, raw_val
                else:
                    away_odd, away_label, away_raw = price, label, raw_val

    return {
        "home_odd": home_odd,
        "draw_odd": draw_odd,
        "away_odd": away_odd,
        "home_label": home_label,
        "draw_label": draw_label,
        "away_label": away_label,
        "home_odd_raw": home_raw,
        "draw_odd_raw": draw_raw,
        "away_odd_raw": away_raw,
    }


def _outcomes_complete(odds: dict[str, Any]) -> bool:
    return (
        odds.get("home_odd") is not None
        and odds.get("draw_odd") is not None
        and odds.get("away_odd") is not None
    )


def _build_result(
    *,
    market_matched: bool,
    market_name_original: str | None,
    odds: dict[str, Any],
    available: list[str],
    raw_market: Any,
    debug_full_time_market: Any = None,
) -> dict[str, Any]:
    complete = _outcomes_complete(odds)
    if not market_matched:
        status = "not_found"
    elif complete:
        status = "ok"
    else:
        status = "incomplete"

    return {
        "market_found": market_matched,
        "market_matched": market_matched,
        "outcomes_complete": complete,
        "normalization_status": status,
        "market_key": "1x2",
        "market_name_original": market_name_original,
        "home_odd": odds.get("home_odd"),
        "draw_odd": odds.get("draw_odd"),
        "away_odd": odds.get("away_odd"),
        "home_label": odds.get("home_label"),
        "draw_label": odds.get("draw_label"),
        "away_label": odds.get("away_label"),
        "home_odd_raw": odds.get("home_odd_raw"),
        "draw_odd_raw": odds.get("draw_odd_raw"),
        "away_odd_raw": odds.get("away_odd_raw"),
        "available_markets": available,
        "raw_market": raw_market,
        "debug_full_time_market": debug_full_time_market,
    }


def _find_debug_full_time_market(markets: list[tuple[str, Any]]) -> Any:
    for name, node in markets:
        if _is_full_time_market_name(name):
            return node
    return None


def extract_1x2_from_event_odds(payload: Any) -> dict[str, Any]:
    """
    Ritorna dict con market_found, normalization_status, quote, available_markets, raw_market.
    """
    markets: list[tuple[str, Any]] = []
    _collect_market_nodes(payload, 0, markets)
    available = sorted({n for n, _ in markets if n})

    best_incomplete: dict[str, Any] | None = None
    best_name: str | None = None
    best_node: Any = None

    for name, node in markets:
        if not _is_1x2_market_name(name):
            continue
        flat = _flatten_choices(node)
        if not flat:
            for k in _CHOICE_CONTAINER_KEYS:
                if isinstance(node.get(k), list):
                    flat = _flatten_choices(node[k])
                    break
        odds = _extract_odds_from_choices(flat, allow_positional=True)
        if _outcomes_complete(odds):
            return _build_result(
                market_matched=True,
                market_name_original=name,
                odds=odds,
                available=available,
                raw_market=node,
            )
        if best_incomplete is None or (
            sum(1 for k in ("home_odd", "draw_odd", "away_odd") if odds.get(k) is not None)
            > sum(
                1
                for k in ("home_odd", "draw_odd", "away_odd")
                if best_incomplete.get(k) is not None
            )
        ):
            best_incomplete = odds
            best_name = name
            best_node = node

    if best_incomplete is not None and best_name is not None:
        debug_ft = _find_debug_full_time_market(markets) if not _outcomes_complete(best_incomplete) else None
        return _build_result(
            market_matched=True,
            market_name_original=best_name,
            odds=best_incomplete,
            available=available,
            raw_market=best_node,
            debug_full_time_market=debug_ft or best_node,
        )

    debug_ft = _find_debug_full_time_market(markets)
    return _build_result(
        market_matched=False,
        market_name_original=None,
        odds={
            "home_odd": None,
            "draw_odd": None,
            "away_odd": None,
            "home_label": None,
            "draw_label": None,
            "away_label": None,
        },
        available=available,
        raw_market=None,
        debug_full_time_market=debug_ft,
    )


def row_status_from_normalization(norm: dict[str, Any]) -> str:
    """Mappa normalizzazione a status riga batch/UI."""
    st = norm.get("normalization_status")
    if st == "ok":
        return "ok"
    if st == "incomplete":
        return "incomplete_1x2"
    return "no_1x2"
