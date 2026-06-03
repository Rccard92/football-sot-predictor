"""Report JSON Pattern Analysis summary/full."""

from __future__ import annotations

import copy
from typing import Any


def build_pattern_report_payload(
    raw: dict[str, Any],
    *,
    detail: str = "summary",
) -> dict[str, Any]:
    payload = copy.deepcopy(raw)
    payload["summary"] = dict(payload.get("summary") or {})
    payload["summary"]["report_detail"] = detail

    if detail == "summary":
        payload.pop("top3_fixtures", None)
        for block in payload.get("strategies") or []:
            for key in ("winning_patterns", "losing_patterns"):
                wp = block.get(key)
                if not isinstance(wp, dict):
                    continue
                cats = wp.get("categories")
                if isinstance(cats, dict):
                    for cat in cats.values():
                        if isinstance(cat, dict):
                            cat.pop("examples", None)
                special = wp.get("special_categories")
                if isinstance(special, dict):
                    for cat in special.values():
                        if isinstance(cat, dict):
                            cat.pop("examples", None)
    return payload
