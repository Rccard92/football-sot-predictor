# Registry feature — baseline_v1_1_sot (Stage 6)

Modello: `baseline_v1_1_sot`  
Architettura: `component_based_strict_real_data`  
Stage: `offensive_defense_split_recent_xg_player_profile`

**Regola:** il modello v1.1 non usa fallback o mock. Se un dato obbligatorio manca, la prediction viene marcata come incompleta (`prediction_valid: false`, `predicted_sot: null`).

Formula stage 6:

`expected_sot_v1_1 = (offensive_production_component × 0.25) + (opponent_defensive_resistance_component × 0.22) + (home_away_split_component × 0.13) + (recent_form_component × 0.15) + (xg_chance_quality_component × 0.12) + (player_layer_component × 0.13)`

Lo split casa/trasferta usa il contesto reale della partita: casa per la squadra di casa, trasferta per la squadra ospite, e split opposto per l'avversario.

## Componente 1 — Produzione offensiva composita (peso formula 0.25)

9 input interni (vedi Stage 1/2). Dati da partite precedenti della squadra analizzata.

## Componente 2 — Resistenza difensiva avversaria (peso formula 0.22)

6 input interni (vedi Stage 2). Concessi ricostruiti dalle partite precedenti dell'avversario.

## Componente 3 — Split casa/trasferta (peso formula 0.13)

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

## Componente 4 — Forma recente (peso formula 0.15)

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

## Componente 5 — Qualità occasioni / xG (peso formula 0.12)

Fonte API-Football: `fixtures/statistics` include `expected_goals` quando disponibile; persistenza DB in `fixture_team_stats.expected_goals` (float nullable). Se la colonna è `NULL` ma il campo è presente in `fixture_team_stats.raw_json`, il valore può essere letto da lì e la traccia indica la fonte alternativa — **non** si inventano valori.

**Campione minimo:** almeno **5** partite con `expected_goals` disponibile per la squadra (media stagionale xG) **e** 5 partite con xG per il ramo concessi avversario (`min_xg_matches = 5`). Se insufficiente → `insufficient_xg_sample`, **nessun fallback**.

Servono anche le medie lega `league_avg_xg_for` e `league_avg_xg_conceded` sul campione eligible; se mancanti o non valide → `missing_required_xg_league_baseline`.

| feature_key | Peso interno | Ruolo |
|-------------|--------------|-------|
| avg_xg_for | 0.30 | xG medi prodotti dalla squadra (scala SOT via lega) |
| opponent_avg_xg_conceded | 0.30 | xG medi concessi dall’avversario (pool avversari, scala SOT) |
| team_xg_delta_vs_league | 0.15 | Delta vs `league_avg_xg_for` (raw = differenza semplice; normalizzato su scala SOT) |
| opponent_xg_conceded_delta_vs_league | 0.15 | Delta vs `league_avg_xg_conceded` |
| xg_prudent_adjustment_signal | 0.10 | Segnale prudente `league_avg_sot_for × (1 + xg_adjustment_pct)` con cap su `xg_adjustment_pct` |

Implementazione: [`xg_quality_strict.py`](backend/app/services/predictions_v11/xg_quality_strict.py), metadati [`xg_feature_sources.py`](backend/app/services/predictions_v11/xg_feature_sources.py).

## Componente 6 — Player layer / impatto giocatori (peso formula 0.13)

Fonte: `player_season_profiles` (nessuna API live in generazione). Per ogni squadra: top **5** profili per `shooting_impact_score` tra giocatori con `minutes_total ≥ 180`, `reliability_score` valorizzato e almeno uno tra `shots_on_per90` / `shots_total_per90`. Se meno di **3** eleggibili → `insufficient_player_profile_sample`.

| feature_key | Peso interno | source_path |
|-------------|--------------|-------------|
| top_players_sot_per90_signal | 0.28 | player_season_profiles.shots_on_per90 |
| top_players_shots_per90_signal | 0.18 | player_season_profiles.shots_total_per90 |
| top_players_sot_share_signal | 0.18 | player_season_profiles.team_sot_share |
| top_players_shots_share_signal | 0.10 | player_season_profiles.team_shots_share |
| top_players_recent_minutes_signal | 0.12 | player_season_profiles.recent_minutes_last5 |
| top_players_rating_signal | 0.08 | player_season_profiles.avg_rating |
| top_players_reliability_signal | 0.06 | player_season_profiles.reliability_score |

Normalizzazione (modalità storica): `team_avg × league_avg_sot_for / league_player_avg` per ciascun segnale (baseline lega = media delle medie team sui top 5).

### Stage 7B — Player layer lineup-adjusted

