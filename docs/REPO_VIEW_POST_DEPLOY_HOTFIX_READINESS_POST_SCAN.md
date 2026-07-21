# REPO VIEW POST-DEPLOY — HOTFIX READINESS POST-SCAN

## Procedura

1. Deploy backend (commit hotfix su `main`).
2. Eseguire `alembic upgrade head` (atteso: `20260721100000`).
3. Verificare revisione applicata (`alembic current`).
4. Su PostgreSQL verificare `column_default` presente per:
   - `cecchino_balance_v5_readiness_snapshots.created_at`
   - `cecchino_balance_v5_readiness_snapshots.updated_at`
   - `cecchino_balance_v5_governance_decisions.created_at`
5. Opzionale: refresh readiness già esistente (endpoint admin), **senza** nuova scansione API-Football.
6. Confermare che la sessione DB resta utilizzabile dopo il refresh.
7. Attendere la prossima scansione naturale (o una scansione solo su decisione esplicita utente).
8. Confermare job `completed` con conteggi coerenti.
9. Assenza di: `NotNullViolation created_at`, `PendingRollbackError`, `job thread exited without terminal status`.

## Non fare

- Non ripetere automaticamente la scansione del 21/07/2026.
- Non cancellare / backfillare le eleggibili già salvate.
- Non modificare formule o policy.
