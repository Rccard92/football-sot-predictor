# SOT Predictor — Cecchino Lab

Archivio storico isolato basato su CSV [football-data.co.uk](https://www.football-data.co.uk/).

## Confine di fase (obbligatorio)

Questa area è **solo dati**:

- import CSV Football-Data;
- anteprima / audit;
- persistenza PostgreSQL dedicata;
- explorer partite e qualità dati.

**Non include e non deve includere in questa fase:**

- formule Cecchino;
- predizioni;
- replay storici / simulazione giornate;
- Rating, Edge, Affidabilità, Acquistabilità;
- machine learning;
- modifiche a Cecchino Today o ai moduli predittivi.

Bookmaker storico normalizzato: **solo Bet365**. Altri bookmaker restano nel `raw_json` della riga.

## Isolamento

Namespace tecnico:

- backend: `app/services/cecchino_data_lab/`, `app/models/cecchino_lab_*.py`, route `/api/cecchino-lab` e `/api/admin/cecchino-lab`
- frontend: `components/cecchino-data-lab/`, pagina `/cecchino-lab` (label UX: **Cecchino Lab**)

Tabelle dedicate (nessuna FK verso fixtures / cecchino_today / odds operative):

1. `cecchino_lab_datasets`
2. `cecchino_lab_imports` (unicità `file_sha256` + `parser_version`)
3. `cecchino_lab_matches`
4. `cecchino_lab_data_issues`

Non si riutilizzano: `cecchino_today_fixtures`, `cecchino_predictions`, `fixture_bookmaker_odds`, `fixtures`, `competitions`, `teams`, `seasons` operative.

## Catalogo campionati e import guidato

Catalogo statico in `competition_catalog.py` (16 campionati Football-Data). Endpoint `GET /api/cecchino-lab/catalog/competitions`.

L'utente seleziona solo **campionato**, **stagione** e **file CSV**. Paese, `division_code` e timezone derivano dal catalogo (non editabili). Preview/import richiedono `competition_key` + `season_label`; il backend non si fida dei metadata liberi del client.

Controllo bloccante: colonna CSV `Div` deve coincidere con `division_code` del campionato selezionato (`division_mismatch`).

## Anomalie Overview

Il totale **Anomalie** = errori + warning. Le issue `severity=info` (es. colonne preservate nel raw) restano in Qualità dati ma **non** contano come anomalie e **non** degradano la qualità del dataset.

## Import

- Token conferma: `IMPORT_CECCHINO_LAB_CSV`
- Parser: `football_data_uk_bet365_v1`
- Encoding: UTF-8 → UTF-8 BOM → fallback CP1252 tracciato
- Valori mancanti = `NULL` (mai zero fittizi)
- Nessuna correzione silenziosa: le anomalie diventano issue
- Asian Handicap parziale → warning `partial_bet365_ah`, riga importabile, 1X2/O/U invariati

## API

| Metodo | Path |
|--------|------|
| GET | `/api/cecchino-lab/catalog/competitions` |
| POST | `/api/admin/cecchino-lab/imports/preview` |
| POST | `/api/admin/cecchino-lab/imports` |
| GET | `/api/cecchino-lab/overview` |
| GET | `/api/cecchino-lab/datasets` |
| GET | `/api/cecchino-lab/datasets/{id}` |
| GET | `/api/cecchino-lab/matches` |
| GET | `/api/cecchino-lab/matches/{id}` |
| GET | `/api/cecchino-lab/data-quality/issues` |

Nessun endpoint di cancellazione in questa fase.

## UI

Pagina full-width `/cecchino-lab` con tab:

1. Overview
2. Importa CSV (wizard: select campionato + stagione + file)
3. Dataset
4. Partite (colonne quote `1` / `X` / `2`)
5. Qualità dati

Tema navy/petrolio + ciano isolato nello shell del Lab; tema globale app invariato.

## Migration

`20260726220000_cecchino_lab_historical_tables` (revises `20260721100000`).
