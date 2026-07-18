# Registry feature modello SOT

Registro delle variabili usate nei modelli SOT. **Parte principale: v2.1** (`baseline_v2_1_weighted_components`). Sezioni brevi su v1.1 (base v2.0) e v2.0.

> **Nota research Indice di Acquistabilità (Fase 1 / 1.1 / 2A / 2A.1):** variabili KPI in audit v1_1; Fase 2A.1 valuta contributo OOF paired (`statistical_research_v2a_1`) senza promuovere feature al registry produttivo SOT. **Non** Indice 0–100.

> **Nota research Intensità Goal v5 (Fase 1D / 1D.1 / 2A / 2A.1):** gli indici candidati `GI_A`–`GI_D` e gli score pilastro OP/DV/MT/OV sono definizioni research fisse (`cecchino_goal_intensity_v5_candidate_indices_v1` / `v1_1`), normalizzate con ECDF train-only. La Preview (`cecchino_goal_intensity_v5_preview_v1_1`) applica lo stesso bundle congelato su snapshot pre-match con freeze reale e identity guard. **Non** sono feature del registry produttivo SOT né della formula Intensità Goal v4; nessun segnale betting.

Fonte codice: `backend/app/services/predictions_v21/v21_manifest_definitions.py`, `v21_feature_collectors.py`, `v21_macro_aggregators.py`, `v21_feature_context.py`.

Legenda modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md).

---

## Regole generali v2.1

| Regola | Dettaglio |
|--------|-----------|
| xG | Solo da `fixture_team_stats.expected_goals`. **No proxy xG.** |
| Anti-leakage | Solo fixture con status finito (`FT`, `AET`, `PEN`) e kickoff **prima** del kickoff target |
| Passaggi riusciti | Colonna `season_avg_passes_completed` se presente, altrimenti derivata: `passes_total × pass_accuracy / 100` (`available_derived`) |
| Assenze top shooter | Due key distinte: `player_layer_top_shooter_absence` (macro player) e `injuries_top_shooter_absence` (macro infortuni) |
| Lineups | Possono essere ufficiali (`confirmed=true`) o probabili — impatto su confidence, non su formula diretta |
| Missing players | Possono essere incompleti/non affidabili — warning in audit |
| Rientri importanti | Richiedono storico snapshot sufficiente (min 3 fixture su 12 match lineup history) |
| Macro 10 | Quality-only: non modifica SOT, incide su audit/confidence/warning |

### Pesi manifest

- Somma `macro_weight` predittivi + quality = **100**
- Somma `micro_weight` per ogni macro predittiva = **100**
- I pesi sono **punti manifest** (16 = 16%), non frazioni 0–1

### Formula (richiamo)

```
expected_sot_v21 = max(0, base_anchor_sot × weighted_macro_multiplier)

base_anchor_sot = 0.55 × team_sot_for + 0.45 × opponent_sot_conceded

macro_index = clamp( Σ(norm × micro_weight) / Σ(micro_weight), 0.75, 1.25 )
weighted_macro_multiplier = clamp( Σ(macro_index × macro_weight) / 100, 0.75, 1.30 )
```

---

## Status possibili

### Status micro (`V21MicroStatus`)

| Status | Significato | Conta in coverage? | Normalizzazione |
|--------|-------------|-------------------|-----------------|
| `available` | Dato presente | sì | ratio vs baseline |
| `available_derived` | Calcolato da derivata | sì | ratio vs baseline |
| `partial` | Dato parziale o baseline assente | sì | neutra 1.0 |
| `fallback_partial` | Stima parziale (es. turnover senza storico) | sì | neutra 1.0 |
| `fallback_historical_profiles` | Profili storici senza lineups SportAPI | sì | neutra 1.0 |
| `fallback` | Fallback generico | no (conta in fallback count) | neutra 1.0 |
| `missing` | Dato assente | no | — |
| `missing_dependency` | Dipendenza mancante (profili/lineups) | no | neutra 1.0 |
| `not_tracked_yet` | Non implementato / collector assente | no | — |
| `feed_unavailable` | Feed xG non disponibile | no | neutra 1.0 |

