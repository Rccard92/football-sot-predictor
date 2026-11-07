"""Regole di acquisto del Diario analisi (dal 07/11/2026): quote minime e massime per segno e tipo di partita.

Dal PDF di Giovanni "Gare sbagliate" (06/11/2026) e dai suoi audio (06-07/11/2026):
- ogni segno ha una fascia di quota: sotto il minimo o sopra il massimo non c'e' piu' valore;
- per gli Under la quota del book deve valere almeno la quota Cecchino x 1,15;
- in una partita di squilibrio niente Under;
- alcuni segni non si comprano da singola;
- la checklist va compilata almeno per 5 punti su 16.
Il tool NON blocca: avvisa, e l'ultima parola resta all'analista (audio del 07/11). La giocata salvata fuori
regola resta segnata, cosi' il Report confronta dentro e fuori regola.

Il tipo di partita (equilibrio, squilibrio, scala) e' la formula semplice dell'analisi manuale e vale SOLO in
questa pagina: non entra in V2.5, V3 o negli altri motori (richiesta di Giovanni, 06/11).
Le soglie si possono cambiare dagli amministratori (tabella analyst_settings, chiave "rules").
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.analyst_journal import AnalystSetting

RULES_KEY = "rules"

_RANGE_LOW = {"min": 1.30, "max": 1.55}
DEFAULT_RULES: dict[str, Any] = {
    "checklist_min": 5,
    "under_no_squilibrio": True,
    "markets": {
        "UNDER_3_5": {"min": 1.50, "cecchino_mult": 1.15},
        "UNDER_2_5": {"min": 2.00, "cecchino_mult": 1.15},
        "UNDER_PT_1_5": {"cecchino_mult": 1.15},
        "HOME": dict(_RANGE_LOW),
        "AWAY": dict(_RANGE_LOW),
        "ONE_X": dict(_RANGE_LOW),
        "X_TWO": dict(_RANGE_LOW),
        "ONE_TWO": dict(_RANGE_LOW),
        "OVER_1_5": dict(_RANGE_LOW),
        "OVER_PT_0_5": dict(_RANGE_LOW),
        "DRAW": {"min": 3.00, "max": 3.80},
        "DRAW_PT": {"min": 1.70, "max": 2.50},
        "OVER_2_5": {"min": 1.70, "max": 2.00},
        "UNDER_1_5": {"avoid": True},
        "UNDER_PT_0_5": {"avoid": True},
        "OVER_3_5": {"avoid": True},
        "HOME_PT": {"avoid": True},
        "AWAY_PT": {"avoid": True},
        "OVER_PT_1_5": {"avoid": True},
    },
}

# codici degli avvisi (gli stessi diventano i motivi d'errore automatici delle gare sbagliate)
CODE_LABELS = {
    "sotto_minimo": "Sotto la quota minima",
    "sopra_massimo": "Oltre la quota massima",
    "segno_da_evitare": "Segno da evitare",
    "under_squilibrio": "Under in squilibrio",
    "checklist_incompleta": "Checklist incompleta",
}
QUOTA_CODES = ("sotto_minimo", "sopra_massimo", "segno_da_evitare", "under_squilibrio")
# motivi che sceglie chi rivede la giocata
MANUAL_TAGS = {
    "motivo_generico": "Motivo generico, non convincente",
    "lettura_sbagliata": "Lettura sbagliata della partita",
    "imprevisto": "Imprevisto (espulsione, infortunio, rigore)",
    "altro": "Altro",
}

MATCH_TYPES = ("Equilibrio", "Squilibrio", "Scala 1X", "Scala X2")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def match_type(home: Any, draw: Any, away: Any) -> str | None:
    """Tipo di partita dalle quote 1-X-2 (regola di Giovanni).

    Equilibrio: la piu' alta tra 1 e 2 e' meno di 1,5 volte la piu' bassa e la X e' al massimo 3,60.
    Squilibrio: la X e' almeno 4,00 e una tra 1 e 2 e' almeno il doppio dell'altra.
    Altrimenti scala: 1X se la favorita gioca in casa, X2 se gioca fuori."""
    h, d, a = _num(home), _num(draw), _num(away)
    if h is None or d is None or a is None:
        return None
    low, high = min(h, a), max(h, a)
    if high < 1.5 * low and d <= 3.60:
        return "Equilibrio"
    if d >= 4.00 and high >= 2 * low:
        return "Squilibrio"
    if h < a:
        return "Scala 1X"
    if a < h:
        return "Scala X2"
    return None


def load_rules(db: Session) -> dict[str, Any]:
    row = db.get(AnalystSetting, RULES_KEY)
    rules = copy.deepcopy(DEFAULT_RULES)
    saved = row.value_json if row is not None and isinstance(row.value_json, dict) else {}
    for key in ("checklist_min", "under_no_squilibrio"):
        if key in saved:
            rules[key] = saved[key]
    if isinstance(saved.get("markets"), dict):
        rules["markets"] = saved["markets"]
    return rules


def clean_rules(raw: Any, market_keys: set[str]) -> dict[str, Any]:
    """Regole inviate dall'amministratore: solo numeri sensati e segni conosciuti."""
    if not isinstance(raw, dict):
        raise ValueError("Regole non valide")
    out: dict[str, Any] = {"markets": {}}
    try:
        out["checklist_min"] = max(0, min(16, int(raw.get("checklist_min", DEFAULT_RULES["checklist_min"]))))
    except (TypeError, ValueError):
        raise ValueError("Punti minimi della checklist non validi") from None
    out["under_no_squilibrio"] = bool(raw.get("under_no_squilibrio", True))
    for key, rule in (raw.get("markets") or {}).items():
        if key not in market_keys or not isinstance(rule, dict):
            continue
        clean: dict[str, Any] = {}
        if rule.get("avoid"):
            clean["avoid"] = True
        for field in ("min", "max", "cecchino_mult"):
            value = _num(rule.get(field))
            if value is not None:
                if value > 100:
                    raise ValueError(f"{key}: valore troppo alto")
                clean[field] = round(value, 2)
        if "min" in clean and "max" in clean and clean["min"] > clean["max"]:
            raise ValueError(f"{key}: il minimo supera il massimo")
        if clean:
            out["markets"][key] = clean
    return out


