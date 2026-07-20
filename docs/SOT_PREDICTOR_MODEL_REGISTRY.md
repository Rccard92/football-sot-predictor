# SOT Predictor — Model Registry (indice)

Registro sintetico delle versioni operative/monitorate. La fonte runtime resta l’API.

## Monitoraggio Moduli — HARDENING export (2026-07-20)

| Artefatto | Versione / note |
|-----------|-----------------|
| Export pack | `cecchino_module_monitoring_exports_v2` |
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