### Status macro (`V21MacroStatus`)

| Status | Condizione |
|--------|------------|
| `available` | Tutte le micro disponibili per coverage |
| `partial` | Alcune micro missing, almeno una available |
| `missing` | Zero micro available |
| `degraded_feed_unavailable` | Solo `chance_quality`: tutte le micro xG in `feed_unavailable`/`missing` |

### Warning testuali (non status formali)

Il codice emette warning come:
- «Storico formazioni insufficiente per cambio modulo vs media»
- «Storico lineups insufficiente, turnover stimato con profili/minuti»
- «xG non disponibile nel feed importato»

> **Nota:** status `not_enough_snapshot_history` / `insufficient_history` **non esistono** come enum nel codice. Usare i warning sopra.

---

## Macroaree v2.1

### 1. Produzione offensiva composita

| Campo | Valore |
|-------|--------|
| Key | `offensive_production` |
| Label | Produzione offensiva composita |
| Peso macro | **16** |
| Predittiva | sì |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `avg_sot_for` | Media tiri in porta fatti | 25 | `team_stats.season_avg_sot_for` |
| `avg_total_shots_for` | Media tiri totali fatti | 20 | `team_stats.season_avg_shots_for` |
| `shot_accuracy` | Precisione tiro: SOT / tiri totali | 18 | `team_stats.shot_accuracy_for` |
| `avg_inside_box_shots` | Media tiri dentro area | 16 | `team_stats.season_avg_inside_box_shots_for` |
| `avg_outside_box_shots` | Media tiri fuori area | 3 | `team_stats.season_avg_outside_box_shots_for` |
| `avg_blocked_shots` | Media tiri bloccati | 2 | `team_stats.season_avg_blocked_shots_for` |
| `avg_off_target_shots` | Media tiri fuori dallo specchio | 1 | `team_stats.season_avg_off_target_shots_for` |
| `avg_goals_for` | Media goal fatti | 5 | `team_stats.season_avg_goals_for` |
| `offensive_trend` | Trend offensivo recente | 10 | `team_stats.offensive_trend_recent` |

**Calcolo:** aggregati stagionali da `fixture_team_stats` (prior pre-kickoff). Trend = confronto ultime 5 vs media stagione.

---

### 2. Resistenza difensiva avversaria

| Campo | Valore |
|-------|--------|
| Key | `opponent_defensive_resistance` |
| Label | Resistenza difensiva avversaria |
| Peso macro | **14** |
| Predittiva | sì |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `opp_sot_conceded` | SOT concessi avversario stagione | 30 | `opponent_stats.season_avg_sot_conceded` |
| `opp_total_shots_conceded` | Tiri totali concessi avversario | 20 | `opponent_stats.season_avg_shots_conceded` |
| `opp_inside_box_conceded` | Tiri dentro area concessi avversario | 25 | `opponent_stats.season_avg_inside_box_conceded` |
| `opp_outside_box_conceded` | Tiri fuori area concessi avversario | 2 | `opponent_stats.season_avg_outside_box_conceded` |
| `opp_blocked_shots` | Tiri bloccati/concessi | 3 | `opponent_stats.season_avg_blocked_shots_conceded` |
| `opp_defensive_trend` | Trend difensivo recente avversario | 20 | `opponent_stats.defensive_trend_recent` |

---

### 3. Split casa/trasferta

| Campo | Valore |
|-------|--------|
| Key | `home_away_split` |
| Label | Split casa/trasferta |
| Peso macro | **10** |
| Predittiva | sì |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `split_sot_for` | SOT fatti casa/fuori | 25 | `team_stats.split_avg_sot_for` |
| `split_opp_sot_conceded` | SOT concessi avversario casa/fuori | 25 | `opponent_stats.split_avg_sot_conceded` |
| `split_shots_for` | Tiri totali fatti casa/fuori | 15 | `team_stats.split_avg_shots_for` |
| `split_shots_conceded` | Tiri totali concessi casa/fuori | 15 | `opponent_stats.split_avg_shots_conceded` |
| `split_performance_delta` | Differenza rendimento casa/fuori | 20 | `team_stats.home_away_performance_delta` |

