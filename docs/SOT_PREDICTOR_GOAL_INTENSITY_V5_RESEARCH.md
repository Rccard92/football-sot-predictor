# Intensità Goal v5 — Research

Modulo di ricerca per rifondare **Intensità Goal** su quattro pilastri indipendenti. Fase 1A = audit storico e disponibilità variabili. **Nessuna formula produttiva.**

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

`/cecchino/ricerca-intensita-goal` — copy coorte Today; diagnostica eleggibilità; banner bloccante (unknown / ineligible / cohort_basis / scan_date &lt; MIN).

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
| **2A** | Preview UI a quattro pilastri (senza promuovere formula) |
| **2B** | Consolidamento pannello ufficiale (v4 resta rollback) |

## Invarianti

Non modificare: formula v4, Goal Engine, EGE, Segnali, KPI, Balance v5, Credibilità X, SOT, migration, API esterne, regole eligibility Today.
