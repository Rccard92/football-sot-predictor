# Modello SOT v3.1 — Calibrated Predictor (sperimentale)

## Obiettivo

Il predittore **v3.1** (`baseline_v3_1_sot_calibrated_predictor`) è un motore **indipendente** pensato per la calibrazione pre-match su Shots on Target. Non sostituisce v3.0 nel path `analyze` e non usa come input le predizioni finali di v1.1, v2.0, v2.1 o v3.0.

## Differenza rispetto a v3.0

| Aspetto | v3.0 Value Selector | v3.1 Calibrated Predictor |
|---------|---------------------|---------------------------|
| Input principali | Pick e trace persistiti (v1.1/v2.1/v3.0) | Feature pre-match grezze / macro PIT |
| Scopo | Simulare strategie di selezione su pick esistenti | Stimare SOT totale e probabilità Over, poi selezionare linea |
| Stato | Integrato in round analysis (sperimentale) | Dataset + simulatore; predictor produzione ancora scaffold |

## Feature ammesse (training / simulazione)

Solo `row.features`:

- `team_raw_features` (medie SOT, xG, volume tiri, last5, split)
- `player_layer`
- `lineups`
- `unavailable`
- `existing_macro_features` (10 indici macro + weighted_macro_multiplier)
- `league_context`
- `data_quality`

## Feature vietate

Mai in input al modello (validazione in `v31_calibration_anti_leakage`):

- Target: `actual_total_sot`, `final_score`, `outcome`, esiti bet
- Predizioni legacy: `predicted_total_sot`, `v*_predicted_total`, `v3_0_decision`, linee e outcome storici

`row.comparisons` è solo per **confronto finale** e audit, con `allowed_for_v31_training: false`.

## Dieci macroaree

1. offensive_production_index  
2. opponent_defensive_resistance_index  
3. recent_form_index  
4. chance_quality_index  
5. pace_control_index  
6. home_away_split_index  
7. player_layer_index  
8. injuries_unavailable_index  
9. lineups_index  
10. weighted_macro_multiplier  

## Formula predittiva (simulatore)

1. **Base SOT assoluta** per squadra (`calculate_team_base_sot`): mix pesato di `avg_sot_for`, `opponent_conceded_sot_avg`, `last5`, split, `xg_to_sot`, `shots_to_sot`. Valori in dataset standard che sembrano indici macro (0.65–1.45) vengono convertiti in SOT assoluti (`league_avg × indice`).

2. **Moltiplicatore contestuale** (macro come correttivi, cap 0.85–1.15): forma, qualità chance, ritmo, split, player layer, assenze, lineups.

3. **Totale**: `home_base × ctx_home + away_base × ctx_away`, con ancoraggio al prior lega (~8.0 SOT totali) senza usare il target della fixture.

4. **Fase attuale:** solo predizione numerica su **tutte** le fixture (`prediction_status` ok/failed). Nessun pick, NO_BET, linee o probabilità Over in questa fase.

## Simulatore predittivo (15 strategie)

Endpoint: `GET /api/backtest/v31/calibration-simulator` (default: strategie **active**)  
Export summary: `GET /api/backtest/v31/calibration-simulator/report?detail=summary`  
Export completo: `GET /api/backtest/v31/calibration-simulator/report?detail=full` o `report-json`

Ogni strategia ha `strategy_status`: `active`, `diagnostic`, `archived`. Il ranking consigliato usa `dynamic_score` solo tra **active**.

| Chiave | Idea |
|--------|------|
| `v31_equal_weights` | Peso uguale sui 6 componenti base |
| `v31_core_sot_xg` | Peso alto su SOT/xG/volume; context più piatto |
| `v31_context_adjusted` | Base standard + correttivi macro pieni |
| `v31_player_layer_heavy` | Enfasi player layer / assenze / lineups |
| `v31_home_away_split_heavy` | Enfasi split casa/trasferta |
| `v31_recent_form_heavy` | Enfasi ultime 5 + forma recente |
| `v31_bias_corrected` | Contesto aggiustato + offset dinamico da errori precedenti |
| `v31_low_variance` | Blend lega alto, cap totali stretti |
| `v31_variance_unlocked` | Varianza sbloccata: blend basso, cap larghi |
| `v31_big_match_boost` | Boost quando entrambe offensive (percentili cohort) |
| `v31_big_vs_weak_push` | Favorita vs difesa fragile |
| `v31_chaos_game` | Partite aperte (concessioni, ritmo) |
| `v31_low_block_guard` | Penalità favorita vs avversario a basso ritmo |
| `v31_extreme_bucket_model` | Classificazione bucket → totale target (diagnostic) |
| `v31_bias_dynamic_high_guard` | Base bias_corrected + boost selettivo high_total_signal (0–100, soglie 52/60/70/80) |

**Signal 0–100:** componenti PIT normalizzati con redistribuzione pesi; trace `hybrid_debug` nel report.

### Volume tiri (`avg_total_shots_for`)

Nel dataset **standard**, il campo è popolato da `pace_control_index` (proxy PIT). Il simulatore applica un resolver con alias e fallback macro; il report espone `feature_availability`.

## Metriche predittive

**Regressione:** MAE, RMSE, bias, median abs error, error std.

**Vicinanza:** within ±0.5 / ±1.0 / ±1.5 / ±2.0 SOT.

