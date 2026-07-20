# HANDOFF PER CHATGPT — FIX DOWNLOAD DOSSIER READINESS BALANCE V5

**Repository:** Rccard92/football-sot-predictor  
**Scope:** micro-fix HTTP 500 su `GET …/balance-v5/readiness/export`.  
**Invariato:** formule, policy, dataset, sync, Signals, CORS, export forensic v9.

---

## Causa

- `_parse_filters` lascia `date` Python in `filters`.
- `_jb` usava `json.dumps(make_json_safe(obj))`.
- `make_json_safe` non converte `date`/`datetime`.
- Eccezione: `TypeError: Object of type date is not JSON serializable`.
- Il “CORS” in browser era effetto secondario del 500.

## Fix

- Serializer dossier: `jsonable_encoder(make_json_safe(obj))` + `json.dumps(..., allow_nan=False)`.
- Logging endpoint: started / completed / failed.
- FE: `toast.error('Download dossier readiness non riuscito')` (Sonner), niente `alert`.

## Verifica

- `metadata.filters.date_from` / `date_to` = stringhe `YYYY-MM-DD`.
- Test builder reale + TestClient ZIP HTTP 200.
- `readinessQuery` continua a passare stringhe senza `Date`/`toISOString`.

## File toccati

- `backend/app/services/cecchino/cecchino_balance_v5_readiness.py`
- `backend/app/routes/cecchino_module_monitoring.py`
- `frontend/src/components/module-monitoring/balance/BalanceReadinessView.tsx`
- `backend/tests/test_cecchino_balance_v5_readiness.py`
- questo handoff + REPO VIEW
