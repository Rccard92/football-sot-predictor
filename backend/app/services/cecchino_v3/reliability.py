"""Affidabilita' della stima (versione 2) e segno sostenuto dagli agenti.

Nessuna quota del book entra qui. Si misura quanto sono solide le probabilita'
prodotte dagli agenti, non quanto e' prevedibile la partita:
- segnali di incertezza pre-partita (conoscenza delle squadre, disaccordo tra
  specialisti, squadre nuove, inizio stagione, irregolarita' recente);
- pesi >= 0 stimati walk-forward sulle stagioni precedenti, con obiettivo
  l'errore in eccesso 1X2 (Brier reale - Brier atteso dal modello).
"""

from __future__ import annotations

import bisect
import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.optimize import nnls

from app.services.cecchino_v3.constants import (
    RELIABILITY_COMPONENTS,
    RELIABILITY_FORM_NEUTRAL,
    RELIABILITY_HIGH,
    RELIABILITY_IRREGULARITY_MATCHES,
    RELIABILITY_IRREGULARITY_MIN_MATCHES,
    RELIABILITY_MEDIUM,
    group_of,
)
from app.services.cecchino_v3.markets import score_matrix

if TYPE_CHECKING:
    from app.services.cecchino_v3.indices import IndexInput

SPECIALISTS: tuple[str, ...] = ("forza", "sot", "shots")
SIGNS: tuple[str, ...] = ("1", "X", "2")


# --- misure di errore -------------------------------------------------------------------


def one_x_two_outcome(ft_home: int, ft_away: int) -> tuple[float, float, float]:
    return float(ft_home > ft_away), float(ft_home == ft_away), float(ft_home < ft_away)


def brier_1x2(probs: Sequence[float], outcome: Sequence[float]) -> float:
    return sum((o - p) ** 2 for p, o in zip(probs, outcome)) / 3.0


def expected_brier_1x2(probs: Sequence[float]) -> float:
    """Brier atteso se le probabilita' fossero esatte: somma p(1-p) / 3."""
    return (1.0 - sum(p * p for p in probs)) / 3.0


def excess_brier_1x2(probs: Sequence[float], ft_home: int, ft_away: int) -> float:
    return brier_1x2(probs, one_x_two_outcome(ft_home, ft_away)) - expected_brier_1x2(probs)


# --- segnali di incertezza ---------------------------------------------------------------


def specialist_disagreement(specialists: dict[str, Any]) -> tuple[float | None, float | None]:
    """Differenza massima tra specialisti su differenza di forza (log casa/ospite)
    e su gol totali (log casa+ospite)."""
    supremacy: list[float] = []
    totals: list[float] = []
    for name in SPECIALISTS:
        opinion = specialists.get(name) if isinstance(specialists, dict) else None
        if not isinstance(opinion, dict):
            continue
        home, away = opinion.get("home"), opinion.get("away")
        if home is None or away is None or home <= 0 or away <= 0:
            continue
        supremacy.append(math.log(home / away))
        totals.append(math.log(home + away))
    if len(supremacy) < 2:
        return None, None
    return max(supremacy) - min(supremacy), max(totals) - min(totals)


@dataclass
class _TeamHistory:
    entries: deque = field(default_factory=lambda: deque(maxlen=RELIABILITY_IRREGULARITY_MATCHES))

    def irregularity(self) -> float:
        """Scarti quadratici su gol attesi (1 = come una Poisson); 1 se poche partite."""
        if len(self.entries) < RELIABILITY_IRREGULARITY_MIN_MATCHES:
            return 1.0
        squared = sum(e[0] for e in self.entries)
        expected = sum(e[1] for e in self.entries)
        return squared / expected if expected > 0 else 1.0


def _add_team_match(history: _TeamHistory, goals_for: int, goals_against: int, lam_for: float, lam_against: float) -> None:
    history.entries.append(((goals_for - lam_for) ** 2 + (goals_against - lam_against) ** 2, lam_for + lam_against))


