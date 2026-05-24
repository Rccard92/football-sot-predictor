"""Normalizzazione nomi arbitro per match cross-fixture."""

from __future__ import annotations

import re
import unicodedata


def normalize_referee_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def referee_names_match(a: str | None, b: str | None) -> bool:
    na = normalize_referee_name(a)
    nb = normalize_referee_name(b)
    if not na or not nb:
        return False
    return na == nb