Quando **entrambe** le formazioni ufficiali (casa e trasferta) sono in DB (`fixture_lineups.is_available`, titolari in `fixture_lineup_players`):

- `mode = lineup_adjusted`
- Calcolo sui **titolari** con profilo `player_season_profiles` (match `api_player_id`)
- Top shooter: top 5 squadra per `shooting_impact_score` / SOT90 / minuti (non solo attaccanti)
- Input aggiuntivi con peso interno: `top_shooter_starter_presence_signal` (0.12), `top_shooter_lineup_absence_signal` (0.05)
- Normalizzazione presence: `league_avg_sot_for × (0.85 + signal × 0.30)`; absence: `league_avg_sot_for × (1 − clamp(signal × 0.25, 0, 0.25))`
- **Nessuna** API live in `generate-v11-sot`; **nessun** injuries/sidelined; **nessun** fallback

Se lineups non disponibili: `mode = historical_recent_profile` (7 segnali storici); presence/absence con `not_available_yet` e contributo 0. La predizione **non** viene invalidata.

Pesi interni lineup-adjusted (somma 1.0): starters SOT/90 0.23, shots/90 0.15, SOT share 0.15, shots share 0.08, recent minutes 0.10, rating 0.07, reliability 0.05, presence 0.12, absence 0.05.

Implementazione: [`player_layer_strict.py`](backend/app/services/predictions_v11/player_layer_strict.py), [`player_layer_lineup_helpers.py`](backend/app/services/predictions_v11/player_layer_lineup_helpers.py), metadati [`player_layer_feature_sources.py`](backend/app/services/predictions_v11/player_layer_feature_sources.py).

## Lineups / formazioni (DB + Player layer 7B)

| Aspetto | Dettaglio |
|---------|-----------|
| Fonte API | `fixtures/lineups` (solo ingestion admin) |
| Tabelle | `fixture_lineups`, `fixture_lineup_players` |
| Ingestion | `POST /api/admin/ingest/serie-a/{season}/lineups` |
| Debug | `GET /api/debug/sot/fixture/{id}/lineups` |
| Stato assenza | `not_available_yet` (non errore modello) |
| Impatto formula | Via **Player layer** (6ª componente, peso 13% invariato) in modalità `lineup_adjusted` |
| Mock / fallback | Vietati |

## Availability / Indisponibili (step 8A) — **rimosso / disattivato**

| Aspetto | Dettaglio |
|---------|-----------|
| Stato | Feature rimossa (maggio 2026): ingest, admin, audit UI e package `services/availability/` eliminati |
| Motivo | Dati API-Sports (`injuries`, `sidelined`) e Sportmonks non affidabili per uso predittivo |
| Impatto formula | **Nessuno** — `availability_adjustment` sempre `disabled`, penalità `0` in v1.1 e v0.2 |
| Tabelle DB | `player_availability`, `player_availability_events` mantenute (storico; nessun drop migration) |
| Player layer | Peso 13% invariato; nessun injuries/sidelined nel calcolo |

La componente indisponibili/infortuni è stata rimossa perché i dati da API-Sports e valutazioni Sportmonks si sono dimostrati non affidabili. Il modello SOT Prediction non utilizza attualmente assenze o infortuni nel calcolo.

## SportAPI RapidAPI (debug only)

| Aspetto | Dettaglio |
|---------|-----------|
| Stato | Integrato solo admin/debug; `SPORTAPI_ENABLED=false` di default |
| Uso modello | **Nessuno** finché `USE_SPORTAPI_LINEUPS_IN_MODEL=false` |
| Tabelle | `fixture_provider_mappings`, `fixture_provider_lineups`, `fixture_provider_lineup_players`, `fixture_missing_players` |
| Endpoint | `/api/admin/sportapi/*` (4 route manuali) |

## Vincoli globali

- **Sample minimo componenti stagionali:** 5 partite (`min_completed_matches = 5`).
- **Forma recente:** 5 partite per lato (squadra e avversario) per le finestre ultime 5; nessuna imputazione.
- **xG:** 5 partite con xG per lato (conteggi `team_xg_sample_n` / `opponent_xg_sample_n`); nessun fallback silenzioso.
- **No data leakage:** solo partite con kickoff precedente e status finito.
- **Nessun fallback** su medie lega o stagione se dati split, forma recente o xG mancano.

## Generazione

`POST /api/predictions/sot/serie-a/{season}/generate-v11-sot`

## Debug

- `GET /api/debug/sot/fixture/{id}/explanation?model_version=baseline_v1_1_sot`
- `GET /api/debug/sot/fixture/{id}/features?model_version=baseline_v1_1_sot`
- `GET /api/debug/sot/fixture/{id}/lineups`