**Calcolo:** split basato su `is_home` della fixture target.

---

### 4. Forma recente

| Campo | Valore |
|-------|--------|
| Key | `recent_form` |
| Label | Forma recente |
| Peso macro | **15** |
| Predittiva | sì |
| Finestra | Ultime **5** partite (`RECENT_FORM_MATCHES`) |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `last5_sot_for` | SOT fatti ultime 5 | 20 | `team_stats.last5_avg_sot_for` |
| `last5_opp_sot_conceded` | SOT concessi avversario ultime 5 | 20 | `opponent_stats.last5_avg_sot_conceded` |
| `last5_shots_for` | Tiri totali fatti ultime 5 | 15 | `team_stats.last5_avg_shots_for` |
| `last5_shots_conceded` | Tiri totali concessi ultime 5 | 15 | `opponent_stats.last5_avg_shots_conceded` |
| `last5_goals_for` | Goal fatti ultime 5 | 10 | `team_stats.last5_avg_goals_for` |
| `form_trend_vs_season` | Trend rispetto alla media stagionale | 20 | `team_stats.form_trend_vs_season_avg` |

---

### 5. Qualità occasioni (xG)

| Campo | Valore |
|-------|--------|
| Key | `chance_quality` |
| Label | Qualità occasioni |
| Peso macro | **17** |
| Predittiva | sì |
| Fonte xG | `fixture_team_stats.expected_goals` |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `xg_produced` | xG prodotti | 30 | `fixture_team_stats.expected_goals` |
| `xg_conceded_by_opponent` | xG concessi dall'avversario | 30 | `opponent_fixture_team_stats.expected_goals_against` |
| `xg_delta_vs_league` | Delta xG squadra vs media lega | 15 | `derived.team_xg_for_vs_league_avg` |
| `opp_xg_conceded_delta` | Delta xG concesso avversario vs media lega | 15 | `derived.opponent_xg_conceded_vs_league_avg` |
| `xg_prudent_adjustment` | xG adjustment prudente | 10 | `derived.xg_prudent_adjustment_signal` |

**Regole xG:**
- Lettura: colonna DB → fallback `raw_json` (chiavi `expected_goals`, `value`, blocchi `statistics`)
- Baseline lega: `compute_v21_xg_league_baselines()` con `leakage_guard: true`
- Se feed non disponibile: tutte le micro → `feed_unavailable`, macro → `degraded_feed_unavailable`, warning «xG non disponibile nel feed importato»
- `xg_prudent_adjustment`: media dei ratio xG, clamp norm `[0.85, 1.15]`
- **No proxy xG**

---

### 6. Player layer

| Campo | Valore |
|-------|--------|
| Key | `player_layer` |
| Label | Player layer |
| Peso macro | **9** |
| Predittiva | sì |
| Top shooters | Top **5** per SOT/90, share, impact, reliability |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `top_sot_per90` | Tiri in porta per 90 dei top player | 20 | `player_season_profiles.top_shooters_sot_per90` |
| `top_shots_per90` | Tiri totali per 90 dei top player | 10 | `player_season_profiles.top_shooters_shots_per90` |
| `top_sot_share` | Quota SOT squadra prodotta dai top player | 15 | `player_season_profiles.top_shooters_sot_share` |
| `top_shots_share` | Quota tiri squadra prodotta dai top player | 8 | `player_season_profiles.top_shooters_shots_share` |
| `offensive_recent_minutes` | Minuti recenti dei giocatori offensivi | 8 | `player_season_profiles.offensive_recent_minutes` |
| `offensive_avg_rating` | Rating medio giocatori offensivi | 7 | `player_season_profiles.offensive_avg_rating` |
| `top_profile_reliability` | Affidabilità profili top player | 6 | `player_season_profiles.top_profile_reliability` |
| `top_shooter_presence` | Presenza dei top shooter | 8 | `lineup_impact.top_shooter_presence` |
| `player_layer_top_shooter_absence` | Assenza dei top shooter | 18 | `lineup_impact.player_layer_top_shooter_absence` |

