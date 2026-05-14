"""Lettura e normalizzazione del catalogo API-Football rilevante per il modello (file JSON statico)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

MODEL_RELEVANT_CATALOG_FILENAME = "api_football_model_relevant_catalog.json"
RESPONSE_VERSION = "api_football_model_relevant_catalog_v1"
TECHNICAL_SECTION_TITLE = "Fonti tecniche per variabili derivate"


def model_relevant_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / MODEL_RELEVANT_CATALOG_FILENAME


def _is_hidden_classification(classification: str) -> bool:
    if classification == "DA_NASCONDERE":
        return True
    return classification.startswith("NASCONDERE_")


def _area_slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower(), flags=re.IGNORECASE)
    s = s.strip("_")
    return s or "area"


def load_model_relevant_raw() -> dict[str, Any] | None:
    path = model_relevant_catalog_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_model_relevant_response(raw: dict[str, Any]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = list(raw.get("fields") or [])
    kept: list[dict[str, Any]] = [f for f in fields if not _is_hidden_classification(str(f.get("classification") or ""))]

    model_rows: list[dict[str, Any]] = []
    technical_rows: list[dict[str, Any]] = []
    for f in kept:
        cls = str(f.get("classification") or "")
        row = dict(f)
        if cls == "SORGENTE_DERIVATA_TECNICA":
            row["selectable"] = False
            technical_rows.append(row)
        else:
            row["selectable"] = True
            model_rows.append(row)

    by_area: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in model_rows:
        title = str(f.get("area") or "Senza area")
        by_area[title].append(f)

    areas: list[dict[str, Any]] = []
    for title in sorted(by_area.keys()):
        params = sorted(by_area[title], key=lambda x: str(x.get("key") or ""))
        areas.append(
            {
                "id": _area_slug(title),
                "title": title,
                "parameters": params,
            }
        )

    technical_sorted = sorted(technical_rows, key=lambda x: str(x.get("key") or ""))

    src = {k: raw[k] for k in ("source_file", "generated_at", "note") if k in raw}

    used_v04 = sum(1 for f in model_rows if f.get("model_v04_status") == "used_v04")

    return {
        "version": RESPONSE_VERSION,
        "message": None,
        "source": src,
        "summary": {
            "model_field_count": len(model_rows),
            "technical_derivative_count": len(technical_rows),
            "area_count": len(areas),
            "fields_used_by_v04_in_model_catalog": used_v04,
            "raw_fields_original": raw.get("summary", {}).get("raw_fields_original"),
            "hide_from_model_catalog": raw.get("summary", {}).get("hide_from_model_catalog"),
        },
        "areas": areas,
        "technical_derivative_sources": {
            "title": TECHNICAL_SECTION_TITLE,
            "fields": technical_sorted,
        },
    }


def empty_model_relevant_payload(message: str) -> dict[str, Any]:
    return {
        "version": RESPONSE_VERSION,
        "message": message,
        "source": {},
        "summary": {
            "model_field_count": 0,
            "technical_derivative_count": 0,
            "area_count": 0,
            "fields_used_by_v04_in_model_catalog": 0,
            "raw_fields_original": None,
            "hide_from_model_catalog": None,
        },
        "areas": [],
        "technical_derivative_sources": {
            "title": TECHNICAL_SECTION_TITLE,
            "fields": [],
        },
    }
