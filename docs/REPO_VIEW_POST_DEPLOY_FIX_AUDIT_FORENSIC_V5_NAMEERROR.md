# REPO VIEW POST-DEPLOY — FIX AUDIT FORENSIC V5 NAMEERROR

## Modifiche

| File | Cambio |
|------|--------|
| `backend/app/services/cecchino/cecchino_module_monitoring_exports.py` | import `build_balance_monitoring_rows`; fail-soft audit globale |
| `backend/tests/test_cecchino_module_monitoring_audit_v5.py` | regressione NameError + endpoint |
| `frontend/.../MonitoringPackQualityCard.tsx` | gestione errore Riverifica |
| `frontend/.../cecchinoModuleMonitoringApi.ts` | tipi `PackAuditItem` estesi |

## Test

```bash
cd backend
python -m pytest tests/test_cecchino_module_monitoring*.py -q
```

## Frontend

```bash
cd frontend
npm run build
npx eslint src/components/module-monitoring/MonitoringPackQualityCard.tsx src/lib/cecchinoModuleMonitoringApi.ts
```

## Endpoint

- `GET /api/cecchino/module-monitoring/analysis-packs-audit` → HTTP 200, 4 moduli
- `GET /api/cecchino/module-monitoring/balance-v5/analysis-pack-audit` → HTTP 200

CORS invariato.
