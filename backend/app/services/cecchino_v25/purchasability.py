"""Indice di Acquistabilita' V2.5.

Difetti della V2 (V3.6) corretti:
- nella RUN V2 il punteggio esisteva solo quando il Cecchino vedeva valore sulla quota
  (circa il 90% delle righe senza classe, le altre quasi tutte "Molto Bassa");
- premiava la distanza tra Cecchino e book come se fosse sempre un vantaggio. Ma lo
  storico mostra che il book e' mediamente piu' preciso: una grande distanza e' spesso
  un errore del Cecchino, non un'occasione;
- usava la probabilita' Cecchino grezza invece di quella normalizzata.

V2.5: per ogni famiglia di mercati (1X2, doppia chance, 1X2 primo tempo, Over/Under) si
stima, solo sulle partite GIA' GIOCATE, quanto la probabilita' Cecchino aggiunge a quella
del book senza margine (regressione logistica, come l'esame usato per la V3). Ne esce una
probabilita' corretta p*, e il valore atteso della giocata p* x quota - 1 diventa il
punteggio 0-100. Finche' lo storico e' poco il Cecchino non viene creduto (p* = book) e il
punteggio resta basso: nessuna classe gonfiata. Il punteggio c'e' per ogni mercato quotato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKET_BY_KEY
from app.services.cecchino_v25.constants import (
    PURCHASABILITY_CLASS_LABELS,
    PURCHASABILITY_EV_CEIL,
    PURCHASABILITY_EV_FLOOR,
    PURCHASABILITY_MIN_ROWS,
    PURCHASABILITY_REFIT_EVERY,
)
from app.services.cecchino_v3.evaluator import LogisticFit, design, fit_logistic

MODULE_VERSION = "cecchino_v25_purchasability_v1"
_PROB_EPS = 1e-4


@dataclass
class _FamilyData:
    p_book: list[float] = field(default_factory=list)
    p_cec: list[float] = field(default_factory=list)
    won: list[float] = field(default_factory=list)
    match_ids: list[int] = field(default_factory=list)
    fit: LogisticFit | None = None
    fitted_at_n: int = 0


class PurchasabilityCalibrator:
    """Stato progressivo: vede solo partite gia' concluse prima del kickoff corrente."""

    def __init__(self) -> None:
        self._families: dict[str, _FamilyData] = {}

    def add(self, *, family: str, p_book: float, p_cec: float, won: bool, lab_match_id: int) -> None:
        data = self._families.setdefault(family, _FamilyData())
        data.p_book.append(min(1 - _PROB_EPS, max(_PROB_EPS, p_book)))
        data.p_cec.append(min(1 - _PROB_EPS, max(_PROB_EPS, p_cec)))
        data.won.append(1.0 if won else 0.0)
        data.match_ids.append(int(lab_match_id))

    def refresh(self) -> None:
        for data in self._families.values():
            n = len(data.won)
            if n < PURCHASABILITY_MIN_ROWS:
                continue
            if data.fit is not None and n - data.fitted_at_n < PURCHASABILITY_REFIT_EVERY:
                continue
            x = design(np.array(data.p_book), np.array(data.p_cec))
            fit = fit_logistic(x, np.array(data.won), np.array(data.match_ids))
            if fit.coef[2] < 0:
                # il Cecchino puo' solo aggiungere informazione nella sua direzione: un peso
                # negativo (mai significativo nello storico) significherebbe giocargli contro
                fit.coef = np.array([fit.coef[0], fit.coef[1], 0.0])
            data.fit = fit
            data.fitted_at_n = n

    def rows(self, family: str) -> int:
        data = self._families.get(family)
        return len(data.won) if data else 0

    def model(self, family: str) -> dict[str, Any] | None:
        data = self._families.get(family)
        if data is None or data.fit is None:
            return None
        return data.fit.summary()

    def corrected_probability(self, family: str, p_book: float, p_cec: float) -> float:
        data = self._families.get(family)
        if data is None or data.fit is None:
            return p_book
        x = design(np.array([p_book]), np.array([p_cec]))
        return float(data.fit.predict(x)[0])


def score_from_ev(ev: float) -> float:
    span = PURCHASABILITY_EV_CEIL - PURCHASABILITY_EV_FLOOR
    return max(0.0, min(100.0, 100.0 * (ev - PURCHASABILITY_EV_FLOOR) / span))


def class_label(score_value: float) -> str:
    return PURCHASABILITY_CLASS_LABELS[min(4, int(score_value // 20))]


def build_purchasability_v25(
    *,
    kpi_panel: dict[str, Any],
    calibrator: PurchasabilityCalibrator,
) -> dict[str, Any]:
    markets: list[dict[str, Any]] = []
    for row in kpi_panel.get("rows") or []:
        key = row["market_key"]
        family = CORE_MARKET_BY_KEY[key].family
        p_cec, p_book, quota = row.get("prob_cecchino"), row.get("prob_book_fair"), row.get("quota_book")
        # quota ricavata dall'1X2 senza margine: non e' una quota giocabile, niente punteggio
        if p_cec is None or p_book is None or quota is None or row.get("quota_book_derived"):
            markets.append(
                {
                    "market_key": key,
                    "status": "not_calculable",
                    "score": None,
                    "class": None,
                    "fair_book_probability": p_book,
                    "fair_book_probability_source": "v25_no_vig_family",
                    "formula_version": MODULE_VERSION,
                }
            )
            continue
        p_star = calibrator.corrected_probability(family, float(p_book), float(p_cec))
        ev = p_star * float(quota) - 1.0
        s = score_from_ev(ev)
        markets.append(
            {
                "market_key": key,
                "status": "score",
                "gate_status": "calibrated" if calibrator.model(family) else "book_only_warmup",
                "score": round(s, 2),
                "class": class_label(s),
                "corrected_probability": round(p_star, 6),
                "expected_value": round(ev, 5),
                "fair_book_probability": round(float(p_book), 6),
                "fair_book_probability_source": "v25_no_vig_family",
                "calibration_rows": calibrator.rows(family),
                "formula_version": MODULE_VERSION,
            }
        )
    return {
        "module_version": MODULE_VERSION,
        "markets": markets,
        "models": {
            fam: calibrator.model(fam)
            for fam in sorted({CORE_MARKET_BY_KEY[m["market_key"]].family for m in markets})
        },
    }
