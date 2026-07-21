# Repo view post-deploy — Goal v5 monitoring + export v11

## Backend (nuovi)
- `backend/app/services/cecchino/cecchino_goal_intensity_v5_dimension_registry.py`
- `backend/app/services/cecchino/cecchino_goal_intensity_v5_monitoring_adapter.py`

## Backend (modificati)
- `cecchino_goal_intensity_v5.py` — dimensions/candidates/calibration/prospective_results/settlement
- `cecchino_goal_intensity_v5_readiness.py` — adapter + prospective_progress int
- `cecchino_balance_v5_readiness.py` — maturity collecting, reconciliation, dedup Dominanza
- `cecchino_module_monitoring_exports.py` — v11, reconciliation, readiness placeholders

## Frontend
- `GoalIntensityViews.tsx` — overview global/periodo, dimensioni registry, readiness progress
- `cecchinoGoalIntensityV5Api.ts` — tipi dimensions_list / candidate_id

## Verifica
```bash
cd backend && pytest -q tests/test_cecchino_goal_intensity_v5_monitoring_consistency_fix.py
cd frontend && npm run build
```

## Fuori scope
Formule, ECDF, bundle/hash, Signals, KPI, backfill, API esterne.
