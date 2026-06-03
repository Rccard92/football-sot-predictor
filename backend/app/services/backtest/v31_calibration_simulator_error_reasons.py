"""Motivi probabili errori predittivi in italiano."""

from __future__ import annotations

from typing import Any


def probable_reason(row: dict[str, Any]) -> str:
    pred = row.get("predicted_total_sot")
    actual = row.get("actual_total_sot")
    err = row.get("error")
    pb = row.get("predicted_bucket")
    ab = row.get("actual_bucket")
    trace = row.get("trace") or {}

    if pred is None or actual is None:
        return "Predizione o actual non disponibile."

    pred_f = float(pred)
    act_f = float(actual)
    e = float(err) if err is not None else pred_f - act_f

    if e < -2.5:
        if ab in ("high_total", "very_high_total") and pb in ("normal_total", "low_total"):
            return (
                "Il modello ha sottostimato: profilo pre-match medio, "
                "ma la partita è esplosa oltre lo storico (bucket alto)."
            )
        boost = trace.get("boost_applied") or 0
        if float(boost) < 0.3:
            return (
                "Possibile sottostima: boost dinamico insufficiente "
                "rispetto alla forza offensiva del match."
            )
        return "Possibile sottostima della forza offensiva o della fragilità difensiva avversaria."

    if e > 2.5:
        if trace.get("boost_reason", "").startswith("chaos") or float(trace.get("boost_applied") or 0) > 0.8:
            return (
                "Il modello ha sovrastimato: dati pre-match indicavano volume alto, "
                "ma il match si è chiuso tatticamente."
            )
        return "Possibile sovrastima del volume offensivo atteso pre-match."

    if abs(e) <= 1.0:
        return "Errore contenuto: predizione vicina al reale."

    if e < 0:
        return "Leggera sottostima; il totale reale ha superato la stima numerica."

    return "Leggera sovrastima; il totale reale è rimasto sotto la stima."
