# Registry feature — baseline_v1_1_sot (Stage 1)

Modello: `baseline_v1_1_sot`  
Architettura: `component_based_strict_real_data`  
Stage: `offensive_production_only`

**Regola:** il modello v1.1 non usa fallback o mock. Se un dato obbligatorio manca, la prediction viene marcata come incompleta (`prediction_valid: false`, `predicted_sot: null`).

Formula stage 1:

`expected_sot_v1_1 = offensive_production_component` (peso 1.0)

## Input interni (component_input)

| feature_key | Peso | API | DB | Formula |
|-------------|------|-----|-----|---------|
| avg_sot_for | 0.30 | fixtures/statistics::Shots on Goal | fixture_team_stats.shots_on_target | avg(shots_on_target), partite precedenti |
| avg_total_shots_for | 0.18 | fixtures/statistics::Total Shots | fixture_team_stats.total_shots | avg(total_shots), partite precedenti |
| shot_accuracy_for | 0.14 | derivata | shots_on_target / total_shots | avg_sot_for / avg_total_shots_for |
| avg_inside_box_shots_for | 0.14 | fixtures/statistics::Shots insidebox | fixture_team_stats.shots_inside_box | avg(shots_inside_box) |
| avg_outside_box_shots_for | 0.05 | fixtures/statistics::Shots outsidebox | fixture_team_stats.shots_outside_box | avg(shots_outside_box) |
| avg_blocked_shots_for | 0.05 | fixtures/statistics::Blocked Shots | fixture_team_stats.blocked_shots | avg(blocked_shots) |
| avg_shots_off_goal_for | 0.04 | fixtures/statistics::Shots off Goal | fixture_team_stats.shots_off_target | avg(shots_off_target) |
| avg_goals_for | 0.05 | fixtures::goals | fixtures.goals (lato squadra) | avg(goals_for) |
| offensive_trend | 0.05 | derivata | fixture_team_stats.shots_on_target | avg_sot_last5 − avg_sot_season |

## Vincoli

- **Sample minimo:** 5 partite finite precedenti alla fixture target (`min_completed_matches = 5`).
- **No data leakage:** solo partite con `kickoff_at < target.kickoff_at` e status finito.
- **Normalizzazione lega:** medie lega calcolate sullo stesso cutoff; se una media lega richiesta è assente o ≤ 0 → `missing_required_league_baseline`.

## Generazione

`POST /api/predictions/sot/serie-a/{season}/generate-v11-sot`

## Debug

- `GET /api/debug/sot/fixture/{id}/explanation?model_version=baseline_v1_1_sot`
- `GET /api/debug/sot/fixture/{id}/features?model_version=baseline_v1_1_sot`
