# Ops — Cecchino RUN V2 preview (2026-09-10)

## Temporary Alembic graph mismatch

Apertura: 2026-09-10, in concomitanza con l'applicazione della migration
`20260909210000_run_v2` sul Postgres di produzione dal container
`backend-run-v2-preview` (environment `preview-run-v2`, branch
`feature/cecchino-run-v2`).

### Cosa succede

La revision `20260909210000_run_v2` esiste **solo** sul branch
`feature/cecchino-run-v2`. Dopo `alembic upgrade head` eseguito dal preview,
la tabella `alembic_version` del Postgres di produzione punta a quella
revision, ma i servizi `production`/`main` non hanno ancora il file
corrispondente in `backend/alembic/versions/`.

Effetto atteso se qualcuno lancia Alembic da un servizio production/main
durante questa finestra:

- `alembic current` riporta una revision sconosciuta al codice caricato, oppure
- `alembic upgrade head` / `alembic history` falliscono perché l'albero locale
  non conosce `20260909210000_run_v2`.

### Divieto assoluto (fino al merge)

Nessun comando Alembic deve essere eseguito dai servizi production/main
durante questa finestra. In particolare:

- non `alembic upgrade`
- non `alembic downgrade`
- non `alembic current` / `heads` / `history` come check operativo da production
- non aggiungere uno start command / release command che invochi Alembic

L'unico upgrade autorizzato è quello dal container `backend-run-v2-preview`
dopo il precheck bloccante (`current = 99102f74d1c9`,
`heads = 20260909210000_run_v2`).

### Verifica start command production (2026-09-10)

- `backend/Procfile` = `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  (nessuna migration all'avvio).
- Processo live PID 1 del service `backend` in `production`:
  `/app/.venv/bin/python /app/.venv/bin/uvicorn app.main:app ...`
  (confermato via `railway ssh`; nessun Alembic nel comando).
- Nei deploy log storici compaiono a volte righe
  `alembic.runtime.migration` vicino a "Starting Container": sono residue /
  ambigue e **non** corrispondono al comando di avvio attuale. Non
  riabilitare un custom start/release command Alembic finché il branch non
  è mergiato.

### Chiusura del mismatch

La finestra si chiude quando `feature/cecchino-run-v2` (o almeno la revision
`20260909210000_run_v2`) è mergiata su `main` e i servizi production sono
ridistribuiti con quel codice. Da quel momento l'albero Alembic di
production conosce di nuovo la revision registrata in `alembic_version`.

### Perimetro DB

La migration è additiva: crea solo

- `cecchino_run_v2_runs`
- `cecchino_run_v2_match_snapshots`
- `cecchino_run_v2_market_results`

Nessuna modifica alle tabelle RUN V1 / Pattern Lab V1. Il runtime preview,
dopo la migration, usa il ruolo ristretto `cecchino_run_v2_preview`
(SELECT sulle due tabelle sorgente V1, CRUD sulle sole tabelle V2, nessun
accesso a `alembic_version`).
