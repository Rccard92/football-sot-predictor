"""Normalizzazione nomi squadra/giocatore per matching SportAPI."""

from __future__ import annotations

import re
import unicodedata

_TEAM_SUFFIXES = re.compile(
    r"\b(ac|afc|fc|sc|ssd|us|as|bc|cf|ud|cd|ss|ec|calcio|club)\b",
    re.IGNORECASE,
)

# Alias controllati per squadre brasiliane (canonical -> varianti normalizzate)
_BRAZIL_TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "sao paulo": ("sao paulo", "spfc"),
    "atletico mineiro": ("atletico mg", "atletico-mg", "ca mineiro", "galo"),
    "athletico paranaense": ("athletico pr", "athletico-paranaense", "atletico paranaense", "cap"),
    "flamengo": ("flamengo", "cr flamengo", "mengao"),
    "palmeiras": ("palmeiras", "se palmeiras"),
    "corinthians": ("corinthians", "sc corinthians"),
    "internacional": ("internacional", "sc internacional", "inter"),
    "gremio": ("gremio", "gremio fbpa"),
    "fluminense": ("fluminense", "fluminense fc"),
    "botafogo": ("botafogo", "botafogo fr"),
    "cruzeiro": ("cruzeiro", "cruzeiro ec"),
    "santos": ("santos", "santos fc"),
    "vasco da gama": ("vasco da gama", "vasco", "cr vasco da gama"),
    "bahia": ("bahia", "ec bahia"),
    "fortaleza": ("fortaleza", "fortaleza ec"),
    "cuiaba": ("cuiaba", "cuiaba ec"),
    "bragantino": ("bragantino", "red bull bragantino", "rb bragantino"),
}


def normalize_team_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = _TEAM_SUFFIXES.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _alias_tokens(name: str) -> set[str]:
    norm = normalize_team_name(name)
    if not norm:
        return set()
    tokens = {norm}
    for _canonical, variants in _BRAZIL_TEAM_ALIASES.items():
        all_v = {normalize_team_name(v) for v in variants}
        all_v.add(_canonical)
        if norm in all_v or any(norm in v or v in norm for v in all_v if v):
            tokens.update(all_v)
            tokens.add(_canonical)
    return {t for t in tokens if t}


def team_names_match(a: str, b: str) -> bool:
    return team_names_match_fuzzy(a, b)


def team_names_match_fuzzy(a: str, b: str) -> bool:
    ta = _alias_tokens(a)
    tb = _alias_tokens(b)
    if not ta or not tb:
        return False
    if ta & tb:
        return True
    for na in ta:
        for nb in tb:
            if na == nb:
                return True
            if na in nb or nb in na:
                return True
    return False


def extract_round_number(round_str: str | None) -> int | None:
    if not round_str:
        return None
    m = re.search(r"(\d+)", str(round_str))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None
