# Intensità Goal v5 — Research

Modulo di ricerca per rifondare **Intensità Goal** su quattro pilastri indipendenti. Fase 1A = audit storico e disponibilità variabili. **Nessuna formula produttiva.**

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

Per ogni riga: identity consistency, cutoff xG, esclusione fixture corrente/futura, max source kickoff &lt; target. Solo righe `passed` nelle statistiche.

## Endpoint

`GET /api/admin/cecchino/research/goal-intensity-v5/availability` — range kickoff locale disponibile.

`POST /api/admin/cecchino/research/goal-intensity-v5/audit`

Versione payload: `cecchino_goal_intensity_v5_audit_v1_2`

## Frontend

`/cecchino/ricerca-intensita-goal` — laboratorio audit con export JSON/CSV; banner range dati locali; init filtri sul range reale.

## Roadmap

| Fase | Obiettivo |
|------|-----------|
| **1A** | Audit copertura, inventario, anti-leakage, piano |
| **1A.1** | Identity fail-closed su eccezione |
| **1A.2** | Coorte `Fixture.kickoff_at`, identity keyword-only, feature goal senza Today, xG snapshot/team_stats |
| **1A.3** | Perf: preload indici in memoria, loop DB-free, availability, timeout 180s invariato |
| **1B** | Dataset storico feature↔target |
| **1C** | Analisi statistica / ridondanza / scelta stabilità |
| **2A** | Preview UI a quattro pilastri (senza promuovere formula) |
| **2B** | Consolidamento pannello ufficiale (v4 resta rollback) |

## Invarianti

Non modificare: formula v4, Goal Engine, EGE, Segnali, KPI, Balance v5, Credibilità X, SOT, migration, API esterne.
