# HANDOFF PER CHATGPT — HOTFIX READINESS POST-SCAN

## Contesto

Repository `Rccard92/football-sot-predictor`, branch `main`.

La scansione Cecchino Today del 21/07/2026 ha elaborato correttamente le fixture e persistito le eleggibili, ma il job è apparso `failed` per un errore accessorio nel salvataggio snapshot Readiness Balance v5.

## Causa primaria

Migrazione `20260720180000` crea `created_at`/`updated_at` su `cecchino_balance_v5_readiness_snapshots` come `NOT NULL` **senza** `server_default`. L’ORM (`TimestampMixin`) e l’upsert non valorizzano quei campi → `NotNullViolation`.

## Cascata

1. `run_scan` completa e committa i dati Today.
2. `upsert_balance_readiness_daily_snapshot(db, commit=True)` sulla stessa sessione fallisce.
3. `try/except` logga ma la sessione resta in stato di rollback obbligatorio.
4. `run_scan_day` chiama `get_day_scan_meta` → `PendingRollbackError`.
5. Il job thread marca `failed` / guardia «job thread exited without terminal status».

## Fix applicato

1. **Nuova migrazione** `20260721100000` (non modifica la 180000): `server_default=now()` su:
   - `cecchino_balance_v5_readiness_snapshots.created_at`
   - `cecchino_balance_v5_readiness_snapshots.updated_at`
   - `cecchino_balance_v5_governance_decisions.created_at`
2. **Isolamento**: helper `safe_upsert_balance_readiness_daily_snapshot` con `SessionLocal` dedicata (rollback/close isolati).
3. Hook fail-soft aggiornati: scan, update-results, recompute, analysis job.
4. Warning stabile `balance_readiness_snapshot_failed_non_blocking` solo in `warnings` / `warnings_json`.
5. FE: warning ambra anche su job `completed` (banner rosso solo su `failed`).

## Non modificato

Formule Balance / Acquistabilità / Goal Intensity / Rating / Signals; eligibility; quote; policy readiness/governance; consumo API; dati delle 14 eleggibili; nessuna riscansione automatica; nessun backfill.

## Post-deploy

Vedi `docs/REPO_VIEW_POST_DEPLOY_HOTFIX_READINESS_POST_SCAN.md`.
