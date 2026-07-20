# HANDOFF PER CHATGPT — STABILIZZAZIONE FINALE MONITORAGGIO MODULI FASE 1/3

**Data:** 2026-07-20 · **Export:** `cecchino_module_monitoring_exports_v5` · **Backfill:** non rieseguito.

## Cosa è cambiato (v5 vs v4)

| Modulo | Fix |
|--------|-----|
| Acquistabilità | Aggregazioni analitiche su coorte `won/lost` + quota valida **senza** `promotion_eligible`; gates/readiness restano prospettici. `source_mode` derivato da `source_cohort`. `source_total_rows` = righe filtrate SQL. |
| Balance | `snapshot_timestamp` solo da odds/KPI persistiti; `generated_at` separato. Book probs da snapshot. `draw_credibility_research.json` da `build_draw_credibility_coverage_audit`. |
| Goal | Filtro `date_from`/`date_to` su `scan_date` in preview export. CSV vuoto = solo header. `effective_date_range` dalle righe esportate. |
| Signals | `all_models=True`; file `activations_all_models.csv`, coorti pre-kickoff, aggregazioni per modello/pesi, `field_availability.json`. ROI solo model F verified current. |
| UI/Audit | Card modulo metriche esplicite; Qualità pacchetti usa `export_audit.actual_files` + stati `technical_status` / `scientific_status`. |

## Verifica consigliata (runtime)

1. Scaricare ZIP per periodo 2026-06-19 → 2026-07-20, coorte `all`.
2. Acquistabilità: `summary.json` metrics.settled > 0 con ~8k rows; distributions popolati.
3. Balance: `snapshot_timestamp` ≠ `generated_at` su righe con odds meta.
4. Goal: nessuna riga con `scan_date` fuori range; completed=0 → `scientific_status=partial_collecting`.
5. Signals: `activations_all_models.csv` con modelli A–F; `source_cohort` valorizzato.

**Nota ambiente Cursor:** Runtime DB non interrogabile dall'ambiente Cursor — validare ZIP su deploy reale.

## File chiave

- `backend/app/services/cecchino/cecchino_purchasability_validation_aggregation.py`
- `backend/app/services/cecchino/cecchino_balance_v5_monitoring.py`
- `backend/app/services/cecchino/cecchino_goal_intensity_v5_preview.py`
- `backend/app/services/cecchino/cecchino_module_monitoring_exports.py`
- `backend/tests/test_cecchino_module_monitoring_forensic_v5.py`
