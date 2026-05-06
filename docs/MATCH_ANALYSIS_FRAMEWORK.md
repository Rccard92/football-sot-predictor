# Match Analysis Framework (framework_v0_1)

Questo documento definisce un **framework chiaro e consultabile** delle variabili che il sistema deve valutare per analizzare una partita di calcio **prima** di generare una previsione per mercati betting.

## Pipeline di lavoro (alto livello)

PARTITA  
↓  
Raccolta variabili  
↓  
Valutazione qualità dato  
↓  
Calcolo base statistico  
↓  
Correzioni giocatori / contesto / motivazioni  
↓  
Output previsione  
↓  
Decisione: giocabile / prudente / no bet

### Nota importante
- Questo framework **non** modifica in alcun modo le formule attuali. È una struttura documentale e consultativa.
- I **pesi** qui sotto sono **teorici iniziali** (statici) e su scala **0–100**.

## Scala pesi teorici (0–100)
- **90–100** = molto alta
- **70–89** = alta
- **40–69** = media
- **10–39** = bassa
- **0** = non applicata

## Stato implementazione (per variabile)
- **implementata**
- **parzialmente implementata**
- **solo debug**
- **da implementare**

## Mercati supportati (codici)
- `tiri_in_porta`
- `tiri_totali`
- `corner`
- `cartellini`
- `falli`
- `goal_over_under`

---

## Aree e variabili

Per ogni area, la tabella elenca le variabili che il modello può considerare.  
Colonne: **variabile**, **descrizione**, **mercati**, **peso**, **fonte dati possibile**, **stato**, **applicata ora**, **note/limiti**.

> **Applicata ora** significa: applicata al modello attuale in produzione (oggi: SOT con baseline storica + player adjustment v0.2). Non implica che sia “definitiva”.

### 1) Dati base partita

Variabili strutturali: servono a collegare e contestualizzare tutto il resto (non sempre entrano nella formula).

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| squadra_casa | Identità squadra casa | tutti | 100 | fixture API/DB | implementata | sì | Chiave primaria per join dati |
| squadra_trasferta | Identità squadra ospite | tutti | 100 | fixture API/DB | implementata | sì | Chiave primaria per join dati |
| data_orario | Kickoff datetime | tutti | 80 | fixture API/DB | implementata | sì | Base per freshness/contesto |
| round | Giornata/turno | tutti | 70 | fixture API/DB | implementata | sì | Utile per late-season logic |
| stadio | Stadio (se disponibile) | tutti | 20 | fixture API | da implementare | no | Non sempre stabile/affidabile |
| competizione | Lega/competizione | tutti | 40 | league/season API/DB | implementata | sì | Serve per baseline/medie lega |
| stato_partita | scheduled/live/finished | tutti | 60 | fixture API/DB | implementata | sì | Filtri e validazioni |
| classifica_attuale | Posizione/punti correnti | tutti | 60 | standings API/DB | implementata | sì | **Applicata al layer match_context/rischio** (non modifica direttamente expected_sot) |
| fase_stagione | inizio/metà/fine stagione | tutti | 60 | round + regole contesto | implementata | sì | **Applicata al layer match_context/rischio** (non modifica direttamente expected_sot) |
| tempo_al_kickoff | Ore/giorni dal kickoff | tutti | 30 | now() + kickoff | implementata | sì | Serve per distinguere pre-lineup vs official |

### 2) Produzione offensiva squadra

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| avg_sot_for | Media tiri in porta fatti | tiri_in_porta, goal_over_under | 95 | team stats pre-match | implementata | sì | Core per SOT baseline |
| avg_shots_for | Media tiri totali fatti | tiri_totali, goal_over_under | 85 | team stats | da implementare | no | Struttura pronta per futuro |
| avg_box_shots_for | Media tiri dentro area | tiri_totali, goal_over_under | 70 | team stats | da implementare | no | Dipende dalla granularità API |
| avg_outbox_shots_for | Media tiri fuori area | tiri_totali | 55 | team stats | da implementare | no | Utile per stile “tira da fuori” |
| avg_goals_for | Media goal fatti | goal_over_under | 80 | team stats | da implementare | no | Separato da conversion rate |
| conv_shots_to_sot | Conversione tiri totali → SOT | tiri_in_porta, tiri_totali | 65 | derived | da implementare | no | Richiede tiri totali |
| conv_sot_to_goals | Conversione SOT → goal | goal_over_under | 65 | derived | da implementare | no | Attenzione a sample/varianza |
| xg_for | xG prodotto (se disponibile) | goal_over_under, tiri | 70 | advanced stats provider | da implementare | no | Non sempre disponibile |
| big_chances_created | Big chances create | goal_over_under | 60 | advanced stats provider | da implementare | no | Alta dipendenza provider |
| avg_possession | Possesso medio | tiri_totali, corner | 45 | fixture/team stats | da implementare | no | Poco diretto sui SOT |
| key_passes | Passaggi chiave | tiri_totali, goal_over_under | 55 | player/team stats | da implementare | no | Richiede player aggregation |
| crosses_for | Cross effettuati | corner, tiri_totali | 55 | team/player stats | da implementare | no | Corner correlate ma non identiche |
| touches_box_for | Tocchi in area avversaria | tiri_totali, goal_over_under | 55 | advanced stats | da implementare | no | Non sempre disponibile |
| corners_for | Corner offensivi prodotti | corner | 80 | fixture/team stats | da implementare | no | Mercato corner dedicato |
| offensive_trend | Trend offensivo (↑/↓) | tutti | 60 | rolling windows | parzialmente implementata | parziale | Legato a “forma recente” |
| vs_strong_weak_offense | Produzione vs forti/deboli | tutti | 45 | standings tiers | da implementare | no | Richiede definizione “forti/deboli” |

