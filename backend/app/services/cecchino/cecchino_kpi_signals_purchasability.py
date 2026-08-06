"""Estrazione snapshot Acquistabilità V3/V3.1 per Segnali KPI (solo lettura pre-match)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.cecchino.cecchino_purchasability_v3_opposition import SUPPORTED_V3_MARKETS

PURCHASABILITY_STATUS_SCORE = "score"
PURCHASABILITY_STATUS_SCORE_PROVISIONAL = "score_provisional"
PURCHASABILITY_STATUS_GATE_FAILED = "gate_failed"
PURCHASABILITY_STATUS_NON_CALCULABLE = "non_calculable"
PURCHASABILITY_STATUS_UNSUPPORTED = "unsupported_market"
PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE = "snapshot_unavailable"

PURCHASABILITY_FILTER_STATUSES: tuple[str, ...] = (
    PURCHASABILITY_STATUS_SCORE,
    PURCHASABILITY_STATUS_SCORE_PROVISIONAL,
    PURCHASABILITY_STATUS_GATE_FAILED,
    PURCHASABILITY_STATUS_NON_CALCULABLE,
    PURCHASABILITY_STATUS_UNSUPPORTED,
    PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE,
)

PURCHASABILITY_CLASS_LABEL_TO_KEY: dict[str, str] = {
    "Molto Bassa": "very_low",
    "Bassa": "low",
    "Media": "medium",
    "Alta": "high",
    "Molto Alta": "very_high",
}
PURCHASABILITY_CLASS_KEY_TO_LABEL: dict[str, str] = {
    v: k for k, v in PURCHASABILITY_CLASS_LABEL_TO_KEY.items()
}
PURCHASABILITY_CLASS_KEYS: tuple[str, ...] = (
    "very_low",
    "low",
    "medium",
    "high",
    "very_high",
)

PURCHASABILITY_QUALITY_VALUES: tuple[str, ...] = (
    "full",
    "provisional",
    "partial",
    "not_applicable",
)

PURCHASABILITY_VERSIONS: tuple[str, ...] = ("v3", "v31")

_GATE_FAILED_STATUSES = frozenset(
    {
        "failed_non_positive_edge",
        "failed_non_positive_probability_advantage",
        "failed_multiple_non_positive_components",
        "gate_failed",
    }
)


def class_key_from_label(label: str | None) -> str | None:
    if not label:
        return None
    return PURCHASABILITY_CLASS_LABEL_TO_KEY.get(str(label).strip())


def class_label_from_key(key: str | None) -> str | None:
    if not key:
        return None
    return PURCHASABILITY_CLASS_KEY_TO_LABEL.get(str(key).strip())


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _score_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score


def _reason_codes(*sources: Any) -> list[str]:
    codes: list[str] = []
    for source in sources:
        if not source:
            continue
        if isinstance(source, str):
            codes.append(source)
            continue
        if isinstance(source, (list, tuple)):
            for item in source:
                if item is None:
                    continue
                text = str(item).strip()
                if text and text not in codes:
                    codes.append(text)
    return codes[:20]


def _find_item_by_market_key(snapshot: dict[str, Any] | None, selection_key: str) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    items = snapshot.get("items")
    if not isinstance(items, list):
        return None
    target = str(selection_key).strip().upper()
    for item in items:
        if not isinstance(item, dict):
            continue
        market_key = str(item.get("market_key") or "").strip().upper()
        if market_key and market_key == target:
            return item
    return None


def _normalize_v3_status(item: dict[str, Any], *, selection_key: str) -> str:
    gate_status = str(item.get("gate_status") or "").strip()
    if gate_status == "unsupported_market" or selection_key not in SUPPORTED_V3_MARKETS:
        # Se l'item esiste ma il mercato non è supportato V3
        if selection_key not in SUPPORTED_V3_MARKETS:
            return PURCHASABILITY_STATUS_UNSUPPORTED
        return PURCHASABILITY_STATUS_UNSUPPORTED
    if gate_status in _GATE_FAILED_STATUSES:
        return PURCHASABILITY_STATUS_GATE_FAILED
    native = str(item.get("status") or "").strip()
    if native in ("available", "score"):
        return PURCHASABILITY_STATUS_SCORE
    if native == "score_provisional":
        return PURCHASABILITY_STATUS_SCORE_PROVISIONAL
    if native == "not_applicable":
        if gate_status in _GATE_FAILED_STATUSES or gate_status.startswith("failed_"):
            return PURCHASABILITY_STATUS_GATE_FAILED
        if gate_status == "unsupported_market":
            return PURCHASABILITY_STATUS_UNSUPPORTED
        return PURCHASABILITY_STATUS_NON_CALCULABLE
    if native in ("unavailable", "non_calculable", "partial"):
        return PURCHASABILITY_STATUS_NON_CALCULABLE
    if native in PURCHASABILITY_FILTER_STATUSES:
        return native
    return PURCHASABILITY_STATUS_NON_CALCULABLE


def _normalize_v31_status(item: dict[str, Any]) -> str:
    native = str(item.get("status") or "").strip()
    if native in PURCHASABILITY_FILTER_STATUSES:
        return native
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    gate_status = str(item.get("gate_status") or gate.get("gate_status") or "").strip()
    if gate_status in _GATE_FAILED_STATUSES:
        return PURCHASABILITY_STATUS_GATE_FAILED
    if native in ("available",):
        return PURCHASABILITY_STATUS_SCORE
    if native in ("unavailable", "partial"):
        return PURCHASABILITY_STATUS_NON_CALCULABLE
    return PURCHASABILITY_STATUS_NON_CALCULABLE


def _empty_v3(*, status: str) -> dict[str, Any]:
    return {
        "family_key": "v3",
        "available": False,
        "version_key": "v3",
        "candidate_version": None,
        "formula_version": None,
        "status": status,
        "score": None,
        "class_key": None,
        "class_label": None,
        "calculation_quality": None,
        "historical_evidence_quality": None,
        "source_snapshot_at": None,
        "generated_at": None,
        "execution_quote_real": None,
        "snapshot_available": False,
        "reason_codes": (
            ["unsupported_market"]
            if status == PURCHASABILITY_STATUS_UNSUPPORTED
            else (
                ["snapshot_unavailable"]
                if status == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
                else []
            )
        ),
    }


def _empty_v31(*, status: str = PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE) -> dict[str, Any]:
    return {
        "family_key": "v31",
        "available": False,
        "version_key": "v31",
        "candidate_version": None,
        "formula_version": None,
        "formula_config_version": None,
        "audit_version": None,
        "registry_status": None,
        "status": status,
        "score": None,
        "class_key": None,
        "class_label": None,
        "calculation_quality": None,
        "historical_evidence_quality": None,
        "source_snapshot_at": None,
        "generated_at": None,
        "execution_quote_real": None,
        "snapshot_available": False,
        "reason_codes": (
            ["snapshot_unavailable"] if status == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE else []
        ),
    }


def extract_v3_snapshot(
    *,
    cecchino_output_json: dict[str, Any] | None,
    selection_key: str,
) -> dict[str, Any]:
    """Estrae snapshot V3 normalizzato. Nessun ricalcolo, nessun risultato partita."""
    key = str(selection_key).strip().upper()
    output = cecchino_output_json if isinstance(cecchino_output_json, dict) else None
    snapshot = output.get("purchasability_preview_v3") if output else None

    if key not in SUPPORTED_V3_MARKETS:
        if isinstance(snapshot, dict):
            item = _find_item_by_market_key(snapshot, key)
            base = _empty_v3(status=PURCHASABILITY_STATUS_UNSUPPORTED)
            if item is not None:
                base.update(
                    {
                        "formula_version": item.get("formula_version")
                        or snapshot.get("formula_version"),
                        "candidate_version": item.get("candidate_version")
                        or snapshot.get("candidate_version"),
                        "source_snapshot_at": _parse_dt(snapshot.get("source_snapshot_at")),
                        "snapshot_available": True,
                        "reason_codes": _reason_codes(
                            item.get("reason_codes"),
                            item.get("gate_reason_codes"),
                            ["unsupported_market"],
                        ),
                    }
                )
            return base
        return _empty_v3(status=PURCHASABILITY_STATUS_UNSUPPORTED)

    if not isinstance(snapshot, dict):
        return _empty_v3(status=PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE)

    item = _find_item_by_market_key(snapshot, key)
    if item is None:
        return _empty_v3(status=PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE)

    status = _normalize_v3_status(item, selection_key=key)
    class_label = item.get("class") or item.get("class_label")
    class_label = str(class_label).strip() if class_label else None
    score = _score_or_none(item.get("score"))
    available = status in (PURCHASABILITY_STATUS_SCORE, PURCHASABILITY_STATUS_SCORE_PROVISIONAL) and score is not None
    return {
        "family_key": "v3",
        "available": available,
        "version_key": "v3",
        "candidate_version": item.get("candidate_version") or snapshot.get("candidate_version"),
        "formula_version": item.get("formula_version") or snapshot.get("formula_version"),
        "status": status,
        "score": score,
        "class_key": class_key_from_label(class_label),
        "class_label": class_label,
        "calculation_quality": item.get("calculation_quality"),
        "historical_evidence_quality": None,
        "source_snapshot_at": _parse_dt(snapshot.get("source_snapshot_at") or item.get("snapshot_at")),
        "generated_at": _parse_dt(snapshot.get("generated_at")),
        "execution_quote_real": None,
        "snapshot_available": True,
        "reason_codes": _reason_codes(item.get("reason_codes"), item.get("gate_reason_codes")),
    }


def extract_v31_snapshot(
    *,
    cecchino_output_json: dict[str, Any] | None,
    selection_key: str,
) -> dict[str, Any]:
    """Estrae snapshot V3.1 normalizzato. Nessun ricalcolo, nessun risultato partita."""
    key = str(selection_key).strip().upper()
    output = cecchino_output_json if isinstance(cecchino_output_json, dict) else None
    snapshot = output.get("purchasability_preview_v31") if output else None
    if not isinstance(snapshot, dict):
        return _empty_v31()

    item = _find_item_by_market_key(snapshot, key)
    if item is None:
        return _empty_v31()

    status = _normalize_v31_status(item)
    class_label = item.get("class") or item.get("class_v31") or item.get("class_label")
    class_label = str(class_label).strip() if class_label else None
    score = _score_or_none(item.get("score") if item.get("score") is not None else item.get("score_v31"))
    historical = item.get("historical") if isinstance(item.get("historical"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    evidence = (
        item.get("historical_evidence_quality")
        or historical.get("historical_evidence_quality")
    )
    execution_quote_real = item.get("execution_quote_real")
    if execution_quote_real is None:
        execution_quote_real = inp.get("execution_quote_real")
    available = status in (PURCHASABILITY_STATUS_SCORE, PURCHASABILITY_STATUS_SCORE_PROVISIONAL) and score is not None
    return {
        "family_key": "v31",
        "available": available,
        "version_key": "v31",
        "candidate_version": item.get("candidate_version") or snapshot.get("candidate_version"),
        "formula_version": item.get("formula_version") or snapshot.get("formula_version"),
        "formula_config_version": item.get("formula_config_version")
        or snapshot.get("formula_config_version"),
        "audit_version": item.get("audit_version") or snapshot.get("audit_version"),
        "registry_status": item.get("registry_status") or snapshot.get("registry_status"),
        "status": status,
        "score": score,
        "class_key": class_key_from_label(class_label),
        "class_label": class_label,
        "calculation_quality": item.get("calculation_quality"),
        "historical_evidence_quality": evidence,
        "source_snapshot_at": _parse_dt(snapshot.get("source_snapshot_at") or item.get("snapshot_at")),
        "generated_at": _parse_dt(snapshot.get("generated_at") or item.get("generated_at")),
        "execution_quote_real": bool(execution_quote_real) if execution_quote_real is not None else None,
        "snapshot_available": True,
        "reason_codes": _reason_codes(
            item.get("reason_codes"),
            item.get("gate_reason_codes"),
            item.get("historical_reason_codes"),
        ),
    }


def extract_purchasability_snapshots_for_selection(
    *,
    cecchino_output_json: dict[str, Any] | None,
    selection_key: str,
    kpi_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapter puro: fixture output + selection key → V3/V3.1 normalizzati.

    ``kpi_row`` è accettato per firma ma non usato per associare l'item (solo market_key).
    Nessun accesso DB, nessuna API, nessun ricalcolo, nessun risultato partita.
    """
    _ = kpi_row  # esplicito: non usare label/riga per match
    return {
        "v3": extract_v3_snapshot(
            cecchino_output_json=cecchino_output_json,
            selection_key=selection_key,
        ),
        "v31": extract_v31_snapshot(
            cecchino_output_json=cecchino_output_json,
            selection_key=selection_key,
        ),
    }


