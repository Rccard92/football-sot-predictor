"""
Engine Cecchino — funzioni pure, nessuna dipendenza dal motore SOT.
Parità formule foglio Excel CECCHINO (picchetti 1–5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.cecchino.cecchino_constants import (
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    PLACEHOLDER_BOOKMAKER,
    PLACEHOLDER_RELIABILITY,
    PLACEHOLDER_SIGNALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    WARNING_ZERO_MATCHES,
    WARNING_ZERO_PROBABILITY,
)


@dataclass(frozen=True)
class WDLRecord:
    wins: int
    draws: int
    losses: int

    @property
    def total(self) -> int:
        return int(self.wins) + int(self.draws) + int(self.losses)

    def to_dict(self) -> dict[str, int]:
        return {"wins": self.wins, "draws": self.draws, "losses": self.losses}


@dataclass
class OutcomeOdds:
    prob: float | None = None
    quota: float | None = None


@dataclass
class PicchettoBlock:
    key: str
    label: str
    home_context: WDLRecord
    away_context: WDLRecord
    total_matches: int
    outcome_1: OutcomeOdds | None = None
    outcome_x: OutcomeOdds | None = None
    outcome_2: OutcomeOdds | None = None
    status: str = STATUS_INSUFFICIENT_DATA
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _outcome(o: OutcomeOdds | None) -> dict[str, Any]:
            if o is None:
                return {"prob": None, "prob_pct": None, "quota": None}
            return {
                "prob": round(o.prob, 6) if o.prob is not None else None,
                "prob_pct": round(o.prob * 100, 4) if o.prob is not None else None,
                "quota": round(o.quota, 2) if o.quota is not None else None,
            }

        return {
            "key": self.key,
            "label": self.label,
            "home_context": self.home_context.to_dict(),
            "away_context": self.away_context.to_dict(),
            "total_matches": self.total_matches,
            "outcome_1": _outcome(self.outcome_1),
            "outcome_x": _outcome(self.outcome_x),
            "outcome_2": _outcome(self.outcome_2),
            "status": self.status,
            "warnings": list(self.warnings),
        }


@dataclass
class FinalOddsBlock:
    quota_1: float | None = None
    quota_x: float | None = None
    quota_2: float | None = None
    prob_1: float | None = None
    prob_x: float | None = None
    prob_2: float | None = None
    status: str = STATUS_INSUFFICIENT_DATA
    warnings: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(FINAL_QUOTA_WEIGHTS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "quota_1": round(self.quota_1, 4) if self.quota_1 is not None else None,
            "quota_x": round(self.quota_x, 4) if self.quota_x is not None else None,
            "quota_2": round(self.quota_2, 4) if self.quota_2 is not None else None,
            "prob_1": round(self.prob_1, 6) if self.prob_1 is not None else None,
            "prob_x": round(self.prob_x, 6) if self.prob_x is not None else None,
            "prob_2": round(self.prob_2, 6) if self.prob_2 is not None else None,
            "prob_1_pct": round(self.prob_1 * 100, 2) if self.prob_1 is not None else None,
            "prob_x_pct": round(self.prob_x * 100, 2) if self.prob_x is not None else None,
            "prob_2_pct": round(self.prob_2 * 100, 2) if self.prob_2 is not None else None,
            "status": self.status,
            "warnings": list(self.warnings),
            "weights": dict(self.weights),
        }


@dataclass
class CecchinoCalculationInput:
    home_away: tuple[WDLRecord, WDLRecord]
    totals: tuple[WDLRecord, WDLRecord]
    last5_home_away: tuple[WDLRecord, WDLRecord]
    last6_totals: tuple[WDLRecord, WDLRecord]


@dataclass
class CecchinoCalculationOutput:
    picchetti: dict[str, PicchettoBlock]
    final: FinalOddsBlock
    signals_matrix: dict[str, Any]
    reliability_index: dict[str, Any]
    bookmaker_comparison: dict[str, Any]
    status: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "picchetti": {k: v.to_dict() for k, v in self.picchetti.items()},
            "final": self.final.to_dict(),
            "signals_matrix": dict(self.signals_matrix),
            "reliability_index": dict(self.reliability_index),
            "bookmaker_comparison": dict(self.bookmaker_comparison),
            "status": self.status,
            "warnings": list(self.warnings),
        }


PICCHETTO_LABELS = {
    PICCHETTO_KEY_HOME_AWAY: "Casa/Trasferta",
    PICCHETTO_KEY_TOTALS: "Totali",
    PICCHETTO_KEY_LAST5_HOME_AWAY: "Ultime 5 casa/fuori",
    PICCHETTO_KEY_LAST6_TOTALS: "Ultime 6 totali",
}


def _prob_to_quota(prob: float) -> float | None:
    if prob <= 0:
        return None
    return 1.0 / prob


def compute_picchetto(
    key: str,
    home: WDLRecord,
    away: WDLRecord,
    *,
    label: str | None = None,
) -> PicchettoBlock:
    """Calcola probabilità e quote 1/X/2 per un picchetto."""
    total_matches = home.total + away.total
    block = PicchettoBlock(
        key=key,
        label=label or PICCHETTO_LABELS.get(key, key),
        home_context=home,
        away_context=away,
        total_matches=total_matches,
    )

    if total_matches == 0:
        block.warnings.append(WARNING_ZERO_MATCHES)
        block.status = STATUS_INSUFFICIENT_DATA
        return block

    prob_1 = (home.wins + away.losses) / total_matches
    prob_x = (home.draws + away.draws) / total_matches
    prob_2 = (home.losses + away.wins) / total_matches

    warnings: list[str] = []
    for name, prob in (("1", prob_1), ("X", prob_x), ("2", prob_2)):
        if prob <= 0:
            warnings.append(f"{WARNING_ZERO_PROBABILITY}:{name}")

    block.outcome_1 = OutcomeOdds(prob=prob_1 if prob_1 > 0 else None, quota=_prob_to_quota(prob_1))
    block.outcome_x = OutcomeOdds(prob=prob_x if prob_x > 0 else None, quota=_prob_to_quota(prob_x))
    block.outcome_2 = OutcomeOdds(prob=prob_2 if prob_2 > 0 else None, quota=_prob_to_quota(prob_2))
    block.warnings = warnings

    outcomes = (block.outcome_1, block.outcome_x, block.outcome_2)
    if any(o is None or o.quota is None for o in outcomes):
        block.status = STATUS_INSUFFICIENT_DATA
    else:
        block.status = STATUS_AVAILABLE

    return block


def compute_final_odds(picchetti: dict[str, PicchettoBlock]) -> FinalOddsBlock:
    """Quota finale Cecchino = media ponderata delle quote dei picchetti."""
    final = FinalOddsBlock()
    missing_keys: list[str] = []
    weighted_warnings: list[str] = []

    for pic_key, weight in FINAL_QUOTA_WEIGHTS.items():
        block = picchetti.get(pic_key)
        if block is None or block.status != STATUS_AVAILABLE:
            missing_keys.append(pic_key)
            continue
        for outcome_attr, quota_attr in (
            ("outcome_1", "quota_1"),
            ("outcome_x", "quota_x"),
            ("outcome_2", "quota_2"),
        ):
            outcome = getattr(block, outcome_attr)
            if outcome is None or outcome.quota is None:
                missing_keys.append(f"{pic_key}:{quota_attr}")
                continue
            current = getattr(final, quota_attr)
            setattr(final, quota_attr, (current or 0.0) + weight * float(outcome.quota))

    if missing_keys:
        final.status = STATUS_INSUFFICIENT_DATA
        final.warnings.append(f"missing_picchetto_quotas:{','.join(missing_keys)}")
        return final

    final.quota_1 = final.quota_1  # type: ignore[assignment]
    final.quota_x = final.quota_x
    final.quota_2 = final.quota_2

    for quota_attr, prob_attr in (
        ("quota_1", "prob_1"),
        ("quota_x", "prob_x"),
        ("quota_2", "prob_2"),
    ):
        q = getattr(final, quota_attr)
        if q is None or q <= 0:
            setattr(final, prob_attr, None)
            weighted_warnings.append(f"{WARNING_ZERO_PROBABILITY}:final_{prob_attr}")
        else:
            setattr(final, prob_attr, 1.0 / q)

    if weighted_warnings or any(
        getattr(final, p) is None for p in ("prob_1", "prob_x", "prob_2")
    ):
        final.warnings = weighted_warnings
        final.status = STATUS_INSUFFICIENT_DATA
    else:
        final.status = STATUS_AVAILABLE

    return final


def build_full_cecchino_output(inp: CecchinoCalculationInput) -> CecchinoCalculationOutput:
    """Pipeline completa: 4 picchetti + quota finale + placeholder sezioni 6–8."""
    picchetti = {
        PICCHETTO_KEY_HOME_AWAY: compute_picchetto(
            PICCHETTO_KEY_HOME_AWAY, inp.home_away[0], inp.home_away[1]
        ),
        PICCHETTO_KEY_TOTALS: compute_picchetto(
            PICCHETTO_KEY_TOTALS, inp.totals[0], inp.totals[1]
        ),
        PICCHETTO_KEY_LAST5_HOME_AWAY: compute_picchetto(
            PICCHETTO_KEY_LAST5_HOME_AWAY, inp.last5_home_away[0], inp.last5_home_away[1]
        ),
        PICCHETTO_KEY_LAST6_TOTALS: compute_picchetto(
            PICCHETTO_KEY_LAST6_TOTALS, inp.last6_totals[0], inp.last6_totals[1]
        ),
    }
    final = compute_final_odds(picchetti)

    all_warnings: list[str] = []
    for p in picchetti.values():
        all_warnings.extend(p.warnings)
    all_warnings.extend(final.warnings)

    if final.status == STATUS_AVAILABLE:
        overall = STATUS_AVAILABLE
    elif any(p.status == STATUS_AVAILABLE for p in picchetti.values()):
        overall = STATUS_INSUFFICIENT_DATA
    else:
        overall = STATUS_INSUFFICIENT_DATA

    return CecchinoCalculationOutput(
        picchetti=picchetti,
        final=final,
        signals_matrix=dict(PLACEHOLDER_SIGNALS),
        reliability_index=dict(PLACEHOLDER_RELIABILITY),
        bookmaker_comparison=dict(PLACEHOLDER_BOOKMAKER),
        status=overall,
        warnings=all_warnings,
    )


def input_from_manual_dict(data: dict[str, Any]) -> CecchinoCalculationInput:
    """Costruisce input da payload debug (chiavi home_away, totals, …)."""

    def _wdl(block: dict[str, Any]) -> WDLRecord:
        return WDLRecord(
            wins=int(block.get("wins", 0)),
            draws=int(block.get("draws", 0)),
            losses=int(block.get("losses", 0)),
        )

    def _pair(key: str) -> tuple[WDLRecord, WDLRecord]:
        section = data[key]
        return _wdl(section["home"]), _wdl(section["away"])

    return CecchinoCalculationInput(
        home_away=_pair("home_away"),
        totals=_pair("totals"),
        last5_home_away=_pair("last5_home_away"),
        last6_totals=_pair("last6_totals"),
    )


def manual_input_to_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Serializza input manuale per input_snapshot_json."""
    inp = input_from_manual_dict(data)
    return {
        "home_away": {
            "home": asdict(inp.home_away[0]),
            "away": asdict(inp.home_away[1]),
        },
        "totals": {
            "home": asdict(inp.totals[0]),
            "away": asdict(inp.totals[1]),
        },
        "last5_home_away": {
            "home": asdict(inp.last5_home_away[0]),
            "away": asdict(inp.last5_home_away[1]),
        },
        "last6_totals": {
            "home": asdict(inp.last6_totals[0]),
            "away": asdict(inp.last6_totals[1]),
        },
    }
