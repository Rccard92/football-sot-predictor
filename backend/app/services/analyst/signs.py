"""Segni della scheda del Diario (capitolato di Giovanni del 24/11/2026, modifiche 1, 2, 3 e 16).

- Q, la quota usata: la seconda lettura Bet365 a 75' dal via se c'e' per quel segno, altrimenti la quota del mattino.
  Stati, colori, R1, valore e conteggi si calcolano su Q; le giocate gia' salvate non cambiano.
- Probabilita' del book senza margine: 1/Q diviso la somma di 1/q del mercato (doppia chance dall'1X2).
- Probabilita' Cecchino = 1 / quota Cecchino; valore secondo il Cecchino = Q / quota Cecchino - 1.
- Quattro stati, provati in quest'ordine (vale il primo si'):
  1. fuori fascia: quota fuori dai limiti del sito o segno da evitare (nascosto dietro "altri N segni");
  2. bloccato, sempre con il motivo: R1 (Q sotto la quota Cecchino x 0,90), R2 (casa con meno di 4 punti su 15 in
     casa su 1 e 1X; almeno 3 volte 0-0 al PT su Over PT 0,5), regole del sito ("squilibrio: niente Under");
  3. da verificare: valore secondo il Cecchino sopra +30% (di solito e' un errore del modello);
  4. giocabile: tutti gli altri.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from app.services.analyst.novig import novig_prob
from app.services.analyst.rules import quota_warnings

STATE_OUT = "out"
STATE_BLOCKED = "blocked"
STATE_CHECK = "check"
STATE_PLAYABLE = "playable"
STATE_LABELS = {STATE_OUT: "fuori fascia", STATE_BLOCKED: "bloccato", STATE_CHECK: "da verificare", STATE_PLAYABLE: "giocabile"}

# gruppi di "Segni · decidi qui" nell'ordine del capitolato; dentro il gruppo l'ordine del sito (MARKETS)
SIGN_GROUPS: dict[str, str] = {
    "HOME": "ESITO FINALE",
    "DRAW": "ESITO FINALE",
    "AWAY": "ESITO FINALE",
    "ONE_X": "DOPPIA CHANCE",
    "X_TWO": "DOPPIA CHANCE",
    "ONE_TWO": "DOPPIA CHANCE",
    "UNDER_0_5": "UNDER / OVER",
    "UNDER_1_5": "UNDER / OVER",
    "UNDER_2_5": "UNDER / OVER",
    "UNDER_3_5": "UNDER / OVER",
    "OVER_0_5": "UNDER / OVER",
    "OVER_1_5": "UNDER / OVER",
    "OVER_2_5": "UNDER / OVER",
    "OVER_3_5": "UNDER / OVER",
    "HOME_PT": "PRIMO TEMPO",
    "DRAW_PT": "PRIMO TEMPO",
    "AWAY_PT": "PRIMO TEMPO",
    "UNDER_PT_0_5": "GOL PRIMO TEMPO",
    "UNDER_PT_1_5": "GOL PRIMO TEMPO",
    "OVER_PT_0_5": "GOL PRIMO TEMPO",
    "OVER_PT_1_5": "GOL PRIMO TEMPO",
}
GROUP_ORDER = ("ESITO FINALE", "DOPPIA CHANCE", "UNDER / OVER", "PRIMO TEMPO", "GOL PRIMO TEMPO")
SECOND_READ_BEFORE = timedelta(minutes=75)


def half_up(value: float) -> int:
    """Arrotondamento come a scuola (12,5 -> 13), non quello "del banchiere" di round()."""
    return int(math.floor(value + 0.5))


def used_quotes(quotes: list[dict[str, Any]], odds_move: dict[str, Any] | None, odds_at: str | None) -> dict[str, dict[str, Any]]:
    """Q per ogni segno (modifica 1): {chiave: {q, at, source, morning, change}}.

    source "t75" = seconda lettura (con la quota del mattino e la variazione), "morning" = quota delle 6."""
    later: dict[str, dict[str, Any]] = {}
    if (odds_move or {}).get("status") == "ok":
        later = {str(m.get("key")): m for m in (odds_move or {}).get("markets") or [] if m.get("later_quota")}
    read_at = (odds_move or {}).get("read_at")
    out: dict[str, dict[str, Any]] = {}
    for q in quotes:
        key, morning = q["key"], q.get("quota")
        m = later.get(key)
        if m is not None:
            value = float(m["later_quota"])
            out[key] = {
                "q": value,
                "at": read_at,
                "source": "t75",
                "morning": morning,
                "change": round(value / float(morning) - 1, 4) if morning else None,
            }
        else:
            out[key] = {"q": morning, "at": odds_at, "source": "morning", "morning": morning, "change": None}
    return out


def second_read_due(kickoff: str | None) -> str | None:
    """Ora prevista della seconda lettura: 75 minuti prima del via."""
    if not kickoff:
        return None
    try:
        return (datetime.fromisoformat(kickoff) - SECOND_READ_BEFORE).isoformat()
    except ValueError:
        return None


def _block_reasons(rules: dict[str, Any], key: str, q: float | None, qc: float | None, home_block: dict[str, Any] | None, codes: set[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Motivi di blocco e avvisi (R2 su 1 e 1X resta un avviso finche' non si accende dalle Regole)."""
    blocked: list[dict[str, str]] = []
    notes: list[dict[str, str]] = []
    if "under_squilibrio" in codes:
        blocked.append({"code": "under_squilibrio", "rule": "sito", "text": "squilibrio: niente Under", "short": "squilibrio"})
    pct = float(rules.get("r1_pct", 10))
    if rules.get("r1_block", True) and q and qc and q < qc * (1 - pct / 100):
        n = half_up((1 - q / qc) * 100)
        blocked.append({"code": "r1", "rule": "R1", "text": f"R1 · book {n}% sotto il Cecchino", "short": "R1"})
    block = home_block or {}
    if block.get("enough"):
        if key in ("HOME", "ONE_X") and int(block.get("points", 99)) < int(rules.get("r2_home_points_min", 4)):
            reason = {
                "code": "r2_casa",
                "rule": "R2",
                "text": f"R2 · casa {block['points']} punti su {block.get('max_points', 15)} in casa",
                "short": "R2",
            }
            (blocked if rules.get("r2_home_block") else notes).append(reason)
        if key == "OVER_PT_0_5":
            results = block.get("results") or []
            zeros = sum(1 for r in results if r.get("ht") == "0-0")
            if zeros >= int(rules.get("r2_pt_zero_min", 3)):
                reason = {"code": "r2_pt", "rule": "R2", "text": f"R2 · casa {zeros} volte 0-0 al PT su {len(results)}", "short": "R2"}
                (blocked if rules.get("r2_pt_block", True) else notes).append(reason)
    return blocked, notes


