# Intensità Goal v5 — Research

Modulo di ricerca per rifondare **Intensità Goal** su quattro pilastri indipendenti. Fase 1A = audit storico e disponibilità variabili. **Nessuna formula produttiva.**

## Fase 2A.1 — Preview freeze reale (2026-07-18)

Versione `cecchino_goal_intensity_v5_preview_v1_1`. `bundle.frozen_at = now UTC` al freeze (non la data protocollo 1D). Ammissione: `source_snapshot_at > frozen_at` e `< kickoff`; esclusione retrospettiva via identity sets congelati (today/local/provider). Same-day post-freeze ammesso. Formule/ECDF/hash invariati; nessuna migration.

## Fase 2A — Preview prospettica (2026-07-18)

Versione storica `cecchino_goal_intensity_v5_preview_v1` (superseduta da v1_1). Bundle congelato da `candidate_indices_v1_1` (ECDF train + calibrazioni). Snapshot pre-match su Today eleggibili; lock post-kickoff; risultati FT senza ricalcolo score.

| Campo | Valore |
|-------|--------|
| Primary | `GI_A_STRICT_CORE` |
| Challenger | `GI_B_RECENCY` |
| Benchmark | `MT1_LONG_TERM` |
| Diagnostico | `GI_A_without_volatility` |
| Hash definition | `3c48413461490d9ad17c59f052e0543919e12a6013a04ca0bdccdddb316273ab` |
| Min prospettico | 200 partite concluse (solo gate Fase 2B) |
| Ammissione v1_1 | `source_snapshot_at > bundle_frozen_at` + identity guard |
| Cache export 1D | `simple_export_cache_skipped=true` (rischio memoria/sessioni) |
| v4 / betting | invariata / nessun segnale |

Tabelle additive: `cecchino_goal_intensity_v5_preview_bundles`, `cecchino_goal_intensity_v5_preview_snapshots`. Script: `python -m scripts.freeze_goal_intensity_v5_preview_bundle`. FE tab «Preview Fase 2A». Phase 2B non automatica sotto 200 match.

## Fase 1D.1 — Calibrazione e valutazione corretta (2026-07-18)

Versione `cecchino_goal_intensity_v5_candidate_indices_v1_1`. Score grezzi invariati (ECDF/formule). Corretti: Brier/logloss su probabilità logistic train-only (non score/100); paired/ablation su predizioni calibrate; expanding CV su GI_A–D, MT1 e LOO × 4 target; protocollo prospettico con `first_prospective_scan_date` = giorno dopo freeze; gate readiness v1_1; export `calibrated_predictions` e `temporal_fold_metrics`.

## Fase 1D — Indici candidati (2026-07-17)

Modulo `cecchino_goal_intensity_v5_candidate_indices_v1`: riusa il dataset Fase 1B, normalizza feature con ECDF midrank **train-only**, costruisce score pilastro/compositi fissi (GI_A–D, equal weight), metriche sui 4 target, ablation, paired bootstrap, Pareto, xG optional paired e readiness Fase 2A.

- Primary default: `GI_A_STRICT_CORE`; challenger = miglior non dominato; `selection_evidence_level=low`
- Hard exclusion: MAD, CV, delta, ge3 frequency, pair rolling — mai negli score
- Display solidità/stabilità = 100 − DV/OV (non entrano nei compositi)
- `validation_status=retrospective_selection_informed`; nessuna claim produttiva; v4 invariata
- Endpoint: `POST .../goal-intensity-v5/candidate-indices` + 12 export streaming
- Benchmark: `python -m scripts.benchmark_goal_intensity_v5_candidate_indices` (<30s preferibile, <45s max, payload <2 MB)

## Fase 1C — Statistiche esplorative (2026-07-17)

La Fase 1C riusa esclusivamente il dataset Fase 1B.1: coorte Today persistita `eligible`, floor `scan_date` 2026-06-19, righe `row_feature_safe` e core disponibili con soglia history 10 o 20. Produce descrittive, Pearson/Spearman con bootstrap deterministico (seed 42), point-biserial/AUC, quintili, correlazioni/ridondanza/VIF, stabilità temporale (PSI, KS e direzione) e confronto xG temporale quando la coorte paired è sufficiente.

L'engine di eligibility è marcato `legacy_pre_utc_fix`: le esclusioni UTC storiche non vengono riclassificate né mutate. È quindi una limitazione esplicita di ricerca, ma non blocca autonomamente la readiness. I risultati sono descrittivi/esplorativi, senza formula, indice, pesi o training produttivo; v4 resta invariata.

Endpoint: `POST .../goal-intensity-v5/statistics`; export CSV/JSON per segnali, ridondanza, stabilità, rolling, xG e raccomandazioni. Benchmark reale: `python -m scripts.benchmark_goal_intensity_v5_statistics` (PASS <30s e payload <2 MB).

## Coorte research (Today eleggibile)

Source of truth: campo persistito `CecchinoTodayFixture.eligibility_status` (prodotto in scan/revalidate). Range su `scan_date` ≥ **2026-06-19**. Mapping: `eligible` → model-ready; status `ELIGIBILITY_*` noti → ineligible (solo diagnostica); null/sconosciuto → **unknown** (fail-closed, fuori model-ready). Storico `Fixture` locale solo come prior per feature pre-match.

`cohort_basis = cecchino_today_eligible_scan_date` · audit `v1_5` · dataset `v1_2`

## Comprensione del fenomeno