### 3) Resistenza difensiva avversaria

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| avg_sot_conceded | Media SOT concessi | tiri_in_porta, goal_over_under | 95 | team stats pre-match | implementata | sì | Core per SOT baseline (lato avversario) |
| avg_shots_conceded | Media tiri concessi | tiri_totali, goal_over_under | 85 | team stats | da implementare | no | Futuro mercato tiri totali |
| box_shots_conceded | Tiri dentro area concessi | goal_over_under, tiri_totali | 70 | team stats | da implementare | no | |
| outbox_shots_conceded | Tiri fuori area concessi | tiri_totali | 55 | team stats | da implementare | no | |
| goals_conceded | Goal concessi | goal_over_under | 80 | team stats | da implementare | no | |
| xga | xGA (se disponibile) | goal_over_under | 70 | advanced stats | da implementare | no | |
| big_chances_conceded | Big chances concesse | goal_over_under | 60 | advanced stats | da implementare | no | |
| corners_conceded | Corner concessi | corner | 75 | team stats | da implementare | no | |
| crosses_conceded | Cross concessi | corner | 50 | team stats | da implementare | no | |
| recent_clean_sheets | Clean sheet recenti | goal_over_under | 40 | derived | da implementare | no | Segnale rumoroso |
| pressure_faced | Pressione subita | tiri_totali, corner | 40 | advanced stats | da implementare | no | |
| defensive_errors | Errori difensivi | goal_over_under | 45 | events/advanced | da implementare | no | Definizione difficile |
| vs_similar_defense | Concessioni vs simili | tutti | 45 | clustering/tiers | da implementare | no | Richiede metrica similarità |
| defensive_trend | Trend difensivo recente | tutti | 60 | rolling windows | parzialmente implementata | parziale | Legato a “forma recente” |

### 4) Rendimento casa / trasferta

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| home_avg_sot_for | SOT fatti in casa | tiri_in_porta | 85 | home/away splits | implementata | sì | Core SOT baseline |
| away_avg_sot_for | SOT fatti in trasferta | tiri_in_porta | 85 | home/away splits | implementata | sì | Core SOT baseline |
| home_avg_sot_conceded | SOT concessi in casa | tiri_in_porta | 75 | home/away splits | implementata | sì | Core SOT baseline |
| away_avg_sot_conceded | SOT concessi in trasferta | tiri_in_porta | 75 | home/away splits | implementata | sì | Core SOT baseline |
| home_away_shots_splits | Split tiri totali casa/fuori | tiri_totali | 70 | home/away splits | da implementare | no | |
| goals_splits | Goal fatti/subiti casa/fuori | goal_over_under | 65 | home/away splits | da implementare | no | |
| corners_splits | Corner prodotti/concessi casa/fuori | corner | 65 | home/away splits | da implementare | no | |
| cards_splits | Cartellini casa/fuori | cartellini | 55 | ref stats | da implementare | no | |
| intensity_home_away | Intensità casa/fuori | falli, cartellini | 45 | derived | da implementare | no | Definizione variabile |
| home_away_delta | Differenza rendimento casa/fuori | tutti | 60 | derived | parzialmente implementata | parziale | Dipende dai mercati disponibili |

### 5) Forma recente

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| last5_overall | Ultime 5 partite (set) | tutti | 70 | fixture history | implementata | sì | Base per rolling averages SOT |
| last10_overall | Ultime 10 partite (set) | tutti | 55 | fixture history | da implementare | no | Possibile estensione |
| last5_home_for_home_team | Ultime 5 in casa (team casa) | tutti | 55 | fixture history | da implementare | no | |
| last5_away_for_away_team | Ultime 5 in trasferta (team ospite) | tutti | 55 | fixture history | da implementare | no | |
| last5_sot_for | SOT fatti ultime 5 | tiri_in_porta | 80 | team stats rolling | implementata | sì | Core SOT baseline |
| last5_shots_for | Tiri totali ultime 5 | tiri_totali | 75 | team stats rolling | da implementare | no | |
| last5_sot_conceded | SOT concessi ultime 5 | tiri_in_porta | 75 | team stats rolling | implementata | sì | Core SOT baseline |
| last5_goals_for | Goal fatti ultime 5 | goal_over_under | 70 | rolling | da implementare | no | |
| last5_goals_conceded | Goal subiti ultime 5 | goal_over_under | 70 | rolling | da implementare | no | |
| last5_corners | Corner ultime 5 | corner | 65 | rolling | da implementare | no | |
| last5_cards | Cartellini ultime 5 | cartellini | 55 | rolling | da implementare | no | |
| momentum_trend | Trend positivo/negativo | tutti | 60 | derived | parzialmente implementata | parziale | Serve definizione unificata |
| form_vs_similar | Forma vs squadre simili | tutti | 45 | tiers | da implementare | no | |
| strength_of_schedule | Difficoltà avversari recenti | tutti | 55 | standings tiers | da implementare | no | Necessita ranking/tiers |

