# Intensità Goal Avanzata v5 — Monitoring & consolidamento

**Stato operativo:** Preview monitorata  
**Bundle frozen:** `cecchino_goal_intensity_v5_preview_v1_1` (invariato)  
**Export pack:** `cecchino_module_monitoring_exports_v10`

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
- `calibration`, `stability`, `readiness`, `data-health`
- `export` → dossier `SOT_GOAL_INTENSITY_V5_READINESS_<FROM>_<TO>.zip`
- Catch-all: `export-status`, `analysis-pack.zip` (forensic v10)

Admin: `POST …/admin/…/goal-intensity-v5/readiness/refresh` (solo cache/report).

## Readiness attesa (campione insufficiente)

- TECH: bundle/hash/no-target  
- SCI: `prospective_not_started` / `prospective_collecting` / `insufficient_completed_sample`  
- DECISION: `continue_monitoring`  
- SIGNALS: `blocked`

Sotto i 200 completed: **non** «validato»; `earliest_theoretical_review_at=null` se completed=0.

## Frontend

- Today: `CecchinoGoalIntensityV5Panel` — badge «Preview monitorata» + «Non collegato ai Segnali»
- Workspace: viste overview · dimensioni · candidati · prospettici · calibrazione · stabilità · readiness · data-health · export
- Redirect: `/cecchino/ricerca-intensita-goal` → `…/monitoraggio-moduli?module=goal-intensity-v5&view=overview`
- Client: `cecchinoGoalIntensityV5Api.ts`

## Fuori scope

Rinomina tabelle `*_preview_*`, re-freeze bundle, promozione Primary, integrazione Signals, switch utente v4/v5.