| Punto | Contenuto |
|-------|-----------|
| Fenomeno | Propensione della partita a generare occasioni e reti |
| Ruolo | Lettura strutturale Cecchino Today (dopo Equilibrio vs Squilibrio, prima dei Segnali) |
| Problema | Separare produzione / difesa / ritmo / stabilità da un unico numero che accende Over |
| Non-mercato | Non prevede Under/Over/GG/X PT; non accende Segnali; non suggerisce quote |
| Indipendenza | I quattro pilastri restano letture distinte |

## Problema della v4

Versione produttiva: `cecchino_goal_intensity_v4_expected_goals`.

- Una sola grandezza (`expected_goals_total` da Goal Engine interno)
- Classificazione Difensiva/Offensiva su soglie fisse 0.5 / 1.5 / 2.5 / 3.5
- Accensione soglie Over
- Non separa produzione, difesa, ritmo, stabilità
- Baseline Q44 legacy non collegata

La v4 resta disponibile come **legacy_reference** (nessuna sostituzione in 1A).

## Quattro pilastri

1. **Produzione offensiva** — capacità di creare occasioni (xG For, goal segnati, rolling)
2. **Solidità difensiva** — capacità di limitare occasioni (xG Against, goal subiti; alto = solida)
3. **Ritmo della partita** — tendenza ad aprirsi (freq Over 2.5 / GG come feature descrittive, non previsioni)
4. **Stabilità offensiva** — costanza nel tempo (std / MAD / CV candidati; nessuna scelta definitiva in 1A)

## Variabili candidate vs escluse

**Candidate** (inventario audit): xG For/Against, rolling goal 5/10, Over 2.5 e GG frequency, medie total goals, misure di dispersione.

**Escluse dal cuore** (documentate in audit): First Half xG, PPDA, Field Tilt, xThreat, Big Chances — copertura irregolare; eventuali correttori futuri.

## Target di ricerca

- Primario: `total_goals_ft` (continuo)
- Diagnostici: `goals_ge_2`, `goals_ge_3`, `btts_ft`
- Non diventano output del modulo
- Nessun dato post-kickoff nelle feature

## Anti-leakage

Per ogni riga: identity consistency statica, esclusione fixture corrente/futura dalle feature goal, max source kickoff &lt; target. Solo righe `row_feature_safe` nelle statistiche di copertura.

**xG (1A.4):** facoltativo per ammissibilità, obbligatorio se completo e anti-leakage. Stati `available` / `partial` / `missing` / `excluded_unsafe`. Cutoff o xG unsafe azzerano solo i campi xG (mai imputazione a 0); la Fixture resta feature-safe se identity/goal OK. Coorti su feature-safe; readiness paired per confronto futuro con/senza xG (soglia ≥50). Feature xG: `recommended_status = optional_enrichment` (non `exclude_low_coverage` per copertura globale bassa).

## Dataset Fase 1B / 1B.1 / coorte Today

Una riga = una partita **eleggibile Today** feature-safe. Dedupe residua provider/composita. Report identity/exclusion bias aggregati. Coorti history e paired xG. Nessuna formula/training.

**1B.1:** payload summary + preview ≤100; export StreamingResponse.

**Coorte Today:** entry da scan eleggibili; CSV con `today_fixture_id`, `scan_date`, `eligibility_*`; export diagnostica non eleggibili separato.

## Endpoint

`GET /api/admin/cecchino/research/goal-intensity-v5/availability` — range Today eleggibile `scan_date` ≥ MIN.

`POST /api/admin/cecchino/research/goal-intensity-v5/audit` — `cecchino_goal_intensity_v5_audit_v1_5`

`POST .../goal-intensity-v5/dataset` — `cecchino_goal_intensity_v5_dataset_v1_2`

Export: `.../dataset/export/all|core-min5|core-min10|xg-paired|ineligible-diagnostics|summary`

## Frontend

`/cecchino/ricerca-intensita-goal` — tab Audit / Dataset 1B / Analisi 1C / **Indici Fase 1D**; copy coorte Today; diagnostica eleggibilità; banner bloccante (unknown / ineligible / cohort_basis / scan_date &lt; MIN). Nessun pick/betting/quote/ROI.

## Roadmap

| Fase | Obiettivo |
|------|-----------|
| **1A** | Audit copertura, inventario, anti-leakage, piano |
| **1A.1** | Identity fail-closed su eccezione |
| **1A.2** | Coorte `Fixture.kickoff_at`, identity keyword-only, feature goal senza Today, xG snapshot/team_stats |
| **1A.3** | Perf: preload indici in memoria, loop DB-free, availability, timeout 180s invariato |
| **1A.3-fix** | Identity storica statica (no status/score bloccanti); gate xG; `audit_quality` + feature-safe rate |
| **1A.4** | xG opzionale ma obbligatorio se available; coorti; fixture audit; FE filtri/CSV |
| **1B** | Dataset storico feature↔target, dedupe composita, paired xG, exclusion bias |
| **1B.1** | Timeout fix: dedupe O(n log n), summary compatto, export stream |
| **Coorte Today** | Solo eleggibili Cecchino Today; floor scan_date; fail-closed unknown |
| **1C** | Analisi statistica / ridondanza / scelta stabilità |
| **1D** | Indici candidati 0–100 (ECDF train-only, GI_A–D, Pareto) |
| **2A** | Preview UI a quattro pilastri (senza promuovere formula) |
| **2B** | Consolidamento pannello ufficiale (v4 resta rollback) |

## Invarianti

Non modificare: formula v4, Goal Engine, EGE, Segnali, KPI, Balance v5, Credibilità X, SOT, migration, API esterne, regole eligibility Today.
