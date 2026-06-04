"""Schemi Pydantic Cecchino."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WDLRecordBody(BaseModel):
    wins: int = Field(0, ge=0)
    draws: int = Field(0, ge=0)
    losses: int = Field(0, ge=0)


class PicchettoContextPairBody(BaseModel):
    home: WDLRecordBody
    away: WDLRecordBody


class CecchinoDebugCalculateBody(BaseModel):
    home_away: PicchettoContextPairBody
    totals: PicchettoContextPairBody
    last5_home_away: PicchettoContextPairBody
    last6_totals: PicchettoContextPairBody


class CecchinoRecalculateBody(BaseModel):
    fixture_id: int | None = None
    limit: int = Field(50, ge=1, le=200)