def reliability_signals(inputs: Sequence[IndexInput]) -> dict[int, dict[str, float]]:
    """Segnali per partita; l'irregolarita' usa solo giorni precedenti."""
    teams: dict[tuple[str, str], _TeamHistory] = {}
    out: dict[int, dict[str, float]] = {}
    n = len(inputs)
    i = 0
    while i < n:
        j = i
        while j < n and inputs[j].match.day == inputs[i].match.day:
            j += 1
        day = inputs[i:j]
        for item in day:
            m = item.match
            group = group_of(m.competition)
            home_hist = teams.setdefault((group, m.home_team), _TeamHistory())
            away_hist = teams.setdefault((group, m.away_team), _TeamHistory())
            d_sup, d_tot = specialist_disagreement(item.specialists or {})
            out[m.lab_match_id] = {
                "poca_conoscenza": 1.0 / math.sqrt(1.0 + max(0.0, min(item.home_evidence, item.away_evidence))),
                "disaccordo_forza": d_sup if d_sup is not None else 0.0,
                "disaccordo_gol": d_tot if d_tot is not None else 0.0,
                "squadra_nuova": float(item.new_team_home or item.new_team_away),
                "inizio_stagione": float(not m.eval_eligible),
                "irregolarita": 0.5 * (home_hist.irregularity() + away_hist.irregularity()),
            }
        for item in day:
            m = item.match
            group = group_of(m.competition)
            _add_team_match(teams[(group, m.home_team)], m.ft_home, m.ft_away, item.lambda_home, item.lambda_away)
            _add_team_match(teams[(group, m.away_team)], m.ft_away, m.ft_home, item.lambda_away, item.lambda_home)
        i = j
    return out


# --- pesi walk-forward --------------------------------------------------------------------


@dataclass
class ReliabilityModel:
    season: str
    trained_on: list[str]
    n_train: int
    mean: dict[str, float]
    std: dict[str, float]
    weights: dict[str, float]
    reference: list[float]  # rischi ordinati delle partite di stima

    @property
    def degenerate(self) -> bool:
        return all(w <= 0.0 for w in self.weights.values())

    def risk(self, signals: dict[str, float]) -> tuple[float, dict[str, float]]:
        contributions = {
            k: self.weights[k] * (signals[k] - self.mean[k]) / self.std[k] for k in RELIABILITY_COMPONENTS
        }
        return sum(contributions.values()), contributions

    def summary(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "trained_on": self.trained_on,
            "n_train": self.n_train,
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "mean": {k: round(v, 6) for k, v in self.mean.items()},
            "std": {k: round(v, 6) for k, v in self.std.items()},
            "degenerate": self.degenerate,
        }


def fit_reliability_model(
    season: str, trained_on: list[str], signals: list[dict[str, float]], excess: list[float]
) -> ReliabilityModel:
    """Minimi quadrati con pesi >= 0 sui segnali standardizzati, obiettivo
    l'errore in eccesso centrato (piu' rischio = piu' errore in eccesso)."""
    x = np.array([[s[k] for k in RELIABILITY_COMPONENTS] for s in signals], dtype=float)
    y = np.asarray(excess, dtype=float)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std <= 1e-12] = 1.0  # segnale costante: z = 0, nessun effetto
    z = (x - mean) / std
    w, _ = nnls(z, y - y.mean())
    reference = sorted((z @ w).tolist())
    return ReliabilityModel(
        season=season,
        trained_on=trained_on,
        n_train=len(y),
        mean=dict(zip(RELIABILITY_COMPONENTS, mean.tolist())),
        std=dict(zip(RELIABILITY_COMPONENTS, std.tolist())),
        weights=dict(zip(RELIABILITY_COMPONENTS, w.tolist())),
        reference=reference,
    )


def reliability_class(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= RELIABILITY_HIGH:
        return "alta"
    if value >= RELIABILITY_MEDIUM:
        return "media"
    return "bassa"


# --- segno sostenuto -------------------------------------------------------------------


def _one_x_two(lam_home: float, lam_away: float, rho: float) -> tuple[float, float, float]:
    m = score_matrix(lam_home, lam_away, rho)
    return float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum())


def _argmax_sign(probs: Sequence[float]) -> str:
    return SIGNS[max(range(3), key=lambda k: probs[k])]


