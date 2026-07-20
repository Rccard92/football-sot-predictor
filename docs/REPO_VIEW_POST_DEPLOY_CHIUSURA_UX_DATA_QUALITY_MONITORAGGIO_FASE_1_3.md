# REPO VIEW POST-DEPLOY — CHIUSURA UX E DATA QUALITY MONITORAGGIO FASE 1/3

## Stato deploy

Micro-fix applicato su layer **monitoraggio moduli v5** (export, overview, audit, card UI). Nessun backfill, nessuna migrazione, nessuna modifica formule/candidate/moduli operativi.

---

## Acquistabilità

### Data quality export
Ogni riga forensic include:

| Campo | Valore se quota_book ≤ 1 |
|-------|--------------------------|
| analysis_eligible | false |
| data_quality_status | invalid |
| analysis_exclusion_reason | invalid_decimal_book_odds |

### Riconciliazione (summary + export meta)
- `raw_rows` = righe totali filtrate
- `performance_eligible_rows` = won/lost con quota valida
- `invalid_book_odds` / `excluded_from_performance_count`
- pending, result_missing espliciti

### Overview API
Campi nuovi: `historical_fixtures`, `evaluated_rows`, `data_quality_excluded_rows`, `reconciliation`.

---

## Balance

- Coorte storica: `historical_diagnostic`
- Derived senza TS verificato: `derived_read_only_from_stored_inputs_unverified_timestamp`
- Overview: `coverage_descriptive_ratio`, `timestamp_verified_ratio`, `scientific_maturity`

---

## Goal

- `global_snapshots` vs `snapshots_in_period`
- `snapshot_collection_progress` / `completed_results_progress`
- `scientific_maturity` basata su completed

---

## Signals

- `fixtures_with_current_signals`, `current_activations_evaluated`
- `historical_activations_total`, `post_kickoff_excluded_count`

---

## Audit export (TECH / SCI)

```python
technical_status = "fail" if hard_failure else "pass"  # warnings NON influenzano TECH
```

`SCHEMA_CONTRACTS` con `optional_aliases` per Purch e Signals.

---

## UI

### ModuleCardSections (nuovo)
Tre blocchi per ogni card modulo:
1. Stato operativo
2. Copertura dati (label esplicita)
3. Maturità scientifica

### ModuleOverviewGrid
- Rimosso `MonitoringProgressRing` (niente cerchio 100% generico)
- Metriche per-modulo (non Fixture/Settled ambigui)

### MonitoringPackQualityCard
- Conteggio file: required presenti / required totali

---

## Test suite

| File | Note |
|------|------|
| test_cecchino_module_monitoring_ux_closure_v5.py | **nuovo** — DQ, TECH/SCI, source_mode, card semantics |
| test_cecchino_module_monitoring_hardening.py | aggiornato source_mode Balance |
| Altri test_cecchino_module_monitoring_* | 74 totali passed |

---

## Comandi verifica post-deploy

```bash
cd backend
python -m pytest tests/test_cecchino_module_monitoring.py \
  tests/test_cecchino_module_monitoring_audit_v5.py \
  tests/test_cecchino_module_monitoring_forensic_v4.py \
  tests/test_cecchino_module_monitoring_forensic_v5.py \
  tests/test_cecchino_module_monitoring_gate.py \
  tests/test_cecchino_module_monitoring_hardening.py \
  tests/test_cecchino_module_monitoring_ux_closure_v5.py -q

cd ../frontend
npm run build
```

---

## Conferme

- [x] Backfill **non** eseguito
- [x] Dati originali Cecchino Today **non** modificati
- [x] Formule / candidate / Rating / Score **non** toccati
- [x] Build frontend OK
- [x] 74 test monitoring OK
