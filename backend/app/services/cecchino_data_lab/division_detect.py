"""Auto-rilevamento del codice Div da un CSV Football-Data."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from app.services.cecchino_data_lab.competition_catalog import LabCompetition, get_competition_by_division
from app.services.cecchino_data_lab.csv_encoding import decode_csv_bytes
from app.services.cecchino_data_lab.csv_parser import file_sha256


MAPPING_MAPPED = "mapped"
MAPPING_UNKNOWN_DIVISION = "unknown_division"
MAPPING_MISSING_DIVISION = "missing_division"
MAPPING_MIXED_DIVISIONS = "mixed_divisions"
MAPPING_INVALID_CSV = "invalid_csv"


@dataclass
class DivisionDetectResult:
    mapping_status: str
    detected_divisions: list[str]
    division_code: str | None = None
    competition: LabCompetition | None = None
    file_sha256: str = ""
    file_size_bytes: int = 0
    message: str | None = None
    details: dict[str, Any] | None = None


def detect_division(raw: bytes) -> DivisionDetectResult:
    """Legge la colonna Div e associa il campionato dal catalogo.

    Non usa il nome file. Non consente override manuale.
    """
    sha = file_sha256(raw)
    size = len(raw)

    try:
        decoded = decode_csv_bytes(raw)
    except Exception as exc:
        return DivisionDetectResult(
            mapping_status=MAPPING_INVALID_CSV,
            detected_divisions=[],
            file_sha256=sha,
            file_size_bytes=size,
            message="Impossibile decodificare il CSV.",
            details={"error": str(exc)},
        )

    if not decoded.text.strip():
        return DivisionDetectResult(
            mapping_status=MAPPING_INVALID_CSV,
            detected_divisions=[],
            file_sha256=sha,
            file_size_bytes=size,
            message="Il file CSV è vuoto.",
        )

    reader = csv.DictReader(io.StringIO(decoded.text))
    if reader.fieldnames is None:
        return DivisionDetectResult(
            mapping_status=MAPPING_INVALID_CSV,
            detected_divisions=[],
            file_sha256=sha,
            file_size_bytes=size,
            message="Intestazione CSV assente o non valida.",
        )

    fieldnames = [h.lstrip("\ufeff") if isinstance(h, str) else h for h in reader.fieldnames]
    has_div = any(h == "Div" for h in fieldnames if h is not None)
    if not has_div:
        return DivisionDetectResult(
            mapping_status=MAPPING_MISSING_DIVISION,
            detected_divisions=[],
            file_sha256=sha,
            file_size_bytes=size,
            message="Colonna Div assente nell'intestazione.",
        )

    divisions: set[str] = set()
    for row in reader:
        if all((v is None or str(v).strip() == "") for k, v in row.items() if k is not None):
            continue
        raw_div = row.get("Div")
        if raw_div is None:
            continue
        div = str(raw_div).strip()
        if div:
            divisions.add(div)

    detected = sorted(divisions)
    if len(detected) == 0:
        return DivisionDetectResult(
            mapping_status=MAPPING_MISSING_DIVISION,
            detected_divisions=[],
            file_sha256=sha,
            file_size_bytes=size,
            message="Nessun valore Div non vuoto nelle righe dati.",
        )

    if len(detected) > 1:
        return DivisionDetectResult(
            mapping_status=MAPPING_MIXED_DIVISIONS,
            detected_divisions=detected,
            file_sha256=sha,
            file_size_bytes=size,
            message=f"Il file contiene più divisioni: {', '.join(detected)}.",
            details={"detected_divisions": detected},
        )

    division_code = detected[0]
    competition = get_competition_by_division(division_code)
    if competition is None:
        return DivisionDetectResult(
            mapping_status=MAPPING_UNKNOWN_DIVISION,
            detected_divisions=detected,
            division_code=division_code,
            file_sha256=sha,
            file_size_bytes=size,
            message=f"Divisione sconosciuta: '{division_code}'.",
        )

    return DivisionDetectResult(
        mapping_status=MAPPING_MAPPED,
        detected_divisions=detected,
        division_code=division_code,
        competition=competition,
        file_sha256=sha,
        file_size_bytes=size,
    )
