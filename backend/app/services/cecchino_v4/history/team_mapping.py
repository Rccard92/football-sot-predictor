"""Mappa nomi squadra API-Football -> nomi football-data (storico CSV).

Funzioni pure: normalizzazione del nome, alias da `team_aliases.json`, confronto fuzzy
(difflib). Nessun accesso al database: la persistenza in `cecchino_v4_team_map` la fa il job.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from app.services.cecchino_v4.constants import LEAGUE_BY_COMPETITION

ALIASES_PATH = Path(__file__).resolve().parent / "team_aliases.json"

# Sigle societarie che non distinguono una squadra dall'altra.
_DROP_TOKENS = frozenset(
    {"fc", "afc", "cf", "sc", "ac", "as", "us", "ss", "ssc", "calcio", "club", "the"}
)
# Parole che possono esserci o mancare nel nome senza cambiare squadra ("Hull" / "Hull City").
_GENERIC_TOKENS = frozenset(
    {
        "city", "town", "united", "utd", "county", "albion", "rovers", "wanderers", "athletic",
        "real", "deportivo", "racing", "sporting", "cd", "ud", "sd", "rcd", "kv", "krc", "kaa",
        "fcv", "vfl", "vfb", "fsv", "tsg", "sv", "spvgg", "bsc", "1", "04", "05", "07", "96", "98",
        "1899", "olympique", "stade", "sl", "cp", "psv", "sk", "jk", "fk", "royal", "de", "la",
    }
)

MIN_CONFIDENCE = 0.80
AMBIGUITY_GAP = 0.05


@dataclass
class MappingResult:
    api_name: str
    history_name: str | None
    confidence: float
    method: str  # alias|exact|core|fuzzy|none
    ambiguous: bool = False
    candidates: list[tuple[str, float]] = field(default_factory=list)

    def as_tuple(self) -> tuple[str | None, float]:
        return self.history_name, self.confidence


def normalize_name(name: str) -> str:
    """Minuscolo, senza accenti, senza sigle societarie e punteggiatura, spazi singoli."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ß", "ss").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if t not in _DROP_TOKENS]
    return " ".join(tokens)


def core_name(name: str) -> str:
    """Come `normalize_name`, ma senza le parole generiche (city, town, real...)."""
    tokens = [t for t in normalize_name(name).split() if t not in _GENERIC_TOKENS]
    return " ".join(tokens)


def _load_aliases_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"global": {}, "leagues": {}}
    if not isinstance(data, dict):
        return {"global": {}, "leagues": {}}
    return data


@lru_cache(maxsize=4)
def load_aliases(path: str | None = None) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Ritorna (alias globali, alias per campionato) con chiavi gia' normalizzate."""
    data = _load_aliases_file(Path(path) if path else ALIASES_PATH)
    glob = {normalize_name(k): str(v) for k, v in (data.get("global") or {}).items() if normalize_name(k)}
    per_league: dict[str, dict[str, str]] = {}
    for code, mapping in (data.get("leagues") or {}).items():
        if not isinstance(mapping, Mapping):
            continue
        per_league[str(code)] = {normalize_name(k): str(v) for k, v in mapping.items() if normalize_name(k)}
    return glob, per_league


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _containment_score(api_norm: str, hist_norm: str) -> float:
    """Un nome contiene l'altro e le parole in piu' sono generiche: 0.9. Altrimenti 0."""
    a, b = api_norm.split(), hist_norm.split()
    if not a or not b or a == b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if not set(short).issubset(set(long_)):
        return 0.0
    extra = [t for t in long_ if t not in short]
    if extra and all(t in _GENERIC_TOKENS for t in extra):
        return 0.9
    return 0.0


def map_team_detail(
    league_code: str | None,
    api_name: str,
    history_names: Iterable[str],
    *,
    aliases_path: str | None = None,
) -> MappingResult:
    """Cerca il nome football-data per un nome API-Football, con dettaglio dei candidati."""
    names = [n for n in dict.fromkeys(history_names) if n]
    api_norm = normalize_name(api_name)
    if not api_norm or not names:
        return MappingResult(api_name, None, 0.0, "none")

    glob, per_league = load_aliases(aliases_path)
    by_norm = {normalize_name(n): n for n in names}

    # 1. alias (prima quello del campionato, poi quello globale)
    for table in (per_league.get(league_code or "", {}), glob):
        target = table.get(api_norm)
        if target:
            if target in by_norm.values():
                return MappingResult(api_name, target, 1.0, "alias", candidates=[(target, 1.0)])
            # alias verso un nome non presente nello storico: prova per forma normalizzata
            hit = by_norm.get(normalize_name(target))
            if hit:
                return MappingResult(api_name, hit, 0.98, "alias", candidates=[(hit, 0.98)])

    # 2. uguaglianza dopo normalizzazione
    if api_norm in by_norm:
        return MappingResult(api_name, by_norm[api_norm], 1.0, "exact", candidates=[(by_norm[api_norm], 1.0)])

    # 3. uguaglianza del nucleo (senza parole generiche) o contenimento
    api_core = core_name(api_name)
    scored: dict[str, float] = {}
    for hist in names:
        hist_norm = normalize_name(hist)
        score = 0.0
        if api_core and api_core == core_name(hist):
            score = 0.95
        score = max(score, _containment_score(api_norm, hist_norm))
        ratio = _similarity(api_norm, hist_norm)
        score = max(score, ratio)
        if api_core:
            score = max(score, _similarity(api_core, core_name(hist)) * 0.97)
        scored[hist] = round(score, 4)

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:5]
    best_name, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if best < MIN_CONFIDENCE:
        return MappingResult(api_name, None, best, "none", candidates=ranked)
    ambiguous = second >= MIN_CONFIDENCE and (best - second) < AMBIGUITY_GAP and best < 1.0
    method = "core" if best >= 0.95 else "fuzzy"
    if ambiguous:
        return MappingResult(api_name, best_name, min(best, 0.5), method, ambiguous=True, candidates=ranked)
    return MappingResult(api_name, best_name, best, method, candidates=ranked)


def map_team(
    league_code: str | None,
    api_name: str,
    history_names: Iterable[str],
) -> tuple[str | None, float]:
    """Nome football-data e confidenza (0-1). Nei casi ambigui la confidenza e' <= 0,5."""
    return map_team_detail(league_code, api_name, history_names).as_tuple()


def history_team_names(history) -> dict[str, set[str]]:
    """Nomi squadra per codice campionato da uno `History` di `football_data.load_history`."""
    out: dict[str, set[str]] = {}
    for m in history.matches:
        league = LEAGUE_BY_COMPETITION.get(m.competition)
        if league is None:
            continue
        bucket = out.setdefault(league.code, set())
        bucket.add(m.home_team)
        bucket.add(m.away_team)
    return out


def load_history_team_names(*, include_lockbox: bool = True) -> dict[str, set[str]]:
    """Carica i CSV (lockbox incluso: servono i nomi delle squadre attuali) e ritorna i nomi per campionato."""
    from app.services.cecchino_v4.history.football_data import load_history

    return history_team_names(load_history(include_lockbox=include_lockbox))
