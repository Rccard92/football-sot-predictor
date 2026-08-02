# Cecchino Lab — Scansione storica (replay pre-match)

## STEP 3A.2 — Semantica integrità storica preflight (2026-08-02)

Causa Run #3: `pre_match_locked_at` è il wall-clock del **freeze di ricostruzione** durante lo scan Lab (`_utcnow()`), non una cattura prospettica pre-kickoff. Confrontarlo con `kickoff_at` storico (2021) marcava tutte le valutazioni come `invalid` → contatori exact/warning/not_replayable a 0 in UI.

| Voce | Valore |
|------|--------|
| Schema | `cecchino_lab_purchasability_v3_replay_preflight_v2` |
| Integrity policy | `cecchino_lab_historical_reconstruction_integrity_v1` |
| Mode Lab | `historical_reconstruction_frozen` (chronology lock check = `not_applicable`) |
| Mode prospettico | `prospective_pre_match` solo se `lock < kickoff` dimostrabile |
| Classificazione | somma stati = `theoretical_evaluations`; `unclassified_evaluations` deve essere 0 |
| Probe | contatori completi + `by_market` + invariante somma = `formula_items_returned` |
| Cache | `run_id\|schema\|integrity_policy\|formula\|runtime_git\|summary\|probe` |

Anti-leakage invariato (whitelist formula / performance separate). **Nessun replay eseguito.** STEP 3B subordinato a Go sul nuovo summary+probe.

## STEP 3A.1 — Preflight resource-safe (2026-07-29)

Incidente Run #3: click preflight → `Failed to fetch` su preflight e sezioni dashboard; processo backend Railway riavviato; nessuna risposta HTTP sul preflight. **Nessuna prova definitiva di OOM**; causa applicativa individuata nel caricamento ORM completo (~6308 snapshot + ~63854 MarketResult) + mappa globale `markets_by_snap` in competizione con la dashboard Run.

Mitigazione 3A.1:

| Voce | Valore |
|------|--------|
| Schema | `cecchino_lab_purchasability_v3_replay_preflight_v1` (poi superato da v2 in 3A.2) |
| Endpoint | `GET .../preflight?include_probe=false` (default summary) / `include_probe=true` (probe 30) |
| Strategia | aggregati SQL + streaming colonne scalari (`yield_per=500`); niente full ORM / JSON pesanti |
| Budget | max 100k righe supportate; max 30s runtime → `blocked` + `preflight_resource_budget_exceeded` |
| UI | pagina autonoma `/cecchino-lab/purchasability-replay` (link da Storico run); **rimossa** dalla dashboard Run |
| Cache | chiave include `include_probe` |

Regole business del preflight invariate fino a 3A.2 (integrità). **Nessun replay eseguito.**

## STEP 3A — Preflight replay Acquistabilità V3 (2026-07-29)

Preflight **read-only** per verificare se Acquistabilità V3 può essere ricalcolata sugli snapshot pre-match già congelati, **senza** nuova scansione, ricalcolo modello/KPI/segnali/Balance/GI, API esterne o scritture DB.

| Voce | Valore |
|------|--------|
| Schema | vedi 3A.2 (`…_preflight_v2`) |
| Servizio | `historical_purchasability_v3_replay_preflight.py` |
| Endpoint | `GET /api/cecchino-lab/historical-scans/{run_id}/purchasability-v3-replay/preflight` |
| UI (post 3A.1) | `/cecchino-lab/purchasability-replay?run_id=` — summary poi probe opzionale |
| Universo | snapshot `eligible_core`; 8 mercati V3; escluse conteggiate a parte |
| Probe | solo se `include_probe=true`; max 30 snapshot; nessuna persistenza |
| Cache | vedi 3A.2 |

**Non implementato in 3A/3A.1/3A.2:** replay completo, job, export V3, pulsante Avvia, migration, overwrite Run #3. STEP 3B solo dopo Go sul preflight reale.

Anti-leakage: formula usa solo campi pre-match; `won`/`profit_*`/`result_*`/`settlement_*` solo per copertura performance futura.

## Dashboard analisi run

Dopo il completamento della scansione, aprire l’analisi da **Storico run → Apri analisi** oppure `/cecchino-lab/historical-scans/:runId`.

