# HANDOFF PER CHATGPT — FIX AUDIT FORENSIC V5 NAMEERROR

**Data:** 2026-07-20 · **Base:** `d186fe6` · **Fix commit:** post-deploy micro-fix

## Causa

In `_build_balance_files` ([`cecchino_module_monitoring_exports.py`](backend/app/services/cecchino/cecchino_module_monitoring_exports.py)) veniva chiamato `build_balance_monitoring_rows` senza importarlo da [`cecchino_balance_v5_monitoring.py`](backend/app/services/cecchino/cecchino_balance_v5_monitoring.py).

`GET /api/cecchino/module-monitoring/analysis-packs-audit` → 500 → browser mostra errore CORS (effetto collaterale).

## Fix applicato

1. **Import aggiunto:** `build_balance_monitoring_rows` nel blocco import Balance.
2. **Fail-soft globale:** `build_modules_analysis_packs_audit` isola errori per modulo con `logger.exception` + payload `{status: failed, error_code: module_audit_failed}`.
3. **Test:** [`test_cecchino_module_monitoring_audit_v5.py`](backend/tests/test_cecchino_module_monitoring_audit_v5.py) — audit Balance reale, global 4 moduli, endpoint HTTP 200.
4. **FE:** `MonitoringPackQualityCard` — toast «Verifica pacchetti non riuscita», conserva items precedenti, banner errore + Riprova.

## Non toccato

Formule, Balance v5, backfill, CORS, migrazioni, snapshot/dati.

## Verifica post-deploy

Su `/monitoraggio-moduli` → «Riverifica» deve restituire HTTP 200 con 4 moduli.

**Runtime DB non interrogabile da Cursor** — validare su Railway.
