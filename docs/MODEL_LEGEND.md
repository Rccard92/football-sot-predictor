# Legenda modelli SOT

Documentazione aggiornata dei modelli di previsione SOT. Per il registry feature v2.1 vedi [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md).

> **Nota disallineamento API:** la pagina frontend **Legenda Modello** legge ancora `GET /api/model/legend`, che restituisce formule legacy v0.1–v0.3. **Questo file Markdown è la fonte aggiornata** finché l'endpoint runtime non viene allineato.

## Panoramica versioni

| Slug | Label UI | Visibile in UI | Ruolo |
|------|----------|----------------|-------|
| `baseline_v2_1_weighted_components` | v2.1 SOT Weighted Components | Sì | Engine autonomo sperimentale/attivo |
| `baseline_v2_0_lineup_impact` | v2.0 SOT Lineup Impact | Sì | Baseline stabile di confronto |
| `baseline_v1_1_sot` | v1.1 SOT | No (legacy) | Base interna di v2.0 |
| `baseline_v1_0_sot` | — | No (legacy) | Storico |
| `baseline_v0_4_offensive_core_sot` | — | No (legacy) | Storico |
| `baseline_v0_3_core_sot` | — | No (legacy) | Storico |
| `baseline_v0_2_context_player` | — | No (legacy) | Storico |
| `baseline_v0_2_player_adjusted` | — | No (legacy) | Storico |
| `baseline_v0_1` | — | No (legacy) | Storico |

Definizioni slug: `backend/app/core/constants.py`. Visibilità UI: `frontend/src/lib/modelVersions.ts`, `backend/app/services/sot_model_registry.py`.

---

## Modelli legacy (v0.1 – v1.1)

Modelli storici usati in fasi precedenti del progetto. **Non sono proposti nel selettore UI principale** (`UI_MODEL_VERSION_SLUGS` contiene solo v2.0 e v2.1).

| Versione | Slug | Note |
|----------|------|------|
| v0.1 | `baseline_v0_1` | Baseline iniziale SOT |
| v0.2 context | `baseline_v0_2_context_player` | Contesto + player |
| v0.2 adjusted | `baseline_v0_2_player_adjusted` | Player adjusted |
| v0.3 | `baseline_v0_3_core_sot` | Core SOT |
| v0.4 | `baseline_v0_4_offensive_core_sot` | Offensive core; pipeline legacy Serie A |
| v1.0 | `baseline_v1_0_sot` | v0.4 + termine xG |
| v1.1 | `baseline_v1_1_sot` | 6 componenti additivi (offensiva, difensiva, split, forma, xG, player). **Base computazionale di v2.0** |

Endpoint legacy Serie A (`/api/predictions/sot/serie-a/{season}/...`) restano attivi per compatibilità ma **non vanno usati** nei flussi multi-campionato.

---

## v2.0 SOT Lineup Impact

| Campo | Valore |
|-------|--------|
| Slug | `baseline_v2_0_lineup_impact` |
| Label frontend | v2.0 SOT Lineup Impact |
| Badge | Lineup Impact |
| Ruolo | Baseline stabile di confronto |
| Vincolo | **Non modificare formula/comportamento** salvo richiesta esplicita |

### Architettura

v2.0 **non ricalcola da zero**: moltiplica la predizione v1.1 già salvata per due fattori lineup.

```
expected_sot_v2_0 = base_v1_1_sot × offensive_lineup_factor × opponent_defensive_weakness_factor
```

- **Prerequisito**: predizione `baseline_v1_1_sot` presente in `team_sot_predictions` per la stessa fixture/squadra.
- **Fonte lineup**: SportAPI via `LineupImpactSimulationService` (lineups + missing players).
- **Fallback**: se SportAPI assente → fattori = 1.0 → output = v1.1 (`lineup_status: fallback_v11_only`, `operating_mode: degraded_fallback`).
- **Scope multi-campionato**: stesso `model_version` globale; filtro dataset via `competition_id` su fixture/predizioni.

### SportAPI in v2.0

**Sì, SportAPI entra nel calcolo.** Il servizio legge formazioni e indisponibili e produce:
- `offensive_lineup_factor` (presenza/assenza top shooter, turnover offensivo)
- `opponent_defensive_weakness_factor` (debolezza difensiva avversaria per assenze chiave)

v2.0 **non** verifica il flag `USE_SPORTAPI_LINEUPS_IN_MODEL` (pensato per v1.1).

File: `backend/app/services/predictions_v20/baseline_v2_0_lineup_impact_service.py`.

---

## v2.1 SOT Weighted Components

| Campo | Valore |
|-------|--------|
| Slug | `baseline_v2_1_weighted_components` |
| Label frontend | v2.1 SOT Weighted Components |
| Badge | Weighted Components |
| Ruolo | Engine autonomo sperimentale/attivo |
| Architettura | `weighted_macro_components` — **non è una patch di v2.0** |

### Formula generale

```
expected_sot_v21 = max(0, base_anchor_sot × weighted_macro_multiplier)
```

#### Base anchor

```
base_anchor_sot = 0.55 × team_sot_for + 0.45 × opponent_sot_conceded
```

| Componente | Fonte |
|------------|-------|
| `team_sot_for` | Media SOT fatti dalla squadra (prior fixtures pre-kickoff) |
| `opponent_sot_conceded` | Media SOT concessi dall'avversario |

Se manca un solo componente, si usa quello disponibile (con warning). Se mancano entrambi → `prediction_valid = false`.

#### Weighted macro multiplier

Solo le **9 macroaree predittive** (1–9) entrano nel moltiplicatore. La macro 10 (qualità/sicurezza) **non modifica i SOT**.

Per ogni macroarea predittiva:

