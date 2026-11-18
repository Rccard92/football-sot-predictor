"""Campionati ammessi nel Diario analisi (decisione di Giovanni del 18/11/2026).

La lista e' il file campionati_ammessi.txt (righe "paese|campionato", con i commenti che spiegano ogni scelta):
fuori Europa fino alla 2a divisione, in Europa fino alla 3a, mai i campionati semiprofessionistici.
I campionati esclusi restano visibili nel resto del tool (Today, Bet Builder...): si tolgono solo dalla Tabella
del Diario e dai pronostici (non si aggiungono al diario). Un campionato nuovo si aggiunge a mano nel file.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

LEAGUES_FILE = Path(__file__).with_name("campionati_ammessi.txt")
NOT_ADMITTED_REASON = "Campionato non ammesso nel Diario"


def _norm(text: str | None) -> str:
    """Confronto senza maiuscole, spazi doppi e differenze di codifica degli accenti."""
    value = unicodedata.normalize("NFC", str(text or "")).strip().casefold()
    return " ".join(value.split())


def parse_leagues(text: str) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        country, league = line.split("|", 1)
        if country.strip() and league.strip():
            out.add((_norm(country), _norm(league)))
    return frozenset(out)


@lru_cache(maxsize=1)
def admitted_leagues() -> frozenset[tuple[str, str]]:
    return parse_leagues(LEAGUES_FILE.read_text(encoding="utf-8"))


def league_admitted(country: str | None, league: str | None) -> bool:
    return (_norm(country), _norm(league)) in admitted_leagues()