Documentazione dedicata: [`CECCHINO_LAB_RUN_DASHBOARD.md`](./CECCHINO_LAB_RUN_DASHBOARD.md).

Endpoint JSON read-only sotto `/api/cecchino-lab/historical-scans/{run_id}/dashboard/*`. Aggregazioni pure in `historical_analytics_agg.py` (condivise col report ZIP, `analytics_aggregation_version=cecchino_lab_analytics_agg_v2_3`). Export segnali opportunità/celle in `historical_signal_export.py` (`signal_export_schema_version=cecchino_lab_signal_export_v1`). Export Acquistabilità compatto in `historical_purchasability_export.py` (`purchasability_export_schema_version=cecchino_lab_purchasability_export_v1`). **Nessuna riscrittura** di run/snapshot/settlement.

Aggregazioni hardened: riconciliazione real+derived+unavailable; medie odds `null` se assenti; pattern sempre `market_key`; soglie su quote reali; `cross_competition_stability`; diagnostiche assenze dati separate. Report AI e dashboard condividono le stesse formule pure — vedi `CECCHINO_LAB_AI_REPORT_SCHEMA.md` e `CECCHINO_LAB_RUN_DASHBOARD.md`.

## Isolamento

- Solo Cecchino Lab (`cecchino_lab_*` + `cecchino_data_lab`).
- **Non** modifica Cecchino Today, formule, gate Betfair, snapshot operativi.
- Bookmaker operativo Today: **Betfair** (invariato).
- Bookmaker replay storico: **Bet365** (CSV Football-Data).
- Run #1 (test tecnico 200 partite) resta consultabile e non viene rielaborato.

## Audit moduli (FASE 1)

| Modulo | Funzione canonica | Parità live | Lab |
|--------|-------------------|-------------|-----|
| Intensità Goal | 7 feature + `TrainEcdf` + `_pillar_scores_from_pct` | **Parziale** (no bundle Today, no xG) | `historical_goal_intensity.py` |
| Acquistabilità | `calculate_purchasability_v2_item` + profilo progressivo | **Non equivalente Betfair** | `historical_purchasability.py` |
| Segnali A–F | pesi ufficiali + `compute_final_odds` + `build_signals_matrix` | **F = modello corrente** | `historical_signal_models.py` |

## Avvio

1. UI: tab **Scansioni storiche** in `/cecchino-lab`
2. API `POST /api/admin/cecchino-lab/historical-scans`

### Modalità

| Modalità | Body | UI |
|----------|------|-----|
| **Scansione completa** (percorso primario) | `max_matches: null` | “Scansione completa” |
| Test tecnico (diagnostica) | `max_matches: 200` | menu **Opzioni tecniche** |
| Pilota bilanciato (diagnostica) | `pilot_strategy: "eligible_per_competition"`, `eligible_per_competition: 20` | menu **Opzioni tecniche** |

La UI principale mostra solo **Verifica dati** e **Scansione completa**. Test tecnico e pilota bilanciato restano disponibili nel backend e nel menu secondario «Opzioni tecniche».

Intensità Goal e Equilibrio vs Squilibrio sono **moduli osservazionali**: valori completi/parziali/non disponibili vengono salvati su ogni partita eleggibile e **non** bloccano l’eleggibilità `eligible_core`.

Pilota bilanciato: per ogni campionato, ordine cronologico, registra escluse, si ferma a N `eligible_core`, poi passa al successivo. Target tipico fino a 320 eleggibili; processate totali possono superare il target. `run_scope=balanced_pilot`, `is_partial_run=true`, `not_full_season_report=true`.

Progresso: a completamento `competitions_completed == competitions_total`, `current_competition=null`, `progress_pct=100` (fix off-by-one sull’ultimo campionato). Run #1/#2 già persistiti non vengono riscritti.

Scansione completa con revisione git sconosciuta: **bloccata**. Pilota: permesso + warning in policy/manifest.

## Revisione Git

Ordine: `RAILWAY_GIT_COMMIT_SHA` → `SOURCE_VERSION` → `GIT_COMMIT_SHA` → `VERCEL_GIT_COMMIT_SHA` → `git rev-parse HEAD`.