### 6) Player impact

Senza formazioni ufficiali, il player impact misura **forza della rosa** (non “chi giocherà”).

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| top_shooters_sot_per90 | Top player per SOT/90 | tiri_in_porta, goal_over_under | 80 | player profiles | implementata | sì | Applicata nel live SOT v0.2 player adjusted |
| top_shooters_shots_per90 | Top player per tiri/90 | tiri_totali, goal_over_under | 70 | player profiles | da implementare | no | Richiede statistiche tiri totali |
| player_team_sot_share | Quota SOT squadra per player | tiri_in_porta | 70 | player profiles | implementata | sì | Parte del profilo/impulso |
| player_team_shots_share | Quota tiri squadra per player | tiri_totali | 60 | player profiles | da implementare | no | |
| top_scorer | Capocannoniere squadra | goal_over_under | 50 | player stats | da implementare | no | |
| penalty_taker | Rigorista | goal_over_under | 45 | lineup/news | da implementare | no | Molto rumoroso senza fonte affidabile |
| main_creator | Assistman/creatore | goal_over_under, corner | 45 | key passes | da implementare | no | |
| key_passes_per90 | Passaggi chiave/90 | goal_over_under, tiri_totali | 45 | player stats | da implementare | no | |
| crosses_per90 | Cross/90 | corner | 45 | player stats | da implementare | no | |
| minutes_played | Minuti giocati | tutti | 40 | player stats | implementata | sì | Usata per reliability |
| starts | Presenze da titolare | tutti | 35 | player stats | implementata | sì | Usata per reliability |
| player_form | Stato di forma giocatore | tutti | 40 | rolling player stats | da implementare | no | |
| sample_reliability | Affidabilità campione | tutti | 60 | derived | implementata | sì | Parte del profilo SOT |
| offensive_dependency | Dipendenza da 1–2 player | tutti | 60 | derived | da implementare | no | Richiede aggregazione team shares |
| bench_depth | Panchina offensiva | tutti | 35 | roster/player stats | da implementare | no | |
| important_returns | Rientri importanti | tutti | 40 | availability/news | da implementare | no | |

### 7) Assenti / infortunati / squalificati / indisponibili

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| injuries_list | Lista infortunati | tutti | 75 | injuries API | solo debug | no | Se dati non affidabili → warning |
| suspensions_list | Lista squalificati | tutti | 75 | injuries/discipline API | da implementare | no | |
| absences_list | Indisponibili generici | tutti | 65 | provider | da implementare | no | |
| doubtful_players | Diffidati/ballottaggi | tutti | 35 | news | da implementare | no | Estremamente rumoroso |
| missing_top_scorer | Assenza top scorer | goal_over_under | 80 | lineup/news | da implementare | no | |
| missing_top_shooter | Assenza top shooter | tiri | 80 | lineup/news | da implementare | no | |
| missing_penalty_taker | Assenza rigorista | goal_over_under | 55 | news | da implementare | no | |
| missing_creator | Assenza creatore principale | goal_over_under, corner | 55 | news | da implementare | no | |
| missing_playmaker | Assenza regista | tutti | 45 | news | da implementare | no | |
| missing_key_defender | Assenza difensore chiave | goal_over_under | 60 | news | da implementare | no | |
| missing_goalkeeper | Assenza portiere titolare | goal_over_under | 70 | lineup/news | da implementare | no | |
| missing_winger_crosser | Assenza esterno/crossatore | corner | 55 | news | da implementare | no | |
| absence_duration | Durata assenza | tutti | 40 | injuries API | da implementare | no | |
| absence_is_new | Assenza nuova vs assorbita | tutti | 65 | compare last matches | da implementare | no | Critico: “assorbita” spesso già nei dati |
| player_weight_in_team | Peso assente nella squadra | tutti | 70 | impact scores | da implementare | no | Collegare a player profiles |
| probable_replacement | Probabile sostituto | tutti | 35 | lineup/news | da implementare | no | |
| starter_vs_backup_gap | Differenza titolare/sostituto | tutti | 60 | roster metrics | da implementare | no | |

### 8) Formazioni probabili e ufficiali

Il modello deve supportare due modalità: **pre-lineup prediction** e **official-lineup prediction**.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| probable_lineup | Formazione probabile | tutti | 60 | provider lineups/news | da implementare | no | Peso medio: incertezza elevata |
| official_lineup | Formazione ufficiale | tutti | 95 | official lineups feed | da implementare | no | Peso molto alto, quando disponibile |
| formation | Modulo tattico | tutti | 55 | lineup data | da implementare | no | |
| formation_change | Cambio modulo | tutti | 45 | derived | da implementare | no | |
| attackers_count | Numero attaccanti | tiri, goal, corner | 60 | lineup data | da implementare | no | |
| wide_players | Presenza esterni offensivi | corner, tiri | 55 | lineup data | da implementare | no | |
| trequartista | Presenza trequartista | goal_over_under | 40 | lineup data | da implementare | no | |
| rotations | Turnover | tutti | 70 | schedule/news | solo debug | no | Collegato a calendario/motivazione |
| out_of_position | Giocatori fuori ruolo | tutti | 45 | lineup + roles | da implementare | no | |
| starter_quality_gap | Qualità titolari vs sostituti | tutti | 65 | roster ratings | da implementare | no | |
| market_compatibility | Compatibilità modulo vs mercato | tutti | 40 | heuristics | da implementare | no | |
| offensive_defensive_lineup | Lineup più off/def | tutti | 55 | derived | da implementare | no | |
| lineup_stability | Stabilità lineup | tutti | 45 | historical lineups | da implementare | no | |

