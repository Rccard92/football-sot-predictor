# Framework di analisi partita

Guida all'interpretazione delle previsioni SOT: cosa significano i dati, come leggere audit e warning, come usare le pagine del tool.

Legenda modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md). Registry feature: [SOT_MODEL_FEATURE_REGISTRY.md](./SOT_MODEL_FEATURE_REGISTRY.md).

---

## Obiettivo

Stimare i **tiri in porta attesi (SOT)** per ogni squadra in una partita, e il **totale match**, per supportare decisioni sui mercati **Over/Under SOT**.

Il modello non predice il risultato della partita (1X2), ma la quantità attesa di tiri in porta.

---

## Cosa significa SOT

**Shots on Target (tiri in porta)**: tiri che avrebbero finito in rete se non fermati dal portiere o da un difensore sulla linea. Esclude tiri bloccati prima del bersaglio e tiri fuori.

Per ogni partita il tool produce:
- **SOT attesi squadra casa**
- **SOT attesi squadra trasferta**
- **SOT attesi totali match** (somma)

---

## Tipologie di dati

| Tipo | Quando disponibile | Esempi | Entra nel modello? |
|------|-------------------|--------|-------------------|
| **Storici pre-kickoff** | Sempre (se ingestion OK) | Media SOT stagione, split casa/trasferta, forma ultime 5 | Sì (v2.1 macro 1–4, 9) |
| **xG reali** | Se API-Football fornisce `expected_goals` | xG prodotti, delta vs media lega | Sì (v2.1 macro 5). **No proxy** |
| **Profili giocatore** | Dopo build profili | Top shooters SOT/90, share, reliability | Sì (v2.1 macro 6) |
| **Lineups SportAPI** | Pre-match (probabili o ufficiali) | Modulo, titolari, turnover | Sì (v2.0 fattori; v2.1 macro 7–8) |
| **Missing players** | Pre-match SportAPI | Infortunati, squalificati, indisponibili | Sì (v2.0, v2.1 macro 8) |
| **Odds/bookmakers** | Admin | Quote O/U SOT | **No** — solo informativo |
| **Arbitri** | Admin/audit | Profilo cartellini | **No** — solo informativo |
| **Debug mapping** | Admin | SportAPI ↔ profili giocatore | **No** — solo debug |

### Differenza probabili vs ufficiali

| Tipo | Affidabilità | Impatto |
|------|-------------|---------|
| **Probabili** (`confirmed=false`) | Media — possono cambiare | Confidence ridotta; warning «Formazioni probabili, non ufficiali» |
| **Ufficiali** (`confirmed=true`) | Alta — confermate pre-kickoff | Confidence piena; cron pre-match le aggiorna automaticamente |

### Differenza dato modello vs informativo

- **Dato modello**: entra nella formula (direttamente o come moltiplicatore). Es. SOT stagionali, xG, top shooter presence.
- **Dato informativo/debug**: visibile in audit o pagine tecniche ma non modifica il SOT atteso. Es. odds bookmaker, debug mapping giocatori, profilo arbitro.

---

## Come si arriva a una previsione

### v2.0 (baseline stabile)

```
SOT v2.0 = SOT v1.1 × fattore_offensivo_lineup × fattore_difesa_avversaria
```

1. Calcola base v1.1 (6 componenti additivi)
2. Applica impatto formazioni SportAPI (2 moltiplicatori)
3. Se SportAPI assente → fattori = 1.0 → output = v1.1

### v2.1 (engine autonomo)

```
SOT v2.1 = base_anchor × weighted_macro_multiplier

base_anchor = 0.55 × media_SOT_squadra + 0.45 × media_SOT_concessi_avversario
multiplier = combinazione pesata di 9 macroaree (lineups, xG, forma, player, ecc.)
```

1. Raccoglie dati pre-kickoff (stats, profili, lineups, xG)
2. Normalizza ogni micro-variabile intorno a 1.0
3. Aggrega in macro-index pesati
4. Applica moltiplicatore con clamp [0.75, 1.30]
5. Macro 10 (qualità) valuta confidence/warning senza modificare SOT

---

## Interpretazione output

### Campi principali

