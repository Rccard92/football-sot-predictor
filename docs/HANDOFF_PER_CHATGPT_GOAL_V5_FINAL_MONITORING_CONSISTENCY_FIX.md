# Handoff — Goal v5 monitoring + Balance export v11

## Obiettivo
Chiudere Monitoraggio Moduli 3/3: dimensioni Goal, adapter monitoring canonico, readiness/calibrazione, export condiviso **v11**, maturità Balance con pending>0, pacchetto forensic autosufficiente + riconciliazione monitoring/empirical.

## Export
- `MONITORING_EXPORT_VERSION = cecchino_module_monitoring_exports_v11`
- Balance: `balance_empirical_reconciliation.json` obbligatorio nello schema
- Readiness Balance: 9 file sempre presenti (placeholder fail-soft se builder fallisce)

## Goal Intensity v5
- Registry dimensioni: `cecchino_goal_intensity_v5_dimension_registry_v1` (OP/DV/MT/OV da `pillar_scores_payload`)
- Adapter: `normalize_goal_v5_monitoring_contract` — `completed_n`/`pending_n` int, `coverage_global`/`coverage_in_period`
- Settlement: `attach_results_for_rows` con `skipped_by_reason` + invalidazione cache readiness
- Nessuna modifica a formule, bundle, score persistiti, Signals

## Balance v5
- Maturità: `prosp_rows = settled + pending`; pending>0 settled=0 → `prospective_collecting`
- Riconciliazione: `build_balance_empirical_reconciliation` spiega gap tipo 978/983 (historical_diagnostic)

## Test
- `backend/tests/test_cecchino_goal_intensity_v5_monitoring_consistency_fix.py`
- Suite goal/balance/module_monitoring aggiornata a v11

## Commit
`fix: finalize goal v5 monitoring and shared exports`