### 9) Scontri diretti / H2H

Segnale di contesto: peso **basso/medio** (rose/allenatori cambiano).

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| h2h_last5 | Ultimi 5 H2H | tutti | 35 | h2h API/DB | solo debug | no | Campioni piccoli = rumorosi |
| h2h_last10 | Ultimi 10 H2H | tutti | 30 | h2h API/DB | da implementare | no | |
| h2h_same_stadium | H2H stesso stadio | tutti | 25 | h2h API | da implementare | no | |
| h2h_avg_goals | Goal medi H2H | goal_over_under | 30 | h2h API | solo debug | no | |
| h2h_avg_sot | SOT medi H2H | tiri_in_porta | 30 | DB team stats | solo debug | no | Solo se copertura DB |
| h2h_avg_shots | Tiri medi H2H | tiri_totali | 25 | DB team stats | da implementare | no | |
| h2h_avg_corners | Corner medi H2H | corner | 25 | h2h stats | da implementare | no | |
| h2h_avg_cards | Cartellini medi H2H | cartellini | 25 | h2h stats | da implementare | no | |
| h2h_wdl | W/D/L H2H | tutti | 20 | h2h API | solo debug | no | |
| tactical_recurrence | Ricorrenza tattica | tutti | 15 | heuristics | da implementare | no | |
| coaches_same | Allenatori uguali/diversi | tutti | 15 | lineup/coaches | da implementare | no | |
| squads_changed | Rose cambiate | tutti | 15 | roster history | da implementare | no | |

### 10) Calendario / fatica / coppe

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| rest_days | Giorni di riposo | tutti | 55 | fixture history | da implementare | no | |
| midweek_match | Turno infrasettimanale | tutti | 45 | schedule | da implementare | no | |
| congested_schedule | Sequenza ravvicinata | tutti | 65 | derived | da implementare | no | |
| european_cups | Coppe europee giocate | tutti | 60 | schedule | da implementare | no | |
| national_cups | Coppe nazionali giocate | tutti | 45 | schedule | da implementare | no | |
| long_travel | Viaggio lungo | tutti | 35 | geo/timezones | da implementare | no | |
| extra_time_prev | Extra time/rigori prima | tutti | 35 | match events | da implementare | no | |
| top_players_recent_minutes | Minuti recenti top player | tutti | 55 | player stats | da implementare | no | |
| turnover_risk | Rischio turnover | tutti | 70 | heuristics | solo debug | no | Può restare warning iniziale |
| calendar_intensity | Intensità calendario | tutti | 60 | derived | da implementare | no | |

### 11) Motivazione / classifica / valore reale partita

Il modello deve saper dire: **“previsione statisticamente buona ma contesto pericoloso”**.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| title_race | Lotta scudetto | tutti | 65 | standings + rules | solo debug | no | |
| ucl_race | Lotta Champions | tutti | 65 | standings + rules | solo debug | no | |
| europa_race | Lotta Europa | tutti | 55 | standings + rules | solo debug | no | |
| relegation_race | Lotta salvezza | tutti | 65 | standings + rules | solo debug | no | |
| already_champion | Già campione | tutti | 75 | standings | da implementare | no | |
| already_relegated | Già retrocessa | tutti | 75 | standings | da implementare | no | |
| already_safe | Già salva | tutti | 60 | standings | da implementare | no | |
| no_objectives | Senza obiettivi | tutti | 60 | standings | da implementare | no | |
| late_season | Ultime giornate | tutti | 70 | round | solo debug | no | |
| derby_rivalry | Derby/rivalità | tutti | 55 | static mapping | da implementare | no | |
| knockout_match | Dentro/fuori | tutti | 70 | competition format | da implementare | no | |
| points_gap | Distanza punti obiettivo | tutti | 55 | standings | solo debug | no | |
| must_win | Necessità di vincere | tutti | 60 | heuristics | da implementare | no | |
| can_draw | Possibilità accontentarsi | tutti | 45 | heuristics | da implementare | no | |
| environment_pressure | Pressione ambiente | tutti | 35 | news/sentiment | da implementare | no | |
| complacency_risk | Rischio appagamento | tutti | 45 | heuristics | da implementare | no | |
| turnover_due_to_objective | Turnover da obiettivo | tutti | 55 | heuristics | da implementare | no | |

### 12) Quote bookmaker e movimento linea

