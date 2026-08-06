# Intensità Goal Avanzata v5 — Monitoring & consolidamento

**Stato operativo:** Supporto ufficiale (`official_support`)  
**Modulo:** `cecchino_goal_intensity_v5_official_support_v1`  
**Bundle ufficiale (post-freeze):** `cecchino_goal_intensity_v5_official_support_bundle_v1`  
**Bundle legacy preview:** `cecchino_goal_intensity_v5_preview_v1_1` (superseded al cutover)  
**Bundle candidate v2.1:** `cecchino_goal_intensity_v5_candidate_bundle_v2_1` (frozen, invariato)  
**Ruolo:** `contextual_support_only` — Signals **bloccati**

## Decisione finale (Phase 2D)

Benchmark esterno Job ID **2** (full, `external_validation`) sul bundle v2.1:

- Indice raw operativo unico: `GI_A_STRICT_CORE`
- Teste: total / ge3 / BTTS ← calibrazione `GI_E_PRIMARY_RECALIBRATED`; ge2 ← `GI_A_STRICT_CORE`
- Nessun blending / refit; GI_B / GI_F / MT1 / diagnostic archiviati dal runtime
- V4 = fallback atomico se feature V5 incomplete (`fallback_reason=official_v5_features_incomplete`)
- Cutover: `strict_after_official_freeze` — nessun backfill; snapshot legacy invariati

## Architettura

| Layer | Modulo | Ruolo |
|-------|--------|-------|
| Finalization | `cecchino_goal_intensity_v5_official_support.py` | Dry-run/freeze atomico, scoring ufficiale, market adapter |
| Motore | `cecchino_goal_intensity_v5_preview.py` | Preview v1.1 + `get_active_bundle` / score dispatch |
| Facade | `cecchino_goal_intensity_v5.py` | Payload Today ufficiale + fallback V4 |
| Audit | `cecchino_goal_intensity_v5_explanations.py` | Official heads / legacy candidati read-only |
| v4 fallback | `cecchino_goal_intensity_analysis.py` | Solo se V5 incompleta; non concorrente in UI |

## Today

Campo canonico: `goal_intensity_v5` con `source` ∈ `{v5_official, v4_fallback, v5_legacy_preview}`.  
Una sola card (indice + Over/Under + Gol/No Gol). Badge «Supporto ufficiale» / «Fallback V4» / «Archivio preview».  
Non collegato ai Segnali.

## API finalization

- `GET /api/cecchino/module-monitoring/goal-intensity-v5/finalization?benchmark_job_id=2&dry_run=true`
- `POST /api/admin/cecchino/module-monitoring/goal-intensity-v5/finalization/freeze`  
  Body: `{ "benchmark_job_id": 2, "dry_run": false, "confirm": "FREEZE_GOAL_INTENSITY_V5_OFFICIAL_SUPPORT_V1" }`

**Freeze produzione:** manuale post-deploy dopo dry-run OK. Non eseguito in sviluppo.

## Monitoring UI

Tab operative: Overview, Output per mercato, Performance post-cutover, Stabilità, Data health, Export.  
Archivio ricerca (candidati, Phase 2C, benchmark…) non caricato di default.

## Feature operative

`OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS` (5):  
`home_goals_scored_avg`, `home_goals_conceded_avg`, `away_goals_conceded_avg`, `total_goals_avg`, `goals_scored_std_last_10`.

## Post-deploy

1. Dry-run con `benchmark_job_id=2`
2. Verificare mapping e coefficienti
3. Freeze con token di conferma
4. Verificare bundle attivo ufficiale
5. Verificare primo snapshot Today post-cutover