**Fallback:** senza lineups SportAPI → `fallback_historical_profiles` (solo profili stagionali).

---

### 7. Lineups / formazioni

| Campo | Valore |
|-------|--------|
| Key | `lineups` |
| Label | Lineups / formazioni |
| Peso macro | **5** |
| Predittiva | sì |
| Fonte | SportAPI (`sportapi_lineups.*`) |
| Storico | 12 match, min 3 fixture (`LINEUP_HISTORY_MATCHES`, `LINEUP_HISTORY_MIN_FIXTURES`) |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `official_lineup` | Formazione ufficiale | 29 | `sportapi_lineups.official` |
| `confirmed_starters` | Titolari confermati | 10 | `sportapi_lineups.confirmed_starters` |
| `bench` | Panchina | 1 | `sportapi_lineups.bench` |
| `tactical_module` | Modulo tattico | 15 | `sportapi_lineups.formation` |
| `module_change_vs_avg` | Cambio modulo rispetto alla media | 5 | `sportapi_lineups.module_change_vs_avg` |
| `attackers_starters` | Presenza attaccanti/trequartisti titolari | 25 | `sportapi_lineups.attackers_in_starters` |
| `offensive_defensive_turnover` | Turnover offensivo/difensivo | 15 | `sportapi_lineups.turnover_offensive_defensive` |

**Probabili vs ufficiali:** `official_lineup` penalizzato se `confirmed=false`. Warning se probabili only.

---

### 8. Infortuni / indisponibili

| Campo | Valore |
|-------|--------|
| Key | `injuries_unavailable` |
| Label | Infortuni / indisponibili |
| Peso macro | **5** |
| Predittiva | sì |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `injured` | Infortunati | 14 | `sportapi_lineups.injured_players` |
| `suspended` | Squalificati | 10 | `sportapi_lineups.suspended_players` |
| `unavailable` | Indisponibili | 5 | `sportapi_lineups.unavailable_players` |
| `absent_player_weight` | Peso del giocatore assente | 17 | `lineup_impact.absent_player_weight` |
| `starter_vs_bench_absence` | Assenza titolare vs panchinaro | 14 | `lineup_impact.starter_vs_bench_absence` |
| `injuries_top_shooter_absence` | Assenza top shooter | 16 | `lineup_impact.injuries_top_shooter_absence` |
| `key_defender_absence_opp` | Assenza difensore chiave avversario | 14 | `lineup_impact.opponent_key_defender_absence` |
| `important_returns` | Rientri importanti | 10 | `sportapi_lineups.important_returns` |

**Distinzione assenze top shooter:**
- `player_layer_top_shooter_absence` → macro 6 (impatto offensivo profili)
- `injuries_top_shooter_absence` → macro 8 (impatto infortuni/indisponibili)

---

### 9. Ritmo e controllo partita

| Campo | Valore |
|-------|--------|
| Key | `pace_control` |
| Label | Ritmo e controllo partita |
| Peso macro | **5** |
| Predittiva | sì |

| Key micro | Label | Peso | Source path |
|-----------|-------|------|-------------|
| `avg_possession` | Possesso palla medio | 15 | `team_stats.season_avg_possession` |
| `total_passes` | Passaggi totali | 5 | `team_stats.season_avg_passes` |
| `passes_completed` | Passaggi riusciti | 5 | `derived.passes_total_x_pass_accuracy` |
| `pass_accuracy` | Precisione passaggi | 15 | `team_stats.season_pass_accuracy` |
| `territorial_control` | Controllo territoriale | 25 | `team_stats.territorial_control_index` |
| `estimated_pace` | Ritmo stimato della squadra | 35 | `team_stats.estimated_pace` |

**Passaggi riusciti:** se colonna `season_avg_passes_completed` presente → `available`; altrimenti derivata → `available_derived`.

---

### 10. Controlli qualità / sicurezza modello

| Campo | Valore |
|-------|--------|
| Key | `model_quality_controls` |
| Label | Controlli qualità / sicurezza modello |
| Peso macro | **4** |
| Predittiva | **no** (quality-only) |