Nota: il modello stima il numero; il mercato serve per value e decisione finale.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| bookmaker | Bookmaker | tutti | 30 | odds provider | da implementare | no | |
| market | Mercato | tutti | 40 | odds provider | da implementare | no | |
| opening_line | Linea apertura | tutti | 70 | odds provider | da implementare | no | |
| opening_odds | Quota apertura | tutti | 70 | odds provider | da implementare | no | |
| current_line | Linea attuale | tutti | 80 | odds provider | da implementare | no | |
| current_odds | Quota attuale | tutti | 80 | odds provider | da implementare | no | |
| odds_movement | Movimento quota | tutti | 75 | derived | da implementare | no | |
| line_movement | Movimento linea | tutti | 75 | derived | da implementare | no | |
| cross_book_diff | Differenze tra bookmaker | tutti | 55 | multi-book | da implementare | no | |
| clv | Closing line value | tutti | 55 | post-match odds | da implementare | no | |
| odds_min_max | Quota min/max | tutti | 40 | odds provider | da implementare | no | |
| implied_prob | Probabilità implicita | tutti | 45 | derived | da implementare | no | |
| bookmaker_margin | Margine bookmaker | tutti | 35 | derived | da implementare | no | |
| theoretical_value | Value teorico (modello vs quota) | tutti | 90 | derived | da implementare | no | Non entra per forza nella stima “pura” |
| market_confidence | Market confidence | tutti | 55 | derived | da implementare | no | |
| late_moves | Movimenti vicino al kickoff | tutti | 65 | time-series | da implementare | no | |
| odds_drop_too_much | Quota scende troppo | tutti | 60 | heuristics | da implementare | no | |
| odds_rise_vs_model | Quota sale contro modello | tutti | 60 | heuristics | da implementare | no | |

### 13) Arbitro

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| ref_yellow_avg | Gialli medi | cartellini | 90 | referee stats | da implementare | no | |
| ref_red_avg | Rossi medi | cartellini | 70 | referee stats | da implementare | no | |
| ref_fouls_avg | Falli fischiati | falli | 90 | referee stats | da implementare | no | |
| ref_penalties | Rigori assegnati | goal_over_under | 55 | referee stats | da implementare | no | |
| ref_style | Permissivo/severo | falli, cartellini | 80 | derived | da implementare | no | |
| ref_history_with_teams | Storico con squadre | cartellini, falli | 45 | referee+teams | da implementare | no | |
| ref_big_match_behavior | Big match behavior | cartellini | 45 | derived | da implementare | no | |
| ref_game_flow | Spezzetta/lascia giocare | tiri, corner, falli | 35 | derived | da implementare | no | Effetto indiretto |
| ref_added_time | Media recupero | tiri, goal | 20 | referee stats | da implementare | no | Effetto minimo |
| ref_season_phase_diff | Differenza per fase stagione | cartellini | 25 | derived | da implementare | no | |

### 14) Stile tattico / matchup

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| possession_team | Squadra da possesso | tiri_totali, corner | 50 | team style metrics | da implementare | no | |
| vertical_team | Squadra verticale | tiri_in_porta, goal | 50 | style metrics | da implementare | no | |
| crossing_team | Squadra da cross | corner, tiri | 60 | crosses | da implementare | no | |
| long_shot_team | Tira da fuori | tiri_totali | 45 | shot zones | da implementare | no | |
| box_entry_team | Entra in area | goal_over_under | 55 | touches box | da implementare | no | |
| wide_attack | Attacco sulle fasce | corner | 55 | style metrics | da implementare | no | |
| low_block_defense | Difesa bassa | tiri_totali, corner | 50 | style metrics | da implementare | no | |
| high_press | Pressa alta | falli, cartellini, tiri | 45 | pressure metrics | da implementare | no | |
| concedes_space | Concede campo | tiri_in_porta | 45 | style metrics | da implementare | no | |
| flank_matchups | Matchup fasce | corner, tiri | 35 | player roles | da implementare | no | |
| key_duels | Duelli chiave | falli, cartellini | 30 | player matchups | da implementare | no | |
| formation_vs_formation | Modulo vs modulo | tutti | 35 | lineup + heuristics | da implementare | no | |
| expected_pace | Ritmo previsto | tiri, corner, falli | 55 | style + context | da implementare | no | |
| expected_game_state | Game state atteso | tiri, corner, goal | 55 | odds/model | da implementare | no | |
| comeback_ability | Recupera da svantaggio | goal_over_under | 30 | historical | da implementare | no | |
| shots_when_ahead | Tiri quando in vantaggio | tiri_totali | 40 | game-state splits | da implementare | no | |
| shots_when_behind | Tiri quando in svantaggio | tiri_totali | 45 | game-state splits | da implementare | no | |
| conceded_when_ahead | Concede quando in vantaggio | tiri, corner | 35 | game-state splits | da implementare | no | |

