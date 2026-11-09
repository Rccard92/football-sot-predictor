"""
Engine Cecchino — funzioni pure, nessuna dipendenza dal motore SOT.
Parità formule foglio Excel CECCHINO (picchetti 1–5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.cecchino.cecchino_constants import (
    CECCHINO_1X2_SUM_TOLERANCE,
    CECCHINO_1X2_VERSION,
    CECCHINO_1X2_VERSION_V1,
    CECCHINO_HOME_FACTOR_1,
    CECCHINO_HOME_FACTOR_X,
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    PICCHETTO_STATUSES_FOR_FINAL,
    PLACEHOLDER_BOOKMAKER,
    PLACEHOLDER_RELIABILITY,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    WARNING_LOW_SAMPLE,
    WARNING_ZERO_MATCHES,
    WARNING_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


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
    home_sample_count: int | None = None
    away_sample_count: int | None = None
    home_target_sample: int | None = None
    away_target_sample: int | None = None

    def to_dict(self) -> dict[str, Any]:
        def _outcome(o: OutcomeOdds | None) -> dict[str, Any]:
            if o is None:
                return {
                    "prob": None,
                    "prob_pct": None,
                    "quota": None,
                    "mathematical_odds": None,
                }
            q = round(o.quota, 2) if o.quota is not None else None
            return {
                "prob": round(o.prob, 6) if o.prob is not None else None,
                "prob_pct": round(o.prob * 100, 4) if o.prob is not None else None,
                "quota": q,
                "mathematical_odds": q,
            }

        o1 = _outcome(self.outcome_1)
        ox = _outcome(self.outcome_x)
        o2 = _outcome(self.outcome_2)

        return {
            "key": self.key,
            "label": self.label,
            "input_records": {
                "home": self.home_context.to_dict(),
                "away": self.away_context.to_dict(),
            },
            "home_context": self.home_context.to_dict(),
            "away_context": self.away_context.to_dict(),
            "sample_home": self.home_sample_count,
            "sample_away": self.away_sample_count,
            "target_sample_home": self.home_target_sample,
            "target_sample_away": self.away_target_sample,
            "total_matches": self.total_matches,
            "probabilities": {
                "prob_1": o1["prob"],
                "prob_x": ox["prob"],
                "prob_2": o2["prob"],
                "prob_1_pct": o1["prob_pct"],
                "prob_x_pct": ox["prob_pct"],
                "prob_2_pct": o2["prob_pct"],
            },
            "mathematical_odds": {
                "quota_1": o1["mathematical_odds"],
                "quota_x": ox["mathematical_odds"],
                "quota_2": o2["mathematical_odds"],
            },
            "outcome_1": o1,
            "outcome_x": ox,
            "outcome_2": o2,
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
    # dal 09/11/2026: versione del calcolo, fattore campo, probabilita' prima del fattore e quota di prima (v1)
    version: str = CECCHINO_1X2_VERSION
    home_factor: dict[str, float] = field(default_factory=dict)
    raw_probs: dict[str, float] = field(default_factory=dict)
    v1: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        probs = [self.prob_1, self.prob_x, self.prob_2]
        return {
            "version": self.version,
            "home_factor": dict(self.home_factor),
            "raw_probs": {k: round(v, 6) for k, v in self.raw_probs.items()},
            "sum_prob": round(sum(probs), 6) if all(p is not None for p in probs) else None,
            "v1": dict(self.v1) if self.v1 else None,
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
    home_sample_count: int | None = None,
    away_sample_count: int | None = None,
    home_target_sample: int | None = None,
    away_target_sample: int | None = None,
) -> PicchettoBlock:
    """Calcola probabilità e quote 1/X/2 per un picchetto."""
    total_matches = home.total + away.total
    block = PicchettoBlock(
        key=key,
        label=label or PICCHETTO_LABELS.get(key, key),
        home_context=home,
        away_context=away,
        total_matches=total_matches,
        home_sample_count=home_sample_count,
        away_sample_count=away_sample_count,
        home_target_sample=home_target_sample,
        away_target_sample=away_target_sample,
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

    low_sample = False
    if home_target_sample is not None and home_sample_count is not None:
        if home_sample_count < home_target_sample:
            warnings.append(f"{WARNING_LOW_SAMPLE}:{key}:home")
            low_sample = True
    if away_target_sample is not None and away_sample_count is not None:
        if away_sample_count < away_target_sample:
            warnings.append(f"{WARNING_LOW_SAMPLE}:{key}:away")
            low_sample = True

    block.outcome_1 = OutcomeOdds(prob=prob_1 if prob_1 > 0 else None, quota=_prob_to_quota(prob_1))
    block.outcome_x = OutcomeOdds(prob=prob_x if prob_x > 0 else None, quota=_prob_to_quota(prob_x))
    block.outcome_2 = OutcomeOdds(prob=prob_2 if prob_2 > 0 else None, quota=_prob_to_quota(prob_2))
    block.warnings = warnings

    outcomes = (block.outcome_1, block.outcome_x, block.outcome_2)
    if any(o is None or o.quota is None for o in outcomes):
        block.status = STATUS_INSUFFICIENT_DATA
    elif low_sample:
        block.status = STATUS_PARTIAL_LOW_SAMPLE
    else:
        block.status = STATUS_AVAILABLE

    return block


def picchetti_blocks_from_output_json(output: dict[str, Any]) -> dict[str, PicchettoBlock]:
    """Ricostruisce PicchettoBlock da cecchino_output_json già persistito (solo quote/status)."""
    raw_picchetti = output.get("picchetti") or {}
    if not isinstance(raw_picchetti, dict):
        return {}

    def _outcome(block: dict[str, Any], attr: str) -> OutcomeOdds | None:
        o = block.get(attr)
        if not isinstance(o, dict):
            return None
        quota = o.get("quota")
        if quota is None:
            quota = (o.get("mathematical_odds") if isinstance(o.get("mathematical_odds"), (int, float)) else None)
        prob = o.get("prob")
        try:
            q = float(quota) if quota is not None else None
        except (TypeError, ValueError):
            q = None
        try:
            p = float(prob) if prob is not None else None
        except (TypeError, ValueError):
            p = None
        if q is None and p is None:
            return None
        return OutcomeOdds(prob=p, quota=q)

    blocks: dict[str, PicchettoBlock] = {}
    for pic_key in (
        PICCHETTO_KEY_HOME_AWAY,
        PICCHETTO_KEY_TOTALS,
        PICCHETTO_KEY_LAST5_HOME_AWAY,
        PICCHETTO_KEY_LAST6_TOTALS,
    ):
        block = raw_picchetti.get(pic_key)
        if not isinstance(block, dict):
            continue
        home_ctx = block.get("home_context") or (block.get("input_records") or {}).get("home") or {}
        away_ctx = block.get("away_context") or (block.get("input_records") or {}).get("away") or {}
        if not isinstance(home_ctx, dict):
            home_ctx = {}
        if not isinstance(away_ctx, dict):
            away_ctx = {}

        def _wdl(ctx: dict[str, Any]) -> WDLRecord:
            return WDLRecord(
                wins=int(ctx.get("wins") or 0),
                draws=int(ctx.get("draws") or 0),
                losses=int(ctx.get("losses") or 0),
            )

        pb = PicchettoBlock(
            key=pic_key,
            label=str(block.get("label") or pic_key),
            home_context=_wdl(home_ctx),
            away_context=_wdl(away_ctx),
            total_matches=int(block.get("total_matches") or 0),
            outcome_1=_outcome(block, "outcome_1"),
            outcome_x=_outcome(block, "outcome_x"),
            outcome_2=_outcome(block, "outcome_2"),
            status=str(block.get("status") or STATUS_INSUFFICIENT_DATA),
            warnings=list(block.get("warnings") or []),
            home_sample_count=block.get("sample_home"),
            away_sample_count=block.get("sample_away"),
            home_target_sample=block.get("target_sample_home"),
            away_target_sample=block.get("target_sample_away"),
        )
        blocks[pic_key] = pb
    return blocks


def _home_factor() -> tuple[float, float]:
    try:
        from app.core.config import get_settings

        st = get_settings()
        return float(st.cecchino_home_factor_1), float(st.cecchino_home_factor_x)
    except Exception:  # noqa: BLE001 - senza configurazione (script, test) valgono i valori del back test
        return CECCHINO_HOME_FACTOR_1, CECCHINO_HOME_FACTOR_X


def compute_final_odds(
    picchetti: dict[str, PicchettoBlock],
    *,
    weights: dict[str, float] | None = None,
    home_factor: tuple[float, float] | None = None,
) -> FinalOddsBlock:
    """Quota finale Cecchino 1-X-2 (v2 dal 09/11/2026, documento "Modifiche" di Giovanni, punto 4).

    1. probabilita' = 0,3/q totali + 0,3/q casa-fuori + 0,2/q ultime 6 + 0,2/q ultime 5 (media pesata delle
       probabilita' dei picchetti: la somma fa 100%; la media delle quote di prima dava ~95%);
    2. fattore campo: probabilita' 1 x 1,25 e X x 1,05, la 2 invariata, poi di nuovo somma al 100%;
    3. quota = 1 / probabilita'.
    La quota di prima (media pesata delle quote) resta in `v1` per il confronto."""
    w = weights or FINAL_QUOTA_WEIGHTS
    k1, kx = home_factor if home_factor is not None else _home_factor()
    final = FinalOddsBlock(weights=dict(w), home_factor={"1": k1, "x": kx, "2": 1.0})
    missing_keys: list[str] = []
    v1 = {"quota_1": 0.0, "quota_x": 0.0, "quota_2": 0.0}
    raw = {"1": 0.0, "x": 0.0, "2": 0.0}
    weight_sum = 0.0

    for pic_key, weight in w.items():
        block = picchetti.get(pic_key)
        if block is None or block.status not in PICCHETTO_STATUSES_FOR_FINAL:
            missing_keys.append(pic_key)
            continue
        weight_sum += float(weight)
        for outcome_attr, quota_attr, sign in (
            ("outcome_1", "quota_1", "1"),
            ("outcome_x", "quota_x", "x"),
            ("outcome_2", "quota_2", "2"),
        ):
            outcome = getattr(block, outcome_attr)
            if outcome is None or outcome.quota is None or float(outcome.quota) <= 0:
                missing_keys.append(f"{pic_key}:{quota_attr}")
                continue
            v1[quota_attr] += weight * float(outcome.quota)
            raw[sign] += weight / float(outcome.quota)

    if missing_keys:
        final.status = STATUS_INSUFFICIENT_DATA
        final.warnings.append(f"missing_picchetto_quotas:{','.join(missing_keys)}")
        return final

    final.v1 = {k: round(v, 4) for k, v in v1.items()}
    final.v1.update({"version": CECCHINO_1X2_VERSION_V1})  # type: ignore[dict-item]
    # pesi che non sommano a 1 (modelli di ricerca): media pesata vera
    if weight_sum > 0:
        raw = {k: v / weight_sum for k, v in raw.items()}
    final.raw_probs = dict(raw)
    scaled = {"1": raw["1"] * k1, "x": raw["x"] * kx, "2": raw["2"]}
    total = sum(scaled.values())
    if total <= 0 or any(v <= 0 for v in scaled.values()):
        final.status = STATUS_INSUFFICIENT_DATA
        final.warnings.append(f"{WARNING_ZERO_PROBABILITY}:final")
        return final
    final.prob_1, final.prob_x, final.prob_2 = (scaled[k] / total for k in ("1", "x", "2"))
    final.quota_1, final.quota_x, final.quota_2 = (1.0 / p for p in (final.prob_1, final.prob_x, final.prob_2))
    # controllo: 1/q1 + 1/qX + 1/q2 = 100% (tolleranza 0,5%)
    if abs(sum(1.0 / q for q in (final.quota_1, final.quota_x, final.quota_2)) - 1.0) > CECCHINO_1X2_SUM_TOLERANCE:
        final.warnings.append("final_sum_out_of_tolerance")
    final.status = STATUS_AVAILABLE
    return final


def build_full_cecchino_output(
    inp: CecchinoCalculationInput,
    *,
    picchetto_sample_meta: dict[str, dict[str, int | None]] | None = None,
) -> CecchinoCalculationOutput:
    """Pipeline completa: 4 picchetti + quota finale + placeholder sezioni 6–8."""
    meta = picchetto_sample_meta or {}

    def _pic(key: str, home: WDLRecord, away: WDLRecord) -> PicchettoBlock:
        m = meta.get(key, {})
        return compute_picchetto(
            key,
            home,
            away,
            home_sample_count=m.get("home_sample_count"),
            away_sample_count=m.get("away_sample_count"),
            home_target_sample=m.get("home_target_sample"),
            away_target_sample=m.get("away_target_sample"),
        )

    picchetti = {
        PICCHETTO_KEY_HOME_AWAY: _pic(PICCHETTO_KEY_HOME_AWAY, inp.home_away[0], inp.home_away[1]),
        PICCHETTO_KEY_TOTALS: _pic(PICCHETTO_KEY_TOTALS, inp.totals[0], inp.totals[1]),
        PICCHETTO_KEY_LAST5_HOME_AWAY: _pic(
            PICCHETTO_KEY_LAST5_HOME_AWAY,
            inp.last5_home_away[0],
            inp.last5_home_away[1],
        ),
        PICCHETTO_KEY_LAST6_TOTALS: _pic(
            PICCHETTO_KEY_LAST6_TOTALS,
            inp.last6_totals[0],
            inp.last6_totals[1],
        ),
    }
    final = compute_final_odds(picchetti)

    all_warnings: list[str] = []
    for p in picchetti.values():
        all_warnings.extend(p.warnings)
    all_warnings.extend(final.warnings)

    pic_statuses = {p.status for p in picchetti.values()}
    if final.status == STATUS_AVAILABLE:
        if STATUS_PARTIAL_LOW_SAMPLE in pic_statuses:
            overall = STATUS_PARTIAL_LOW_SAMPLE
        else:
            overall = STATUS_AVAILABLE
    elif any(s in PICCHETTO_STATUSES_FOR_FINAL for s in pic_statuses):
        overall = STATUS_INSUFFICIENT_DATA
    else:
        overall = STATUS_INSUFFICIENT_DATA

    home_away_block = picchetti[PICCHETTO_KEY_HOME_AWAY]
    sample_home = home_away_block.home_sample_count or 0
    sample_away = home_away_block.away_sample_count or 0
    sample_split = int(sample_home) + int(sample_away)

    signals_matrix = build_signals_matrix(
        q1=final.quota_1,
        qx=final.quota_x,
        q2=final.quota_2,
        sample_home_away_split=sample_split,
        prob_1=final.prob_1,
        prob_x=final.prob_x,
        prob_2=final.prob_2,
    )
    all_warnings.extend(signals_matrix.get("warnings") or [])

    reliability_index = signals_matrix.get("reliability") or dict(PLACEHOLDER_RELIABILITY)

    return CecchinoCalculationOutput(
        picchetti=picchetti,
        final=final,
        signals_matrix=signals_matrix,
        reliability_index=reliability_index,
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
