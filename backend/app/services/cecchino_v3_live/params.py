"""Parametri congelati della V3 estesa.

Nessun parametro nuovo: si usano quelli che il modello di riferimento V3 (Forza + Gioco
tiri in porta e tiri + Forma + Calendario) ha scelto per l'ultima stagione del Lab nel
calcolo finale (iperparametri per specialista, pesi dell'orchestratore con e senza
correzioni). Se il calcolo non e' nel database valgono i valori salvati qui, identici a
quelli del calcolo finale #11 (stagione 2025/2026).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino_v3.constants import Hyper

ENGINE_VERSION = "cecchino_v3_extended_v1"
MODEL_LABEL = "V3 estesa"

_FALLBACK = {
    "source_run_id": 11,
    "season": "2025/2026",
    "hyper": {"forza": (0.002, 0.4), "sot": (0.004, 0.4), "shots": (0.004, 0.4)},
    "weights": {
        "sot": 0.2601,
        "forza": 0.488955,
        "shots": 0.343216,
        "intercept": -0.03365,
        "form_goals": -0.008395,
        "form_shots": 0.19625,
        "final_phase": 0.081146,
        "rest_attack": -0.09047,
        "rest_defence": 0.123995,
    },
    "base_weights": None,
}


@dataclass(frozen=True)
class V3Params:
    source_run_id: int | None
    season: str
    hyper_forza: Hyper
    hyper_sot: Hyper
    hyper_shots: Hyper
    weights: dict[str, float]
    base_weights: dict[str, float]
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_version": ENGINE_VERSION,
            "source_run_id": self.source_run_id,
            "season": self.season,
            "hyper": {
                "forza": {"xi": self.hyper_forza.xi, "sigma": self.hyper_forza.sigma},
                "sot": {"xi": self.hyper_sot.xi, "sigma": self.hyper_sot.sigma},
                "shots": {"xi": self.hyper_shots.xi, "sigma": self.hyper_shots.sigma},
            },
            "weights": self.weights,
        }


_cache: V3Params | None = None
_lock = threading.Lock()


def _hyper(value: Any, default: tuple[float, float]) -> Hyper:
    if isinstance(value, dict) and value.get("xi") is not None and value.get("sigma") is not None:
        return Hyper(xi=float(value["xi"]), sigma=float(value["sigma"]))
    return Hyper(xi=default[0], sigma=default[1])


def _from_summary(run_id: int, summary: dict[str, Any]) -> V3Params | None:
    weights_by_season = summary.get("orchestrator_weights") or {}
    if not weights_by_season:
        return None
    season = max(weights_by_season)
    base = (summary.get("base_orchestrator_weights") or {}).get(season)
    game = summary.get("game_chosen_hyper") or {}
    return V3Params(
        source_run_id=run_id,
        season=season,
        hyper_forza=_hyper((summary.get("chosen_hyper") or {}).get(season), _FALLBACK["hyper"]["forza"]),
        hyper_sot=_hyper((game.get("sot") or {}).get(season), _FALLBACK["hyper"]["sot"]),
        hyper_shots=_hyper((game.get("shots") or {}).get(season), _FALLBACK["hyper"]["shots"]),
        weights={k: float(v) for k, v in weights_by_season[season].items()},
        base_weights={k: float(v) for k, v in (base or {}).items()} or _base_from(weights_by_season[season]),
    )


def _base_from(weights: dict[str, float]) -> dict[str, float]:
    return {k: float(weights[k]) for k in ("intercept", "forza", "sot", "shots")}


def fallback_params() -> V3Params:
    f = _FALLBACK
    return V3Params(
        source_run_id=f["source_run_id"],
        season=f["season"],
        hyper_forza=Hyper(*f["hyper"]["forza"]),
        hyper_sot=Hyper(*f["hyper"]["sot"]),
        hyper_shots=Hyper(*f["hyper"]["shots"]),
        weights=dict(f["weights"]),
        base_weights=_base_from(f["weights"]),
    )


def load_params(db: Session) -> V3Params:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        params: V3Params | None = None
        try:
            from app.services.cecchino_v3.runs import final_model_run

            run = final_model_run(db)
            if run is not None and isinstance(run.summary_json, dict):
                params = _from_summary(int(run.id), run.summary_json)
        except Exception:  # noqa: BLE001 - senza database valgono i parametri salvati
            params = None
        _cache = params or fallback_params()
        return _cache
