"""Spiegazioni in italiano per il value selector v3.0 (solo pre-match, anti-leakage)."""

from __future__ import annotations

from typing import Any

from app.services.backtest.sot_v30_value_selector_logic import V30Selection

REASON_CODE_IT: dict[str, str] = {
    "V21_LINE_6_5": "La v2.1 porta il match su una linea 6.5, considerata la fascia più sicura.",
    "SAFE_LINE": "La linea scelta è conservativa rispetto alla previsione.",
    "V11_V21_CONSENSUS": "v1.1 e v2.1 sono allineate nella stessa direzione.",
    "MACRO_NOT_OVERHEATED": "Le macro non risultano surriscaldate: il modello non sta forzando una previsione troppo alta.",
    "LINEUP_OK": "Le formazioni disponibili non riducono in modo significativo il profilo SOT.",
    "INJURY_INDEX_OK": "Il profilo infortuni/indisponibili è accettabile per la giocata.",
    "MEDIUM_CONFIDENCE": "La confidence v2.1 non è al massimo: la giocata resta borderline.",
    "PREMIUM_7_5": "Profilo premium sulla linea 7.5 con filtri stringenti superati.",
    "STRONG_PREDICTION": "La previsione v2.1 è abbastanza alta per la linea premium.",
    "MACRO_CONTROLLED": "Le macro restano in un range controllato per la 7.5.",
    "NO_OVERHEAT": "Nessun segnale di surriscaldamento macro sul ritmo/qualità occasioni.",
}

NO_BET_REASON_IT: dict[str, str] = {
    "V21_NOT_AVAILABLE": "La v2.1 non è disponibile per questa partita.",
    "LINE_TOO_HIGH": "La linea proposta dalla v2.1 è troppo alta per il selettore.",
    "LINE_5_5_EXCLUDED": "La linea 5.5 viene esclusa dalla v3.0 attuale perché non offre abbastanza valore nel framework del selettore.",
    "TOO_MANY_WARNINGS": "Ci sono troppi warning sui dati o sul contesto, quindi la giocata viene esclusa.",
    "FALLBACK_TOO_HIGH": "Troppi fallback nei dati v2.1: profilo non abbastanza affidabile.",
    "DATA_QUALITY_LOW": "Qualità dati insufficiente (mapping o lineup).",
    "MACRO_OVERHEAT": "Le macro sono troppo spinte: il modello teme una sovrastima della partita.",
    "V21_V11_GAP_TOO_HIGH": "La distanza tra v2.1 e v1.1 è troppo alta, quindi la previsione non è abbastanza stabile.",
    "V21_PRED_TOO_LOW": "La previsione v2.1 è troppo bassa per giocare la linea 6.5.",
    "V21_PRED_TOO_HIGH": "La previsione v2.1 è troppo alta: rischio di profilo irrealistico.",
    "LINEUP_WEAK": "Le formazioni non sono abbastanza solide per confermare la giocata.",
    "INJURY_PLAYER_LAYER_WEAK": "Assenze e player layer insieme penalizzano troppo il profilo offensivo.",
    "V21_NOT_GIOCA": "La v2.1 non consiglia di giocare: la 7.5 non è attivabile.",
    "V11_REQUIRED_FOR_7_5": "Per la 7.5 serve anche il consenso della v1.1.",
    "V21_PRED_TOO_LOW_FOR_7_5": "La previsione v2.1 non è abbastanza alta per rendere giocabile la linea 7.5.",
    "V11_PRED_TOO_LOW_FOR_7_5": "La v1.1 è troppo prudente per confermare una giocata sulla 7.5.",
    "CONFIDENCE_LOW": "La confidence v2.1 è bassa: la 7.5 non è premium.",
    "MACRO_CONTROLLED_FAIL": "Le macro non restano nel range controllato richiesto per la 7.5.",
    "NO_OVERHEAT_FAIL": "I controlli anti-surriscaldamento macro non sono superati.",
    "OFFENSE_TOO_HIGH": "La macro di produzione offensiva è troppo spinta.",
    "INJURIES_LOW": "L'indice indisponibili è troppo basso per una 7.5 premium.",
    "UNSUPPORTED_LINE": "Linea non supportata dal selettore v3.0.",
}

CONFIDENCE_TIER_IT: dict[str, str] = {
    "strong": "strong (profilo solido)",
    "medium": "medium (profilo discreto)",
    "weak": "weak (profilo fragile)",
    "no_bet": "nessuna giocata",
}

