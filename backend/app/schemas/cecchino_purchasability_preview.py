"""Contratto tecnico Acquistabilità V1 Preview — FASE 1/5.

Versione: cecchino_purchasability_v1_preview_contract

Solo schema / factory. Nessuna formula produttiva, nessuno score, nessun
endpoint KPI, nessuna persistenza come previsione reale.

Distinzioni obbligatorie:
- Affidabilità storica ≠ Acquistabilità (moduli separati).
- Acquistabilità non copia il Rating.
- Acquistabilità non usa Affidabilità storica come score finale.
- Non somma automaticamente Rating, Score, Edge e Vantaggio.
- Distingue «valore individuato» da «qualità del valore».
- Una forte differenza Cecchino–Book non è automaticamente penalizzante.
- La decisione di gioco resta ai Segnali Cecchino.

Fase 2/5 riusa la mappa canonica in
``app.services.cecchino.cecchino_market_opposition``:
comparator_selections, complement_selection, opposition_status,
canonical_market_family, period, line.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PURCHASABILITY_PREVIEW_CONTRACT_VERSION = "cecchino_purchasability_v1_preview_contract"

PurchasabilityStatus = Literal[
    "not_calculated",
    "available",
    "partial",
    "unavailable",
]

PurchasabilityClass = Literal[
    "Molto Bassa",
    "Bassa",
    "Media",
    "Alta",
    "Molto Alta",
]

ContextHookStatus = Literal["not_connected", "connected", "unavailable"]


class PurchasabilityPhase1ValueInputs(BaseModel):
    prob_cecchino: float | None = None
    vantaggio_prob: float | None = None
    edge_pct: float | None = None
    score_acquisto: float | None = None
    rating: float | None = None


class PurchasabilityPhase1Value(BaseModel):
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    inputs: PurchasabilityPhase1ValueInputs = Field(
        default_factory=PurchasabilityPhase1ValueInputs
    )


class PurchasabilityBookFavourite(BaseModel):
    selection: str | None = None
    implied_prob: float | None = None


class PurchasabilityModelFavourite(BaseModel):
    selection: str | None = None
    model_prob: float | None = None


class PurchasabilityPhase2Quality(BaseModel):
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    opposition_status: str | None = None
    comparator_selections: list[str] = Field(default_factory=list)
    book_favourite: PurchasabilityBookFavourite | None = None
    model_favourite: PurchasabilityModelFavourite | None = None
    favourite_alignment: str | None = None
    favourite_intensity_book: float | None = None
    favourite_intensity_model: float | None = None


class PurchasabilityContextHook(BaseModel):
    status: ContextHookStatus = "not_connected"
    payload: dict[str, Any] | None = None


class PurchasabilityContextHooks(BaseModel):
    balance_v5: PurchasabilityContextHook = Field(
        default_factory=PurchasabilityContextHook
    )
    goal_intensity_v5: PurchasabilityContextHook = Field(
        default_factory=PurchasabilityContextHook
    )


class PurchasabilityDataQuality(BaseModel):
    pre_match_only: bool = True
    no_post_match_features: bool = True


class CecchinoPurchasabilityPreviewContract(BaseModel):
    """Contratto preview — score sempre null finché status=not_calculated."""

    version: str = PURCHASABILITY_PREVIEW_CONTRACT_VERSION
    status: PurchasabilityStatus = "not_calculated"
    score: float | None = None
    class_: PurchasabilityClass | None = Field(default=None, alias="class")
    reading: str | None = None
    market_key: str | None = None
    selection: str | None = None
    phase_1_value: PurchasabilityPhase1Value = Field(
        default_factory=PurchasabilityPhase1Value
    )
    phase_2_quality: PurchasabilityPhase2Quality = Field(
        default_factory=PurchasabilityPhase2Quality
    )
    context_hooks: PurchasabilityContextHooks = Field(
        default_factory=PurchasabilityContextHooks
    )
    reason_codes: list[str] = Field(default_factory=list)
    data_quality: PurchasabilityDataQuality = Field(
        default_factory=PurchasabilityDataQuality
    )

    model_config = {"populate_by_name": True}


def build_purchasability_preview_not_calculated(
    *,
    market_key: str | None = None,
    selection: str | None = None,
) -> dict[str, Any]:
    """Factory Fase 1: contratto valido senza formula né placeholder numerici."""
    contract = CecchinoPurchasabilityPreviewContract(
        version=PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        status="not_calculated",
        score=None,
        class_=None,
        reading=None,
        market_key=market_key,
        selection=selection or market_key,
        phase_1_value=PurchasabilityPhase1Value(
            status="not_calculated",
            score=None,
            inputs=PurchasabilityPhase1ValueInputs(),
        ),
        phase_2_quality=PurchasabilityPhase2Quality(
            status="not_calculated",
            score=None,
            opposition_status=None,
            comparator_selections=[],
            book_favourite=None,
            model_favourite=None,
            favourite_alignment=None,
            favourite_intensity_book=None,
            favourite_intensity_model=None,
        ),
        context_hooks=PurchasabilityContextHooks(
            balance_v5=PurchasabilityContextHook(status="not_connected", payload=None),
            goal_intensity_v5=PurchasabilityContextHook(
                status="not_connected", payload=None
            ),
        ),
        reason_codes=["formula_not_implemented_phase_1"],
        data_quality=PurchasabilityDataQuality(
            pre_match_only=True,
            no_post_match_features=True,
        ),
    )
    return contract.model_dump(by_alias=True)
