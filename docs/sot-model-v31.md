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

## Simulatore predittivo (8 strategie)

Endpoint: `GET /api/backtest/v31/calibration-simulator`  
Export: `GET /api/backtest/v31/calibration-simulator/report-json` (tutte le righe fixture)

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

## Metriche predittive

**Regressione:** MAE, RMSE, bias, median abs error, error std.

**Vicinanza:** within ±0.5 / ±1.0 / ±1.5 / ±2.0 SOT.

**Coverage WIN (direzionale):** WIN se `actual_total_sot > predicted_total_sot` (non sostituisce MAE/bias).

**Ranking:** `balanced_prediction_score` (35% MAE + 20% RMSE + 15% |bias| + 20% within_1.5 + 10% coverage).

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
