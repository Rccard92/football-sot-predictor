"""Cache su disco dei risultati intermedi pesanti, in `backend/.runtime/v4/`
(ignorata da git). La cache non cambia nessun numero: la chiave include
l'impronta dei dati che hanno prodotto il risultato."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Any, Callable

from app.services.cecchino_v3.data import MatchRecord

RUNTIME_DIR = Path(__file__).resolve().parents[4] / ".runtime" / "v4"


def matches_digest(matches: list[MatchRecord]) -> str:
    """Impronta dei dati che entrano nel walk-forward (id, giorno, squadre, gol, tiri)."""
    h = hashlib.sha256()
    for m in matches:
        h.update(
            f"{m.lab_match_id}|{m.day}|{m.competition}|{m.season_label}|{m.home_team}|{m.away_team}|"
            f"{m.ft_home}|{m.ft_away}|{m.ht_home}|{m.ht_away}|{m.home_shots}|{m.away_shots}|"
            f"{m.home_sot}|{m.away_sot}\n".encode("utf-8")
        )
    return h.hexdigest()[:16]


def safe_name(name: str) -> str:
    """Nome di file valido su ogni sistema (niente `|`, `=`, `/`, spazi)."""
    return "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in name)


def cached(name: str, compute: Callable[[], Any], *, enabled: bool = True) -> Any:
    """Legge `name.pkl` dalla cache se esiste, altrimenti calcola e salva."""
    if not enabled:
        return compute()
    path = RUNTIME_DIR / f"{safe_name(name)}.pkl"
    if path.exists():
        try:
            with path.open("rb") as fh:
                return pickle.load(fh)
        except Exception:  # noqa: BLE001 - cache corrotta: si ricalcola
            path.unlink(missing_ok=True)
    value = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    return value