| Key micro | Label | Source path |
|-----------|-------|-------------|
| `sample_count` | Sample count per ogni variabile | `quality.sample_count_by_variable` |
| `fallbacks_used` | Fallback usati | `quality.fallbacks_used` |
| `missing_data` | Dati mancanti | `quality.missing_data_flags` |
| `no_data_leakage` | No data leakage | `quality.no_data_leakage_check` |
| `source_path_audit` | Source path per ogni variabile | `quality.source_path_audit` |
| `formula_quality_status` | Formula quality status | `quality.formula_quality_status` |
| `suspicious_value_warnings` | Warning su valori sospetti | `quality.suspicious_value_warnings` |

**Impatto:** non modifica `weighted_macro_multiplier`. Alimenta `confidence_score`, `warnings`, audit UI.

**Confidence score:**
```
quality_score = clamp(coverage_pct - 0.5×missing - 0.3×fallback, 0, 100)
confidence_score = clamp(quality_score - 10 se leakage != ok, 0, 100)
```

---

## v1.1 — sintesi (base interna v2.0)

| Campo | Valore |
|-------|--------|
| Slug | `baseline_v1_1_sot` |
| Architettura | Additiva (6 componenti) |
| Visibilità UI | No (legacy, nascosto dal selettore) |

**Componenti (6 termini):**

| Key | Label | Ruolo |
|-----|-------|-------|
| `offensive_production_component` | Produzione offensiva | Media SOT/tiri/accuracy |
| `opponent_defensive_resistance_component` | Resistenza difensiva avversaria | SOT/tiri concessi avversario |
| `home_away_split_component` | Split casa/trasferta | Performance casa vs trasferta |
| `recent_form_component` | Forma recente | Ultime 5 partite |
| `xg_chance_quality_component` | Qualità occasioni (xG) | `expected_goals` reali |
| `player_layer_component` | Player layer | Top shooters da `player_season_profiles` |

**Strictness:** dati obbligatori mancanti → `prediction_valid = false` (più strict di v2.1).

File: `backend/app/services/predictions_v11/baseline_v1_1_sot_service.py`.

---

## v2.0 — sintesi (lineup impact)

| Campo | Valore |
|-------|--------|
| Slug | `baseline_v2_0_lineup_impact` |
| Base | Predizione v1.1 salvata |
| Fattori SportAPI | `offensive_lineup_factor`, `opponent_defensive_weakness_factor` |
| Fallback | Fattori = 1.0 se SportAPI assente |

Non ha registry micro-variabili proprio: usa output v1.1 + simulazione lineup a 2 fattori.

File: `backend/app/services/predictions_v20/baseline_v2_0_lineup_impact_service.py`, `sportapi/sportapi_lineup_impact_service.py`.

---

## Costanti numeriche v2.1

| Costante | Valore |
|----------|--------|
| `ANCHOR_TEAM_SOT_WEIGHT` | 0.55 |
| `ANCHOR_OPP_SOT_CONCEDED_WEIGHT` | 0.45 |
| `MICRO_NORM_MIN/MAX` | 0.70 / 1.30 |
| `MACRO_INDEX_MIN/MAX` | 0.75 / 1.25 |
| `FINAL_MULTIPLIER_MIN/MAX` | 0.75 / 1.30 |
| `XG_PRUDENT_ADJ_MIN/MAX` | 0.85 / 1.15 |
| `RECENT_FORM_MATCHES` | 5 |
| `TOP_SHOOTERS_COUNT` | 5 |
| `LINEUP_HISTORY_MATCHES` | 12 |
| `LINEUP_HISTORY_MIN_FIXTURES` | 3 |

File: `backend/app/services/predictions_v21/v21_constants.py`.

---

## Riferimenti

- Legenda modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md)
- Catalogo dati: [API_DATA_CATALOG.md](./API_DATA_CATALOG.md)
- Framework analisi: [MATCH_ANALYSIS_FRAMEWORK.md](./MATCH_ANALYSIS_FRAMEWORK.md)
