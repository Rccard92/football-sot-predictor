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

Il totale **Anomalie** = errori + warning. Le issue `severity=info` (es. colonne extra uniformi, colonne preservate nel raw) restano in Qualità dati / preview ma **non** contano come anomalie e **non** degradano la qualità del dataset da Completo a Parziale.

La Overview espone `datasets_status` (tabella «Stato dataset»): campionato, stagione, partite, coverage Bet365, errori, warning, stato. I campi legacy `best_quality_datasets` / `worst_quality_datasets` restano nella response API per compatibilità ma non sono più usati dalla UI.

Stati qualità dataset (stringa, senza migration):

| Stato | Condizione |
|-------|------------|
| `complete` | 0 errori issue, 0 warning, tutte le partite complete |
| `complete_with_warnings` | 0 errori, ≥1 warning, tutte le partite complete |
| `partial` | almeno una partita partial |
| `error` | errori bloccanti / partite error |
| `unknown` | nessuna partita |

## Colonne extra senza intestazione

Se tutte le righe hanno lo stesso numero di valori trailing oltre l’header (caso League Two: 132 header, 133 valori):

- i valori sono preservati in `raw_json` sotto `__extra_columns__: [{position, value}, …]` (position 1-based);
- una sola issue file-level `severity=info`, `issue_code=uniform_extra_trailing_columns`;
- **non** si generano centinaia di warning per riga;
- le righe restano importabili e non diventano `partial` per questo solo motivo.

Se il numero di colonne non è uniforme → una sola issue aggregata `severity=warning`, `issue_code=irregular_column_count` con distribuzione e sample_rows.

## Import

- Token conferma import: `IMPORT_CECCHINO_LAB_CSV`
- Token conferma replace: `REPLACE_CECCHINO_LAB_DATASET`
- Parser: `football_data_uk_bet365_v2`
- Encoding: UTF-8 → UTF-8 BOM → fallback CP1252 tracciato
- Valori mancanti = `NULL` (mai zero fittizi)
- Nessuna correzione silenziosa: le anomalie diventano issue
- Asian Handicap parziale → warning `partial_bet365_ah`, riga importabile, 1X2/O/U invariati
- Tutte le issue di `ParseResult` sono persistite una sola volta (dedup in memoria); issue file-level con `source_row_number` non vengono più scartate

## Sostituzione controllata dataset

`POST /api/admin/cecchino-lab/datasets/{dataset_id}/replace` (multipart: `file`, `confirm=REPLACE_CECCHINO_LAB_DATASET`).

Comportamento:

1. ricava campionato/stagione/timezone dal dataset esistente (`division_code` → catalogo);
2. analizza completamente il nuovo CSV **prima** di eliminare dati;
3. in una sola transazione rimuove solo issue/match/import del dataset scelto, mantiene la riga `cecchino_lab_datasets` e il suo ID, reimporta;
4. `flush` dopo la delete libera il vincolo univoco `file_sha256` + `parser_version` (stesso SHA consentito);
5. rollback completo se qualcosa fallisce.

Non tocca altri dataset né tabelle fuori da `cecchino_lab_*`. Nessun endpoint di delete generico.

## API

| Metodo | Path |
|--------|------|
| GET | `/api/cecchino-lab/catalog/competitions` |
| POST | `/api/admin/cecchino-lab/imports/preview` |
| POST | `/api/admin/cecchino-lab/imports` |
| POST | `/api/admin/cecchino-lab/datasets/{id}/replace` |
| GET | `/api/cecchino-lab/overview` |
| GET | `/api/cecchino-lab/datasets` |
| GET | `/api/cecchino-lab/datasets/{id}` |
| GET | `/api/cecchino-lab/matches` |
| GET | `/api/cecchino-lab/matches/{id}` |
| GET | `/api/cecchino-lab/data-quality/issues` |

## UI

Pagina full-width `/cecchino-lab` con tab:

1. Overview (KPI + Ultimi import + **Stato dataset**)
2. Importa CSV (wizard: select campionato + stagione + file; card Errori / Warning / Info)
3. Dataset (azione discreta **Sostituisci CSV**)
4. Partite (colonne quote `1` / `X` / `2`)
5. Qualità dati

Tema navy/petrolio + ciano isolato nello shell del Lab; tema globale app invariato.

## Migration

`20260726220000_cecchino_lab_historical_tables` (revises `20260721100000`). Nessuna migration aggiuntiva per colonne extra / replace / stato qualità.