### 15) Set pieces / palle inattive

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| set_piece_corners_for | Corner offensivi | corner | 80 | team stats | da implementare | no | |
| set_piece_corners_against | Corner concessi | corner | 75 | team stats | da implementare | no | |
| wide_free_kicks | Punizioni laterali | corner, goal | 35 | events | da implementare | no | |
| deadball_crosses | Cross da fermo | corner, goal | 35 | events | da implementare | no | |
| set_piece_goals | Goal da palla inattiva | goal_over_under | 55 | events | da implementare | no | |
| set_piece_shots | Tiri da palla inattiva | tiri_totali | 45 | events | da implementare | no | |
| penalty_takers | Rigoristi | goal_over_under | 45 | lineup/news | da implementare | no | |
| fouls_near_box | Falli subiti vicino area | falli, goal | 35 | events | da implementare | no | |
| set_piece_defense | Difesa su piazzati | goal_over_under | 45 | events | da implementare | no | |
| avg_team_height | Altezza media squadra | goal_over_under, corner | 25 | roster | da implementare | no | |
| aerial_threats | Colpitori di testa | goal_over_under | 30 | player profiles | da implementare | no | |

### 16) Portieri

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| starting_goalkeeper | Portiere titolare | goal_over_under | 60 | lineup | da implementare | no | |
| goalkeeper_absent | Portiere assente | goal_over_under | 70 | lineup/news | da implementare | no | |
| saves_avg | Parate medie | goal_over_under | 45 | keeper stats | da implementare | no | |
| goals_prevented | Goal evitati (se disponibile) | goal_over_under | 45 | advanced | da implementare | no | |
| sot_vs_goals_ratio | SOT concessi vs goal subiti | goal_over_under | 55 | derived | da implementare | no | |
| keeper_reliability | Affidabilità portiere | goal_over_under | 40 | derived | da implementare | no | |
| clean_sheets | Clean sheet | goal_over_under | 30 | team stats | da implementare | no | |
| keeper_errors | Errori portiere | goal_over_under | 35 | events | da implementare | no | |
| keeper_change | Cambio portiere | goal_over_under | 45 | lineup | da implementare | no | |

### 17) Cambio allenatore / stato tecnico

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| coach_changed | Allenatore cambiato | tutti | 70 | team news | da implementare | no | |
| matches_under_new_coach | Partite con nuovo coach | tutti | 55 | derived | da implementare | no | |
| offense_before_after | Offense prima/dopo | tiri, goal, corner | 60 | rolling | da implementare | no | |
| defense_before_after | Defense prima/dopo | tiri, goal, corner | 60 | rolling | da implementare | no | |
| style_change | Cambio stile di gioco | tutti | 55 | heuristics | da implementare | no | |
| locker_room_stability | Stabilità spogliatoio | no_bet/risk | 35 | news/sentiment | da implementare | no | Rumoroso |
| technical_crisis | Crisi tecnica | tutti | 45 | derived/news | da implementare | no | |

### 18) Sentiment / news / contesto esterno

Inizialmente: **warning qualitativo**, non correzione matematica automatica.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| coach_press_conf | Conferenza stampa coach | no_bet/risk | 25 | news NLP | da implementare | no | Rumoroso |
| injury_news | News infortuni | tutti | 35 | news | da implementare | no | |
| lineup_rumors | Rumor formazione | tutti | 25 | news | da implementare | no | |
| fan_pressure | Pressione tifoseria | no_bet/risk | 20 | sentiment | da implementare | no | |
| club_problems | Problemi societari | no_bet/risk | 25 | news | da implementare | no | |
| media_hype | Clima mediatico | no_bet/risk | 15 | trends | da implementare | no | |
| psychological_event | Evento psicologico recente | no_bet/risk | 20 | news | da implementare | no | |
| cup_elimination | Eliminazione coppa | tutti | 25 | schedule | da implementare | no | |
| trophy_win | Vittoria trofeo | tutti | 20 | schedule | da implementare | no | |
| derby_result | Derby perso/vinto | tutti | 25 | fixture history | da implementare | no | |

### 19) Qualità dati e confidence

Spesso non modifica la stima “pura”, ma modifica **fiducia** e **decisione finale**.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| team_data_completeness | Completezza dati squadra | tutti | 80 | DB coverage | implementata | sì | Influenza qualità/lettura |
| player_stats_completeness | Completezza player stats | tutti | 60 | DB coverage | implementata | sì | |
| lineups_completeness | Completezza lineups | tutti | 60 | DB coverage | da implementare | no | |
| injuries_completeness | Completezza injuries | tutti | 55 | ingestion | da implementare | no | |
| odds_completeness | Completezza odds | tutti | 50 | ingestion | da implementare | no | |
| h2h_completeness | Completezza H2H | tutti | 40 | ingestion | solo debug | no | |
| sample_size | Sample size storico | tutti | 70 | fixture history | implementata | sì | Core quality score |
| matches_count | Numero partite precedenti | tutti | 65 | derived | implementata | sì | |
| fallbacks_used | Fallback usati | tutti | 80 | breakdown flags | implementata | sì | Aumenta prudenza |
| missing_data_flags | Dati mancanti | tutti | 80 | derived | implementata | sì | |
| suspicious_data_flags | Dati sospetti | tutti | 70 | heuristics | implementata | sì | |
| data_freshness | Freschezza dati | tutti | 50 | timestamps | da implementare | no | |
| prediction_confidence | Prediction confidence | tutti | 85 | model output | implementata | sì | Euristico/di lettura |
| model_disagreement | Disaccordo tra modelli/varianti | tutti | 55 | compare versions | da implementare | no | Utile per “prudente” |
| diff_v01_vs_v02 | Differenza v0.1 vs v0.2 | tiri_in_porta | 55 | compare outputs | parzialmente implementata | parziale | In UI esiste confronto |
| backtest_mae | MAE backtest | tutti | 40 | backtest | implementata | sì | Non riga-per-riga |
| backtest_rmse | RMSE backtest | tutti | 40 | backtest | implementata | sì | Non riga-per-riga |

