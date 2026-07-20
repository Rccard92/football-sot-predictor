# HANDOFF PER CHATGPT — CHIUSURA UX E DATA QUALITY MONITORAGGIO FASE 1/3

**Repository:** Rccard92/football-sot-predictor  
**Scope:** layer monitoring/export/UI/audit v5 — nessuna modifica a formule, candidate, backfill o migrazioni.

---

## 1. Invalid book odds (Acquistabilità)

**Trattamento:** righe con `quota_book <= 1.00` marcate in export con:

- `analysis_eligible = false`
- `data_quality_status = invalid`
- `analysis_exclusion_reason = invalid_decimal_book_odds`

**Runtime atteso (forensic v5):** 4 righe (0.97 × 3, 1.00 × 1). Restano in `rows.csv`, conteggiate in riconciliazione, **escluse** da ROI/profitto/margine/win rate e bootstrap.

**Contatori export/summary:** `invalid_book_odds_count`, `excluded_from_performance_count`, blocco `reconciliation`:

```json
{
  "raw_rows": 8890,
  "performance_eligible_rows": 8070,
  "pending": 814,
  "result_missing": 2,
  "invalid_book_odds": 4,
  "excluded_from_performance_count": 4
}
```

---

## 2. Card Acquistabilità — prima/dopo

| Prima | Dopo |
|-------|------|
| Fixture 0 / Settled 8074 (ambiguo) | Fixture prospettiche 0 · Fixture storiche 964 |
| — | Righe storiche 8890 · Righe valutate 8074 |
| — | Pending 814 · Result missing 2 · Escluse data quality 4 |

Tre sezioni card: **Stato operativo** / **Copertura dati** / **Maturità scientifica**.

---

## 3. Balance — source_mode onesto

Storico 964 righe: `snapshot_timestamp null`, `pre_match_verified null`, `book_verified false`, `source_cohort historical_diagnostic`.

**Derived senza timestamp verificato:**

`source_mode = derived_read_only_from_stored_inputs_unverified_timestamp`

(non più `derived_read_only_from_stored_pre_match` senza verifica temporale).

Path prospettico `balance_v5_monitoring` + `pre_match_verified` invariato.

**Card:** Copertura descrittiva 964/964 · Timestamp verificati 0/964 · Snapshot prospettici 0 · Fixture settled 876 · Maturità: validazione empirica da avviare. **Nessun cerchio 100% generico.**

---

## 4. Goal — snapshot globali vs filtrati

| Metrica | Atteso runtime |
|---------|----------------|
| Snapshot globali | 204 |
| Snapshot nel periodo (19/06–20/07) | 192 |
| Completed | 0 |
| Pending | 192 |

Progressioni distinte: `snapshot_collection_progress`, `completed_results_progress`. Readiness scientifica da completed, non solo snapshot count.

---

## 5. Signals — metriche con unità

- Fixture con segnali correnti
- Attivazioni correnti
- Attivazioni correnti valutate
- Attivazioni storiche totali
- Pre-match verificate
- Post-kickoff escluse

---

## 6. Status TECH / SCI

| Modulo | TECH | SCI (atteso) |
|--------|------|--------------|
| Acquistabilità | PASS | PARTIAL |
| Balance | PASS | PARTIAL |
| Goal | PASS | PARTIAL_COLLECTING |
| Signals | PASS | PARTIAL o MONITORING |

Warning scientifici (no prospettica, timestamp non verificato, completed=0) **non** abbassano TECH.

---

## 7. File duplicati

- **Rimosso** `distributions.csv` dal pacchetto (alias legacy documentato → `distributions_by_score_band.csv` canonico).
- **Signals:** `activations_all_rows.csv` / `activations_current_rows.csv` = optional aliases, non in `required_files`.

UI audit: conteggio file = required presenti (niente 21/20).

---

## 8. Verifiche eseguite

```
pytest tests/test_cecchino_module_monitoring*.py → 74 passed
npm run build → OK
eslint (file module-monitoring modificati) → OK
```

**Backfill:** non eseguito.

---

## 9. File toccati (principali)

**Backend:** `cecchino_purchasability_validation.py`, `cecchino_purchasability_validation_aggregation.py`, `cecchino_balance_v5_monitoring.py`, `cecchino_module_monitoring_exports.py`

**Frontend:** `ModuleCardSections.tsx`, `ModuleOverviewGrid.tsx`, `*ModulePanel.tsx`, `MonitoringPackQualityCard.tsx`, `moduleMonitoringUi.ts`, `cecchinoModuleMonitoringApi.ts`

**Test:** `test_cecchino_module_monitoring_ux_closure_v5.py`
