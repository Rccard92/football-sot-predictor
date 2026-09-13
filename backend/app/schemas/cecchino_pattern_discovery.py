from __future__ import annotations

from pydantic import BaseModel, Field


class CecchinoPatternDiscoveryStartBody(BaseModel):
    market_key: str = Field(description="Es. ONE_X, DRAW, HOME, OVER_2_5, ...")
    run_ids: list[int] = Field(
        description="Id dei run/stagioni Cecchino Lab da usare (almeno 2, per costruire un fold walk-forward)"
    )
    competition: str | None = Field(
        default=None,
        description=(
            "Se indicato, ristringe la scoperta a un solo campionato (es. 'Serie A') — "
            "pattern 'league-native'. Se omesso, i campionati vengono impastati insieme."
        ),
    )


class CecchinoPatternGridStartBody(BaseModel):
    market_key: str = Field(description="Es. ONE_X, DRAW, HOME, OVER_2_5, ...")
    run_ids: list[int] = Field(
        description="Id dei run/stagioni Cecchino Lab, in ordine cronologico (almeno 2)"
    )
    competition: str | None = Field(
        default=None,
        description="Se indicato, ricerca ristretta a un solo campionato. Se omesso, globale.",
    )


class CecchinoRunV2PatternInsightStartBody(BaseModel):
    run_v2_run_id: int = Field(description="Id del run Run V2 completato da analizzare (es. 4)")
    odds_mode: str = Field(
        default="closing",
        description="'closing' = quota di chiusura come metro unico (default); 'v2' = quote come salvate da Run V2",
    )