```
macro_index = clamp( Σ(normalized_value × micro_weight) / Σ(micro_weight), 0.75, 1.25 )
```

```
weighted_macro_multiplier = clamp( Σ(macro_index × macro_weight) / 100, 0.75, 1.30 )
```

Normalizzazione micro: `ratio = raw_value / baseline` (o inverso se `invert=True`), clamp `[0.70, 1.30]`. Baseline assente → `normalized_value = 1.0` (neutro).

Costanti: `backend/app/services/predictions_v21/v21_constants.py`.

### Macroaree (pesi manifest, somma = 100)

| # | Key | Label | Peso | Predittiva |
|---|-----|-------|------|------------|
| 1 | `offensive_production` | Produzione offensiva composita | 16 | sì |
| 2 | `opponent_defensive_resistance` | Resistenza difensiva avversaria | 14 | sì |
| 3 | `home_away_split` | Split casa/trasferta | 10 | sì |
| 4 | `recent_form` | Forma recente | 15 | sì |
| 5 | `chance_quality` | Qualità occasioni (xG) | 17 | sì |
| 6 | `player_layer` | Player layer | 9 | sì |
| 7 | `lineups` | Lineups / formazioni | 5 | sì |
| 8 | `injuries_unavailable` | Infortuni / indisponibili | 5 | sì |
| 9 | `pace_control` | Ritmo e controllo partita | 5 | sì |
| 10 | `model_quality_controls` | Controlli qualità / sicurezza | 4 | **no** (solo audit/confidence) |

Dettaglio micro-variabili: [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md).

### xG in v2.1

- Fonte: colonna `fixture_team_stats.expected_goals` (fallback `raw_json` se colonna assente).
- **No proxy xG.** Se il feed xG non è disponibile nel campionato → macro `chance_quality` neutralizzata (`feed_unavailable`), warning esplicito.
- Anti-leakage: solo fixture finite prima del kickoff target.

### SportAPI in v2.1

Integrato come micro-variabili nelle macro `player_layer`, `lineups`, `injuries_unavailable`. Fonte: `build_sportapi_lineups_audit()`. Modalità profili: `lineup_and_profiles`, `fallback_historical_profiles`, `not_available`.

### Stati output v2.1

| Campo | Valori | Significato |
|-------|--------|-------------|
| `engine_status` | `ready`, `partial`, `manifest_invalid` | `partial` se `expected_sot is None` o `formula_quality_status == insufficient_data` |
| `prediction_valid` / `valid` | boolean | `expected_sot is not None` |
| `formula_quality_status` | `ok`, `partial`, `insufficient_data` | Coverage ≥75% e missing=0 → ok; ≥40% → partial |
| `confidence_score` | 0–100 | Da quality summary: coverage − penalità missing/fallback/leakage |
| `data_leakage_check` | `ok`, `warning_insufficient_prior_sample` | Verifica sample prior pre-kickoff |

File engine: `backend/app/services/predictions_v21/v21_prediction_engine.py`.

---

## Selezione modello in UI

| Concetto | Comportamento |
|----------|---------------|
| **Selected** | Modello scelto dall'utente nel dropdown (`localStorage`: `sot_selected_model_version`). Default frontend: v2.1. |
| **Recommended** | Backend suggerisce v2.1 se manifest valido + coverage prossimo turno; altrimenti v2.0; poi v1.1/v1.0/legacy. |
| **Active** | Modello effettivamente usato per la fixture: `selected` → `active` (status) → `recommended` → selected. |
| **Default API** | Se `model_version` omesso in query → default v2.0 (`resolve_requested_model_version`). |
| **No fallback silenzioso** | Se `model_version` esplicita e prediction assente → payload `missing_prediction`, non un altro modello. |

Audit/spiegazione: dropdown limitato a v2.0 e v2.1 (`MODEL_OPTIONS_AUDIT`).

### Raccomandazione backend

Ordine per prossimo turno (`resolve_recommended_model_version_for_next_round`):
1. v2.1 se manifest valido + predizioni complete sul turno
2. v2.0 se predizioni complete + lineups SportAPI
3. null (non pronto)

Ordine upcoming generale (`resolve_recommended_model_version`):
1. v2.1 → 2. v2.0 → 3. v1.1 → 4. v1.0 → 5. legacy

---

## Compatibilità multi-campionato

- Stesso slug `model_version` per tutti i campionati.
- Scope operativo via `competition_id` su `fixtures`, `fixture_team_stats`, `team_sot_predictions`, `player_season_profiles`, tabelle SportAPI.
- Ogni route competition-scoped valida che la fixture appartenga alla competition richiesta.
- Guardrail: refresh next-round interrotto se `fixture.competition_id` mancante o diverso.

---

## Confronto v2.0 vs v2.1

| Aspetto | v2.0 | v2.1 |
|---------|------|------|
| Base | Moltiplica v1.1 | Engine autonomo (anchor 55/45) |
| Lineup | 2 fattori globali SportAPI | Micro-variabili in 3 macroaree |
| xG | Tramite v1.1 | Macro `chance_quality` diretta |
| Granularità | Bassa (2 moltiplicatori) | Alta (9 macro × N micro) |
| Modificabilità | Frozen | Sperimentale attivo |
| UI | Baseline stabile | Modello principale da confrontare |

Endpoint confronto: `GET /api/competitions/{competition_id}/next-round/model-comparison?base_model=baseline_v2_0_lineup_impact&compare_model=baseline_v2_1_weighted_components`.

---

## Riferimenti

- Registry feature: [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md)
- Pipeline admin: [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md)
- Framework analisi: [MATCH_ANALYSIS_FRAMEWORK.md](./MATCH_ANALYSIS_FRAMEWORK.md)
- Contesto progetto: [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
