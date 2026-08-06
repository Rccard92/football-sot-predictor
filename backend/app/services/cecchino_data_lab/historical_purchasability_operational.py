"""Configurazione operativa Acquistabilità (V3 default, V3.1 solo post GO_FINAL).

Stato runtime in JSON locale (nessuna migration). Rollback = modifica config.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.cecchino_purchasability_v3 import PURCHASABILITY_V3_FORMULA_VERSION
from app.schemas.cecchino_purchasability_v31 import PURCHASABILITY_V31_FORMULA_VERSION
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v31_go_no_go import (
    DECISION_GO_FINAL,
)

DEFAULT_OPERATIONAL = "v3"
FALLBACK = "v3"
FALLBACK_VERSION = FALLBACK
PROMOTE_CONFIRM_TOKEN = "PROMOTE_V31_GO_FINAL"
ROLLBACK_CONFIRM_TOKEN = "ROLLBACK_TO_V3"

_lock = threading.Lock()


def _state_path() -> Path:
    override = os.environ.get("PURCHASABILITY_OPERATIONAL_STATE_PATH")
    if override:
        return Path(override)
    # backend/app/services/cecchino_data_lab/ → backend/.runtime/
    here = Path(__file__).resolve()
    backend_root = here.parents[3]
    return backend_root / ".runtime" / "purchasability_operational_state.json"


def _settings_defaults() -> dict[str, Any]:
    """Default da Settings (env); il JSON runtime li sovrascrive."""
    try:
        from app.core.config import get_settings

        s = get_settings()
        return {
            "operational_purchasability_version": str(
                getattr(s, "operational_purchasability_version", None)
                or DEFAULT_OPERATIONAL
            ),
            "fallback_version": str(
                getattr(s, "purchasability_fallback_version", None) or FALLBACK
            ),
            "validation_replay_id": getattr(
                s, "purchasability_validation_replay_id", None
            ),
            "validation_source_run_id": getattr(
                s, "purchasability_validation_source_run_id", None
            ),
            "validation_decision_version": getattr(
                s, "purchasability_validation_decision_version", None
            ),
            "validation_decision": getattr(
                s, "purchasability_validation_decision", None
            ),
            "validated_at": getattr(s, "purchasability_validated_at", None),
            "validation_commit": getattr(s, "purchasability_validation_commit", None),
            "formula_version": getattr(
                s, "purchasability_validation_formula_version", None
            )
            or PURCHASABILITY_V3_FORMULA_VERSION,
            "promoted_formula_version": None,
            "audit": [],
        }
    except Exception:
        return {
            "operational_purchasability_version": DEFAULT_OPERATIONAL,
            "fallback_version": FALLBACK,
            "validation_replay_id": None,
            "validation_source_run_id": None,
            "validation_decision_version": None,
            "validation_decision": None,
            "validated_at": None,
            "validation_commit": None,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "promoted_formula_version": None,
            "audit": [],
        }


def _default_state() -> dict[str, Any]:
    return _settings_defaults()


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_state()
        base = _default_state()
        base.update(data)
        return base
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_operational_purchasability_config() -> dict[str, Any]:
    """Snapshot pubblico della versione operativa (Settings + JSON runtime)."""
    with _lock:
        st = _read_state()
    op = str(st.get("operational_purchasability_version") or DEFAULT_OPERATIONAL).lower()
    if op in {"v3.1", "3.1"}:
        op = "v31"
    if op not in {"v3", "v31"}:
        op = DEFAULT_OPERATIONAL
    promoted = op == "v31" and st.get("validation_decision") == DECISION_GO_FINAL
    return {
        "operational_version": op,
        "operational_purchasability_version": op,
        "fallback_version": str(st.get("fallback_version") or FALLBACK),
        "purchasability_fallback_version": str(st.get("fallback_version") or FALLBACK),
        "validation_replay_id": st.get("validation_replay_id"),
        "validation_source_run_id": st.get("validation_source_run_id"),
        "validation_decision_version": st.get("validation_decision_version"),
        "validation_decision": st.get("validation_decision"),
        "validated_at": st.get("validated_at"),
        "validation_commit": st.get("validation_commit"),
        "formula_version": st.get("formula_version"),
        "promoted_formula_version": st.get("promoted_formula_version"),
        "v31_is_operational": promoted,
        "is_v31_operationally_promoted": promoted,
        "strong_buy_message_allowed": promoted,
        "shadow_default": not promoted,
        "state_path": str(_state_path()),
        "default_operational": DEFAULT_OPERATIONAL,
        "fallback": FALLBACK,
    }


def is_v31_operationally_promoted() -> bool:
    return bool(get_operational_purchasability_config()["is_v31_operationally_promoted"])


def strong_buy_message_allowed() -> bool:
    return bool(get_operational_purchasability_config()["strong_buy_message_allowed"])


def promote_purchasability_v31(
    *,
    replay_id: int,
    decision: str,
    formula_version: str,
    confirm_token: str,
    validation_meta: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Promuove V3.1 soltanto con GO_FINAL + token esplicito."""
    meta = dict(validation_meta or {})
    if decision != DECISION_GO_FINAL:
        raise CecchinoLabImportError(
            "promotion_denied_decision",
            f"Promozione negata: decision={decision} (richiesto GO_FINAL)",
            status_code=409,
            details={"decision": decision},
        )
    if confirm_token != PROMOTE_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "promotion_denied_token",
            "Confirm token non valido",
            status_code=403,
            details={"expected_token_hint": "PROMOTE_V31_GO_FINAL"},
        )
    if formula_version != PURCHASABILITY_V31_FORMULA_VERSION:
        raise CecchinoLabImportError(
            "promotion_denied_formula",
            "formula_version non corrisponde alla V3.1 validata",
            status_code=409,
            details={
                "expected": PURCHASABILITY_V31_FORMULA_VERSION,
                "got": formula_version,
            },
        )

    with _lock:
        st = _read_state()
        # Idempotenza: già promosso con stesso replay
        if (
            st.get("operational_purchasability_version") == "v31"
            and int(st.get("validation_replay_id") or -1) == int(replay_id)
        ):
            out = get_operational_purchasability_config()
            out["idempotent_reuse"] = True
            return out

        if idempotency_key and idempotency_key in {
            a.get("idempotency_key") for a in (st.get("audit") or []) if isinstance(a, dict)
        }:
            out = get_operational_purchasability_config()
            out["idempotent_reuse"] = True
            return out

        now = datetime.now(timezone.utc).isoformat()
        st["operational_purchasability_version"] = "v31"
        st["fallback_version"] = FALLBACK_VERSION
        st["validation_replay_id"] = int(replay_id)
        st["validation_source_run_id"] = meta.get("source_run_id")
        st["validation_decision_version"] = meta.get("decision_version")
        st["validation_decision"] = DECISION_GO_FINAL
        st["validated_at"] = now
        st["validation_commit"] = meta.get("validation_commit")
        st["formula_version"] = PURCHASABILITY_V31_FORMULA_VERSION
        st["promoted_formula_version"] = PURCHASABILITY_V31_FORMULA_VERSION
        audit = list(st.get("audit") or [])
        audit.append(
            {
                "action": "promote_v31",
                "at": now,
                "replay_id": int(replay_id),
                "idempotency_key": idempotency_key,
                "meta": {
                    k: meta.get(k)
                    for k in (
                        "source_run_id",
                        "decision_version",
                        "validation_commit",
                    )
                },
            }
        )
        st["audit"] = audit[-50:]
        _write_state(st)

    out = get_operational_purchasability_config()
    out["idempotent_reuse"] = False
    return out


def rollback_purchasability_to_v3(*, confirm_token: str) -> dict[str, Any]:
    """Rollback a V3 con sola modifica di configurazione."""
    if confirm_token != ROLLBACK_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "rollback_denied_token",
            "Confirm token rollback non valido",
            status_code=403,
        )
    with _lock:
        st = _read_state()
        now = datetime.now(timezone.utc).isoformat()
        st["operational_purchasability_version"] = DEFAULT_OPERATIONAL
        st["fallback_version"] = FALLBACK_VERSION
        st["formula_version"] = PURCHASABILITY_V3_FORMULA_VERSION
        audit = list(st.get("audit") or [])
        audit.append({"action": "rollback_v3", "at": now})
        st["audit"] = audit[-50:]
        _write_state(st)
    return get_operational_purchasability_config()
