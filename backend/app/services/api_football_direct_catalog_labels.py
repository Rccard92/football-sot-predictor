"""Etichette italiane manuali, tooltip e rilevamento metriche avanzate in path."""

from __future__ import annotations

import re
from typing import Any

# json_path (suffix o match) / chiave normalizzata → nome IT
MANUAL_NAME_IT: dict[str, str] = {
    "fixture.id": "ID partita API",
    "fixture.referee": "Arbitro",
    "fixture.date": "Data partita",
    "fixture.timestamp": "Timestamp partita",
    "fixture.timezone": "Fuso orario",
    "fixture.venue.id": "ID stadio",
    "fixture.venue.name": "Stadio",
    "fixture.venue.city": "Città stadio",
    "fixture.status.short": "Stato partita (codice)",
    "fixture.status.long": "Stato partita (testo)",
    "teams.home.id": "ID squadra casa",
    "teams.home.name": "Squadra casa",
    "teams.away.id": "ID squadra trasferta",
    "teams.away.name": "Squadra trasferta",
    "goals.home": "Goal squadra casa",
    "goals.away": "Goal squadra trasferta",
    'statistics["Shots on Goal"]': "Tiri in porta",
    'statistics["Total Shots"]': "Tiri totali",
    'statistics["Blocked Shots"]': "Tiri bloccati",
    'statistics["Shots insidebox"]': "Tiri dentro area",
    'statistics["Shots outsidebox"]': "Tiri fuori area",
    'statistics["Fouls"]': "Falli",
    'statistics["Corner Kicks"]': "Calci d'angolo",
    'statistics["Offsides"]': "Fuorigioco",
    'statistics["Ball Possession"]': "Possesso palla",
    'statistics["Yellow Cards"]': "Cartellini gialli",
    'statistics["Red Cards"]': "Cartellini rossi",
    'statistics["Goalkeeper Saves"]': "Parate portiere",
    'statistics["Total passes"]': "Passaggi totali",
    'statistics["Passes accurate"]': "Passaggi riusciti",
    'statistics["Passes %"]': "Precisione passaggi",
}

MANUAL_TOOLTIP_IT: dict[str, str] = {
    "Possesso palla": (
        "Percentuale approssimativa del tempo di possesso: non implica automaticamente più tiri in porta."
    ),
    "Passaggi chiave": (
        "Passaggi che hanno portato a un tiro: utili per creatività, ma dipendono da come l'API etichetta l'evento."
    ),
    "Rating giocatore": (
        "Voto sintetico del provider: è una sintesi, non un dato fisico misurato sul campo."
    ),
    "Tiri dentro area": "Tiri conclusi dall'interno dell'area di rigore: in genere occasioni più pericolose.",
    "Tiri fuori area": "Tiri dalla distanza: aiutano a capire il volume di tiro anche lontano dalla porta.",
    "Parate portiere": "Interventi del portiere su tiri verso la porta: correlato con i tiri in porta subiti.",
    "Quote bookmaker": "Prezzo offerto da un operatore su un mercato: utile per confronti, non per il modello SOT.",
    "Linea quota": "Soglia numerica del mercato (es. over/under su un totale): va letta insieme alla quota.",
    "Predictions provider": "Suggerimento statistico del provider: non è la nostra previsione SOT interna.",
    "Stato partita": "Codice breve (es. FT, NS): indica se la partita è finita o da giocare.",
    "Formazione": "Modulo e undici iniziale comunicati prima della partita.",
    "Sostituzioni": "Eventi di cambio durante la partita.",
    "Infortuni": "Segnalazioni di indisponibilità legate a squadra/giocatore.",
}


def _auto_name_it(json_path: str) -> str:
    """Traduzione leggibile automatica dal path."""
    tail = json_path.split(".")[-1] if "." in json_path else json_path
    tail = tail.split("[")[0]
    t = re.sub(r"[_\-]+", " ", tail).strip()
    if not t:
        return json_path
    return t[:1].upper() + t[1:]


def label_for_path(json_path: str) -> tuple[str, bool]:
    """(name_it, is_auto)."""
    if json_path in MANUAL_NAME_IT:
        return MANUAL_NAME_IT[json_path], False
    for k, v in MANUAL_NAME_IT.items():
        if json_path.endswith(k) or k in json_path:
            return v, False
    return _auto_name_it(json_path), True


def tooltip_for_name(name_it: str) -> str | None:
    return MANUAL_TOOLTIP_IT.get(name_it)


def advanced_metric_note(json_path: str, sample_value: Any) -> str | None:
    blob = f"{json_path} {sample_value}".lower()
    if re.search(r"\bxg\b|expected\s*goals|expected_goals|xga", blob):
        return "Trovato direttamente nella response API (metrica avanzata)."
    if re.search(r"big\s*chance|big_chances", blob):
        return "Trovato direttamente nella response API (metrica avanzata)."
    if re.search(r"touches?\s*in|touches_in", blob):
        return "Trovato direttamente nella response API (metrica avanzata)."
    if re.search(r"pressure|pressing|ppda", blob):
        return "Trovato direttamente nella response API (metrica avanzata)."
    return None


def description_it(name_it: str, json_path: str, endpoint: str) -> str:
    return f"Campo diretto dall'endpoint `{endpoint}`: {name_it} (`{json_path}`)."
