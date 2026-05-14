# Catalogo dati API (scan reale API-Football)

## A cosa serve

Il **Catalogo dati API** è uno strumento di **consultazione e diagnostica**: elenca solo i **campi effettivamente presenti** nelle response API-Football dopo uno **scan** con parametri reali (Serie A, stagione configurata, fixture campionate dal database). Non include parametri “ipotetici” o non osservati (ad esempio metriche avanzate tipo xG o big chances **non** compaiono se l’API non le espone nello scan).

- **Frontend:** pagina *Catalogo dati API* (menu *Strumenti tecnici*), con due viste: **Catalogo diretto API** e **Diagnostica scan**, filtri, macro-aree a fisarmonica, badge coerenti con lo scan, selezione campi in `localStorage`.
- **Backend:**
  - `GET /api/data-catalog/api-football/direct` — legge l’**ultimo risultato** salvato in cache (file JSON sul server, tipicamente ignorato da git). Se non è mai stato eseguito uno scan, la risposta contiene un messaggio esplicativo e strutture vuote. **Non** include la diagnostica dettagliata degli endpoint.
  - `POST /api/admin/debug/api-football-catalog/serie-a/{season}/scan` — esegue lo scan (DB + chiamate API + flatten + confronto `raw_json`), salva la cache e restituisce il catalogo completo con **`diagnostics`** per ogni chiamata endpoint.

La stessa **base URL** e **chiave** del progetto (`API_FOOTBALL_BASE_URL`, `API_FOOTBALL_KEY`) sono usate dallo scan. Se la chiave manca, il POST risponde con errore chiaro (es. 503).

## Dato diretto API vs variabile derivata

| Concetto | Significato |
|----------|-------------|
| **Diretto API** | Valore osservato nello scan, con `json_path` e `endpoint` reali. È l’unico tipo di riga mostrato nel catalogo principale. |
| **Derivato (modello / aggregazioni)** | Medie, trend, conversioni, componenti combinate, ecc. **Non** sono elencate in questa pagina; il pulsante “Crea variabili derivate da questi campi” è disabilitato (roadmap). |

## Disponibile in response vs salvato in DB vs modello v0.4

| Concetto | Significato |
|----------|-------------|
| **Trovato in API** | Il campo compare nel flatten della response dello scan (badge coerente in UI). |
| **`db_status`** | Euristiche sul mapping verso colonne note o solo `raw_json` del DB; `unknown` quando non mappabile. Non si inventano colonne. |
| **`model_v04_status`** | Solo se esiste un **mapping esplicito** verso concetti noti del modello (es. SOT, tiri, gol); altrimenti “non usato”. Nessuna modifica a formule o manifest: solo **etichettatura** in lettura. |
| **`appeared_in_raw_json`** | Il path (o equivalente normalizzato) compare anche nel flatten di `raw_json` salvati su fixture/statistiche/lineup/giocatori. |

Metriche “avanzate” (xg, expected goals, big chances, …): compaiono **solo** se il flatten trova path/valori coerenti nello scan; altrimenti **non** vengono create righe fittizie.

## `json_path`

Stringa che identifica la posizione del valore nel JSON normalizzato (es. indici negli array, chiavi oggetto). Utile per confrontare con payload reali e con `raw_json` in database.

## Cache e deploy

Il file di cache (percorso configurabile lato backend, default sotto `backend/app/data/cache/`) può essere **ignorato da git** così ogni ambiente non eredita scan di altri deploy. Il `GET /direct` funziona dopo almeno uno scan nell’ambiente corrente.

## Selezione campi e localStorage

Le checkbox usano uno **`stable_id`** stabile (derivato da endpoint + path). Le selezioni sono persistite in **`localStorage`** sotto la chiave `apiFootballDirectCatalogSelected` (array JSON di stringhe).

- Il pulsante **“Crea variabili derivate da questi campi”** è disabilitato con tooltip che spiega che la funzione è pianificata e non modifica il modello in questa versione.

## Diagnostica scan

Dopo un POST scan, la vista **Diagnostica scan** mostra tabella per endpoint: parametri, stato HTTP/logico, conteggio campi trovati, messaggio di errore se presente. Utile per capire piani API, rate limit o endpoint non disponibili.

## Manutenzione

- Logica scan, flatten, aree, etichette: servizi sotto `backend/app/services/` (`api_football_direct_catalog_*`, `api_football_json_flatten`).
- Route: `backend/app/routes/data_catalog.py`, `backend/app/routes/admin_debug_api_football_catalog.py`.
- Il catalogo **statico** (`api_football_catalog.py`) è stato rimosso: l’unica fonte “diretta” per la UI è scan + cache.
