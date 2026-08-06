# Intensità Goal Avanzata v5 — Monitoring & consolidamento

**Stato operativo:** Preview monitorata  
**Bundle frozen:** `cecchino_goal_intensity_v5_preview_v1_1` (invariato)  
**Export pack:** `cecchino_module_monitoring_exports_v11`

## Architettura

| Layer | Modulo | Ruolo |
|-------|--------|-------|
| Motore | `cecchino_goal_intensity_v5_preview.py` | Formule, ECDF, calibrazione, snapshot (frozen) |
| Facade | `cecchino_goal_intensity_v5.py` | API pubblica Today/monitoring/settlement |
| Policy | `cecchino_goal_intensity_v5_readiness_policy.py` | Soglie immutabili (`MINIMUM_PROSPECTIVE_MATCHES=200`) |
| Readiness | `cecchino_goal_intensity_v5_readiness.py` | Gate, maturità, dossier ZIP |
| v4 rollback | `goal_intensity_analysis.py` | Solo JSON Today; non esposto in UI |

Versioni stringa (non toccano il bundle):

- Monitoring: `cecchino_goal_intensity_v5_monitoring_v1`
- Readiness: `cecchino_goal_intensity_v5_readiness_v1`
- Policy: `cecchino_goal_intensity_v5_readiness_policy_v1`
- Export modulo: `cecchino_goal_intensity_v5_export_v1`

## Today

Campo canonico: `goal_intensity_v5`  
Alias deprecato: `goal_intensity_v5_preview` (`deprecated: true`, `replacement: "goal_intensity_v5"`)  
v4: `goal_intensity_analysis` resta nel payload per rollback/regression.

Dopo update-results: `attach_results_for_rows(..., commit=False)` fail-soft (niente ricalcolo score).

## API canoniche

Prefix: `/api/cecchino/module-monitoring/goal-intensity-v5/`

- `overview`, `dimensions`, `candidates`, `prospective-results`
- `benchmark-v4-v5` (Phase 2B paired V4 vs quattro candidati V5)
- `phase-2c-candidates` (Phase 2C dry-run: GI_E/GI_F, split, holdout)
- `calibration`, `stability`, `readiness`, `data-health`
- `export` → dossier `SOT_GOAL_INTENSITY_V5_READINESS_<FROM>_<TO>.zip`
- Catch-all: `export-status`, `analysis-pack.zip` (forensic + `benchmark_v4_v5_*` + `phase_2c_*`)

Admin:
- `POST …/admin/…/goal-intensity-v5/readiness/refresh` (solo cache/report)
- `POST …/admin/…/goal-intensity-v5/phase-2c-candidates/freeze` (`dry_run` + confirm `FREEZE_GOAL_INTENSITY_V5_CANDIDATE_BUNDLE_V2_1`)

## Phase 2C (varianti candidate bundle)

- Conservati GI_A / GI_B; archiviati MT1 / without_volatility; nuovi GI_E / GI_F
- Bundle v2.1 non operativo (`is_active=false`); parent v1.1 resta attivo
- Tab FE «Varianti Phase 2C»; testi neutri (nessuna promozione)
- Migration `20260806200000` (status String(64)); freeze produzione richiede `alembic upgrade head`

## Phase 2B (campione ≥200)

- Maturità: `ready_for_manual_review` su overview, readiness e card modulo (allineate)
- Next step: `phase_2b_replacement_review` («Revisione manuale Phase 2B»)
- `current_decision=continue_monitoring`; Signals `blocked`
- Coverage globale vs periodo esplicite; Readiness non mostra più zero su completed/pending
- Benchmark: versione `cecchino_goal_intensity_v4_v5_prospective_benchmark_v1`; V4 da input pre-match persistiti; niente run 2021/22

## Readiness attesa (campione insufficiente)

- TECH: bundle/hash/no-target  
- SCI: `prospective_not_started` / `prospective_collecting` / `insufficient_completed_sample`  
- DECISION: `continue_monitoring`  
- SIGNALS: `blocked`

Sotto i 200 completed: **non** «validato»; `earliest_theoretical_review_at=null` se completed=0.

## Frontend

- Today: `CecchinoGoalIntensityV5Panel` — badge «Preview monitorata» + «Non collegato ai Segnali»
- Workspace: viste overview · dimensioni · candidati · prospettici · **benchmark V4 vs V5** · calibrazione · stabilità · readiness · data-health · export
- Redirect: `/cecchino/ricerca-intensita-goal` → `…/monitoraggio-moduli?module=goal-intensity-v5&view=overview`
- Client: `cecchinoGoalIntensityV5Api.ts`

## Fuori scope

Rinomina tabelle `*_preview_*`, re-freeze bundle, promozione Primary, integrazione Signals, switch utente v4/v5.
