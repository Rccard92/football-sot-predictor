from __future__ import annotations

from pydantic import BaseModel, Field


class CecchinoPatternDiscoveryStartBody(BaseModel):
    market_key: str = Field(description="Es. ONE_X, DRAW, HOME, OVER_2_5, ...")
    run_ids: list[int] = Field(
        description="Id dei run/stagioni Cecchino Lab da usare (almeno 2, per costruire un fold walk-forward)"
    )
