"""Equilibrio vs Squilibrio — Preview v5 (Fase 2A).

Adapter read-only: riusa balance_analysis v4 + candidati research già definiti.
Nessuna nuova formula produttiva; production_changes sempre false.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_balance_research_candidates import (
    RESEARCH_CANDIDATES_VERSION,
    dominant_side_to_market_label,
    research_candidates_from_probs,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)

VERSION = "balance_v5_preview_v1_2"


RESEARCH_NOTE = (
    "F36 è il pilastro produttivo attuale. "
    "Gli altri indici sono mostrati come ricerca o in calibrazione. "
    "Il Book è separato e non modifica la valutazione interna."
)

_MARKET_READING = (
    "Il dato descrive la distanza tra Cecchino e mercato, "
    "ma non stabilisce quale dei due abbia ragione."
)

_DRAW_CRED_READING = (
    "La struttura di ricerca è attiva. "
    "L’indice definitivo verrà consolidato con la crescita dello storico."
)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def _component(
    key: str,
    label: str,
    value: Any,
    *,
    unit: str = "text",
    status: str = "available",
) -> dict[str, Any]:
    if value is None and status == "available":
        status = "missing"
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
    }


def _kpi_row_map(kpi_panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in kpi_panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or "").strip().upper()
        if mk:
            out[mk] = row
    return out


def _goal_odds_from_final(final: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not final or not isinstance(final, dict):
        return None, None
    gm = final.get("goal_markets") or {}
    if not isinstance(gm, dict):
        return None, None
    under = None
    over = None
    u = gm.get(SEL_UNDER_2_5) or gm.get("under_2_5") or {}
    o = gm.get(SEL_OVER_2_5) or gm.get("over_2_5") or {}
    if isinstance(u, dict):
        under = _num(u.get("final_odd") or u.get("odd"))
    if isinstance(o, dict):
        over = _num(o.get("final_odd") or o.get("odd"))
    return under, over


def _goal_probs_from_odds(under: float | None, over: float | None) -> tuple[float | None, float | None]:
    """Implied % grezzi da quote Cecchino goal (solo display)."""
    if under is None or under <= 1:
        up = None
    else:
        up = round(100.0 / under, 2)
    if over is None or over <= 1:
        op = None
    else:
        op = round(100.0 / over, 2)
    return up, op


def _f36_side_from_signed(signed: Any) -> str | None:
    s = _num(signed)
    if s is None or s == 0:
        return None
    # convention produttiva: signed > 0 → struttura verso 1; < 0 → verso 2
    return "1" if s > 0 else "2"


def _f36_structural_reading(f36: dict[str, Any]) -> str:
    """Lettura geometrica: nessuna formulazione predittiva sul modello."""
    class_key = str(f36.get("class_key") or "")
    side = _f36_side_from_signed(f36.get("signed"))

    if class_key == "imbalance":
        if side:
            return (
                f"La distanza tra le quote laterali descrive una struttura "
                f"sbilanciata verso il lato {side}."
            )
        return "La distanza tra le quote laterali descrive una struttura sbilanciata."

    if class_key == "transition":
        if side:
            return (
                "Le quote laterali mostrano una distanza intermedia, "
                f"con inclinazione strutturale verso il lato {side}."
            )
        return "Le quote laterali mostrano una distanza intermedia tra equilibrio e squilibrio."

    # strong_balance / balance / default
    if side:
        return (
            "Le quote laterali risultano relativamente vicine, "
            f"con una lieve inclinazione verso il lato {side}."
        )
    return "Le quote laterali risultano vicine e la struttura della partita appare equilibrata."


def _pillar_f36(balance: dict[str, Any]) -> dict[str, Any]:
    f36 = balance.get("f36") or {}
    if not f36 or balance.get("status") != "available":
        return {
            "key": "f36",
            "title": "Geometria della partita",
            "question": "Quanto è equilibrata la struttura della partita?",
            "status": "unavailable",
            "index": None,
            "class_label": None,
            "reading": "Dati F36 non disponibili.",
            "direction": None,
            "source_version": balance.get("version"),
            "components": [],
            "warnings": ["f36_unavailable"],
        }
    return {
        "key": "f36",
        "title": "Geometria della partita",
        "question": "Quanto è equilibrata la struttura della partita?",
        "status": "official",
        "index": f36.get("score"),
        "class_label": f36.get("label"),
        "reading": _f36_structural_reading(f36),
        "direction": _f36_side_from_signed(f36.get("signed")),
        "source_version": balance.get("version"),
        "components": [
            _component("f36_abs", "Distanza geometrica |F36|", f36.get("abs"), unit="index"),
            _component("f36_signed", "F36 firmato", f36.get("signed"), unit="index"),
            _component("f36_class_key", "Classe tecnica", f36.get("class_key"), unit="text"),
        ],
        "warnings": [],
    }


def _dominance_reading(market_label: str | None, conviction: float | None, class_label: str | None) -> str:
    side = market_label or "?"
    if conviction is None:
        return f"Il modello indica come scenario principale il segno {side}."
    intensity = (class_label or "moderata").lower()
    return f"Il modello mostra una preferenza {intensity} per il segno {side}."


def _pillar_dominance(balance: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    dom = balance.get("dominance") or {}
    ctx = balance.get("dominance_context") or {}
    best = dom.get("best_side") or ctx.get("best_side")
    market = dominant_side_to_market_label(best)
    conviction = candidates.get("conviction_index_candidate")
    conv_class = candidates.get("conviction_class_candidate")
    if conviction is not None:
        status = "research"
        index = conviction
        class_label = conv_class
    else:
        status = "calibration_pending"
        index = None
        class_label = None
    components = [
        _component("dominant_sign", "Segno dominante", market, unit="text"),
        _component("dominance_pp", "Dominanza", dom.get("value"), unit="pp"),
        _component(
            "conviction_index_candidate",
            "Indice di convinzione (ricerca)",
            conviction,
            unit="index",
            status="research" if conviction is not None else "missing",
        ),
        _component("best_probability", "Prob. scenario principale", dom.get("best_probability"), unit="pct"),
    ]
    return {
        "key": "dominance",
        "title": "Convinzione del modello",
        "question": "Quanto il modello è convinto dello scenario principale?",
        "status": status,
        "index": index,
        "class_label": class_label,
        "reading": _dominance_reading(market, conviction, conv_class),
        "direction": market,
        "source_version": RESEARCH_CANDIDATES_VERSION,
        "components": components,
        "warnings": ["research_index"] if status == "research" else ["calibration_pending"],
    }


def _pillar_draw_credibility(
    balance: dict[str, Any],
    candidates: dict[str, Any],
    *,
    under_odd: float | None,
    over_odd: float | None,
    under_pct: float | None,
    over_pct: float | None,
) -> dict[str, Any]:
    inputs = balance.get("inputs") or {}
    components = [
        _component("prob_x", "Probabilità X Cecchino", inputs.get("prob_x"), unit="pct"),
        _component("quota_x", "Quota X Cecchino", inputs.get("quota_x"), unit="quota"),
        _component("prob_under_2_5", "Under 2.5 Cecchino", under_pct, unit="pct"),
        _component("prob_over_2_5", "Over 2.5 Cecchino", over_pct, unit="pct"),
        _component("quota_under_2_5", "Quota Under 2.5 Cecchino", under_odd, unit="quota"),
        _component("quota_over_2_5", "Quota Over 2.5 Cecchino", over_odd, unit="quota"),
        _component("x_rank", "Posizione X nel ranking", candidates.get("x_rank"), unit="text"),
        _component(
            "conviction_direction",
            "Direzione convinzione",
            dominant_side_to_market_label((balance.get("dominance") or {}).get("best_side")),
            unit="text",
        ),
        _component("data_coverage", "Stato copertura dati", balance.get("status"), unit="text"),
    ]
    # Garantisce assenza Book nei componenti del pilastro
    components = [c for c in components if "book" not in c["key"].lower() and "book" not in c["label"].lower()]
    return {
        "key": "draw_credibility",
        "title": "Credibilità della X",
        "question": "Quanto il pareggio è credibile secondo il modello Cecchino?",
        "status": "calibration_pending",
        "index": None,
        "class_label": None,
        "reading": _DRAW_CRED_READING,
        "direction": None,
        "source_version": None,
        "components": components,
        "warnings": ["index_in_calibration", "no_book_in_pillar"],
    }


def _format_gap_pp_it(gap_pp: float | None) -> str:
    if gap_pp is None:
        return "n/d"
    # presentation only: Italian decimal comma, max 2 decimals, no trailing zeros forced
    text = f"{float(gap_pp):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _gap_coherence_is_low(class_label: str | None) -> bool:
    if not class_label:
        return False
    low = class_label.lower()
    return low in ("non confermato", "debole") or "non confermato" in low


def _gap_reading(
    gap_coh: float | None,
    gap_class: str | None,
    gap_pp: float | None,
    *,
    f36_class_key: str | None,
) -> str:
    if gap_coh is None:
        return (
            "La coerenza tra probabilità 1/2 e geometria F36 è in calibrazione. "
            "I componenti disponibili sono mostrati senza indice aggregato."
        )
    if _gap_coherence_is_low(gap_class):
        return "Il gap probabilistico non conferma pienamente la geometria descritta da F36."

    gap_txt = _format_gap_pp_it(gap_pp)
    f36_key = str(f36_class_key or "")
    if f36_key == "imbalance":
        return f"Il gap probabilistico di {gap_txt} pp conferma lo squilibrio rilevato da F36."
    if f36_key in ("strong_balance", "balance"):
        return (
            f"Il gap probabilistico di {gap_txt} pp è coerente con la struttura "
            "equilibrata rilevata da F36."
        )
    if f36_key == "transition":
        return (
            f"Il gap probabilistico di {gap_txt} pp è coerente con la struttura "
            "di transizione rilevata da F36."
        )
    return f"Il gap probabilistico di {gap_txt} pp è coerente con la geometria descritta da F36."


def _pillar_gap(balance: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    gap_coh = candidates.get("gap_coherence_index_candidate")
    gap_class = candidates.get("gap_coherence_class_candidate")
    gap_pp = candidates.get("probability_gap_1_2_pp")
    side = balance.get("side_probability_gap") or {}
    f36 = balance.get("f36") or {}
    if gap_pp is None:
        gap_pp = side.get("value")
    if gap_coh is not None:
        status = "research"
        index = gap_coh
        class_label = gap_class
    else:
        status = "calibration_pending"
        index = None
        class_label = None
    return {
        "key": "gap_coherence",
        "title": "Coerenza matematica 1/2",
        "question": "Le probabilità confermano la geometria descritta da F36?",
        "status": status,
        "index": index,
        "class_label": class_label,
        "reading": _gap_reading(
            gap_coh,
            gap_class,
            gap_pp,
            f36_class_key=f36.get("class_key"),
        ),
        "direction": None,
        "source_version": RESEARCH_CANDIDATES_VERSION,
        "components": [
            _component(
                "gap_coherence_index_candidate",
                "Indice coerenza (ricerca)",
                gap_coh,
                unit="index",
                status="research" if gap_coh is not None else "missing",
            ),
            _component("probability_gap_1_2_pp", "Gap probabilistico 1/2", gap_pp, unit="pp"),
            _component(
                "probability_balance_index",
                "Indice equilibrio 1/2",
                candidates.get("probability_balance_index"),
                unit="index",
            ),
            _component("side_gap_label", "Lettura gap produttiva", side.get("label"), unit="text"),
        ],
        "warnings": ["research_index"] if status == "research" else ["calibration_pending"],
    }


def _market_pair(
    key: str,
    label: str,
    *,
    quota_cecchino: float | None,
    quota_book: float | None,
    prob_cecchino: float | None = None,
    prob_book: float | None = None,
) -> dict[str, Any]:
    deviation = None
    if prob_cecchino is not None and prob_book is not None:
        deviation = round(abs(float(prob_cecchino) - float(prob_book)), 2)
    elif quota_cecchino is not None and quota_book is not None and quota_cecchino > 0 and quota_book > 0:
        # fallback: distanza in probabilità implicite grezze
        pc = 100.0 / float(quota_cecchino)
        pb = 100.0 / float(quota_book)
        deviation = round(abs(pc - pb), 2)
    return {
        "key": key,
        "label": label,
        "quota_cecchino": quota_cecchino,
        "quota_book": quota_book,
        "prob_cecchino_pct": prob_cecchino,
        "prob_book_pct": prob_book,
        "deviation_pp": deviation,
    }


def _build_market_deviation(
    balance: dict[str, Any],
    kpi_panel: dict[str, Any] | None,
    *,
    under_odd: float | None,
    over_odd: float | None,
    under_pct: float | None,
    over_pct: float | None,
) -> dict[str, Any]:
    inputs = balance.get("inputs") or {}
    rows = _kpi_row_map(kpi_panel)

    def book_q(sel: str) -> float | None:
        r = rows.get(sel) or {}
        return _num(r.get("quota_book"))

    def cec_q(sel: str, fallback: float | None) -> float | None:
        r = rows.get(sel) or {}
        return _num(r.get("quota_cecchino")) if r.get("quota_cecchino") is not None else fallback

    pairs = [
        _market_pair(
            "x",
            "Segno X",
            quota_cecchino=cec_q(SEL_DRAW, inputs.get("quota_x")),
            quota_book=book_q(SEL_DRAW),
            prob_cecchino=_num(inputs.get("prob_x")),
        ),
        _market_pair(
            "1",
            "Segno 1",
            quota_cecchino=cec_q(SEL_HOME, inputs.get("quota_1")),
            quota_book=book_q(SEL_HOME),
            prob_cecchino=_num(inputs.get("prob_1")),
        ),
        _market_pair(
            "2",
            "Segno 2",
            quota_cecchino=cec_q(SEL_AWAY, inputs.get("quota_2")),
            quota_book=book_q(SEL_AWAY),
            prob_cecchino=_num(inputs.get("prob_2")),
        ),
        _market_pair(
            "under_2_5",
            "Under 2.5",
            quota_cecchino=cec_q(SEL_UNDER_2_5, under_odd),
            quota_book=book_q(SEL_UNDER_2_5),
            prob_cecchino=under_pct,
        ),
        _market_pair(
            "over_2_5",
            "Over 2.5",
            quota_cecchino=cec_q(SEL_OVER_2_5, over_odd),
            quota_book=book_q(SEL_OVER_2_5),
            prob_cecchino=over_pct,
        ),
    ]
    # Enrich book implied % when only odds available
    for p in pairs:
        if p["prob_book_pct"] is None and p["quota_book"] and p["quota_book"] > 1:
            p["prob_book_pct"] = round(100.0 / float(p["quota_book"]), 2)
        if p["deviation_pp"] is None and p["prob_cecchino_pct"] is not None and p["prob_book_pct"] is not None:
            p["deviation_pp"] = round(abs(float(p["prob_cecchino_pct"]) - float(p["prob_book_pct"])), 2)

    has_any_book = any(p.get("quota_book") is not None for p in pairs)
    return {
        "title": "Scostamento dal mercato",
        "subtitle": "Il mercato non modifica la Credibilità X.",
        "status": "calibration_pending",
        "index": None,
        "class_label": None,
        "pairs": pairs,
        "reading": _MARKET_READING,
        "warnings": [] if has_any_book else ["book_odds_missing"],
        "has_book_data": has_any_book,
    }


def _unavailable_pillar(key: str, title: str, question: str) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "question": question,
        "status": "unavailable",
        "index": None,
        "class_label": None,
        "reading": "Analisi non disponibile per mismatch di identità fixture.",
        "direction": None,
        "source_version": None,
        "components": [],
        "warnings": ["fixture_identity_mismatch"],
    }


def _unavailable_preview(*, extra_warnings: list[str] | None = None) -> dict[str, Any]:
    warnings = ["fixture_identity_mismatch"]
    if extra_warnings:
        warnings.extend(extra_warnings)
    return {
        "status": "unavailable",
        "version": VERSION,
        "pillars": [
            _unavailable_pillar(
                "f36",
                "Geometria della partita",
                "Quanto è equilibrata la struttura della partita?",
            ),
            _unavailable_pillar(
                "dominance",
                "Convinzione del modello",
                "Quanto il modello è convinto dello scenario principale?",
            ),
            _unavailable_pillar(
                "draw_credibility",
                "Credibilità della X",
                "Quanto il pareggio è credibile secondo il modello Cecchino?",
            ),
            _unavailable_pillar(
                "gap_coherence",
                "Coerenza matematica 1/2",
                "Le probabilità confermano la geometria descritta da F36?",
            ),
        ],
        "market_deviation": {
            "title": "Scostamento dal mercato",
            "subtitle": "Il mercato non modifica la Credibilità X.",
            "status": "unavailable",
            "index": None,
            "class_label": None,
            "pairs": [],
            "reading": "Sezione non disponibile: identità fixture non allineata.",
            "warnings": ["fixture_identity_mismatch"],
            "has_book_data": False,
        },
        "research_note": RESEARCH_NOTE,
        "production_changes": False,
        "warnings": warnings,
    }


def build_balance_v5_preview(
    *,
    balance_analysis: dict[str, Any] | None,
    kpi_panel: dict[str, Any] | None = None,
    cecchino_final: dict[str, Any] | None = None,
    identity_consistency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(identity_consistency, dict) and identity_consistency.get("status") == "inconsistent":
        return _unavailable_preview(
            extra_warnings=list(identity_consistency.get("warnings") or []),
        )

    balance = balance_analysis if isinstance(balance_analysis, dict) else {}
    inputs = balance.get("inputs") or {}
    f36 = balance.get("f36") or {}

    candidates = research_candidates_from_probs(
        prob_1=_num(inputs.get("prob_1")),
        prob_x=_num(inputs.get("prob_x")),
        prob_2=_num(inputs.get("prob_2")),
        f36_score=_num(f36.get("score")),
    )

    under_odd, over_odd = _goal_odds_from_final(cecchino_final)
    # Prefer KPI cecchino odds if present
    rows = _kpi_row_map(kpi_panel)
    if rows.get(SEL_UNDER_2_5, {}).get("quota_cecchino") is not None:
        under_odd = _num(rows[SEL_UNDER_2_5].get("quota_cecchino")) or under_odd
    if rows.get(SEL_OVER_2_5, {}).get("quota_cecchino") is not None:
        over_odd = _num(rows[SEL_OVER_2_5].get("quota_cecchino")) or over_odd
    under_pct, over_pct = _goal_probs_from_odds(under_odd, over_odd)

    pillars = [
        _pillar_f36(balance),
        _pillar_dominance(balance, candidates),
        _pillar_draw_credibility(
            balance,
            candidates,
            under_odd=under_odd,
            over_odd=over_odd,
            under_pct=under_pct,
            over_pct=over_pct,
        ),
        _pillar_gap(balance, candidates),
    ]

    return {
        "status": "ok",
        "version": VERSION,
        "pillars": pillars,
        "market_deviation": _build_market_deviation(
            balance,
            kpi_panel,
            under_odd=under_odd,
            over_odd=over_odd,
            under_pct=under_pct,
            over_pct=over_pct,
        ),
        "research_note": RESEARCH_NOTE,
        "production_changes": False,
        "research_candidates": candidates,
        "warnings": [],
    }
