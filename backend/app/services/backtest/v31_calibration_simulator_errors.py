"""Eccezioni strutturate simulatore predittivo v3.1."""

from __future__ import annotations


class V31SimulatorInternalError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        strategy: str | None = None,
        fixture_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.strategy = strategy
        self.fixture_id = fixture_id

    def to_payload(self) -> dict:
        return {
            "status": "error",
            "error_code": "V31_SIMULATOR_INTERNAL_ERROR",
            "message": self.message,
            "stage": self.stage,
            "strategy": self.strategy,
            "fixture_id": self.fixture_id,
        }