### 20) Regole no bet / risk management

Un buon modello deve sapere quando **evitare**.

| Variabile | Descrizione | Mercati | Peso | Fonte dati possibile | Stato | Applicata ora | Note/limiti |
|---|---|---|---:|---|---|---|---|
| insufficient_data | Dati insufficienti | tutti | 95 | quality layer | da implementare | no | Regola hard |
| lineups_too_uncertain | Formazioni troppo incerte | tutti | 80 | lineup certainty | da implementare | no | |
| key_absences_unconfirmed | Assenze chiave non confermate | tutti | 75 | injuries/news | da implementare | no | |
| high_turnover_risk | Turnover alto | tutti | 70 | schedule/context | solo debug | no | In parte esiste come warning contesto |
| low_or_uncertain_motivation | Motivazione bassa/incerta | tutti | 70 | context | solo debug | no | |
| odds_moved_too_much | Quota troppo scesa | tutti | 70 | odds movement | da implementare | no | |
| line_already_correct | Linea già corretta | tutti | 65 | odds+model | da implementare | no | |
| movement_against_model | Movimento contro modello | tutti | 65 | odds+model | da implementare | no | |
| v01_v02_disagree | v0.1 e v0.2 discordanti | tutti | 60 | compare | parzialmente implementata | parziale | Già leggibile in confronto SOT |
| late_season_danger | Fine stagione pericolosa | tutti | 60 | round+context | solo debug | no | Warning già presente in UI |
| high_volatility_match | Match troppo volatile | tutti | 70 | variance features | da implementare | no | |
| low_edge | Edge basso | tutti | 90 | model vs line | da implementare | no | Dipende odds |
| high_variance | Alta varianza storica | tutti | 60 | variance | da implementare | no | |
| h2h_sample_insufficient | Campione H2H insufficiente | tutti | 45 | h2h | solo debug | no | |
| ref_unpredictable | Arbitro imprevedibile | cartellini, falli | 55 | referee stats | da implementare | no | |
| unquantified_negative_news | News negative non quantificabili | tutti | 50 | sentiment/news | da implementare | no | Warning qualitativo |

---

## Framework per mercato

Non esiste un framework universale: ogni mercato valorizza variabili diverse.

### 1) Framework tiri in porta (`tiri_in_porta`)
- **Variabili principali**: `avg_sot_for`, `avg_sot_conceded`, `home_avg_sot_for`, `away_avg_sot_for`, `last5_sot_for`, `last5_sot_conceded`, `top_shooters_sot_per90`, `player_team_sot_share`.
- **Variabili secondarie**: `offensive_trend`, `defensive_trend`, `expected_pace`, `time_al_kickoff`.
- **Variabili solo warning**: `late_season`, `turnover_risk`, `low_or_uncertain_motivation`, `fallbacks_used`.
- **Variabili meno rilevanti**: `ref_added_time`, `avg_team_height`.

### 2) Framework tiri totali (`tiri_totali`)
- **Variabili principali**: `avg_shots_for`, `avg_shots_conceded`, `avg_possession`, `expected_game_state`, `last5_shots_for`.
- **Variabili secondarie**: `long_shot_team`, `high_press`, `shots_when_ahead`, `shots_when_behind`.
- **Variabili solo warning**: `congested_schedule`, `rotations`, `lineups_too_uncertain`.
- **Variabili meno rilevanti**: `ref_red_avg`.

### 3) Framework corner (`corner`)
- **Variabili principali**: `corners_for`, `corners_conceded`, `crosses_for`, `crossing_team`, `wide_attack`, `expected_pace`.
- **Variabili secondarie**: `set_piece_corners_for`, `set_piece_corners_against`, `wide_players`.
- **Variabili solo warning**: assenza di `official_lineup`, `injury_news` sugli esterni.
- **Variabili meno rilevanti**: `h2h_wdl`.

### 4) Framework cartellini (`cartellini`)
- **Variabili principali**: `ref_yellow_avg`, `ref_fouls_avg`, `derby_rivalry`, `relegation_race`, `high_press`.
- **Variabili secondarie**: `h2h_last5`, `environment_pressure`, `expected_pace`.
- **Variabili solo warning**: layer `sentiment/news` non affidabile.
- **Variabili meno rilevanti**: `avg_possession`.

### 5) Framework falli (`falli`)
- **Variabili principali**: `ref_fouls_avg`, `high_press`, `key_duels`, `expected_pace`.
- **Variabili secondarie**: `environment_pressure`, `derby_rivalry`.
- **Variabili solo warning**: `lineups_too_uncertain`.
- **Variabili meno rilevanti**: `set_piece_goals`.