**Coverage WIN (direzionale):** WIN se `actual_total_sot > predicted_total_sot` (non sostituisce MAE/bias).

**Distribuzione:** `predicted_std`, `compression_ratio`, warning `V31_MODEL_TOO_FLAT` se ratio &lt; 0.55.

**Bucket:** low (≤5), normal (6–9), high (≥10), very high (≥12) — accuracy, recall/precision high/low.

**Ranking:** `best_numeric_model` (MAE), `best_dynamic_model` (`dynamic_detection_score`), `best_compromise_model` (`compromise_score`). Raccomandazione su compromesso, non coverage win. `model_interpretation` nel summary.

**Hybrid (`v31_bias_dynamic_high_guard`):** boost tier ≥52 (+0.25), ≥60 (+0.50), ≥70 (+0.75), ≥80 (+1.00); guardrail graduali; `hybrid_debug` con warning `V31_HYBRID_BOOST_NOT_APPLIED` / `V31_HYBRID_IDENTICAL_TO_BASELINE`.

## Pattern Analysis (post-match)

Analisi qualità coverage WIN/LOSS su top-3 strategie (`bias_corrected`, `dynamic_high_guard`, `chaos_game`).

- **`actual_sot_distribution`:** percentili calcolati dal campionato (no soglie fisse).
- **Bucket dinamici:** low/normal/high/very_high/extreme da p25/p75/p90/p95.
- **`win_quality`:** HEALTHY_WIN, ACCEPTABLE_WIN, UNDERSTATED_WIN, EXTREME_WIN_OUTLIER, BAD_LOSS, CLOSE_LOSS, NORMAL_LOSS.
- **`diagnostic_weight`:** solo analisi; non modifica pesi modello.
- Endpoint: `GET /backtest/v31/pattern-analysis` (+ report summary/full).

**UI:** pagina dedicata [`/predictive-simulator`](frontend/src/pages/PredictiveSimulatorPage.tsx) con verdetto, problemi strutturali e tab Simulatore/Pattern Analysis. Backtest contiene solo card link.

## Laboratorio predittivo persistente (v31-predictive-lab-persistence)

Il simulatore predittivo è ora un **laboratorio persistente** con run salvate in PostgreSQL.

### API (`/api/predictive-simulator`)

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `POST` | `/run` | Esegue simulatore + pattern analysis e persiste la run |
| `GET` | `/runs` | Storico run (filtri `competition_id`, `season_year`) |
| `GET` | `/runs/{id}` | Payload completo (simulator + pattern + insights + audit) |
| `GET` | `/runs/{id}/fixtures` | Diagnosi fixture-by-fixture con filtri |
| `POST` | `/runs/{id}/fixtures/{fixture_id}/notes` | Nota utente per fixture×strategia |
| `POST` / `GET` | `/runs/{id}/ai-insights` | Analisi AI diagnostica (opzionale, `OPENAI_API_KEY`) |
| `GET` | `/config` | `{ openai_configured: bool }` |

Gli endpoint GET `/api/backtest/v31/*` restano per export one-shot e retrocompatibilità.

### Tabelle DB

- `predictive_simulation_runs` — summary + snapshot JSON simulator/pattern
- `predictive_fixture_predictions` — una riga per fixture×strategia con `reason_codes_json`, `win_quality`, `outcome_type`
- `predictive_pattern_insights` — insight aggregati tipizzati
- `predictive_fixture_notes` — note utente
- `predictive_ai_insights` — output analisi OpenAI (solo diagnostica, no predizione SOT)

### UI

Sette tab: Panoramica, Storico analisi, Simulatore v3.1, Diagnosi partite, Pattern Analysis, Analisi AI, Audit.

**Esegui analisi** → `POST /run` → messaggio «Analisi salvata nello storico».

La fase bet/no bet resta disabilitata (`betting_phase_enabled: false`).

### Changelog v31-predictive-lab-persistence

- Persistenza run, fixture predictions, pattern insights e note
- Reason codes analitici deterministici (`HIGH_TOTAL_MISSED`, `FALSE_HIGH_PREDICTION`, …)
- Placeholder OpenAI diagnostico post-match (503 graceful se API key assente)
- Audit esteso anti-leakage nel laboratorio

## Walk-forward

| Split | Train | Test |
|-------|-------|------|
| `wf_5_15_to_16_26` | 5–15 | 16–26 |
| `wf_5_26_to_27_37` | 5–26 | 27–37 |

Metriche test: MAE, RMSE, bias, within_1_5, coverage_win_rate (solo numerico).

## Fase bet (futura)

La selezione linee, probabilità Over e GIOCA/NO_BET sarà aggiunta in una fase successiva, separata dal confronto numerico attuale.
- Feature mancanti: nessun valore inventato → `missing_fields`, confidenza ridotta, spesso `NO_BET`.

## Limiti attuali

- Simulatore usa dataset **standard** (macro da trace v2.1, non rebuild PIT full).
- Nessuna integrazione quote bookmaker nel punteggio.
- `SotV31CalibratedPredictorService` in produzione resta scaffold (`NotImplementedError`).

## Prossimo step

1. Calibrare coefficienti su export full PIT.  
2. Integrare quote bookmaker (margine mercato vs μ).  
3. Abilitare predictor v3.1 nel flusso round analysis quando anti-leakage e backtest sono soddisfatti.
