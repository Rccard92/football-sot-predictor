# SOT Predictor — Model Registry (indice)

Registro sintetico delle versioni operative/monitorate. La fonte runtime resta l’API.

## Segnali Cecchino — formula V3 Decimal + current-only (2026-08-06)

| Artefatto | Versione / note |
|-----------|-----------------|
| Formula matrix legacy | `cecchino_signals_matrix_v1_legacy` (archiviata) |
| Formula matrix previous | `cecchino_signals_matrix_v2_draw_dfg` (archiviata) |
| Formula matrix current | `cecchino_signals_matrix_v3_draw_dfg_decimal2` (DRAW Decimal 0.01 ROUND_HALF_UP; E invariata) |
| Consenso | `cecchino_signal_consensus_v1_min_two` (Opzione B) |
| Audit explanations | `cecchino_signal_explanations_v3` |
| Contratto helper | `get_current_signal_contract()` — canonico; gate Today `is_current_signal_matrix` + `signal_contract` |
| Semantica operativa | `acquired_only` — raw SI ≠ `is_acquired=true`; DRAW_PT eredita consenso DRAW |
| Formula registry API | `GET /api/admin/cecchino/signals/formula-registry` (FE non più unica fonte) |
| Lab A–F module | `cecchino_lab_signals_af_v2_current_v3_consensus` (acquired-only) |
| Lab KPI / settlement | **19 mercati** (`KPI_V2_ROW_DEFS`) |
| Derived rebuild | dry-run + confirm `REBUILD_CECCHINO_LAB_DERIVED_V3`; provenance `derived_refresh`; no overwrite `source_git_commit` |
| Evaluation / odds refresh | V3-only (`signal_formula_version` filter); backfill/revaluate/backtest ancora disponibili ma V3-only |
| Diagnostics | versionate (contatori v1/v2/v3 archived vs V3 acquired) |
| Migration | nessuna nuova — resta `20260806170000` |
| Operativo | sync/monitoraggio/Today/A–F: **solo V3**; V1/V2 preservate nel DB invariate |
| Value gate / settlement regole | **invariati** (universo mercati Lab = 19) |

## Segnali Cecchino — formula V2 + consenso (2026-08-06) — storico

| Artefatto | Versione / note |
|-----------|-----------------|
| Formula matrix legacy | `cecchino_signals_matrix_v1_legacy` |
| Formula matrix current (allora) | `cecchino_signals_matrix_v2_draw_dfg` (D/F/G X; E invariata) |
| Consenso | `cecchino_signal_consensus_v1_min_two` (Opzione B) |
| Audit explanations | `cecchino_signal_explanations_v2` |
| Migration | `20260806170000` additiva (unique con formula version) |
| Value gate / settlement | **invariati** |

## Segnali KPI — mercati e snapshot Acquistabilità (2026-08-06)

| Artefatto | Versione / note |
|-----------|-----------------|
| Mercati Segnali KPI | **19** (`KPI_SIGNAL_MARKET_DEFS`) — allineati al Pannello KPI |
| Attivazione | Rating ≥ 50 + Quota Book finita **> 1,00** |
| Snapshot V3 su activation | campi `purchasability_v3_*` (pre-match, no ricalcolo) |
| Snapshot V3.1 su activation | campi `purchasability_v31_*` incl. `purchasability_v31_registry_status` (pre-match, no ricalcolo) |
| V3 formula | **invariata** (`fixed_discount_v3`) |
| V3.1 formula | **invariata** (shadow `empirical_v2`) |
| Migration snapshot | `20260806120000` additiva |
| Migration registry_status | `20260806143000` additiva (nullable; no backfill SQL) |

## Balance v5 Pilastro 1 — Quota Media X (2026-08-06)

| Artefatto | Versione / note |
|-----------|-----------------|
| Balance formule | **`cecchino_balance_v5_v3`** (Pilastro 1: F36 base + correzione Quota Media X) |
| Audit explanations | `cecchino_balance_explanations_v2` |
| Monitoring snapshot | `cecchino_balance_v5_monitoring_snapshot_v2` |
| Pilastri 2–4 | matematica **invariata**; Gap usa `f36_base_index` |
| Acquistabilità V3 / V3.1 | **invariate** |
| Snapshot storici V2 | leggibili; non ricostruiti |

## Hotfix — isolamento Readiness post-scan (2026-07-21)

| Artefatto | Versione / note |
|-----------|-----------------|
| Balance formule | `cecchino_balance_v5_v2` (storico; superseduto da `_v3` per nuove scan) |
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
| Balance v5 | Ufficiale monitorato | `cecchino_balance_v5_v3` | module-monitoring |
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
| V3 ufficiale | `fixed_discount_v3` (invariata; ancora default operativo UI) |
| V3.1 shadow | `purchasability_v31_shadow` / `cecchino_purchasability_v31_fixed_discount_empirical_v2` (`shadow_candidate`; v1 frozen riproducibile; `go_no_go_v2`; storico non bloccante; promozione solo `GO_FINAL`) |
| Operational version | `v3` (default); fallback `v3`; stato runtime `.runtime/purchasability_operational_state.json` |
| KPI panel mapping | `kpi_markets_v31_phase1` |
| Goal OU Cecchino | `goal_market_poisson_empirical_v2` (coppie condivise Fase 1B) |
| HT 1X2 Cecchino | `first_half_1x2_empirical_shrinkage_v2` (famiglia normalizzata) |
| Backfill formule | `formula_backfill_v31_phase1b` (dry-run default) |

Registry candidate resta `active_preview` (nessun auto-promote). V3.1 resta `shadow_candidate`.

