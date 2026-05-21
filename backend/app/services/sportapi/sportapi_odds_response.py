"""Helper estrazione liste/oggetti da payload SportAPI."""

from __future__ import annotations

from typing import Any


def unwrap_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("response", "providers", "data", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return inner
        if any(k in payload for k in ("slug", "name", "id", "oddsProvider")):
            return [payload]
    return []


def unwrap_odds_provider(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("oddsProvider") or payload.get("odds_provider")
    if isinstance(inner, dict):
        return inner
    return payload


def nested_id_name(obj: Any) -> tuple[int | None, str | None, str | None]:
    if not isinstance(obj, dict):
        return None, None, None
    raw_id = obj.get("id")
    try:
        pid = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        pid = None
    slug = str(obj.get("slug") or "").strip() or None
    name = str(obj.get("name") or "").strip() or None
    return pid, slug, name
