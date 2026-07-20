"""Vocabolario coorti Monitoraggio Moduli — canoniche + alias legacy.

Non riclassificare automaticamente dati legacy come prospective_persisted.
"""

from __future__ import annotations

from typing import Literal

# Canonical cohorts (gate Fase 1/3)
COHORT_PROSPECTIVE = "prospective_persisted"
COHORT_HISTORICAL_PERSISTED_VERIFIED = "historical_persisted_verified"
COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED = "historical_reconstructed_verified"
COHORT_HISTORICAL_DIAGNOSTIC = "historical_diagnostic"
COHORT_UNUSABLE = "unusable"

# Legacy aliases (persisted in DB / older exports)
ALIAS_LEGACY_PERSISTED_BACKFILL = "legacy_persisted_backfill"
ALIAS_LEGACY_DERIVED_DIAGNOSTIC = "legacy_derived_diagnostic"

CANONICAL_COHORTS: frozenset[str] = frozenset(
    {
        COHORT_PROSPECTIVE,
        COHORT_HISTORICAL_PERSISTED_VERIFIED,
        COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED,
        COHORT_HISTORICAL_DIAGNOSTIC,
        COHORT_UNUSABLE,
    }
)

LEGACY_TO_CANONICAL: dict[str, str] = {
    ALIAS_LEGACY_PERSISTED_BACKFILL: COHORT_HISTORICAL_PERSISTED_VERIFIED,
    ALIAS_LEGACY_DERIVED_DIAGNOSTIC: COHORT_HISTORICAL_DIAGNOSTIC,
}

CANONICAL_TO_LEGACY_ALIAS: dict[str, str] = {
    COHORT_HISTORICAL_PERSISTED_VERIFIED: ALIAS_LEGACY_PERSISTED_BACKFILL,
    COHORT_HISTORICAL_DIAGNOSTIC: ALIAS_LEGACY_DERIVED_DIAGNOSTIC,
}

CohortKey = Literal[
    "prospective_persisted",
    "historical_persisted_verified",
    "historical_reconstructed_verified",
    "historical_diagnostic",
    "unusable",
]

# Promotion: only prospective
PROMOTION_ELIGIBLE_COHORTS: frozenset[str] = frozenset({COHORT_PROSPECTIVE})


def normalize_cohort(raw: str | None) -> str | None:
    """Map alias → canonical; pass-through if already canonical."""
    if raw is None:
        return None
    key = str(raw).strip()
    if not key:
        return None
    if key in CANONICAL_COHORTS:
        return key
    return LEGACY_TO_CANONICAL.get(key, key)


def is_promotion_eligible_cohort(raw: str | None) -> bool:
    return normalize_cohort(raw) in PROMOTION_ELIGIBLE_COHORTS


def storage_cohort_for_purchasability(canonical: str) -> str:
    """DB column may still use legacy alias for persisted_verified / diagnostic."""
    if canonical == COHORT_HISTORICAL_PERSISTED_VERIFIED:
        return ALIAS_LEGACY_PERSISTED_BACKFILL
    if canonical == COHORT_HISTORICAL_DIAGNOSTIC:
        return ALIAS_LEGACY_DERIVED_DIAGNOSTIC
    return canonical


COHORT_LABELS_IT: dict[str, str] = {
    COHORT_PROSPECTIVE: "Prospettica",
    COHORT_HISTORICAL_PERSISTED_VERIFIED: "Storica persistita verificata",
    COHORT_HISTORICAL_RECONSTRUCTED_VERIFIED: "Storica ricostruita verificata",
    COHORT_HISTORICAL_DIAGNOSTIC: "Storica diagnostica",
    COHORT_UNUSABLE: "Non utilizzabile",
    ALIAS_LEGACY_PERSISTED_BACKFILL: "Storica persistita verificata",
    ALIAS_LEGACY_DERIVED_DIAGNOSTIC: "Storica diagnostica",
}