| Campo | Significato | Come leggerlo |
|-------|-------------|---------------|
| `predicted_sot` / `expected_sot` | SOT attesi | Valore numerico principale |
| `prediction_valid` / `valid` | Predizione calcolabile | `false` → non usare per decisioni |
| `confidence_score` | Affidabilità 0–100 | Più alto = dati più completi |
| `engine_status` | Stato engine v2.1 | `ready`, `partial`, `manifest_invalid` |
| `formula_quality_status` | Qualità dati formula | `ok`, `partial`, `insufficient_data` |
| `operating_mode` | Modalità v2.0 | `complete`, `degraded_fallback`, `not_ready` |
| `warnings` | Lista avvisi | Leggere sempre prima di decidere |
| `fallback` / status micro | Dato sostituito/neutro | Riduce confidence, non invalida v2.1 |

### Audit e spiegazione

Pagina **Spiegazione previsione** (`/match-variable-audit`):
- Endpoint: `GET /api/competitions/{competition_id}/predictions/sot/fixture/{fixture_id}/explanation?model_version=`
- Mostra trace macro/micro v2.0 o v2.1
- Dropdown limitato a v2.0 e v2.1

**Non confondere** con endpoint legacy `GET /api/match-analysis/fixture/{id}/variables` (v0.x).

---

## Come usare le pagine del tool

### Prossima giornata (`/`)

- Selettore campionato in sidebar
- Selettore modello (v2.1 default, v2.0 alternativa)
- **Model status**: readiness modelli, raccomandazione backend
- **Quick report**: sintesi turno con SOT attesi, confidence, warnings
- **Confronto v2.0 vs v2.1**: delta per fixture, utile per capire divergenze
- **Variazione post-lineup**: mostra impatto refresh formazioni (quando disponibile da `fixture_lineup_refresh_impacts`)

Endpoint:
- `GET /api/competitions/{id}/next-round/quick-report`
- `GET /api/competitions/{id}/next-round/model-comparison`

### Spiegazione previsione (`/match-variable-audit`)

Audit model-aware per singola fixture. Permette di capire **perché** il modello ha prodotto un certo SOT: quali macro hanno spinto su/giù, quali dati mancano, quali fallback attivi.

### Monitoraggio Giocate (`/monitoraggio-giocate`)

- Pick tracciate create manualmente (admin) o automaticamente (cron pre-match)
- Confronto previsione vs SOT reali post-partita
- Filtrabile per `model_version`
- Endpoint: `GET /api/competitions/{id}/betting-picks/tracked`

### Data Health (`/data-health`)

- Copertura dati per campionato e modello
- Identifica gap: team stats mancanti, profili assenti, lineups incomplete
- Endpoint: `GET /api/admin/data-health/competitions/{competition_id}`

### Bookmakers (`/bookmakers`)

- Quote e mercati SOT da SportAPI
- **Solo informativo** — non modifica predizioni

### Framework Analisi (`/match-analysis-framework`)

Questa pagina/documento — consultazione metodologica.

---

## Anti data leakage

**Regola:** per predire una partita, il modello usa **solo** dati di partite finite **prima** del kickoff target.

- Status ammessi: `FT`, `AET`, `PEN`
- Partite future o in corso al momento del kickoff target → escluse
- xG league baseline calcolata con `leakage_guard: true`
- Campo audit: `data_leakage_check` = `ok` o `warning_insufficient_prior_sample`

Se `data_leakage_check != ok` → confidence penalizzata di 10 punti.

---

## Cosa NON interpretare come certezza

| Elemento | Perché |
|----------|--------|
| SOT atteso esatto | È una stima statistica, non un risultato garantito |
| Formazioni probabili | Possono cambiare fino al kickoff |
| Missing players incompleti | SportAPI potrebbe non avere tutti gli indisponibili |
| xG assente | Macro xG neutralizzata; predizione meno informativa |
| Delta v2.0 vs v2.1 | Divergenza indica incertezza modello, non «verità» |
| Odds bookmaker | Mercato, non modello |
| Confidence 100 | Significa dati completi, non certezza sul risultato |

---

## Regole di interpretazione operativa

### 1. Alta confidence + dati completi

