"""Registry formula-configurable per replay Acquistabilità Lab (V3 / V3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_AUDIT_VERSION,
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    calculate_purchasability_v3_batch,
)
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    calculate_purchasability_v31_batch,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)

FormulaId = Literal["v3", "v31"]
FORMULA_ID_V3 = "v3"
FORMULA_ID_V31 = "v31"

# Allineate a historical_purchasability_v3_replay_{preflight,resolver,service}.
PREFLIGHT_SCHEMA_VERSION_V3 = "cecchino_lab_purchasability_v3_replay_preflight_v2"
REPLAY_SCHEMA_VERSION_V3 = "cecchino_lab_purchasability_v3_replay_v1"
REPLAY_ENGINE_VERSION_V3 = "cecchino_lab_purchasability_v3_replay_engine_v1"

PREFLIGHT_SCHEMA_VERSION_V31 = "cecchino_lab_purchasability_v31_replay_preflight_v1"
REPLAY_SCHEMA_VERSION_V31 = "cecchino_lab_purchasability_v31_replay_v1"
REPLAY_ENGINE_VERSION_V31 = "cecchino_lab_purchasability_v31_replay_engine_v1"
ANALYTICS_SCHEMA_VERSION_V31 = "cecchino_lab_purchasability_v31_analytics_v1"
EXPORT_SCHEMA_VERSION_V31 = "cecchino_lab_purchasability_v31_export_v1"
INTEGRITY_POLICY_VERSION = "cecchino_lab_historical_reconstruction_integrity_v1"

# Stesse 8 chiavi del preflight V3 (ridefinite per evitare import circolari).
V3_MARKET_ORDER: tuple[str, ...] = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
)

V31_MARKET_ORDER: tuple[str, ...] = tuple(PANEL_MARKET_KEYS)

BatchFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ReplayFormulaConfig:
    """Config immutabile di una formula replay Lab."""

    formula_id: FormulaId
    formula_version: str
    candidate_version: str
    audit_version: str
    market_order: tuple[str, ...]
    requires_historical_reliability: bool
    preflight_schema_version: str
    replay_schema_version: str
    replay_engine_version: str
    calculate_batch: BatchFn

    @property
    def is_v3(self) -> bool:
        return self.formula_id == "v3"

    @property
    def is_v31(self) -> bool:
        return self.formula_id == "v31"

    @property
    def market_count(self) -> int:
        return len(self.market_order)

    def supports_market(self, market_key: str) -> bool:
        return bool(market_key) and market_key in self.market_order

    @property
    def integrity_policy_version(self) -> str:
        return INTEGRITY_POLICY_VERSION

    @property
    def analytics_schema_version(self) -> str:
        if self.is_v31:
            return ANALYTICS_SCHEMA_VERSION_V31
        return "cecchino_lab_purchasability_v3_analytics_v2"


_V3_CONFIG = ReplayFormulaConfig(
    formula_id="v3",
    formula_version=PURCHASABILITY_V3_FORMULA_VERSION,
    candidate_version=PURCHASABILITY_V3_CANDIDATE_VERSION,
    audit_version=PURCHASABILITY_V3_AUDIT_VERSION,
    market_order=V3_MARKET_ORDER,
    requires_historical_reliability=False,
    preflight_schema_version=PREFLIGHT_SCHEMA_VERSION_V3,
    replay_schema_version=REPLAY_SCHEMA_VERSION_V3,
    replay_engine_version=REPLAY_ENGINE_VERSION_V3,
    calculate_batch=calculate_purchasability_v3_batch,
)

_V31_CONFIG = ReplayFormulaConfig(
    formula_id="v31",
    formula_version=PURCHASABILITY_V31_FORMULA_VERSION,
    candidate_version=PURCHASABILITY_V31_CANDIDATE_VERSION,
    audit_version=PURCHASABILITY_V31_AUDIT_VERSION,
    market_order=V31_MARKET_ORDER,
    requires_historical_reliability=True,
    preflight_schema_version=PREFLIGHT_SCHEMA_VERSION_V31,
    replay_schema_version=REPLAY_SCHEMA_VERSION_V31,
    replay_engine_version=REPLAY_ENGINE_VERSION_V31,
    calculate_batch=calculate_purchasability_v31_batch,
)

_BY_ID: dict[str, ReplayFormulaConfig] = {
    "v3": _V3_CONFIG,
    "v31": _V31_CONFIG,
    "v3.1": _V31_CONFIG,
    "3": _V3_CONFIG,
    "3.1": _V31_CONFIG,
}

_BY_FORMULA_VERSION: dict[str, ReplayFormulaConfig] = {
    PURCHASABILITY_V3_FORMULA_VERSION: _V3_CONFIG,
    PURCHASABILITY_V31_FORMULA_VERSION: _V31_CONFIG,
}


def get_replay_formula_config(formula_id: str) -> ReplayFormulaConfig:
    """Risolve config da id corto (`v3`/`v31`) o da `formula_version` piena."""
    key = str(formula_id or "").strip()
    if not key:
        raise ValueError("formula_id mancante")
    cfg = _BY_ID.get(key.lower())
    if cfg is not None:
        return cfg
    cfg = _BY_FORMULA_VERSION.get(key)
    if cfg is not None:
        return cfg
    # Prefissi utili per versioni future dello stesso ramo.
    low = key.lower()
    if "v31" in low or "v3.1" in low or "v3_1" in low:
        return _V31_CONFIG
    if low.endswith("_v3") or "purchasability_v3_" in low or low == "v3":
        return _V3_CONFIG
    raise ValueError(f"formula_id/formula_version non supportata: {formula_id!r}")


def list_replay_formula_ids() -> tuple[str, ...]:
    return ("v3", "v31")


def invoke_formula(
    config: ReplayFormulaConfig,
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
    v3_items_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Invoca il batch corretto per la formula configurata."""
    if config.requires_historical_reliability:
        return config.calculate_batch(
            kpi_panel=kpi_panel,
            fixture_meta=fixture_meta,
            historical_by_market=historical_by_market,
            v3_items_by_market=v3_items_by_market,
        )
    return config.calculate_batch(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
    )


__all__ = [
    "FormulaId",
    "FORMULA_ID_V3",
    "FORMULA_ID_V31",
    "PREFLIGHT_SCHEMA_VERSION_V3",
    "REPLAY_SCHEMA_VERSION_V3",
    "REPLAY_ENGINE_VERSION_V3",
    "PREFLIGHT_SCHEMA_VERSION_V31",
    "REPLAY_SCHEMA_VERSION_V31",
    "REPLAY_ENGINE_VERSION_V31",
    "ANALYTICS_SCHEMA_VERSION_V31",
    "EXPORT_SCHEMA_VERSION_V31",
    "INTEGRITY_POLICY_VERSION",
    "V3_MARKET_ORDER",
    "V31_MARKET_ORDER",
    "ReplayFormulaConfig",
    "get_replay_formula_config",
    "list_replay_formula_ids",
    "invoke_formula",
]
