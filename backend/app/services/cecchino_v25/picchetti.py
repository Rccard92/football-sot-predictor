"""Picchetti 1X2 V2.5: stesse 4 finestre e stessi pesi della V2, calcoli corretti.

Correzioni rispetto alla V2:
- la quota finale V2 era la media pesata delle QUOTE dei picchetti: una media di quote
  gonfia gli esiti incerti (soprattutto la X) e le tre probabilita' non sommano a 1.
  In V2.5 si fa la media pesata delle PROBABILITA' (somma sempre 1) e la quota e' 1/p;
- in V2 un esito con 0 casi in una finestra rendeva la partita non calcolabile. In V2.5
  ogni picchetto aggiunge poche partite "virtuali" con le frequenze del campionato:
  con poche partite la stima resta vicina al campionato e nessun esito vale 0.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import (
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    WARNING_LOW_SAMPLE,
    WARNING_ZERO_MATCHES,
)
from app.services.cecchino.cecchino_engine import PICCHETTO_LABELS, WDLRecord
from app.services.cecchino_v25.constants import PICCHETTI_PRIOR_MATCHES
from app.services.cecchino_v25.league import LeagueReference

FORMULA_VERSION = "cecchino_v25_picchetti_v1"


def _quota(p: float) -> float:
    return 1.0 / p


def picchetto_probabilities(
    home: WDLRecord,
    away: WDLRecord,
    league: LeagueReference,
    *,
    prior_matches: float = PICCHETTI_PRIOR_MATCHES,
) -> tuple[float, float, float] | None:
    """(p1, pX, p2) del picchetto: conteggi V2 + partite virtuali di campionato."""
    n = home.total + away.total
    if n == 0:
        return None
    k = prior_matches
    p1 = (home.wins + away.losses + k * league.p_home) / (n + k)
    px = (home.draws + away.draws + k * league.p_draw) / (n + k)
    p2 = (home.losses + away.wins + k * league.p_away) / (n + k)
    total = p1 + px + p2
    return p1 / total, px / total, p2 / total


def _block(
    key: str,
    home: WDLRecord,
    away: WDLRecord,
    league: LeagueReference,
    meta: dict[str, Any],
    prior_matches: float,
) -> dict[str, Any]:
    probs = picchetto_probabilities(home, away, league, prior_matches=prior_matches)
    warnings: list[str] = []
    low_sample = False
    for side in ("home", "away"):
        count, target = meta.get(f"{side}_sample_count"), meta.get(f"{side}_target_sample")
        if count is not None and target is not None and count < target:
            warnings.append(f"{WARNING_LOW_SAMPLE}:{key}:{side}")
            low_sample = True

    def outcome(p: float | None) -> dict[str, Any]:
        if p is None:
            return {"prob": None, "prob_pct": None, "quota": None, "mathematical_odds": None}
        q = round(_quota(p), 4)
        return {"prob": round(p, 6), "prob_pct": round(p * 100, 4), "quota": q, "mathematical_odds": q}

    if probs is None:
        warnings.append(WARNING_ZERO_MATCHES)
        status = STATUS_INSUFFICIENT_DATA
        o1 = ox = o2 = outcome(None)
    else:
        status = STATUS_PARTIAL_LOW_SAMPLE if low_sample else STATUS_AVAILABLE
        o1, ox, o2 = (outcome(p) for p in probs)
    return {
        "key": key,
        "label": PICCHETTO_LABELS.get(key, key),
        "home_context": home.to_dict(),
        "away_context": away.to_dict(),
        "input_records": {"home": home.to_dict(), "away": away.to_dict()},
        "sample_home": meta.get("home_sample_count"),
        "sample_away": meta.get("away_sample_count"),
        "target_sample_home": meta.get("home_target_sample"),
        "target_sample_away": meta.get("away_target_sample"),
        "total_matches": home.total + away.total,
        "league_prior_matches": prior_matches,
        "probabilities": {
            "prob_1": o1["prob"], "prob_x": ox["prob"], "prob_2": o2["prob"],
        },
        "mathematical_odds": {
            "quota_1": o1["quota"], "quota_x": ox["quota"], "quota_2": o2["quota"],
        },
        "outcome_1": o1,
        "outcome_x": ox,
        "outcome_2": o2,
        "status": status,
        "warnings": warnings,
    }


def compute_cecchino_v25(
    contexts: Any,
    league: LeagueReference,
    *,
    prior_matches: float = PICCHETTI_PRIOR_MATCHES,
) -> dict[str, Any]:
    """Output con la stessa forma di `cecchino_output_json` della V2 (picchetti + final)."""
    records = {
        PICCHETTO_KEY_HOME_AWAY: (contexts.home_context, contexts.away_context),
        PICCHETTO_KEY_TOTALS: (contexts.home_total, contexts.away_total),
        PICCHETTO_KEY_LAST5_HOME_AWAY: (contexts.home_recent_context_5, contexts.away_recent_context_5),
        PICCHETTO_KEY_LAST6_TOTALS: (contexts.home_recent_total_6, contexts.away_recent_total_6),
    }
    picchetti = {
        key: _block(key, h, a, league, contexts.sample_meta.get(key) or {}, prior_matches)
        for key, (h, a) in records.items()
    }

    weights = dict(FINAL_QUOTA_WEIGHTS)
    acc = [0.0, 0.0, 0.0]
    used = 0.0
    missing: list[str] = []
    for key, weight in weights.items():
        block = picchetti[key]
        p = block["probabilities"]
        if block["status"] == STATUS_INSUFFICIENT_DATA or p["prob_1"] is None:
            missing.append(key)
            continue
        acc[0] += weight * p["prob_1"]
        acc[1] += weight * p["prob_x"]
        acc[2] += weight * p["prob_2"]
        used += weight

    warnings = [w for b in picchetti.values() for w in b["warnings"]]
    if missing or used <= 0:
        final = {
            "quota_1": None, "quota_x": None, "quota_2": None,
            "prob_1": None, "prob_x": None, "prob_2": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "warnings": [f"missing_picchetti:{','.join(missing)}"],
            "weights": weights,
            "formula_version": FORMULA_VERSION,
        }
        status = STATUS_INSUFFICIENT_DATA
    else:
        p1, px, p2 = (v / used for v in acc)
        final = {
            "quota_1": round(_quota(p1), 4),
            "quota_x": round(_quota(px), 4),
            "quota_2": round(_quota(p2), 4),
            "prob_1": round(p1, 6),
            "prob_x": round(px, 6),
            "prob_2": round(p2, 6),
            "prob_1_pct": round(p1 * 100, 2),
            "prob_x_pct": round(px * 100, 2),
            "prob_2_pct": round(p2 * 100, 2),
            "status": STATUS_AVAILABLE,
            "warnings": [],
            "weights": weights,
            "formula_version": FORMULA_VERSION,
            "method": "media_pesata_probabilita",
        }
        statuses = {b["status"] for b in picchetti.values()}
        status = STATUS_PARTIAL_LOW_SAMPLE if STATUS_PARTIAL_LOW_SAMPLE in statuses else STATUS_AVAILABLE
    warnings.extend(final["warnings"])
    return {
        "picchetti": picchetti,
        "final": final,
        "league_reference": league.to_dict(),
        "status": status,
        "warnings": warnings,
        "formula_version": FORMULA_VERSION,
    }
