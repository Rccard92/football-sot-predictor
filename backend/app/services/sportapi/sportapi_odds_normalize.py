"""Normalizzazione difensiva payload odds SportAPI."""

from __future__ import annotations

from typing import Any

MAX_DEPTH = 8

_MARKET_KEYS = frozenset({"market", "marketname", "market_name", "bet", "betname", "bet_name", "type"})
_BOOKMAKER_KEYS = frozenset({"bookmaker", "bookmakername", "bookmaker_name", "bookie"})
_PROVIDER_KEYS = frozenset({"provider", "providername", "provider_name", "oddsprovider"})
_LINE_KEYS = frozenset({"line", "handicap", "hdp", "total", "parameter"})
_OUTCOME_KEYS = frozenset({"outcome", "outcomename", "outcome_name", "label", "name", "selection"})
_PRICE_KEYS = frozenset({"odd", "odds", "price", "value", "coefficient"})
_STATUS_KEYS = frozenset({"status", "suspended", "active", "isactive", "stopped"})


def _norm_key(k: str) -> str:
    return k.replace("-", "").replace("_", "").lower()


def _pick(d: dict[str, Any], keys: frozenset[str]) -> Any:
    for k, v in d.items():
        if _norm_key(str(k)) in keys:
            return v
    return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        s = str(v).strip()
        return s if s else None
    return None


def _looks_like_odds_row(d: dict[str, Any]) -> bool:
    nk = {_norm_key(str(k)) for k in d}
    has_price = bool(nk & _PRICE_KEYS)
    has_market = bool(nk & (_MARKET_KEYS | _OUTCOME_KEYS | _LINE_KEYS))
    return has_price or (has_market and len(d) >= 2)


def _row_from_dict(d: dict[str, Any], provider_id: int) -> dict[str, Any] | None:
    if not _looks_like_odds_row(d):
        return None
    market = _pick(d, _MARKET_KEYS)
    outcome = _pick(d, _OUTCOME_KEYS)
    if market is None and outcome is not None and len(d) <= 4:
        market = outcome
    price = _pick(d, _PRICE_KEYS)
    return {
        "source": "sportapi",
        "provider_id": int(provider_id),
        "market_name": _str_or_none(market),
        "bookmaker_name": _str_or_none(_pick(d, _BOOKMAKER_KEYS)),
        "outcome_name": _str_or_none(outcome),
        "line": _str_or_none(_pick(d, _LINE_KEYS)),
        "price": _str_or_none(price),
        "status": _str_or_none(_pick(d, _STATUS_KEYS)),
    }


def _walk(node: Any, provider_id: int, depth: int, out: list[dict[str, Any]]) -> None:
    if depth > MAX_DEPTH:
        return
    if isinstance(node, dict):
        row = _row_from_dict(node, provider_id)
        if row is not None:
            out.append(row)
        for v in node.values():
            _walk(v, provider_id, depth + 1, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, provider_id, depth + 1, out)


def normalize_sportapi_odds_payload(
    payload: Any,
    *,
    provider_id: int = 1,
) -> tuple[list[dict[str, Any]], int | None]:
    """Ritorna (normalized_markets, bookmakers_count dedotto)."""
    if payload is None:
        return [], None
    rows: list[dict[str, Any]] = []
    _walk(payload, provider_id, 0, rows)
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for r in rows:
        key = (r.get("market_name"), r.get("bookmaker_name"), r.get("outcome_name"), r.get("line"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    names = {r["bookmaker_name"] for r in deduped if r.get("bookmaker_name")}
    bk_count = len(names) if names else None
    return deduped, bk_count
