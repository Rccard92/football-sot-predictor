"""Alias espliciti CSV → nome squadra Lab (mai fuzzy auto-match)."""

from __future__ import annotations

# Chiave: nome come appare nel CSV (display). Valore: nome tipico in CecchinoLabMatch.
TEAM_ALIASES: dict[str, str] = {
    "Standard Liège": "Standard",
    "KRC Genk": "Genk",
}

# Competizione CSV → competition_name Lab (estendibile). Vuota di default.
COMPETITION_ALIASES: dict[str, str] = {}