def purchasability_fingerprint(v3: dict[str, Any], v31: dict[str, Any]) -> str:
    payload = {
        "v3": {
            "status": v3.get("status"),
            "score": v3.get("score"),
            "class_key": v3.get("class_key"),
            "formula_version": v3.get("formula_version"),
            "calculation_quality": v3.get("calculation_quality"),
            "source_snapshot_at": (
                v3.get("source_snapshot_at").isoformat()
                if isinstance(v3.get("source_snapshot_at"), datetime)
                else v3.get("source_snapshot_at")
            ),
            "reason_codes": v3.get("reason_codes") or [],
        },
        "v31": {
            "status": v31.get("status"),
            "score": v31.get("score"),
            "class_key": v31.get("class_key"),
            "candidate_version": v31.get("candidate_version"),
            "formula_version": v31.get("formula_version"),
            "calculation_quality": v31.get("calculation_quality"),
            "historical_evidence_quality": v31.get("historical_evidence_quality"),
            "source_snapshot_at": (
                v31.get("source_snapshot_at").isoformat()
                if isinstance(v31.get("source_snapshot_at"), datetime)
                else v31.get("source_snapshot_at")
            ),
            "execution_quote_real": v31.get("execution_quote_real"),
            "reason_codes": v31.get("reason_codes") or [],
        },
    }
    return json.dumps(payload, sort_keys=True, default=str)


