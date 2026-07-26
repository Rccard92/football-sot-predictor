"""Decodifica CSV Football-Data con fallback encoding tracciato."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedCsv:
    text: str
    encoding: str
    used_fallback: bool


def decode_csv_bytes(raw: bytes) -> DecodedCsv:
    """Prova UTF-8, UTF-8-BOM, poi CP1252 (fallback tracciato)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return DecodedCsv(text=raw.decode("utf-8-sig"), encoding="utf-8-sig", used_fallback=False)

    try:
        return DecodedCsv(text=raw.decode("utf-8"), encoding="utf-8", used_fallback=False)
    except UnicodeDecodeError:
        pass

    text = raw.decode("cp1252")
    return DecodedCsv(text=text, encoding="cp1252", used_fallback=True)
