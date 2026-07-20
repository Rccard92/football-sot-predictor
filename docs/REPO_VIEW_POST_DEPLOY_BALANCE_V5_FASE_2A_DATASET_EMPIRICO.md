# REPO VIEW POST-DEPLOY — BALANCE V5 FASE 2A DATASET EMPIRICO

## Comportamento runtime atteso

1. Migrazione `20260720120000` applicata → tabella `cecchino_balance_v5_evaluations`.
2. Scan/recompute eleggibile → upsert empirico fail-soft (scan non fallisce se empirico fallisce).
3. Update-results con FT → settle empirico; `snapshot_hash` invariato.
4. Monitoraggio → Balance → vista **Dataset empirico**: health/coorti/governance + dry-run → conferma → run.
5. Overview Balance: maturità «Dataset empirico in raccolta»; operativo «Ufficiale monitorato».
6. Export analysis pack Balance: versione **v6** con file `empirical_*`.

---

## File toccati (principali)

| Area | Path |
|------|------|
| Model | `backend/app/models/cecchino_balance_v5_evaluation.py` |
| Migration | `backend/alembic/versions/20260720120000_cecchino_balance_v5_evaluations.py` |
| Empirical service | `backend/app/services/cecchino/cecchino_balance_v5_empirical.py` |
| Overview maturity | `backend/app/services/cecchino/cecchino_balance_v5_monitoring.py` |
| Export v6 | `backend/app/services/cecchino/cecchino_module_monitoring_exports.py` |
| Pipeline | `cecchino_today_service.py`, `cecchino_recompute_service.py` |
| Routes | `cecchino_module_monitoring.py`, `cecchino_module_monitoring_backfill.py` |
| FE vista | `frontend/src/components/module-monitoring/balance/BalanceEmpiricalDatasetView.tsx` |
| FE panel/registry/API | `BalanceModulePanel.tsx`, `moduleMonitoringRegistry.ts`, `cecchinoModuleMonitoringApi.ts` |
| Test | `backend/tests/test_cecchino_balance_v5_empirical.py` |

---

## API

```
POST /api/admin/cecchino/module-monitoring/balance-v5/empirical-sync/plan
POST /api/admin/cecchino/module-monitoring/balance-v5/empirical-sync/run  # confirm token
GET  /api/cecchino/module-monitoring/balance-v5/empirical/health|summary|rows|target-contract|cardinality
```

---

## Verifiche eseguite

Vedere handoff §21 e output pytest / `npm run build` nella sessione di implementazione.
