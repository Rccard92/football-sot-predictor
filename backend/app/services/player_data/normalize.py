"""Normalizzazione nomi giocatore per matching e deduplica."""

from __future__ import annotations

import re
import unicodedata


def normalize_player_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s