def apply_purchasability_to_activation(activation: Any, snapshots: dict[str, Any]) -> None:
    """Scrive i campi Acquistabilità sull'activation (in-place)."""
    v3 = snapshots.get("v3") or _empty_v3(status=PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE)
    v31 = snapshots.get("v31") or _empty_v31()

    activation.purchasability_v3_formula_version = v3.get("formula_version")
    activation.purchasability_v3_status = v3.get("status")
    activation.purchasability_v3_score = (
        None if v3.get("score") is None else float(v3["score"])
    )
    activation.purchasability_v3_class_key = v3.get("class_key")
    activation.purchasability_v3_class_label = v3.get("class_label")
    activation.purchasability_v3_calculation_quality = v3.get("calculation_quality")
    activation.purchasability_v3_source_snapshot_at = v3.get("source_snapshot_at")
    activation.purchasability_v3_reason_codes_json = list(v3.get("reason_codes") or [])

    activation.purchasability_v31_candidate_version = v31.get("candidate_version")
    activation.purchasability_v31_formula_version = v31.get("formula_version")
    activation.purchasability_v31_formula_config_version = v31.get("formula_config_version")
    activation.purchasability_v31_audit_version = v31.get("audit_version")
    activation.purchasability_v31_status = v31.get("status")
    activation.purchasability_v31_score = (
        None if v31.get("score") is None else float(v31["score"])
    )
    activation.purchasability_v31_class_key = v31.get("class_key")
    activation.purchasability_v31_class_label = v31.get("class_label")
    activation.purchasability_v31_calculation_quality = v31.get("calculation_quality")
    activation.purchasability_v31_historical_evidence_quality = v31.get(
        "historical_evidence_quality"
    )
    activation.purchasability_v31_source_snapshot_at = v31.get("source_snapshot_at")
    activation.purchasability_v31_generated_at = v31.get("generated_at")
    activation.purchasability_v31_execution_quote_real = v31.get("execution_quote_real")
    activation.purchasability_v31_reason_codes_json = list(v31.get("reason_codes") or [])


