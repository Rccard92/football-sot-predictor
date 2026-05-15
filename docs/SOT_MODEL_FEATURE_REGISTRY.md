# Registry feature — baseline_v1_1_sot (Stage 4)

Modello: `baseline_v1_1_sot`  
Architettura: `component_based_strict_real_data`  
Stage: `offensive_plus_opponent_defense_plus_home_away_split_plus_recent_form`

**Regola:** il modello v1.1 non usa fallback o mock. Se un dato obbligatorio manca, la prediction viene marcata come incompleta (`prediction_valid: false`, `predicted_sot: null`).

Formula stage 4:

`expected_sot_v1_1 = (offensive_production_component × 0.35) + (opponent_defensive_resistance_component × 0.30) + (home_away_split_component × 0.15) + (recent_form_component × 0.20)`

Lo split casa/trasferta usa il contesto reale della partita: casa per la squadra di casa, trasferta per la squadra ospite, e split opposto per l'avversario.

## Componente 1 — Produzione offensiva composita (peso formula 0.35)

9 input interni (vedi Stage 1/2). Dati da partite precedenti della squadra analizzata.

## Componente 2 — Resistenza difensiva avversaria (peso formula 0.30)

6 input interni (vedi Stage 2). Concessi ricostruiti dalle partite precedenti dell'avversario.

## Componente 3 — Split casa/trasferta (peso formula 0.15)

| feature_key | Peso interno | API | DB |
|-------------|--------------|-----|-----|
| split_avg_sot_for | 0.30 | fixtures/statistics::Shots on Goal | fixture_team_stats.shots_on_target |
| split_opponent_avg_sot_conceded | 0.30 | fixtures/statistics::Shots on Goal | stats avversari nell'split avversario |
| split_avg_total_shots_for | 0.15 | fixtures/statistics::Total Shots | fixture_team_stats.total_shots |
| split_opponent_avg_total_shots_conceded | 0.15 | fixtures/statistics::Total Shots | stats avversari nell'split avversario |
| home_away_performance_delta | 0.10 | derivata | split_avg_sot_for − season_avg_sot_for |

**Filtri split:**

- Squadra in casa: solo partite precedenti giocate in casa; avversario solo partite precedenti in trasferta.
- Squadra in trasferta: solo partite precedenti fuori casa; avversario solo partite precedenti in casa.

**Sample minimo split:** 5 partite valide per squadra e per avversario nello split richiesto (`min_split_matches = 5`). Se insufficiente → `insufficient_split_sample`, nessun fallback su media stagione.

**Normalizzazione lega split:** `league_split_avg_sot_for`, `league_split_avg_sot_conceded`, `league_split_avg_total_shots_for`, `league_split_avg_total_shots_conceded` (calcolate per contesto home/away sul cutoff).

## Componente 4 — Forma recente (peso formula 0.20)

Finestra **ultime 5** partite finite (ordine kickoff, id) sia per la squadra sia per l’avversario (storici separati).  
**Nessun fallback** se `prior_fixtures` o `opponent_prior_fixtures` hanno meno di 5 partite o se non si possono costruire le medie richieste.

| feature_key | Peso interno | Nota |
|-------------|--------------|------|
| recent_avg_sot_for | 0.25 | Media SOT fatti nelle ultime 5 |
| recent_opponent_avg_sot_conceded | 0.25 | Media SOT concessi (avversari vs avversario) ultime 5 |
| recent_avg_total_shots_for | 0.15 | Media tiri totali fatti ultime 5 |
| recent_opponent_avg_total_shots_conceded | 0.15 | Media tiri concessi ultime 5 |
| recent_avg_goals_for | 0.10 | Media goal fatti ultime 5 |
| recent_trend_vs_season | 0.10 | `0.60 × ΔSOT_team + 0.40 × ΔSOT_concessi_opp`, poi clamp e scala su medie lega recent |

**Medie lega per normalizzazione:** `league_recent_avg_sot_for`, `league_recent_avg_sot_conceded`, `league_recent_avg_total_shots_for`, `league_recent_avg_total_shots_conceded`, `league_recent_avg_goals_for` — calcolate in [`league_baselines_strict.py`](backend/app/services/predictions_v11/league_baselines_strict.py) (strict: servono squadre con almeno 5 partite idonee e dati completi nella finestra).

Se le medie lega „recent“ non sono definibili → errore baseline / `missing_required_recent_league_baseline`.

Implementazione: [`recent_form_strict.py`](backend/app/services/predictions_v11/recent_form_strict.py), metadati input [`recent_feature_sources.py`](backend/app/services/predictions_v11/recent_feature_sources.py).

## Vincoli globali

- **Sample minimo componenti stagionali:** 5 partite (`min_completed_matches = 5`).
- **Forma recente:** 5 partite per lato (squadra e avversario) per le finestre ultime 5; nessuna imputazione.
- **No data leakage:** solo partite con kickoff precedente e status finito.
- **Nessun fallback** su medie lega o stagione se dati split o forma recente mancano.

## Generazione

`POST /api/predictions/sot/serie-a/{season}/generate-v11-sot`

## Debug

- `GET /api/debug/sot/fixture/{id}/explanation?model_version=baseline_v1_1_sot`
- `GET /api/debug/sot/fixture/{id}/features?model_version=baseline_v1_1_sot`
