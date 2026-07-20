# REPO VIEW POST-DEPLOY — STABILIZZAZIONE FINALE MONITORAGGIO MODULI FASE 1/3

## HEAD atteso post-merge

Branch `main` con export **`cecchino_module_monitoring_exports_v5`**.

## Superficie API (invariata)

- `GET /api/cecchino/module-monitoring/overview`
- `GET /api/cecchino/module-monitoring/analysis-packs-audit`
- `GET /api/cecchino/module-monitoring/{module}/analysis-pack.zip`

Parametro `source_cohort` wired end-to-end.

## Test

```bash
cd backend
python -m pytest tests/test_cecchino_module_monitoring_forensic_v5.py \
  tests/test_cecchino_module_monitoring_gate.py \
  tests/test_cecchino_module_monitoring_hardening.py -q
```

38 test monitoraggio pass (2026-07-20).

## Frontend

- Card overview per modulo con metriche stabilizzate (Acquistabilità/Balance/Goal/Signals).
- `MonitoringPackQualityCard`: file count da audit, tech/sci separati.

```bash
cd frontend && npm run build
```

## Non toccato (per brief)

- Formule Balance/Goal/Signals operative
- Backfill storico (`run_module_historical_backfill`)
- Gate promozione Acquistabilità (solo path readiness)

## Runtime

Validazione ZIP/backfill su DB produzione: **non eseguita da Cursor** (DB non interrogabile).
