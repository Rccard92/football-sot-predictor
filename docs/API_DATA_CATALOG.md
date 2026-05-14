# Catalogo dati API (API-Football / API-Sports)

## A cosa serve

Il **Catalogo dati API** è uno strumento di **consultazione e pianificazione**: elenca in italiano i principali parametri ottenibili da API-Football, indica endpoint e presenza nel database del progetto, e confronta lo stato con il **modello attivo v0.4** (senza modificare formule, pesi o previsioni).

- **Frontend:** pagina `Catalogo dati API` (menu *Strumenti tecnici*), con filtri, macro-aree a fisarmonica e selezione opzionale delle variabili.
- **Backend:** `GET /api/data-catalog/api-football` — risposta JSON statica arricchita con riferimenti al manifest v0.4 (`framework_keys`, `in_v04_manifest`).

## Disponibile API vs salvato DB vs usato nel modello

| Concetto | Significato |
|----------|-------------|
| **Stato API** | Se il dato è tipicamente esposto dal provider (o richiede verifica / non è nel piano attuale / serve un provider esterno). |
| **Stato DB** | Se nel nostro database esiste una colonna dedicata, solo `raw_json`, non è ancora importato, o non è disponibile. |
| **Stato modello v0.4** | Se il dato entra nella logica predittiva v0.4 in modo diretto, indiretto, è implementato ma non usato, è da implementare, o non è disponibile per il modello. |

Non tutte le variabili “disponibili” devono entrare nel modello: più dati possono introdurre **rumore**, **instabilità** o **collinearità**; altri richiedono ingestion costosa o copertura scarsa. Il catalogo aiuta a decidere **cosa** valutare in un secondo momento.

## Selezione variabili e localStorage

Le checkbox sulla pagina salvano le chiavi selezionate in **`localStorage`** sotto la chiave `apiFootballCatalogSelectedKeys` (array JSON di stringhe). In questa versione:

- il pulsante **“Crea set variabili modello”** è disabilitato e non invia nulla al backend;
- nessuna variabile viene aggiunta automaticamente al motore predittivo.

In futuro la stessa selezione potrà alimentare un elenco di **variabili candidate** per un modello algoritmico (es. export o configurazione esplicita), sempre con passi di validazione separati.

## Macro-aree

I parametri sono raggruppati in undici macro-aree (partite, contesto calendario, arbitro, statistiche squadra/giocatore, formazioni, eventi, classifiche, infortuni, quote, dati avanzati). Le statistiche in intestazione a ogni area sono calcolate su **tutti** i parametri dell’area, mentre l’elenco sotto rispetta i **filtri** attivi.

## Manutenzione

I testi e gli stati “statici” vivono in `backend/app/data/api_football_catalog.py`. Il mapping verso le chiavi del manifest v0.4 è in `CATALOG_KEY_TO_FRAMEWORK_KEYS`: va aggiornato se cambiano le chiavi framework o il manifest.