def sign_state(
    rules: dict[str, Any],
    key: str,
    q: float | None,
    qc: float | None,
    match_type: str | None,
    home_block: dict[str, Any] | None,
) -> dict[str, Any]:
    """Stato del segno con i motivi (modifica 3)."""
    warnings = quota_warnings(rules, key, q, qc, match_type)
    codes = {w["code"] for w in warnings}
    value = round(q / qc - 1, 4) if q and qc else None
    base = {"value": value, "notes": []}
    if "segno_da_evitare" in codes:
        return {**base, "state": STATE_OUT, "reasons": [{"code": "segno_da_evitare", "rule": "sito", "text": "segno da evitare", "short": "da evitare"}]}
    fascia = [w for w in warnings if w["code"] in ("sotto_minimo", "sopra_massimo")]
    if fascia:
        return {**base, "state": STATE_OUT, "reasons": [{**w, "rule": "sito", "short": "fuori fascia"} for w in fascia]}
    blocked, notes = _block_reasons(rules, key, q, qc, home_block, codes)
    base["notes"] = notes
    if blocked:
        return {**base, "state": STATE_BLOCKED, "reasons": blocked}
    if value is not None and value > float(rules.get("anomaly_pct", 30)) / 100:
        return {
            **base,
            "state": STATE_CHECK,
            "reasons": [{"code": "anomalia", "rule": "controllo", "text": f"anomalia >{int(rules.get('anomaly_pct', 30))}%: probabile errore del modello", "short": "anomalia"}],
        }
    return {**base, "state": STATE_PLAYABLE, "reasons": []}


def evaluate_row(rules: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Tutti i segni della gara con Q, probabilita', valore e stato; conteggi per la testata e la lista."""
    used = used_quotes(row.get("quotes") or [], row.get("odds_move"), row.get("odds_checked_at"))
    book = {k: v["q"] for k, v in used.items() if v.get("q")}
    home_block = (row.get("blocks") or {}).get("forma_casa")
    signs = []
    counts = {STATE_PLAYABLE: 0, STATE_CHECK: 0, STATE_BLOCKED: 0, STATE_OUT: 0}
    for q in row.get("quotes") or []:
        u = used.get(q["key"]) or {}
        qv, qc = u.get("q"), q.get("quota_cecchino")
        st = sign_state(rules, q["key"], qv, qc, row.get("match_type"), home_block)
        counts[st["state"]] += 1
        p_book = novig_prob(book, q["key"]) if qv else None
        signs.append(
            {
                "key": q["key"],
                "label": q["label"],
                "group": SIGN_GROUPS.get(q["key"], "ALTRI"),
                "q": qv,
                "q_at": u.get("at"),
                "q_source": u.get("source"),
                "morning": u.get("morning"),
                "change": u.get("change"),
                "prob_book": p_book,
                "quota_cecchino": qc,
                "prob_cecchino": round(1 / qc, 4) if qc else None,
                **st,
            }
        )
    second = row.get("odds_move") or {}
    t75 = second.get("status") == "ok"
    return {
        "signs": signs,
        "counts": counts,
        "odds_at": row.get("odds_checked_at"),
        "second_read": {"done": t75, "at": second.get("read_at") if t75 else None, "due": second_read_due(row.get("kickoff"))},
    }


def sign_of(evaluation: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((s for s in evaluation.get("signs") or [] if s["key"] == key), None)