def sign_support(item: IndexInput) -> dict[str, Any]:
    probs = (item.prob_home, item.prob_draw, item.prob_away)
    sign = _argmax_sign(probs)
    detail: dict[str, dict[str, float]] = {}
    agree = 0
    specialists = item.specialists if isinstance(item.specialists, dict) else {}
    for name in SPECIALISTS:
        opinion = specialists.get(name)
        if not isinstance(opinion, dict) or opinion.get("home") is None or opinion.get("away") is None:
            continue
        own = _one_x_two(float(opinion["home"]), float(opinion["away"]), item.rho)
        detail[name] = {s: round(p, 4) for s, p in zip(SIGNS, own)}
        agree += int(_argmax_sign(own) == sign)

    form = specialists.get("form")
    form_view = "non disponibile"
    if isinstance(form, dict) and sign != "X":
        try:
            home_play = float(form["home_attack_shots"]) - float(form["home_defence_shots"])
            away_play = float(form["away_attack_shots"]) - float(form["away_defence_shots"])
        except (KeyError, TypeError, ValueError):
            home_play = away_play = None
        if home_play is not None and away_play is not None:
            diff = (home_play - away_play) if sign == "1" else (away_play - home_play)
            form_view = "concorde" if diff > RELIABILITY_FORM_NEUTRAL else "contraria" if diff < -RELIABILITY_FORM_NEUTRAL else "neutra"
    elif sign == "X":
        form_view = "neutra"

    return {
        "sign": sign,
        "prob": round(probs[SIGNS.index(sign)], 4),
        "agents_agree": agree,
        "agents_total": len(detail),
        "specialists": detail,
        "form": form_view,
    }


# --- calcolo completo -------------------------------------------------------------------


@dataclass
class ReliabilityResult:
    per_match: dict[int, dict[str, Any]]
    models: list[ReliabilityModel]


def compute_reliability(inputs: Sequence[IndexInput]) -> ReliabilityResult:
    """Affidabilita' per ogni partita (input in ordine cronologico)."""
    signals = reliability_signals(inputs)
    seasons = sorted({item.match.season_label for item in inputs})
    by_season: dict[str, list[IndexInput]] = {s: [] for s in seasons}
    for item in inputs:
        by_season[item.match.season_label].append(item)

    per_match: dict[int, dict[str, Any]] = {}
    models: list[ReliabilityModel] = []
    for idx, season in enumerate(seasons):
        model: ReliabilityModel | None = None
        if idx > 0:
            previous = seasons[:idx]
            train = [item for s in previous for item in by_season[s]]
            model = fit_reliability_model(
                season,
                previous,
                [signals[item.match.lab_match_id] for item in train],
                [
                    excess_brier_1x2((it.prob_home, it.prob_draw, it.prob_away), it.match.ft_home, it.match.ft_away)
                    for it in train
                ],
            )
            models.append(model)
        for item in by_season[season]:
            s = signals[item.match.lab_match_id]
            value: float | None = None
            contributions: dict[str, float] | None = None
            if model is not None and not model.degenerate:
                risk, contributions = model.risk(s)
                rank = bisect.bisect_left(model.reference, risk)
                value = 100.0 * (1.0 - rank / len(model.reference))
            per_match[item.match.lab_match_id] = {
                "value": round(value, 1) if value is not None else None,
                "class": reliability_class(value),
                "signals": {k: round(v, 4) for k, v in s.items()},
                "contributions": (
                    {k: round(v, 4) for k, v in contributions.items()} if contributions is not None else None
                ),
                "new_team": bool(item.new_team_home or item.new_team_away),
                "early_season": not item.match.eval_eligible,
                "sign_support": sign_support(item),
            }
    return ReliabilityResult(per_match=per_match, models=models)


# --- esame R1-R4 ------------------------------------------------------------------------