Salvati sul run: `source_git_commit`, `source_git_commit_source`, `source_revision_status` (revisione **scan**).
Report/dashboard espongono anche la revisione **runtime** (`report_generator_git_commit` / `analytics_runtime_git_commit`) risolva a generazione/lettura — non riscrivono il run.

## Pipeline per partita

1. Contesti pre-match (anti-leakage)
2. Cecchino + goal markets + KPI Bet365
3. Intensità Goal storica (pilastri) + Acquistabilità storica Bet365 + segnali modelli A–F
4. Eleggibilità storica
5. Freeze snapshot + hash SHA-256 pre-match (include GI/purch/A–F/profilo/versioni; **no** risultato/settlement)
6. Collegamento risultato FT/HT
7. Settlement mercati **solo se** `core_eligible=true` (default settlement su modello F)

### Partite escluse

- Snapshot + risultato + motivo salvati; `settlement_status=excluded`
- Zero righe mercato nelle metriche di performance
- Diagnostica in `excluded_diagnostics`

## Intensità Goal storica

- Versione: `cecchino_lab_goal_intensity_historical_v1`
- `parity_status=partial`: stesse feature/pilastri, ECDF progressivo solo su eligible_core precedenti dello stesso run; **nessun** bundle produzione Today
- xG: `missing`, mai imputato a 0
- Campione insufficiente → status esplicito, score null
- Persistenza: `goal_intensity_compatibility_json` (payload arricchito, retrocompatibile)

## Acquistabilità storica Bet365

- Versione: `cecchino_lab_purchasability_historical_v1`
- Profilo progressivo: solo KPI eligible_core precedenti; target/futuro esclusi; no risultati reali nel profilo; no profilo Betfair
- Prima di `MIN_SIDE_SAMPLES` (15): `insufficient_historical_normalization_sample`, score null
- `quote_quality`: `real` | `derived` | `unavailable`
- Osservazionale: non blocca eleggibilità, non sceglie giocate, non entra in Today
- Resume: stesso profilo hash dagli snapshot precedenti
- **Export read-only** (`cecchino_lab_purchasability_export_v1`): `purchasability_compact.jsonl` canonico; gate rejected ≠ «Molto Bassa»; `diagnostic_ungated_score` da phase persistite; decisioni/drift/profili; formula **non** ricalcolata; Run #3 invariato

## Modelli segnali A–F

`signals_json`:

```json
{
  "default_model_key": "F",
  "default_matrix": {},
  "models": { "A": { "meta", "weights", "final", "matrix", "active_signals", "settlements" }, "...": "F" }
}
```

Pesi ufficiali invariati; F ≡ modello corrente. Snapshot legacy (Run #1, matrice flat) restano leggibili.

## Report AI v4 (frammentati)

`GET /api/cecchino-lab/historical-scans/{id}/report?mode=...`

| Mode | Contenuto |
|------|-----------|
| `ai_summary` | Sintesi ChatGPT (consigliata): manifest, report_index, summary, patterns_top, schema — senza JSONL enormi |
| `competition` | Singolo campionato + matches/purchasability compact |
| `module` | `markets` \| `signals` \| `goal_intensity` \| `purchasability` \| `balance` |
| `full_archive` | Archivio tecnico completo — non necessario per la prima analisi ChatGPT |

Generazione progressiva (`SpooledTemporaryFile` + JSONL riga-per-riga). Etichette A–F da `model_meta_for_key` / `get_cecchino_weight_model` (nessun `model_label` null in export).

Profitto in `summary_json` del run: per mercato / modello A–F / fascia rating / fascia Acquistabilità.
`technical_sum_across_all_independent_market_rows` + `not_a_betting_strategy=true` — non è profitto del Cecchino.

## Anti-leakage e hash

Priori con kickoff strettamente precedente. Hash include moduli calcolati; non include FT/HT/esito/profitto.

## Test

```bash
cd backend
pytest -q tests/test_cecchino_lab_historical_scan.py
pytest -q tests/test_cecchino_lab_historical_modules_v3.py
pytest -q tests/test_cecchino_lab_*.py
```
