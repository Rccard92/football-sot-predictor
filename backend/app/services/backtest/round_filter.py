"""Filtro giornata esatta per mini-run PIT backtest."""

from __future__ import annotations

import re

_ROUND_NUMBER_RE = re.compile(r"Regular Season\s*-\s*(\d+)\s*$", re.IGNORECASE)


def extract_fixture_round_number(round_str: str | None) -> int | None:
    if not round_str:
        return None
    text = str(round_str).strip()
    m = _ROUND_NUMBER_RE.search(text)
    if m:
        return int(m.group(1))
    trailing = re.search(r"(\d+)\s*$", text)
    return int(trailing.group(1)) if trailing else None


def fixture_matches_round_number(round_str: str | None, round_number: int) -> bool:
    extracted = extract_fixture_round_number(round_str)
    return extracted is not None and extracted == int(round_number)
