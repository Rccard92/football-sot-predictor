# Catalogo dati API (catalogo model-relevant)

## A cosa serve

La pagina **Catalogo dati API** mostra le variabili API-Football **classificate** per rilevanza statistico-modellistica, lette da un file statico curato nel repository. **Non** interroga API-Football al caricamento e **non** ricostruisce la classificazione in tempo reale.

- **Frontend:** menu *Strumenti tecnici* — macro-aree a fisarmonica, filtri, checkbox solo sui campi “modello”, sezione separata **«Fonti tecniche per variabili derivate»** (sola lettura, senza selezione), export JSON/CSV della **vista filtrata**, `localStorage` `apiFootballModelRelevantSelected`.
- **Backend principale:** `GET /api/data-catalog/model-relevant` — legge [`backend/app/data/api_football_model_relevant_catalog.json`](backend/app/data/api_football_model_relevant_catalog.json), esclude le righe con classificazione `NASCONDERE_*` o `DA_NASCONDERE`, separa `SORGENTE_DERIVATA_TECNICA` nel blocco `technical_derivative_sources`.

## Catalogo “grezzo” da scan (strumenti avanzati)

Per operazioni di audit o confronto con response reali restano disponibili (non usati dalla pagina principale):

- `GET /api/data-catalog/api-football/direct` — ultimo scan in cache.
- `POST /api/admin/debug/api-football-catalog/serie-a/{season}/scan` — esegue lo scan e aggiorna la cache.

## Struttura della risposta `model-relevant`

- **`areas`:** raggruppamento per stringa `area` del JSON; ogni parametro include `key`, `classification`, `priority`, `recommended_markets`, `reason`, `model_v04_status`, `selectable: true`, ecc.
- **`technical_derivative_sources`:** campi `SORGENTE_DERIVATA_TECNICA` con `selectable: false` (solo consultazione in UI).

## Export

I pulsanti **Esporta JSON** / **Esporta CSV** serializzano il catalogo **dopo i filtri attivi** nella UI (più metadati di contesto), non l’intero file sorgente né il catalogo da scan. **Esporta selezionati (JSON)** include solo le chiavi `key` selezionate tra i campi del catalogo modello.

## Manutenzione

- Aggiornare il file `api_football_model_relevant_catalog.json` quando si raffinano le regole di scrematura (processo esterno al runtime dell’app).
- Logica di filtro/split: [`backend/app/services/api_football_model_relevant_catalog.py`](backend/app/services/api_football_model_relevant_catalog.py).
- Route: [`backend/app/routes/data_catalog.py`](backend/app/routes/data_catalog.py).
