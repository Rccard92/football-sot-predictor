"""Regola della selezione V4 (docs/v4/PREREGISTRAZIONE_FASE_4.md): probabilità prudente, verdetti, riga di mercato.

Funzioni pure. Le quote entrano qui solo come prezzo: mai dentro `p`, `lo`, `hi`.

Probabilità prudente:
    u = incertezza tagliata in [0, 1]
    se lo > tasso_base:  p_prudente = lo - (lo - tasso_base) * u   (lo, ristretto verso il tasso base)
    altrimenti:          p_prudente = lo                           (mai gonfiare)
Profitto atteso = p_prudente * quota_usata - 1. Quota usata = Bet365 se c'è, altrimenti Betfair.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from app.services.cecchino_v3.markets import score_matrix
from app.services.cecchino_v4.constants import (
    ANOMALY_RATIO,
    VERDICT_ANOMALOUS,
    BOOKMAKER_BET365_ID,
    BOOKMAKER_BETFAIR_ID,
    BOOKMAKERS,
    MIN_QUOTA,
    PROFIT_MARGIN,
    VERDICT_DESCRIPTIVE,
    VERDICT_FAIR_PRICE,
    VERDICT_LABELS,
    VERDICT_NO_ODDS,
    VERDICT_PLAYABLE,
    VERDICT_UNCERTAIN,
)
from app.services.cecchino_v4.selection.labels import (
    KIND_AH,
    KIND_STAT,
    ParsedMarket,
    market_label,
    parse_market_key,
    stat_market_key,
)
from app.services.cecchino_v4.selection.settlement import HALF_LOST, HALF_WON, LOST, WON, ah_outcome

# --- Tassi base -------------------------------------------------------------------
# Frequenze storiche dei mercati classici nei 16 campionati (football-data 2017-2025, arrotondate).
# Servono solo come punto di richiamo della probabilità prudente: più il modello è incerto,
# più la probabilità usata per il prezzo scivola verso questi valori.
BASE_RATES: dict[str, float] = {
    "HOME": 0.44,
    "DRAW": 0.26,
    "AWAY": 0.30,
    "ONE_X": 0.70,
    "X_TWO": 0.56,
    "ONE_TWO": 0.74,
    "OVER_0_5": 0.93,
    "UNDER_0_5": 0.07,
    "OVER_1_5": 0.75,
    "UNDER_1_5": 0.25,
    "OVER_2_5": 0.51,
    "UNDER_2_5": 0.49,
    "OVER_3_5": 0.29,
    "UNDER_3_5": 0.71,
    "HOME_PT": 0.31,
    "DRAW_PT": 0.42,
    "AWAY_PT": 0.27,
}
# Partita "media" della divisione per il tasso base dell'handicap asiatico: gol attesi 1,45 casa,
# 1,15 ospite, rho Dixon-Coles -0,05 (valori medi dei 16 campionati sulle stagioni di giudizio).
REFERENCE_LAMBDA_HOME = 1.45
REFERENCE_LAMBDA_AWAY = 1.15
REFERENCE_RHO = -0.05

# Candidati considerati da `no_play_reason` (i primi per p x quota).
NO_PLAY_TOP_CANDIDATES = 5

_UNCERTAINTY_HIGH = "alta"


def poisson_tail_over(mean: float, line: float) -> float:
    """P(X > linea) con X ~ Poisson(media). Per linee a mezzo è P(X >= linea + 0,5)."""
    mean = max(float(mean), 1e-9)
    k_max = int(math.floor(line))
    if k_max < 0:
        return 1.0
    cdf = 0.0
    log_term = -mean
    for k in range(k_max + 1):
        if k > 0:
            log_term += math.log(mean) - math.log(k)
        cdf += math.exp(log_term)
    return float(min(1.0, max(0.0, 1.0 - cdf)))


def ah_effective_probability(matrix: np.ndarray, side: str, line: float) -> float:
    """Probabilità "efficace" dell'handicap dalla matrice dei punteggi: w / (w + l), con
    w = P(vinta) + P(mezza vinta)/2 e l = P(persa) + P(mezza persa)/2. I void non contano.
    Con questa definizione il segno di p * quota - 1 coincide con quello del profitto atteso."""
    w = 0.0
    l = 0.0
    rows, cols = matrix.shape
    for h in range(rows):
        for a in range(cols):
            prob = float(matrix[h, a])
            if prob <= 0.0:
                continue
            outcome = ah_outcome(side, line, h, a)
            if outcome == WON:
                w += prob
            elif outcome == HALF_WON:
                w += prob / 2.0
            elif outcome == LOST:
                l += prob
            elif outcome == HALF_LOST:
                l += prob / 2.0
    if w + l <= 0.0:
        return 0.5
    return w / (w + l)


_REFERENCE_MATRIX: np.ndarray | None = None


def _reference_matrix() -> np.ndarray:
    global _REFERENCE_MATRIX
    if _REFERENCE_MATRIX is None:
        _REFERENCE_MATRIX = score_matrix(REFERENCE_LAMBDA_HOME, REFERENCE_LAMBDA_AWAY, REFERENCE_RHO)
    return _REFERENCE_MATRIX


def base_rate(market_key: str, division_mean: float | None = None) -> float:
    """Tasso base del mercato.

    - classici: tabella `BASE_RATES`;
    - handicap asiatico: probabilità efficace nella partita media della divisione;
    - statistiche: P(over) con una Poisson alla media di divisione fornita nel payload (1 - P per l'under).
    """
    parsed = parse_market_key(market_key)
    if parsed.kind == KIND_AH:
        return ah_effective_probability(_reference_matrix(), parsed.side or "home", parsed.line or 0.0)
    if parsed.kind == KIND_STAT:
        if division_mean is None:
            raise ValueError("tasso base di una statistica: serve la media di divisione")
        over = poisson_tail_over(division_mean, parsed.line or 0.0)
        return over if parsed.direction == "over" else 1.0 - over
    return BASE_RATES[parsed.key]


# --- Probabilità prudente ---------------------------------------------------------
def prudent_probability(p: float, lo: float | None, uncertainty_score: float | None, base_rate_value: float) -> float:
    """Probabilità usata per il prezzo. Parte dal bordo inferiore dell'intervallo e, se sta sopra il
    tasso base, lo restringe verso il tasso base in proporzione all'incertezza. Mai sopra `p`, mai gonfiata."""
    p = float(p)
    lo_value = p if lo is None else min(float(lo), p)
    u = 0.0 if uncertainty_score is None else min(1.0, max(0.0, float(uncertainty_score)))
    if lo_value > base_rate_value:
        lo_value = lo_value - (lo_value - base_rate_value) * u
    return float(min(1.0, max(0.0, lo_value)))


# --- Riga di mercato -------------------------------------------------------------
@dataclass
class RowInputs:
    market_key: str
    p: float
    lo: float | None
    hi: float | None
    uncertainty_score: float | None
    uncertainty_level: str | None
    base_rate: float
    label: str = ""
    quota_bet365: float | None = None
    quota_betfair: float | None = None
    lineups_status: str = "non_note"
    stat_exam: str = "superato"  # superato | non_superato | in_attesa (solo statistiche)
    advised: bool = True  # False quando l'esame E4 della famiglia non è superato


@dataclass
class MarketRow:
    market_key: str
    family: str
    label: str
    p: float
    lo: float | None
    hi: float | None
    p_prudent: float
    quota_bet365: float | None
    quota_betfair: float | None
    quota_used: float | None
    bookmaker_used: str | None
    bookmaker_id: int | None
    expected_profit: float | None
    verdict: str
    verdict_label: str
    provisional: bool = False  # formazioni non note: giocata provvisoria
    advised: bool = True  # False = in osservazione (esame E4 non superato)
    base_rate: float = 0.0
    stat_exam: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("extra", None)
        return data


def choose_quota(quota_bet365: float | None, quota_betfair: float | None) -> tuple[float | None, str | None, int | None]:
    """Prezzo usato: Bet365 se presente, altrimenti Betfair. Ritorna (quota, nome book, id book)."""
    if quota_bet365 is not None and float(quota_bet365) > 1.0:
        return float(quota_bet365), BOOKMAKERS[BOOKMAKER_BET365_ID], BOOKMAKER_BET365_ID
    if quota_betfair is not None and float(quota_betfair) > 1.0:
        return float(quota_betfair), BOOKMAKERS[BOOKMAKER_BETFAIR_ID], BOOKMAKER_BETFAIR_ID
    return None, None, None


def evaluate_market(inputs: RowInputs) -> MarketRow:
    """Applica la regola a un mercato e produce la riga con il verdetto.

    Ordine dei verdetti: solo_descrittivo (statistica senza esame superato) -> non_quotato ->
    incertezza_alta -> giocabile (profitto atteso >= margine e quota >= minima) -> prezzo_giusto.
    """
    parsed: ParsedMarket = parse_market_key(inputs.market_key)
    p_prudent = prudent_probability(inputs.p, inputs.lo, inputs.uncertainty_score, inputs.base_rate)
    quota_used, bookmaker_used, bookmaker_id = choose_quota(inputs.quota_bet365, inputs.quota_betfair)
    expected_profit = None if quota_used is None else round(p_prudent * quota_used - 1.0, 4)

    if parsed.kind == KIND_STAT and inputs.stat_exam != "superato":
        verdict = VERDICT_DESCRIPTIVE
    elif quota_used is None:
        verdict = VERDICT_NO_ODDS
    elif quota_used * float(inputs.p) > ANOMALY_RATIO:
        # il modello vede l'esito 2,5+ volte piu' probabile del prezzo: errore di lettura della quota o quota
        # sbagliata, mai una giocata (protezione contro chiavi di mercato invertite)
        verdict = VERDICT_ANOMALOUS
    elif (inputs.uncertainty_level or "").lower() == _UNCERTAINTY_HIGH:
        verdict = VERDICT_UNCERTAIN
    elif expected_profit is not None and expected_profit >= PROFIT_MARGIN and quota_used >= MIN_QUOTA:
        verdict = VERDICT_PLAYABLE
    else:
        verdict = VERDICT_FAIR_PRICE

    return MarketRow(
        market_key=parsed.key,
        family=parsed.family,
        label=inputs.label,
        p=round(float(inputs.p), 4),
        lo=None if inputs.lo is None else round(float(inputs.lo), 4),
        hi=None if inputs.hi is None else round(float(inputs.hi), 4),
        p_prudent=round(p_prudent, 4),
        quota_bet365=None if inputs.quota_bet365 is None else float(inputs.quota_bet365),
        quota_betfair=None if inputs.quota_betfair is None else float(inputs.quota_betfair),
        quota_used=quota_used,
        bookmaker_used=bookmaker_used,
        bookmaker_id=bookmaker_id,
        expected_profit=expected_profit,
        verdict=verdict,
        verdict_label=VERDICT_LABELS[verdict],
        provisional=inputs.lineups_status == "non_note",
        advised=bool(inputs.advised),
        base_rate=round(float(inputs.base_rate), 4),
        stat_exam=inputs.stat_exam if parsed.kind == KIND_STAT else None,
    )


def _odds_for(odds: dict[int, dict[str, float]] | None, market_key: str) -> tuple[float | None, float | None]:
    if not odds:
        return None, None
    b365 = (odds.get(BOOKMAKER_BET365_ID) or {}).get(market_key)
    betfair = (odds.get(BOOKMAKER_BETFAIR_ID) or {}).get(market_key)
    return (None if b365 is None else float(b365)), (None if betfair is None else float(betfair))


def _uncertainty(goals_payload: dict[str, Any] | None) -> tuple[float | None, str | None]:
    unc = (goals_payload or {}).get("uncertainty") or {}
    return unc.get("score"), unc.get("level")


def evaluate_fixture(
    goals_payload: dict[str, Any] | None,
    stats_payload: dict[str, Any] | None,
    odds: dict[int, dict[str, float]] | None,
    home_team: str,
    away_team: str,
    lineups_status: str = "non_note",
    advised_families: dict[str, bool] | None = None,
) -> list[MarketRow]:
    """Tutte le righe di mercato di una partita: classici e handicap dal payload gol, tutte le linee
    (over e under) dal payload statistiche. `odds` = {id_book: {chiave: quota}}.
    `advised_families` = {famiglia: bool} per marcare le famiglie in osservazione (default: tutte consigliate)."""
    rows: list[MarketRow] = []
    score, level = _uncertainty(goals_payload)
    advised_families = advised_families or {}

    for market_key, values in ((goals_payload or {}).get("markets") or {}).items():
        try:
            parsed = parse_market_key(market_key)
        except ValueError:
            continue
        if not isinstance(values, dict) or values.get("p") is None:
            continue
        b365, betfair = _odds_for(odds, parsed.key)
        rows.append(
            evaluate_market(
                RowInputs(
                    market_key=parsed.key,
                    label=market_label(parsed.key, home_team, away_team),
                    p=float(values["p"]),
                    lo=values.get("lo"),
                    hi=values.get("hi"),
                    uncertainty_score=score,
                    uncertainty_level=level,
                    base_rate=base_rate(parsed.key),
                    quota_bet365=b365,
                    quota_betfair=betfair,
                    lineups_status=lineups_status,
                    advised=advised_families.get(parsed.family, True),
                )
            )
        )

    stats_unc = (stats_payload or {}).get("uncertainty") or {}
    for stat, block in ((stats_payload or {}).get("stats") or {}).items():
        if not isinstance(block, dict):
            continue
        exam = block.get("exam") or "in_attesa"
        stat_score = (block.get("uncertainty") or stats_unc).get("score", score)
        stat_level = (block.get("uncertainty") or stats_unc).get("level", level)
        for side in ("home", "away", "total"):
            side_block = block.get(side)
            if not isinstance(side_block, dict):
                continue
            division_mean = side_block.get("division_mean")
            lines = side_block.get("lines") or {}
            for raw_line, probs in lines.items():
                if not isinstance(probs, dict) or probs.get("over") is None:
                    continue
                try:
                    line = float(raw_line)
                except (TypeError, ValueError):
                    continue
                p_over = float(probs["over"])
                lo_over, hi_over = probs.get("lo"), probs.get("hi")
                for direction in ("over", "under"):
                    key = stat_market_key(stat, side, direction, line)
                    if direction == "over":
                        p, lo, hi = p_over, lo_over, hi_over
                    else:
                        p = 1.0 - p_over
                        lo = None if hi_over is None else 1.0 - float(hi_over)
                        hi = None if lo_over is None else 1.0 - float(lo_over)
                    try:
                        rate = base_rate(key, division_mean) if division_mean is not None else p
                    except ValueError:
                        rate = p
                    b365, betfair = _odds_for(odds, key)
                    rows.append(
                        evaluate_market(
                            RowInputs(
                                market_key=key,
                                label=market_label(key, home_team, away_team),
                                p=p,
                                lo=lo,
                                hi=hi,
                                uncertainty_score=stat_score,
                                uncertainty_level=stat_level,
                                base_rate=rate,
                                quota_bet365=b365,
                                quota_betfair=betfair,
                                lineups_status=lineups_status,
                                stat_exam=exam,
                                advised=advised_families.get(f"STAT_{stat}", True),
                            )
                        )
                    )
    return rows


def playable_rows(rows: list[MarketRow]) -> list[MarketRow]:
    return [r for r in rows if r.verdict == VERDICT_PLAYABLE and r.expected_profit is not None]


def best_play(rows: list[MarketRow]) -> MarketRow | None:
    """Giocata migliore: profitto atteso più alto tra le giocabili (a parità, probabilità prudente più alta)."""
    candidates = playable_rows(rows)
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r.expected_profit or 0.0, r.p_prudent))


def no_play_reason(rows: list[MarketRow]) -> str | None:
    """Motivo dell'astensione: il verdetto bloccante più frequente tra i primi candidati per p x quota.
    None se esiste una giocata o se non ci sono righe."""
    if not rows or playable_rows(rows):
        return None

    def key(row: MarketRow) -> float:
        return row.p * row.quota_used if row.quota_used else 0.0

    # se almeno un mercato ha un prezzo, il motivo si legge sui mercati con prezzo; altrimenti tutti (non quotati)
    candidates = [r for r in rows if r.quota_used] or rows
    top = sorted(candidates, key=key, reverse=True)[:NO_PLAY_TOP_CANDIDATES]
    counts = Counter(r.verdict for r in top)
    best_count = max(counts.values())
    for row in top:  # a parità di conteggio vince il verdetto del candidato più alto
        if counts[row.verdict] == best_count:
            return row.verdict
    return None


def rows_to_dicts(rows: list[MarketRow]) -> list[dict[str, Any]]:
    return [r.to_dict() for r in rows]
