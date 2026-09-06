"""Normalizzazione nomi team/competition per matching Lab (senza fuzzy assign)."""

from __future__ import annotations

import re
import unicodedata

from app.services.cecchino_data_lab.bet365_enrichment.team_aliases import (
    COMPETITION_ALIASES,
    TEAM_ALIASES,
)

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_name(value: str | None) -> str:
    """Lowercase, trim, strip accenti, punteggiatura → spazi, collapse whitespace."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = _PUNCT_RE.sub(" ", without_marks)
    return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


def _alias_lookup(raw: str | None, aliases: dict[str, str]) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text in aliases:
        return aliases[text]
    # Lookup case-insensitive su chiavi alias
    lower = text.lower()
    for key, target in aliases.items():
        if key.lower() == lower:
            return target
    return None


def resolve_team_name(
    raw: str | None,
    extra_aliases: dict[str, str] | None = None,
) -> tuple[str, bool, bool]:
    """Restituisce (nome_per_match, used_static_alias, used_temp_alias).

    Precedenza assoluta: TEAM_ALIASES statici, poi ``extra_aliases`` temporanei.
    """
    static_target = _alias_lookup(raw, TEAM_ALIASES)
    if static_target is not None:
        return static_target, True, False
    if extra_aliases:
        temp_target = _alias_lookup(raw, extra_aliases)
        if temp_target is not None:
            return temp_target, False, True
    return str(raw or "").strip(), False, False


def resolve_competition_name(raw: str | None) -> str:
    alias_target = _alias_lookup(raw, COMPETITION_ALIASES)
    if alias_target is not None:
        return alias_target
    return str(raw or "").strip()


def team_names_equal(
    csv_name: str | None,
    db_name: str | None,
    *,
    extra_aliases: dict[str, str] | None = None,
) -> tuple[bool, bool, bool]:
    """Confronta CSV vs DB dopo normalizzazione (+ alias CSV).

    Returns:
        (matched, used_static_alias, used_temp_alias)
    """
    resolved, used_static, used_temp = resolve_team_name(
        csv_name, extra_aliases=extra_aliases
    )
    matched = normalize_name(resolved) == normalize_name(db_name) and bool(
        normalize_name(resolved)
    )
    if not matched:
        return False, False, False
    return True, used_static, used_temp


def competition_names_match(
    csv_competition_name: str | None,
    csv_competition_api_name: str | None,
    db_competition_name: str | None,
) -> bool:
    db_norm = normalize_name(db_competition_name)
    if not db_norm:
        return False
    candidates = [
        resolve_competition_name(csv_competition_name),
        resolve_competition_name(csv_competition_api_name),
        csv_competition_name,
        csv_competition_api_name,
    ]
    for cand in candidates:
        if normalize_name(cand) == db_norm:
            return True
    return False
