-- Ruolo PostgreSQL dedicato all'ambiente preview della RUN V2.
--
-- NON ESEGUIRE PRIMA DELLA MIGRATION `20260909210000_run_v2`: i GRANT sulle
-- tabelle V2 e sulle relative sequenze falliscono se gli oggetti non esistono.
--
-- Ordine previsto:
--   1. `alembic upgrade head` eseguita come `postgres` (owner dello schema).
--      La migration ha bisogno di CREATE su schema public, REFERENCES sulle
--      due tabelle V1 e scrittura su alembic_version: concedere tutto questo
--      al ruolo di runtime vanificherebbe la restrizione, quindi resta a postgres.
--   2. Questo script, sempre come `postgres`.
--   3. DATABASE_URL del servizio preview riscritta con il nuovo ruolo.
--
-- Garanzia ottenuta: il backend preview puo' leggere le due tabelle sorgente V1
-- e scrivere solo sulle tabelle cecchino_run_v2_*. UPDATE e DELETE sulle tabelle
-- V1 diventano impossibili a livello di database, non per convenzione.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Ruolo di login
-- ---------------------------------------------------------------------------
-- Sostituire il placeholder con una password generata (>= 32 caratteri casuali)
-- e non riutilizzare quella del ruolo postgres.
CREATE ROLE cecchino_run_v2_preview LOGIN PASSWORD 'SOSTITUIRE_CON_PASSWORD_GENERATA';

-- Nessuna ereditarieta' implicita di privilegi da altri ruoli.
ALTER ROLE cecchino_run_v2_preview NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Limite di connessioni: il preview usa un solo worker RUN V2 piu' le richieste API.
ALTER ROLE cecchino_run_v2_preview CONNECTION LIMIT 10;

-- ---------------------------------------------------------------------------
-- 2. Accesso allo schema (senza CREATE: il ruolo non deve poter fare DDL)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO cecchino_run_v2_preview;
REVOKE CREATE ON SCHEMA public FROM cecchino_run_v2_preview;

-- ---------------------------------------------------------------------------
-- 3. Sola lettura sulle tabelle sorgente V1 effettivamente usate dalla RUN V2
-- ---------------------------------------------------------------------------
-- Verificate sul codice: executor._load_work legge cecchino_lab_datasets e
-- cecchino_lab_matches; export.py rilegge cecchino_lab_matches. Nessun altro
-- accesso a tabelle V1 (GlobalRollingStateRegistry lavora in memoria e
-- settlement.py importa solo costanti).
GRANT SELECT ON TABLE
    public.cecchino_lab_datasets,
    public.cecchino_lab_matches
  TO cecchino_run_v2_preview;

-- ---------------------------------------------------------------------------
-- 4. CRUD sulle sole tabelle RUN V2
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.cecchino_run_v2_runs,
    public.cecchino_run_v2_match_snapshots,
    public.cecchino_run_v2_market_results
  TO cecchino_run_v2_preview;

-- Le PK sono BIGSERIAL (nextval), non IDENTITY: senza questi grant ogni INSERT
-- fallisce con "permission denied for sequence".
GRANT USAGE, SELECT ON SEQUENCE
    public.cecchino_run_v2_runs_id_seq,
    public.cecchino_run_v2_match_snapshots_id_seq,
    public.cecchino_run_v2_market_results_id_seq
  TO cecchino_run_v2_preview;

-- ---------------------------------------------------------------------------
-- 5. alembic_version: nessun privilegio
-- ---------------------------------------------------------------------------
-- L'applicazione non legge mai alembic_version a runtime e non esiste alcun
-- create_all in backend/app: il ruolo di runtime non deve vederla. Le migration
-- restano appannaggio di postgres.

COMMIT;

-- ---------------------------------------------------------------------------
-- 6. Verifiche post-esecuzione (read-only, da eseguire dopo il COMMIT)
-- ---------------------------------------------------------------------------
-- Atteso: t per SELECT sulle V1, f per UPDATE/DELETE sulle V1.
SELECT has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_lab_matches', 'SELECT') AS v1_select_ok,
       has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_lab_matches', 'UPDATE') AS v1_update_ko,
       has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_lab_matches', 'DELETE') AS v1_delete_ko,
       has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_lab_datasets', 'UPDATE') AS v1_ds_update_ko;

-- Atteso: t su tutte e quattro.
SELECT has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_run_v2_runs', 'INSERT') AS v2_insert_ok,
       has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_run_v2_match_snapshots', 'UPDATE') AS v2_update_ok,
       has_table_privilege('cecchino_run_v2_preview', 'public.cecchino_run_v2_market_results', 'DELETE') AS v2_delete_ok,
       has_sequence_privilege('cecchino_run_v2_preview', 'public.cecchino_run_v2_runs_id_seq', 'USAGE') AS v2_seq_ok;

-- Atteso: f su entrambe (nessuna DDL, nessun accesso alle migration).
SELECT has_schema_privilege('cecchino_run_v2_preview', 'public', 'CREATE') AS ddl_ko,
       has_table_privilege('cecchino_run_v2_preview', 'public.alembic_version', 'SELECT') AS alembic_ko;

-- Elenco completo dei privilegi effettivi del ruolo, per audit.
SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type) AS privilegi
  FROM information_schema.role_table_grants
 WHERE grantee = 'cecchino_run_v2_preview'
 GROUP BY table_name
 ORDER BY table_name;

-- ---------------------------------------------------------------------------
-- 7. Rollback completo, se serve smontare il preview
-- ---------------------------------------------------------------------------
-- REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM cecchino_run_v2_preview;
-- REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM cecchino_run_v2_preview;
-- REVOKE USAGE ON SCHEMA public FROM cecchino_run_v2_preview;
-- DROP ROLE cecchino_run_v2_preview;
