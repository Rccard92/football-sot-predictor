"""Errori HTTP strutturati per Backtest Engine API."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException


def raise_backtest_http(status: int, code: str, message: str, **extra: object) -> NoReturn:
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message, **extra},
    )
