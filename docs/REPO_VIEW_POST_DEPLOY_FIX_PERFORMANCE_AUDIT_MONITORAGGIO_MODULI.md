# REPO VIEW POST-DEPLOY — FIX PERFORMANCE AUDIT MONITORAGGIO MODULI

## Comportamento runtime atteso

1. Apri Monitoraggio Moduli → card «Qualità pacchetti»: **nessuna** GET audit automatica.
2. Clicca **Riverifica** → una sola richiesta, timeout fino a 240s, feedback «Verifica forensic in corso…».
3. Cambia date/filtri → badge stale, risultati precedenti restano.
4. Secondo click durante loading → ignorato (single-flight).
5. Seconda Riverifica identica entro 5 min → risposta veloce (cache hit backend).

---

## File toccati

| Area | Path |
|------|------|
| FE card | `frontend/src/components/module-monitoring/MonitoringPackQualityCard.tsx` |
| FE guard | `frontend/src/components/module-monitoring/auditRequestGuard.ts` |
| FE test | `frontend/src/components/module-monitoring/auditRequestGuard.test.ts` |
| FE API | `frontend/src/lib/cecchinoModuleMonitoringApi.ts` |
| BE export/audit | `backend/app/services/cecchino/cecchino_module_monitoring_exports.py` |
| BE test | `backend/tests/test_cecchino_module_monitoring_audit_v5.py` |

---

## API

`GET /api/cecchino/module-monitoring/analysis-packs-audit` — invariata nel contratto; più veloce su hit cache.

Client:

```ts
getAnalysisPacksAudit(filters, { timeoutMs: 240_000, signal })
```

---

## Verifiche eseguite

```
pytest …module_monitoring*.py → 78 passed
npm run build → OK
```

---

## Non modificato

Formule, candidate, Balance/Goal/Signals/Acquistabilità operativi, coorti, backfill, DB, migrazioni, CORS, generazione ZIP analysis-pack.
