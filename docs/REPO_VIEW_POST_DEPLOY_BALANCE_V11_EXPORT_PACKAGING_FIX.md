# Repo view post-deploy — Balance v11 export packaging

## File modificati
- `backend/app/services/cecchino/cecchino_balance_v5_readiness.py` — payload condiviso, CSV helpers, `_serialize_filters`, `list_balance_governance_decisions`
- `backend/app/services/cecchino/cecchino_module_monitoring_exports.py` — forensic readiness refactor, placeholder completi, audit Balance
- `backend/app/services/cecchino/cecchino_balance_v5_monitoring.py` — `last_snapshot_at`
- `backend/tests/test_cecchino_balance_v5_export_pack_readiness.py` — integrazione ZIP

## Verifica
```bash
cd backend && pytest -q tests/test_cecchino_balance_v5_export_pack_readiness.py
```

## Invariato
Formule, policy readiness/governance, dataset empirico, coorti, Goal v5, Signals.