WARNING_SUMMARY_IT: dict[str, str] = {
    "top_shooter_only_bench": "tiratore chiave solo in panchina",
    "split_fallback": "split casa/trasferta con fallback",
    "low_sample": "campione storico ridotto",
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_sot(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _fmt_line(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v - round(v)) < 0.01:
        return str(int(round(v)))
    return f"{v:.1f}"


def injury_phrase(
    injuries_avg: float | None,
    player_layer_avg: float | None,
) -> str:
    if injuries_avg is not None and injuries_avg >= 0.90:
        return "Le assenze non sembrano penalizzare in modo rilevante la produzione SOT."
    if injuries_avg is not None and injuries_avg < 0.90 and (player_layer_avg or 0) >= 1.00:
        return (
            "Ci sono assenze, ma il profilo dei giocatori disponibili compensa parzialmente l'impatto."
        )
    if injuries_avg is not None and injuries_avg < 0.85 and (player_layer_avg or 0) < 1.00:
        return "Le assenze riducono il profilo offensivo e il modello preferisce evitare."
    return "Il profilo infortuni/indisponibili è nel range atteso."


def _macro_from_context(pre_match_context: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    snap = trace.get("macro_snapshot") or {}
    macros = pre_match_context.get("macros") or {}
    out = dict(macros)
    for k, v in snap.items():
        if v is not None:
            out[k] = v
    return out


def extract_important_absence_names(
    explanation_v21: dict[str, Any] | None,
    *,
    max_names: int = 3,
) -> list[str]:
    if not isinstance(explanation_v21, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for side in ("home", "away"):
        side_data = explanation_v21.get(side)
        if not isinstance(side_data, dict):
            continue
        macros = side_data.get("macros")
        if not isinstance(macros, list):
            continue
        for macro in macros:
            if not isinstance(macro, dict) or macro.get("key") != "injuries_unavailable":
                continue
            details = macro.get("details") or macro.get("trace") or {}
            if isinstance(details, dict):
                inner = details.get("details") if isinstance(details.get("details"), dict) else details
                absences = inner.get("important_absences") if isinstance(inner, dict) else []
                if not isinstance(absences, list):
                    continue
                for item in absences:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("player_name") or "").strip()
                    if name and name not in seen:
                        seen.add(name)
                        names.append(name)
                        if len(names) >= max_names:
                            return names
    return names


def phrase_for_code(code: str, injuries_avg: float | None, player_layer_avg: float | None) -> str:
    if code == "INJURY_INDEX_OK":
        return injury_phrase(injuries_avg, player_layer_avg)
    return REASON_CODE_IT.get(code) or NO_BET_REASON_IT.get(code) or code.replace("_", " ").lower()


def _short_reason_play(codes: list[str], line: float | None) -> str:
    if "V11_V21_CONSENSUS" in codes and "SAFE_LINE" in codes:
        return "Linea safe + consenso modelli"
    if line == 7.5 or "PREMIUM_7_5" in codes:
        return "7.5 premium confermata"
    if "MACRO_NOT_OVERHEATED" in codes:
        return "Linea safe, macro OK"
    if "V21_LINE_6_5" in codes:
        return "Linea 6.5 safe"
    return "Profilo selezionato positivo"


def _short_reason_no_bet(reasons: list[str]) -> str:
    primary = reasons[0] if reasons else ""
    short_map = {
        "V11_PRED_TOO_LOW_FOR_7_5": "v1.1 non conferma 7.5",
        "V21_PRED_TOO_LOW_FOR_7_5": "7.5 non premium",
        "MACRO_OVERHEAT": "Macro troppo spinte",
        "V21_V11_GAP_TOO_HIGH": "Gap v2.1–v1.1 alto",
        "TOO_MANY_WARNINGS": "Troppi warning",
        "LINE_5_5_EXCLUDED": "Linea 5.5 esclusa",
        "CONFIDENCE_LOW": "Confidence bassa",
        "INJURIES_LOW": "Indisponibili penalizzanti",
        "LINEUP_WEAK": "Formazioni deboli",
        "INJURY_PLAYER_LAYER_WEAK": "Assenze + player layer",
        "V21_PRED_TOO_LOW": "Previsione troppo bassa",
        "V21_NOT_GIOCA": "v2.1 non gioca",
    }
    return short_map.get(primary, NO_BET_REASON_IT.get(primary, "Nessuna giocata")[:48])


def _warning_notes_human(warnings: list[str], warning_count: int) -> list[str]:
    notes: list[str] = []
    for w in warnings[:5]:
        wstr = str(w).strip()
        if not wstr:
            continue
        label = WARNING_SUMMARY_IT.get(wstr, wstr.replace("_", " "))
        notes.append(f"Warning: {label}.")
    if warning_count > len(warnings) and warning_count > 0:
        notes.append(f"Totale {warning_count} warning sul contesto v2.1.")
    return notes


def build_human_explanation(
    pre_match_context: dict[str, Any],
    selection: V30Selection,
    trace: dict[str, Any],
    *,
    explanation_v21: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Genera spiegazione leggibile senza usare actuals/outcome."""
    v11 = pre_match_context.get("v1_1") or {}
    v21 = pre_match_context.get("v2_1") or {}
    macros = _macro_from_context(pre_match_context, trace)

    v11_pt = _num(v11.get("predicted_total_sot"))
    v21_pt = _num(v21.get("predicted_total_sot"))
    v21_line = _num(v21.get("cautious_line"))
    gap = round(v21_pt - v11_pt, 2) if v11_pt is not None and v21_pt is not None else None

    line = selection.line
    decision = selection.decision
    tier = selection.confidence_tier
    codes = list(selection.reason_codes or [])
    no_bet = list(selection.no_bet_reasons or [])

    warnings = list(v21.get("warnings") or [])
    warning_count = int((trace.get("inputs") or {}).get("warning_count") or len(warnings))

    wmm = _num(macros.get("weighted_macro_multiplier_avg"))
    lineups = _num(macros.get("lineups_avg"))
    injuries = _num(macros.get("injuries_unavailable_avg"))
    player_layer = _num(macros.get("player_layer_avg"))

    absence_names = extract_important_absence_names(explanation_v21)

    data_used = {
        "v1_1_predicted_total_sot": v11_pt,
        "v2_1_predicted_total_sot": v21_pt,
        "prediction_gap": gap,
        "v2_1_cautious_line": v21_line,
        "selected_line": line,
        "confidence_tier": tier,
        "weighted_macro_multiplier_avg": wmm,
        "lineups_avg": lineups,
        "injuries_unavailable_avg": injuries,
        "player_layer_avg": player_layer,
        "warning_count": warning_count,
    }

    key_factors: list[str] = []
    warning_notes = _warning_notes_human(warnings, warning_count)

    for code in codes:
        phrase = phrase_for_code(code, injuries, player_layer)
        if phrase and phrase not in key_factors:
            key_factors.append(phrase[:120])

    if absence_names:
        key_factors.append(f"Assenze rilevanti: {', '.join(absence_names)}.")

    totals_phrase = ""
    if v11_pt is not None and v21_pt is not None:
        totals_phrase = (
            f"v1.1 stima {_fmt_sot(v11_pt)} SOT e v2.1 stima {_fmt_sot(v21_pt)} SOT"
        )
        if gap is not None:
            totals_phrase += f"; il gap è {gap:+.2f}."
    elif v21_pt is not None:
        totals_phrase = f"v2.1 stima {_fmt_sot(v21_pt)} SOT totali."

    margin_phrase = ""
    if line is not None and v21_pt is not None:
        margin = v21_pt - float(line)
        if margin > 0:
            margin_phrase = (
                f"La linea {_fmt_line(line)} lascia circa {_fmt_sot(margin)} SOT di margine "
                f"rispetto alla previsione v2.1."
            )

    confidence_reason = (
        f"Confidence {CONFIDENCE_TIER_IT.get(tier, tier)}."
        if tier != "no_bet"
        else "Nessuna confidence: partita non giocata."
    )

    risk_reason = ""
    line_reason = margin_phrase or (
        f"Linea {_fmt_line(line)} selezionata dal profilo {selection.profile}."
        if line is not None
        else ""
    )

    if decision == "GIOCA" and line is not None:
        headline = f"Giocata proposta: Over {_fmt_line(line)} SOT"
        decision_reason = (
            f"Entrambi i modelli principali supportano la direzione: {totals_phrase}"
            if "V11_V21_CONSENSUS" in codes and totals_phrase
            else totals_phrase or "I modelli di riferimento supportano la linea scelta."
        )
        if wmm is not None and wmm <= 1.15:
            risk_reason = "Le macro non risultano surriscaldate e il profilo resta controllato."
        elif gap is not None and abs(gap) <= 0.5:
            risk_reason = f"Il gap tra v1.1 e v2.1 è contenuto ({gap:+.2f})."
        else:
            risk_reason = "Restano alcuni segnali da monitorare, ma non bloccanti per la giocata."

        if not key_factors:
            key_factors = [
                "Consenso modelli" if "V11_V21_CONSENSUS" in codes else "Previsione v2.1",
                f"Linea {_fmt_line(line)}",
            ]
            if "LINEUP_OK" in codes:
                key_factors.append("Formazioni OK")
            if "MACRO_NOT_OVERHEATED" in codes or "NO_OVERHEAT" in codes:
                key_factors.append("Macro non surriscaldate")

        italian_parts = [
            f"La v3.0 propone Over {_fmt_line(line)} perché ",
        ]
        if totals_phrase:
            italian_parts.append(
                f"{totals_phrase.replace(';', ',')} "
                f"{'Entrambe sono sopra la linea.' if line and v11_pt and v21_pt and v11_pt > line and v21_pt > line else ''}"
            )
        if margin_phrase:
            italian_parts.append(margin_phrase + " ")
        if "MACRO_NOT_OVERHEATED" in codes or "NO_OVERHEAT" in codes:
            italian_parts.append("Le macro non risultano surriscaldate. ")
        if "LINEUP_OK" in codes:
            italian_parts.append("Le formazioni sono disponibili. ")
        if injuries is not None:
            italian_parts.append(injury_phrase(injuries, player_layer) + " ")
        if absence_names:
            italian_parts.append(
                f"Tra le assenze rilevanti: {', '.join(absence_names)}. "
            )
        italian_parts.append(
            f"Per questo la giocata viene classificata come {tier}."
        )
        italian_text = "".join(italian_parts).strip()
        summary = (
            f"La v3.0 propone Over {_fmt_line(line)} con profilo {selection.profile}: "
            f"{decision_reason[:200]}"
        )
        short_reason = _short_reason_play(codes, line)

    elif decision == "BORDERLINE" and line is not None:
        headline = f"Profilo borderline: Over {_fmt_line(line)} SOT"
        decision_reason = (
            f"{totals_phrase} La confidence v2.1 non è pienamente solida."
            if totals_phrase
            else "Profilo incerto tra modelli e confidence."
        )
        risk_reason = "La giocata resta borderline: meglio valutare stake ridotto o skip."
        italian_text = (
            f"La v3.0 classifica Over {_fmt_line(line)} come borderline. "
            f"{totals_phrase} "
            f"{confidence_reason} "
            "Non c'è consenso pieno o la confidence non è al massimo."
        ).strip()
        summary = headline
        short_reason = "Borderline: confidence non piena"

    else:
        headline = "Nessuna giocata (NO BET)"
        primary = no_bet[0] if no_bet else "UNKNOWN"
        primary_it = NO_BET_REASON_IT.get(primary, phrase_for_code(primary, injuries, player_layer))
        decision_reason = primary_it
        if totals_phrase:
            decision_reason += f" {totals_phrase}"
        if v21_line is not None:
            line_reason = f"La linea disponibile dalla v2.1 sarebbe {_fmt_line(v21_line)}."
        risk_reason = "; ".join(
            NO_BET_REASON_IT.get(r, r) for r in no_bet[1:3]
        ) or "Il selettore preferisce evitare senza margine forte."

        italian_parts = [
            "La v3.0 non gioca questa partita perché ",
            primary_it,
        ]
        if v21_line == 7.5 or "V11_PRED_TOO_LOW_FOR_7_5" in no_bet or "V21_PRED_TOO_LOW_FOR_7_5" in no_bet:
            italian_parts.append(
                " La linea 7.5 non viene considerata abbastanza sicura."
            )
        if totals_phrase and v11_pt is not None and v21_pt is not None:
            if v21_pt > (v21_line or 0) and v11_pt < (v21_line or 99):
                italian_parts.append(
                    f" La v2.1 è sopra la linea, ma la v1.1 è più prudente ({_fmt_sot(v11_pt)} SOT) "
                    f"e non conferma con sufficiente forza."
                )
        if "MACRO_OVERHEAT" in no_bet:
            italian_parts.append(" Le macro sono troppo spinte.")
        if absence_names:
            italian_parts.append(f" Assenze rilevanti: {', '.join(absence_names)}.")
        italian_parts.append(" In assenza di un margine forte, il selettore preferisce evitare la giocata.")
        italian_text = "".join(italian_parts).strip()
        summary = italian_text[:220]
        short_reason = _short_reason_no_bet(no_bet)

    if warning_notes and decision == "GIOCA":
        risk_reason = (risk_reason + " " + warning_notes[0]).strip()

    return {
        "headline": headline,
        "summary": summary,
        "decision_reason": decision_reason,
        "risk_reason": risk_reason,
        "line_reason": line_reason,
        "confidence_reason": confidence_reason,
        "key_factors": key_factors[:8],
        "warning_notes": warning_notes,
        "italian_text": italian_text,
        "short_reason": short_reason[:60],
        "data_used": data_used,
    }
