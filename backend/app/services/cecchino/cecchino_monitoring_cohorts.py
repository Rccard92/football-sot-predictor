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

# Export cohort filter
COHORT_FILTER_ALL = "all"

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


def parse_export_cohort_filter(raw: str | None) -> str:
    """
    Normalizza il filtro coorte per export/analisi.
    
    Ritorna "all" oppure una coorte canonica.
    
    Alias mappati:
    - "prospective" → prospective_persisted
    - "legacy_persisted_backfill" → historical_persisted_verified
    - "legacy_derived_diagnostic" → historical_diagnostic
    """
    if raw is None:
        return COHORT_FILTER_ALL
    
    key = str(raw).strip().lower()
    
    if not key or key == "all":
        return COHORT_FILTER_ALL
    
    # Normalizza alias UI comuni
    ui_aliases = {
        "prospective": COHORT_PROSPECTIVE,
        "prospective_persisted": COHORT_PROSPECTIVE,
    }
    
    if key in ui_aliases:
        return ui_aliases[key]
    
    # Normalizza via funzione esistente
    normalized = normalize_cohort(raw)
    
    if normalized and normalized in CANONICAL_COHORTS:
        return normalized
    
    # Se non riconosciuto, ritorna "all" (non fallire)
    return COHORT_FILTER_ALL


def cohort_storage_variants(canonical: str) -> list[str]:
    """
    Ritorna valori DB da matchare per una coorte canonica.
    
    Include il valore canonico + eventuali alias legacy persistiti.
    
    Esempio:
    - historical_persisted_verified → ["historical_persisted_verified", "legacy_persisted_backfill"]
    - prospective_persisted → ["prospective_persisted"]
    """
    if canonical == COHORT_FILTER_ALL:
        return []
    
    variants = [canonical]
    
    # Aggiungi alias legacy se presente
    legacy_alias = CANONICAL_TO_LEGACY_ALIAS.get(canonical)
    if legacy_alias:
        variants.append(legacy_alias)
    
    return variants


def analysis_query_flags(cohort_filter: str) -> dict[str, bool | str | list[str] | None]:
    """
    Ritorna flag per query di analisi basati sul filtro coorte.
    
    Keys:
    - promotion_eligible_only: bool (True solo se prospective_persisted)
    - source_cohort: str | None (None se "all")
    - source_cohorts: list[str] | None (varianti DB per SQL IN, None se "all")
    """
    if cohort_filter == COHORT_FILTER_ALL:
        return {
            "promotion_eligible_only": False,
            "source_cohort": None,
            "source_cohorts": None,
        }
    
    # Determina se solo promotion eligible
    promotion_only = cohort_filter == COHORT_PROSPECTIVE
    
    # Ottieni varianti di storage
    variants = cohort_storage_variants(cohort_filter)
    
    return {
        "promotion_eligible_only": promotion_only,
        "source_cohort": cohort_filter,
        "source_cohorts": variants if variants else None,
    }
