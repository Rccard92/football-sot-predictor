"""Errori import Cecchino Lab (modulo dedicato per evitare cicli di import)."""

from __future__ import annotations


class CecchinoLabImportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
