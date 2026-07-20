# Balance v5 — Dataset empirico (Fase 2/3 Step 2A)

Persistenza e settlement del dataset empirico Balance v5 **senza** modificare formule, soglie, classi, pesi, score aggregato, Signals o Acquistabilità candidate.

**Step 2B (analisi):** vedi [`SOT_PREDICTOR_BALANCE_V5_EMPIRICAL_ANALYSIS.md`](SOT_PREDICTOR_BALANCE_V5_EMPIRICAL_ANALYSIS.md) — export v7, evidence esplorativa.

## Versioni

| Artefatto | Valore |
|-----------|--------|
| Dataset | `cecchino_balance_v5_empirical_dataset_v1` |
| Target contract | `cecchino_balance_v5_empirical_target_contract_v1` |
| Sync confirm | `SYNC_BALANCE_V5_EMPIRICAL_DATASET` |
| Tabella | `cecchino_balance_v5_evaluations` |
| Migrazione | `20260720120000` |
| Export pack | `cecchino_module_monitoring_exports_v6` |
| Maturità overview | `empirical_dataset_collecting` |

## Flusso

1. **Scan / recompute** → dopo attach monitoring Balance → upsert empirico fail-soft  
2. **Update-results** → solo `settle` su score fixture (hash invariato)  
3. **Admin sync** → plan (dry-run) / run (token)  
4. **API read-only** → health / summary / rows / target-contract / cardinality  
5. **Export ZIP v6** → file `empirical_*` nel pack Balance  
6. **UI** → vista «Dataset empirico» (dopo Overview)

## Coorti e promozione

- Coorti mappate dal resolver monitoring esistente  
- `historical_diagnostic` **non** promuove  
- `promotion_eligible` solo su `prospective_persisted` verificata pre-match  

## Settlement

Status: `pending|settled|not_evaluable|result_missing|cancelled|postponed`  
Outcome: `HOME|DRAW|AWAY`  
`dominance_selection_hit`: DRAW hit solo se selection `X`; altrimenti miss.

## Fuori scope (Step 2B)

Win-rate, calibrazione, promozione automatica, cambio formule.
