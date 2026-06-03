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

3. **Totale**: `home_base × ctx_home + away_base × ctx_away`, con leggero ancoraggio al prior lega (~8.0 SOT totali) senza usare il target della fixture.

4. **Probabilità Over**: normale con σ = 2.2; `P(Over k.5) = 1 - Φ((k.5 - μ) / σ)`.

5. **Selector**: soglie per strategia (conservative / balanced); confidence da qualità dato pre-match.

## Simulatore calibrazione (5 strategie)

Endpoint: `GET /api/backtest/v31/calibration-simulator`

| Chiave | Idea |
|--------|------|
| `v31_equal_weights` | Peso uguale sulle macro disponibili |
| `v31_core_sot_xg` | Peso alto su SOT/xG/volume; basso su player/assenze |
| `v31_context_adjusted` | Core + moltiplicatori split/forma/player/assenze |
| `v31_conservative_selector` | Gioca solo con dati OK, pochi warning, confidenza alta, P(Over 6.5) alta |
| `v31_balanced_selector` | Più aperto; ammette Over 7.5 con margine e probabilità sufficienti |

Ogni strategia espone pesi, metriche, walk-forward e spiegazione umana in italiano per fixture campione.

## Metriche

**Regressione:** MAE, bias, RMSE del `predicted_total_sot` vs actual (solo valutazione).

**Betting:** pick / no bet, win/loss, hit rate globale e per linea 6.5 / 7.5 / 8.5, per tier di confidenza, per blocchi giornate 5–15, 16–26, 27–37.

## Walk-forward

| Split | Train | Test |
|-------|-------|------|
| `wf_5_15_to_16_26` | 5–15 | 16–26 |
| `wf_5_26_to_27_37` | 5–26 | 27–37 |

**Limite v1:** le soglie del selector sono fisse per strategia (nessun ri-fit automatico sul train). Il walk-forward misura robustezza out-of-sample con la stessa configurazione.

## Logica bet / no bet

- Stima μ = totale SOT previsto; probabilità Over via Poisson(μ).
- Linea scelta per margine μ − linea e soglie su P(Over).
- `GIOCA` / `BORDERLINE` / `NO_BET` in base a qualità dato, warning, confidenza e strategia.
- Feature mancanti: nessun valore inventato → `missing_fields`, confidenza ridotta, spesso `NO_BET`.

## Limiti attuali

- Simulatore usa dataset **standard** (macro da trace v2.1, non rebuild PIT full).
- Nessuna integrazione quote bookmaker nel punteggio.
- `SotV31CalibratedPredictorService` in produzione resta scaffold (`NotImplementedError`).

## Prossimo step

1. Calibrare coefficienti su export full PIT.  
2. Integrare quote bookmaker (margine mercato vs μ).  
3. Abilitare predictor v3.1 nel flusso round analysis quando anti-leakage e backtest sono soddisfatti.
