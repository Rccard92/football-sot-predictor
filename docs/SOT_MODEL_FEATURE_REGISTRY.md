# Registry feature — baseline_v1_1_sot (Stage 2)

Modello: `baseline_v1_1_sot`  
Architettura: `component_based_strict_real_data`  
Stage: `offensive_plus_opponent_defense`

**Regola:** il modello v1.1 non usa fallback o mock. Se un dato obbligatorio manca, la prediction viene marcata come incompleta (`prediction_valid: false`, `predicted_sot: null`).

Formula stage 2:

`expected_sot_v1_1 = (offensive_production_component × 0.60) + (opponent_defensive_resistance_component × 0.40)`

## Componente 1 — Produzione offensiva composita (peso formula 0.60)

| feature_key | Peso interno | API | DB |
|-------------|--------------|-----|-----|
| avg_sot_for | 0.30 | fixtures/statistics::Shots on Goal | fixture_team_stats.shots_on_target |
| avg_total_shots_for | 0.18 | fixtures/statistics::Total Shots | fixture_team_stats.total_shots |
| shot_accuracy_for | 0.14 | derivata | shots_on_target / total_shots |
| avg_inside_box_shots_for | 0.14 | fixtures/statistics::Shots insidebox | fixture_team_stats.shots_inside_box |
| avg_outside_box_shots_for | 0.05 | fixtures/statistics::Shots outsidebox | fixture_team_stats.shots_outside_box |
| avg_blocked_shots_for | 0.05 | fixtures/statistics::Blocked Shots | fixture_team_stats.blocked_shots |
| avg_shots_off_goal_for | 0.04 | fixtures/statistics::Shots off Goal | fixture_team_stats.shots_off_target |
| avg_goals_for | 0.05 | fixtures::goals | fixtures.goals (lato squadra) |
| offensive_trend | 0.05 | derivata | last5 SOT − season SOT |

Dati da **partite precedenti della squadra** analizzata (stesso cutoff anti-leakage).

## Componente 2 — Resistenza difensiva avversaria (peso formula 0.40)

| feature_key | Peso interno | API | DB |
|-------------|--------------|-----|-----|
| opponent_avg_sot_conceded | 0.35 | fixtures/statistics::Shots on Goal | stats avversario dell'avversario |
| opponent_avg_total_shots_conceded | 0.22 | fixtures/statistics::Total Shots | stats avversario dell'avversario |
| opponent_avg_inside_box_shots_conceded | 0.18 | fixtures/statistics::Shots insidebox | stats avversario dell'avversario |
| opponent_avg_outside_box_shots_conceded | 0.07 | fixtures/statistics::Shots outsidebox | stats avversario dell'avversario |
| opponent_avg_blocked_shots_conceded | 0.06 | fixtures/statistics::Blocked Shots | stats avversario dell'avversario |
| opponent_defensive_trend_recent | 0.12 | derivata | last5 SOT concessi − season SOT concessi |

**Concessi:** per ogni partita precedente dell'**avversario**, si leggono le statistiche della squadra che ha affrontato l'avversario in quella partita (equivalente a `sot_against` in `PriorMatch`).

Medie lega defensive: `league_avg_*_conceded` calcolate sullo stesso cutoff (stat dell'altra squadra per ogni coppia fixture/squadra).

## Vincoli

- **Sample minimo:** 5 partite finite precedenti per la squadra e per l'avversario.
- **No data leakage:** solo partite con `kickoff_at < target.kickoff_at` e status finito.
- **Normalizzazione lega:** medie offensive e defensive sullo stesso cutoff; se assenti o ≤ 0 → `missing_required_league_baseline`.

## Generazione

`POST /api/predictions/sot/serie-a/{season}/generate-v11-sot`

## Debug

- `GET /api/debug/sot/fixture/{id}/explanation?model_version=baseline_v1_1_sot`
- `GET /api/debug/sot/fixture/{id}/features?model_version=baseline_v1_1_sot`
