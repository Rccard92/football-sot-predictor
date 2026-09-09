"""Audit anti-leakage RUN V2.

Due controlli indipendenti per ogni match:

1. temporale — nessuna partita usata come storico puo avere
   `kickoff_at >= target.kickoff_at` (confronto stretto, mai `<=`);
2. strutturale — il payload pre-match congelato non puo contenere chiavi
   riconducibili all'esito o alle statistiche della partita stessa.

Le violazioni non vengono mai ignorate in silenzio: contano nel summary e
`leakage_violations = 0` e condizione di successo della run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

LEAKAGE_AUDIT_VERSION = "cecchino_run_v2_leakage_audit_v1"

VIOLATION_HISTORY_NOT_STRICTLY_BEFORE = "history_kickoff_not_strictly_before_target"
VIOLATION_TARGET_IN_HISTORY = "target_match_in_history"
VIOLATION_FORBIDDEN_PAYLOAD_KEY = "forbidden_key_in_pre_match_payload"
VIOLATION_CONTEXT_BUILDER_FLAG = "context_builder_leakage_flag"

# Sottostringhe vietate nelle chiavi del payload pre-match congelato.
FORBIDDEN_PAYLOAD_KEY_SUBSTRINGS: tuple[str, ...] = (
    "actual_",
    "result",
    "settlement",
    "fulltime",
    "outcome",
    "won",
    "profit",
    "economic_benchmark",
    "quote_observations",
    "movement",
    "closing",
)

# Chiavi ammesse nonostante contengano una sottostringa vietata: sono
# dichiarazioni di policy, non dati della partita.
ALLOWED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "no_closing_fallback",
        "pre_closing_reference",
        "reference_timing",
        "strict_policy_version",
    }
)


@dataclass
class MatchLeakageAudit:
    """Esito dell'audit per un singolo match."""

    lab_match_id: int
    target_kickoff: datetime | None
    latest_history_kickoff_used: datetime | None
    history_count: int
    pre_match_cutoff_ok: bool
    violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_violation(self) -> bool:
        return bool(self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": LEAKAGE_AUDIT_VERSION,
            "lab_match_id": self.lab_match_id,
            "target_kickoff": self.target_kickoff.isoformat() if self.target_kickoff else None,
            "latest_history_kickoff_used": (
                self.latest_history_kickoff_used.isoformat()
                if self.latest_history_kickoff_used
                else None
            ),
            "history_count": self.history_count,
            "pre_match_cutoff_ok": self.pre_match_cutoff_ok,
            "violations": list(self.violations),
        }


def audit_history_window(
    *,
    lab_match_id: int,
    target_kickoff: datetime | None,
    history_kickoffs: list[datetime | None],
    history_ids: list[int] | None = None,
    context_builder_leakage_ok: bool = True,
) -> MatchLeakageAudit:
    """Verifica che tutto lo storico usato preceda strettamente il target."""
    valid = [k for k in history_kickoffs if k is not None]
    latest = max(valid) if valid else None
    audit = MatchLeakageAudit(
        lab_match_id=lab_match_id,
        target_kickoff=target_kickoff,
        latest_history_kickoff_used=latest,
        history_count=len(history_kickoffs),
        pre_match_cutoff_ok=True,
    )

    if target_kickoff is not None and latest is not None and latest >= target_kickoff:
        audit.pre_match_cutoff_ok = False
        audit.violations.append(
            {
                "code": VIOLATION_HISTORY_NOT_STRICTLY_BEFORE,
                "target_kickoff": target_kickoff.isoformat(),
                "latest_history_kickoff_used": latest.isoformat(),
            }
        )

    if history_ids and lab_match_id in set(history_ids):
        audit.pre_match_cutoff_ok = False
        audit.violations.append({"code": VIOLATION_TARGET_IN_HISTORY})

    if not context_builder_leakage_ok:
        audit.pre_match_cutoff_ok = False
        audit.violations.append({"code": VIOLATION_CONTEXT_BUILDER_FLAG})

    return audit


def _iter_keys(payload: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.append(path)
            keys.extend(_iter_keys(v, path))
    elif isinstance(payload, list):
        for item in payload:
            keys.extend(_iter_keys(item, prefix))
    return keys


def audit_pre_match_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Cerca chiavi post-match nel payload congelato."""
    violations: list[dict[str, Any]] = []
    for path in _iter_keys(payload):
        leaf = path.rsplit(".", 1)[-1]
        if leaf in ALLOWED_PAYLOAD_KEYS:
            continue
        lowered = leaf.lower()
        for bad in FORBIDDEN_PAYLOAD_KEY_SUBSTRINGS:
            if bad in lowered:
                violations.append(
                    {
                        "code": VIOLATION_FORBIDDEN_PAYLOAD_KEY,
                        "path": path,
                        "matched": bad,
                    }
                )
                break
    return violations


class RunLeakageAuditor:
    """Aggregatore run-level delle violazioni."""

    def __init__(self, *, max_details: int = 100) -> None:
        self.matches_audited = 0
        self.violations_count = 0
        self.matches_with_violation = 0
        self.details: list[dict[str, Any]] = []
        self._max_details = max_details

    def record(self, audit: MatchLeakageAudit) -> None:
        self.matches_audited += 1
        if not audit.has_violation:
            return
        self.matches_with_violation += 1
        self.violations_count += len(audit.violations)
        if len(self.details) < self._max_details:
            self.details.append(audit.to_dict())

    @property
    def ok(self) -> bool:
        return self.violations_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": LEAKAGE_AUDIT_VERSION,
            "matches_audited": self.matches_audited,
            "matches_with_violation": self.matches_with_violation,
            "leakage_violations": self.violations_count,
            "leakage_ok": self.ok,
            "details": list(self.details),
            "details_truncated": self.matches_with_violation > len(self.details),
        }