### 6) Framework goal / over-under (`goal_over_under`)
- **Variabili principali**: `avg_goals_for`, `goals_conceded`, `conv_sot_to_goals`, `xg_for`, `xga`, `starting_goalkeeper`.
- **Variabili secondarie**: `top_scorer`, `missing_goalkeeper`, `expected_game_state`.
- **Variabili solo warning**: `late_season_danger`, `unquantified_negative_news`.
- **Variabili meno rilevanti**: `h2h_wdl` (da usare con cautela).

---

## Futuro: pesi modificabili da frontend

In questa versione i pesi sono **statici e documentali**. In una prossima fase sarà possibile:
- modificare i pesi dall’interfaccia,
- salvare una configurazione modello,
- ricalcolare le previsioni.

---

## Audit variabili partita

Per rendere il modello **verificabile** e ridurre ambiguità, esiste un audit che mostra come il sistema compila le variabili per una singola fixture.

## Scheda Analisi Partita (UI) / Audit Variabili

La pagina frontend “Audit Variabili” è stata riprogettata come **Scheda Analisi Partita**, con due obiettivi:

- rendere la lettura **intuitiva e compatta** (output, driver, livelli)
- mantenere la trasparenza completa, spostando i dettagli in un pannello **debug** chiuso di default

### Struttura UI
- **Header/controlli**: selezione fixture, mercato (Tiri in porta), modalità `pre_match` / `post_match`, link al Framework Analisi.
- **Hero partita**: match card compatta con squadre, kickoff, round, status, badge “No data leakage” (pre‑match).
- **Output previsione**: numeri principali v0.1 e v0.2 player adjusted (se disponibili) + differenze.
- **Driver principali**: sintesi interpretativa generata lato frontend usando variabili core (es. trend last5 vs stagione, player impact).
- **Framework per livelli**: variabili organizzate per livelli (Core statistico, Player, …). I layer non auditati sono mostrati come **roadmap**.
- **Audit tecnico completo**: payload raw, meta e dettagli (chiuso di default).

### Regola “calcolo completo” vs “sample rows”
Per evitare ambiguità:

- **`calculation.meta.matches_count`**: numero reale di partite usate nel calcolo.
- **`sample_rows`**: solo un **campione** (tipicamente ultime 10) per controllo manuale.
- La UI deve dichiarare sempre che il campione mostrato **non** coincide necessariamente con il dataset di calcolo.

### Variabile “disponibile” vs variabile “applicata”
Per evitare confusione nella lettura:

- **Disponibile**: la variabile è calcolabile/auditabile (può esistere nel payload) ma **non entra** nel modello attivo.
- **Applicata al calcolo**: la variabile (o una **componente aggregata**) entra **direttamente** nella formula del **modello attivo**.

### Variabile “applicata al contesto” (match_context) vs “applicata al calcolo”
Alcune variabili non modificano il numero \(expected\_sot\), ma **cambiano la lettura e il rischio**:

- **Applicata al contesto**: incide su `match_context`, `motivation_level`, `turnover_risk`, `late_season_risk`, `risk_flags` e `confidence_adjustment` (warning/prudenza/decisione), **senza** modificare la formula numerica SOT.
- Esempi attuali: **Classifica attuale** e **Fase della stagione**.

### Componente applicata vs variabile di supporto
Nella UI distinguiamo:

- **Componenti applicate** (vista principale): blocchi aggregati che hanno un **peso** esplicito nella formula del modello attivo (es. v0.3: Core SOT, Volume tiri, Precisione, Forma recente, Goal context).
- **Variabili di supporto** (solo dettaglio tecnico / audit completo): input e sotto-variabili usate per costruire una componente (es. medie, split, ratio), ma che non devono diventare 20 card “Disponibile” nella vista principale.

### Regola UI: vista principale vs audit completo
- **Vista principale**: mostra **solo** ciò che impatta il **modello attivo**.
- **Audit completo (chiuso di default)**: mostra anche dati disponibili **non usati**, variabili debug, roadmap e dettagli tecnici.

### Obiettivo
- verificare che le variabili siano calcolate con i **dati corretti**
- vedere **formula**, **fonte**, **partite considerate** e note anti‑leakage
- confrontare pre‑match vs post‑match (solo audit)

### Modalità
- **pre_match**: usa solo fixture concluse con `kickoff_at` **precedente** alla fixture analizzata (no data leakage).
- **post_match**: può includere dati successivi **solo** per verifica; deve essere chiaramente marcata come audit post‑match.

### Regola no data leakage (pre_match)
Per ogni variabile pre‑match si includono solo partite:
- con `status_short` in `FT`, `AET`, `PEN`
- con `kickoff_at < current_fixture.kickoff_at`

### Esempi di calcolo

**Media stagionale tiri in porta fatti (team)**
- Fonte: `fixture_team_stats.shots_on_target`
- Formula: `sum(shots_on_target) / matches_count`
- Sample rows: ultime 10 fixture considerate + conteggio totale

**Ultime 5 tiri in porta fatti (team)**
- Fonte: `fixture_team_stats.shots_on_target`
- Regola: ultime 5 fixture concluse precedenti ordinate per kickoff
- Formula: `mean(shots_on_target over last5)`

### Endpoint audit
- `GET /api/match-analysis/fixture/{fixture_id}/variables?market=shots_on_target&mode=pre_match`