def activation_purchasability_fingerprint(activation: Any) -> str:
    v3 = {
        "status": getattr(activation, "purchasability_v3_status", None),
        "score": getattr(activation, "purchasability_v3_score", None),
        "class_key": getattr(activation, "purchasability_v3_class_key", None),
        "formula_version": getattr(activation, "purchasability_v3_formula_version", None),
        "calculation_quality": getattr(activation, "purchasability_v3_calculation_quality", None),
        "source_snapshot_at": getattr(activation, "purchasability_v3_source_snapshot_at", None),
        "reason_codes": getattr(activation, "purchasability_v3_reason_codes_json", None) or [],
    }
    v31 = {
        "status": getattr(activation, "purchasability_v31_status", None),
        "score": getattr(activation, "purchasability_v31_score", None),
        "class_key": getattr(activation, "purchasability_v31_class_key", None),
        "candidate_version": getattr(activation, "purchasability_v31_candidate_version", None),
        "formula_version": getattr(activation, "purchasability_v31_formula_version", None),
        "calculation_quality": getattr(activation, "purchasability_v31_calculation_quality", None),
        "historical_evidence_quality": getattr(
            activation, "purchasability_v31_historical_evidence_quality", None
        ),
        "source_snapshot_at": getattr(activation, "purchasability_v31_source_snapshot_at", None),
        "execution_quote_real": getattr(activation, "purchasability_v31_execution_quote_real", None),
        "reason_codes": getattr(activation, "purchasability_v31_reason_codes_json", None) or [],
    }
    return purchasability_fingerprint(v3, v31)