def save_rules(db: Session, rules: dict[str, Any], user_id: int | None) -> None:
    row = db.get(AnalystSetting, RULES_KEY)
    if row is None:
        row = AnalystSetting(key=RULES_KEY, value_json=rules, updated_by=user_id)
        db.add(row)
    else:
        row.value_json = rules
        row.updated_by = user_id
        row.updated_at = datetime.now(timezone.utc)


def _q(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def quota_warnings(
    rules: dict[str, Any],
    market_key: str,
    quota: Any,
    quota_cecchino: Any = None,
    kind: str | None = None,
) -> list[dict[str, str]]:
    """Avvisi sulla quota di un segno: vuoto se si puo' comprare (o se per quel segno non c'e' una regola)."""
    q = _num(quota)
    rule = (rules.get("markets") or {}).get(market_key) or {}
    out: list[dict[str, str]] = []
    if rule.get("avoid"):
        out.append({"code": "segno_da_evitare", "text": "Segno da evitare: non si compra da singola"})
    if q is not None and not rule.get("avoid"):
        floor, why = _num(rule.get("min")), None
        if floor is not None:
            why = f"minimo {_q(floor)}"
        mult, qc = _num(rule.get("cecchino_mult")), _num(quota_cecchino)
        if mult is not None and qc is not None and qc * mult > (floor or 0):
            floor = round(qc * mult, 2)
            why = f"quota Cecchino {_q(qc)} × {_q(mult).rstrip('0').rstrip(',')}"
        if floor is not None and q < floor:
            out.append({"code": "sotto_minimo", "text": f"Sotto la quota minima {_q(floor)} ({why})"})
        top = _num(rule.get("max"))
        if top is not None and q > top:
            out.append({"code": "sopra_massimo", "text": f"Oltre la quota massima {_q(top)}"})
    if kind == "Squilibrio" and rules.get("under_no_squilibrio", True) and market_key.startswith("UNDER"):
        out.append({"code": "under_squilibrio", "text": "Partita di squilibrio: niente Under"})
    return out


def quota_status(rules: dict[str, Any], market_key: str, quota: Any, quota_cecchino: Any = None, kind: str | None = None) -> str:
    """Per i colori della Tabella: ok (si compra), out (fuori regola), avoid (segno da evitare), none (nessuna regola)."""
    rule = (rules.get("markets") or {}).get(market_key)
    warnings = quota_warnings(rules, market_key, quota, quota_cecchino, kind)
    if any(w["code"] == "segno_da_evitare" for w in warnings):
        return "avoid"
    if warnings:
        return "out"
    if not rule or _num(quota) is None:
        return "none"
    return "ok"


def checklist_count(checklist: Any) -> int:
    if not isinstance(checklist, dict):
        return 0
    return sum(1 for item in checklist.values() if isinstance(item, dict) and item.get("value"))


def checklist_warning(rules: dict[str, Any], checklist: Any) -> dict[str, str] | None:
    need = int(rules.get("checklist_min") or 0)
    have = checklist_count(checklist)
    if need and have < need:
        return {"code": "checklist_incompleta", "text": f"Checklist compilata per {have} punti su 16: ne servono almeno {need}"}
    return None


def fixture_context(fx: Any, market_key: str) -> dict[str, Any]:
    """Quota Cecchino del segno e tipo di partita, dal pannello KPI salvato da Today."""
    by_key: dict[str, dict[str, Any]] = {}
    for row in ((getattr(fx, "kpi_panel_json", None) or {}).get("rows") or []):
        if isinstance(row, dict) and row.get("market_key"):
            by_key[str(row["market_key"])] = row
    kind = match_type(*((by_key.get(k) or {}).get("quota_book") for k in ("HOME", "DRAW", "AWAY")))
    row = by_key.get(market_key) or {}
    return {"match_type": kind, "quota_cecchino": _num(row.get("quota_cecchino")), "quota_book": _num(row.get("quota_book"))}


def entry_check(rules: dict[str, Any], fx: Any, market_key: str, quota: Any) -> dict[str, Any]:
    """Controllo salvato sulla giocata quando la si salva: resta com'era anche se poi le regole cambiano."""
    ctx = fixture_context(fx, market_key) if fx is not None else {"match_type": None, "quota_cecchino": None}
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "match_type": ctx["match_type"],
        "quota_cecchino": ctx["quota_cecchino"],
        "warnings": quota_warnings(rules, market_key, quota, ctx["quota_cecchino"], ctx["match_type"]),
    }


def entry_codes(entry: Any, rules: dict[str, Any], review_tags: set[str] | None = None) -> set[str]:
    """Motivi d'errore di una giocata: avvisi salvati + checklist (letta ora: si chiude al calcio d'inizio) + revisioni."""
    codes = {w.get("code") for w in ((entry.rule_check_json or {}).get("warnings") or []) if isinstance(w, dict)}
    if checklist_warning(rules, entry.checklist_json):
        codes.add("checklist_incompleta")
    codes |= review_tags or set()
    return {c for c in codes if c}
