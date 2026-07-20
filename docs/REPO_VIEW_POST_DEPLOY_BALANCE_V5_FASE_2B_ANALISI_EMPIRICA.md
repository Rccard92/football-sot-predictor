# REPO VIEW POST-DEPLOY — BALANCE V5 FASE 2B ANALISI EMPIRICA

## Runtime atteso

1. Non rieseguire sync empirico.
2. Monitoraggio → Balance → Geometria F36 / Dominanza / Credibilità X / Gap / Stabilità / Data health.
3. Evidence badge «esplorativa» con coorte historical_diagnostic.
4. Job statistico completo (POST jobs → poll) se necessario.
5. Scaricare ZIP Balance forensic **v7** e verificare audit TECH PASS / SCI exploratory|partial_diagnostic.

## File principali

| Area | Path |
|------|------|
| Registry | `backend/app/services/cecchino/cecchino_balance_v5_empirical_registry.py` |
| Analysis | `…/cecchino_balance_v5_empirical_analysis.py` |
| Stats | `…/cecchino_balance_v5_empirical_analysis_stats.py` |
| Jobs | `…/cecchino_balance_v5_empirical_analysis_jobs.py` |
| Routes | `backend/app/routes/cecchino_module_monitoring.py` |
| Export | `…/cecchino_module_monitoring_exports.py` (v7) |
| FE | `frontend/src/components/module-monitoring/balance/*` |

## Verifiche

Pytest analysis + monitoring; `npm run build`; eslint file Balance.