def reliability_exam(
    inputs: Sequence[IndexInput],
    per_match: dict[int, dict[str, Any]],
    judge_seasons: tuple[str, ...],
    min_class_share: float,
) -> list[dict[str, Any]]:
    classes = ("bassa", "media", "alta")
    rows = [
        (item, per_match[item.match.lab_match_id])
        for item in inputs
        if item.match.season_label in judge_seasons
        and item.match.eval_eligible
        and item.match.lab_match_id in per_match
    ]

    def excess(item: IndexInput) -> float:
        return excess_brier_1x2((item.prob_home, item.prob_draw, item.prob_away), item.match.ft_home, item.match.ft_away)

    def overconfidence(item: IndexInput) -> float:
        probs = (item.prob_home, item.prob_draw, item.prob_away)
        k = max(range(3), key=lambda c: probs[c])
        return probs[k] - one_x_two_outcome(item.match.ft_home, item.match.ft_away)[k]

    def means(subset, metric) -> dict[str, tuple[int, float | None]]:
        buckets: dict[str, list[float]] = {c: [] for c in classes}
        for item, rel in subset:
            if rel["class"] in buckets:
                buckets[rel["class"]].append(metric(item))
        return {c: (len(v), (sum(v) / len(v)) if v else None) for c, v in buckets.items()}

    def decreasing(values: list[float | None]) -> bool:
        return all(v is not None for v in values) and all(b < a for a, b in zip(values, values[1:]))

    total = sum(1 for _, rel in rows if rel["class"] in classes)
    ex = means(rows, excess)
    oc = means(rows, overconfidence)

    realized = means(rows, lambda it: brier_1x2((it.prob_home, it.prob_draw, it.prob_away), one_x_two_outcome(it.match.ft_home, it.match.ft_away)))
    expected = means(rows, lambda it: expected_brier_1x2((it.prob_home, it.prob_draw, it.prob_away)))

    r1_rows = [
        {
            "class": c,
            "n": ex[c][0],
            "value": round(ex[c][1], 5) if ex[c][1] is not None else None,
            "realized": round(realized[c][1], 5) if realized[c][1] is not None else None,
            "expected": round(expected[c][1], 5) if expected[c][1] is not None else None,
        }
        for c in classes
    ]
    r2_rows = []
    for season in judge_seasons:
        per = means([(it, rel) for it, rel in rows if it.match.season_label == season], excess)
        low, high = per["bassa"][1], per["alta"][1]
        r2_rows.append(
            {
                "class": season,
                "n": per["bassa"][0] + per["media"][0] + per["alta"][0],
                "value": round(low - high, 5) if low is not None and high is not None else None,
            }
        )
    r3_rows = [
        {"class": c, "n": ex[c][0], "value": round(ex[c][0] / total, 4) if total else None} for c in classes
    ]
    r4_rows = [
        {"class": c, "n": oc[c][0], "value": round(oc[c][1], 5) if oc[c][1] is not None else None} for c in classes
    ]
    return [
        {
            "code": "R1",
            "label": "Affidabilita' bassa -> alta: errore in eccesso 1X2 sempre decrescente",
            "index": "affidabilita",
            "value_format": "brier_signed",
            "rows": r1_rows,
            "passed": decreasing([r["value"] for r in r1_rows]),
        },
        {
            "code": "R2",
            "label": "In ogni stagione: errore in eccesso bassa > alta",
            "index": "affidabilita",
            "value_format": "brier_signed",
            "rows": r2_rows,
            "passed": all(r["value"] is not None and r["value"] > 0 for r in r2_rows),
        },
        {
            "code": "R3",
            "label": f"Ogni classe con almeno il {min_class_share * 100:.0f}% delle partite",
            "index": "affidabilita",
            "value_format": "pct",
            "rows": r3_rows,
            "passed": all(r["value"] is not None and r["value"] >= min_class_share for r in r3_rows),
        },
        {
            "code": "R4",
            "label": "Eccesso di fiducia sul segno piu' probabile sempre decrescente",
            "index": "affidabilita",
            "value_format": "pp_signed",
            "rows": r4_rows,
            "passed": decreasing([r["value"] for r in r4_rows]),
        },
    ]


def sign_support_table(
    inputs: Sequence[IndexInput], per_match: dict[int, dict[str, Any]], judge_seasons: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Descrittivo: per numero di specialisti concordi, probabilita' media del
    segno e frequenza reale (stagioni di giudizio, partite idonee)."""
    buckets: dict[int, list[tuple[float, float]]] = {}
    for item in inputs:
        m = item.match
        if m.season_label not in judge_seasons or not m.eval_eligible or m.lab_match_id not in per_match:
            continue
        support = per_match[m.lab_match_id]["sign_support"]
        k = SIGNS.index(support["sign"])
        buckets.setdefault(int(support["agents_agree"]), []).append(
            (support["prob"], one_x_two_outcome(m.ft_home, m.ft_away)[k])
        )
    return [
        {
            "agents_agree": agree,
            "n": len(values),
            "mean_prob": round(sum(p for p, _ in values) / len(values), 4),
            "hit_rate": round(sum(h for _, h in values) / len(values), 4),
        }
        for agree, values in sorted(buckets.items())
    ]