**Segnali:** `confidence_score ≥ 80`, `formula_quality_status = ok`, `engine_status = ready`, lineups ufficiali, xG available, nessun warning.

**Interpretazione:** predizione affidabile per decisioni operative. Tutte le macro hanno dati reali. Confrontare v2.0 e v2.1: se allineati, maggiore robustezza.

**Esempio:** Serie A, giornata 30, formazioni ufficiali confermate 2h prima, xG coverage 95%, confidence 88, delta v2.0/v2.1 = 0.3 SOT.

### 2. Confidence media + lineups probabili

**Segnali:** `confidence_score` 50–79, warning «Formazioni probabili, non ufficiali», `lineups_probable_only = true`.

**Interpretazione:** predizione utilizzabile con cautela. Il SOT atteso potrebbe cambiare significativamente con formazioni ufficiali. Attendere cron pre-match o refresh manuale SportAPI.

**Esempio:** Brasileirão, 24h prima del kickoff, formazioni probabili, confidence 62, macro lineups in `partial`.

### 3. Missing xG (`feed_unavailable`)

**Segnali:** macro `chance_quality` in `degraded_feed_unavailable`, micro xG con status `feed_unavailable`, warning «xG non disponibile nel feed importato».

**Interpretazione:** predizione basata su SOT/tiri storici senza segnale xG. Meno informativa per squadre con stile diverso dal volume tiri. Verificare xG coverage admin. Non inventare proxy xG.

**Esempio:** Lega senza `expected_goals` in API-Football, confidence 55, macro xG neutralizzata (moltiplicatore ≈ 1.0).

### 4. Player layer incompleto

**Segnali:** micro player con `missing_dependency` o `fallback_historical_profiles`, profili con sample basso, warning profili.

**Interpretazione:** impatto formazioni calcolato parzialmente. Top shooter presence/assence potrebbe essere impreciso. Eseguire build profili e verificare player-match-stats.

**Esempio:** Nuova competizione con 5 giornate, profili con 3 partite/sample, macro player_layer in `partial`, confidence 48.

### 5. SportAPI lineups non ufficiali

**Segnali:** `official_lineup` micro con valore basso, `confirmed=false`, `operating_mode = degraded_fallback` (v2.0).

**Interpretazione:** v2.0 potrebbe coincidere con v1.1 (fattori lineup = 1.0). v2.1 usa segnali lineup ma con peso ridotto sulla confidence. Rieseguire ingest SportAPI o attendere cron.

**Esempio:** v2.0 SOT = v1.1 SOT, v2.1 diverge per macro lineups/infortuni, warning formazioni probabili.

### 6. Differenza forte tra v2.0 e v2.1

**Segnali:** delta > 1.5 SOT per squadra nel confronto prossimo turno.

**Interpretazione:** i due modelli pesano diversamente i segnali. v2.0 è baseline conservativa (2 fattori lineup su base v1.1). v2.1 integra 9 macroaree con pesi manifest. **Non assumere che uno sia «giusto»** — la divergenza indica incertezza. Preferire il modello raccomandato dal backend (v2.1 se ready) ma considerare v2.0 come sanity check.

**Esempio:** Squadra attesa 4.2 SOT (v2.0) vs 6.1 SOT (v2.1). Verificare in audit quali macro spingono v2.1 (forma recente? xG? player layer?) e valutare se i dati di quelle macro sono completi.

---

## Flusso decisionale consigliato

```
1. Seleziona campionato (CompetitionSelector)
2. Verifica model-status → recommended model
3. Controlla Data Health → gap dati?
4. Leggi quick-report prossimo turno
5. Confronta v2.0 vs v2.1 per fixture di interesse
6. Apri spiegazione previsione per audit dettagliato
7. Verifica warnings e confidence
8. (Opzionale) Confronta con odds Bookmakers
9. Decidi con consapevolezza dei limiti
```

---

## Riferimenti

- Legenda modelli: [MODEL_LEGEND.md](./MODEL_LEGEND.md)
- Pipeline admin: [ADMIN_PIPELINE.md](./ADMIN_PIPELINE.md)
- Catalogo dati: [API_DATA_CATALOG.md](./API_DATA_CATALOG.md)
- Contesto progetto: [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
