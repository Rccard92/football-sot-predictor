# SOT Predictor — Model Registry (indice)

Registro sintetico delle versioni operative/monitorate. La fonte runtime resta l’API.

## Hotfix — isolamento Readiness post-scan (2026-07-21)

| Artefatto | Versione / note |
|-----------|-----------------|
| Balance formule | `cecchino_balance_v5_v2` (**invariato**) |
| Readiness / policy / governance | versioni Step 2C **invariate** |
| Schema | solo `server_default now()` su timestamp readiness/governance |

## Intensità Goal Avanzata v5 — Consolidamento finale (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v11` |
| Bundle | `cecchino_goal_intensity_v5_preview_v1_1` (frozen, invariato) |
| Facade / monitoring | `cecchino_goal_intensity_v5_monitoring_v1` |
| Readiness | `cecchino_goal_intensity_v5_readiness_v1` |
| Readiness policy | `cecchino_goal_intensity_v5_readiness_policy_v1` |
| Stato | Preview monitorata · Signals blocked |

## Balance v5 Fase 2C — Readiness & Governance (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v11` (bump condiviso) |
| Readiness | `cecchino_balance_v5_readiness_v1` |
| Readiness policy | `cecchino_balance_v5_readiness_policy_v1` |
| Governance | `cecchino_balance_v5_governance_v1` |
| Decision contract | `cecchino_balance_v5_decision_contract_v1` |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |

## Scientific Consistency Fix / export v8 (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v8` |
| Evidence canon | `build_balance_full_pillar_evidence_status` (pilastri full) |
| Bootstrap export | `BOOTSTRAP_ITERATIONS_DEFAULT` (2000) |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |

## Balance v5 Fase 2B — Analisi empirica (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v8` |
| Empirical analysis | `cecchino_balance_v5_empirical_analysis_v1` |
| Statistical policy | `cecchino_balance_v5_statistical_policy_v1` |
| Evidence cap (diagnostic) | `exploratory_evidence` |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |

## Balance v5 Fase 2A — Dataset empirico (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v6` |
| Empirical dataset | `cecchino_balance_v5_empirical_dataset_v1` |
| Target contract | `cecchino_balance_v5_empirical_target_contract_v1` |
| Tabella | `cecchino_balance_v5_evaluations` |
| Maturità Balance | `empirical_dataset_collecting` |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |

## Stabilizzazione finale Monitoraggio Moduli Fase 1/3 — export v5 (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v5` |
| Acquistabilità analisi | aggregazioni su coorte analitica (`won/lost` + quota) senza gate promozione |
| Balance timestamp | `snapshot_timestamp` da odds/KPI; `generated_at` = ora export |
| Goal preview | filtro `scan_date` end-to-end; no righe `note=empty` |
| Signals export | `all_models`; `activations_all_models.csv` + coorti + `field_availability.json` |
| Audit scientifico | regole per modulo (`partial_collecting` Goal se completed=0) |

## Fix export coorti e schemi forensic v4 (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v4` |
| Analysis vs readiness | filtro coorte su analisi; gates solo `prospective_persisted` |
| Signals forensic | multi-file activations_* |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |

## Gate chiusura Monitoraggio Moduli Fase 1/3 (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Cohorts | `prospective_persisted`, `historical_persisted_verified`, `historical_reconstructed_verified`, `historical_diagnostic`, `unusable` |
| Backfill | `cecchino_module_historical_backfill_v1` |
| Export pack | `cecchino_module_monitoring_exports_v3` |
| Audit | `analysis-pack-audit` / `analysis-packs-audit` |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |
| Roadmap | Fase 2/3 empirica Balance · Fase 3/3 (post-approvazione ZIP) |

## Monitoraggio Moduli — HARDENING export (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v2` → v3 al gate |
| Balance monitoring snapshot | `cecchino_balance_v5_monitoring_snapshot_v1` |
| Balance formule | `cecchino_balance_v5_v2` (invariato) |
| export-status | `GET /api/cecchino/module-monitoring/{key}/export-status` |

## Monitoraggio Moduli Cecchino — MICRO-FIX export portal + overview (2026-07-19)

| Artefatto | Note |
|-----------|------|
| Export portal | `MonitoringExportMenu` / `MonitoringGlobalExportMenu` → `createPortal(document.body)` |
| rows.csv | `GET /api/cecchino/module-monitoring/{module_key}/rows.csv` |
| Balance coverage | covered/eligible; settled_covered ⊆ covered; solo snapshot persistito |
| Status labels | `monitoringStatusLabel` (IT); raw key in aria-label |

## Monitoraggio Moduli Cecchino — FASE 1/3 (2026-07-19)

| Modulo | Status UI | Version fallback | Endpoint overview |
|--------|-----------|------------------|-------------------|
| Acquistabilità | Preview monitorata | `candidate_2` / validation_v1 | module-monitoring |
| Balance v5 | Ufficiale monitorato | `cecchino_balance_v5_v2` | module-monitoring |
| Goal Intensity v5 | Preview research | `goal_intensity_v5_preview` | module-monitoring |
| Segnali | Operativo | `signals_lab` | module-monitoring |

Export: `GET /api/cecchino/module-monitoring/{module_key}/analysis-pack.zip`.

Route FE: `/monitoraggio-moduli`.

## Acquistabilità

| Artefatto | Versione |
|-----------|----------|
| Feature | `cecchino_purchasability_features_v1_1` |
| Candidate attivo | `cecchino_purchasability_v1_preview_candidate_2` |
| Snapshot | `cecchino_purchasability_snapshot_v1` |
| Validation | `cecchino_purchasability_validation_v1` |
| Policy | `cecchino_purchasability_promotion_policy_v1` |

Registry candidate resta `active_preview` (nessun auto-promote).