def serialize_purchasability_from_activation(activation: Any, *, version: str) -> dict[str, Any]:
    """Serializza oggetto sintetico API da campi persistiti (retrocompatibile)."""
    if version == "v3":
        status = getattr(activation, "purchasability_v3_status", None)
        score = getattr(activation, "purchasability_v3_score", None)
        if status is None and score is None and getattr(activation, "purchasability_v3_formula_version", None) is None:
            status = PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
        snapshot_available = status not in (None, PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE) or (
            getattr(activation, "purchasability_v3_formula_version", None) is not None
        )
        if status is None:
            status = PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
        return {
            "available": status in (PURCHASABILITY_STATUS_SCORE, PURCHASABILITY_STATUS_SCORE_PROVISIONAL)
            and score is not None,
            "version_key": "v3",
            "candidate_version": None,
            "formula_version": getattr(activation, "purchasability_v3_formula_version", None),
            "status": status,
            "score": float(score) if score is not None else None,
            "class_key": getattr(activation, "purchasability_v3_class_key", None),
            "class_label": getattr(activation, "purchasability_v3_class_label", None),
            "calculation_quality": getattr(activation, "purchasability_v3_calculation_quality", None),
            "historical_evidence_quality": None,
            "source_snapshot_at": (
                activation.purchasability_v3_source_snapshot_at.isoformat()
                if getattr(activation, "purchasability_v3_source_snapshot_at", None)
                else None
            ),
            "generated_at": None,
            "execution_quote_real": None,
            "snapshot_available": bool(snapshot_available),
            "reason_codes": list(getattr(activation, "purchasability_v3_reason_codes_json", None) or []),
        }

    status = getattr(activation, "purchasability_v31_status", None)
    score = getattr(activation, "purchasability_v31_score", None)
    if (
        status is None
        and score is None
        and getattr(activation, "purchasability_v31_formula_version", None) is None
        and getattr(activation, "purchasability_v31_candidate_version", None) is None
    ):
        status = PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
    if status is None:
        status = PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
    snapshot_available = status != PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE or (
        getattr(activation, "purchasability_v31_formula_version", None) is not None
    )
    return {
        "available": status in (PURCHASABILITY_STATUS_SCORE, PURCHASABILITY_STATUS_SCORE_PROVISIONAL)
        and score is not None,
        "version_key": "v31",
        "candidate_version": getattr(activation, "purchasability_v31_candidate_version", None),
        "formula_version": getattr(activation, "purchasability_v31_formula_version", None),
        "formula_config_version": getattr(activation, "purchasability_v31_formula_config_version", None),
        "audit_version": getattr(activation, "purchasability_v31_audit_version", None),
        "registry_status": None,
        "status": status,
        "score": float(score) if score is not None else None,
        "class_key": getattr(activation, "purchasability_v31_class_key", None),
        "class_label": getattr(activation, "purchasability_v31_class_label", None),
        "calculation_quality": getattr(activation, "purchasability_v31_calculation_quality", None),
        "historical_evidence_quality": getattr(
            activation, "purchasability_v31_historical_evidence_quality", None
        ),
        "source_snapshot_at": (
            activation.purchasability_v31_source_snapshot_at.isoformat()
            if getattr(activation, "purchasability_v31_source_snapshot_at", None)
            else None
        ),
        "generated_at": (
            activation.purchasability_v31_generated_at.isoformat()
            if getattr(activation, "purchasability_v31_generated_at", None)
            else None
        ),
        "execution_quote_real": getattr(activation, "purchasability_v31_execution_quote_real", None),
        "snapshot_available": bool(snapshot_available),
        "reason_codes": list(getattr(activation, "purchasability_v31_reason_codes_json", None) or []),
    }


def purchasability_filter_options() -> dict[str, Any]:
    return {
        "versions": list(PURCHASABILITY_VERSIONS),
        "statuses": list(PURCHASABILITY_FILTER_STATUSES),
        "classes": [
            {"key": key, "label": PURCHASABILITY_CLASS_KEY_TO_LABEL[key]}
            for key in PURCHASABILITY_CLASS_KEYS
        ],
        "qualities": list(PURCHASABILITY_QUALITY_VALUES),
        "score_range": {"min": 0, "max": 100},
    }
