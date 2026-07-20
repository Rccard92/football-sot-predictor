# Balance v5 — Readiness & Governance (Step 2C)

Policy immutabile, gate tecnici/scientifici, decisioni di governance e tab UI Readiness.
**Non** modifica formule, soglie, classi Balance, Signals, Today KPI, Acquistabilità o Goal.

## Versioni

| Chiave | Valore |
|--------|--------|
| Readiness | `cecchino_balance_v5_readiness_v1` |
| Policy | `cecchino_balance_v5_readiness_policy_v1` |
| Governance | `cecchino_balance_v5_governance_v1` |
| Decision contract | `cecchino_balance_v5_decision_contract_v1` |
| Export pack | `cecchino_module_monitoring_exports_v10` |

## Principi

- Separare sempre `operational_status` / `scientific_maturity` / `signals_integration_status` / `current_decision`.
- Mai `signals_integration = active` automatico.
- `historical_diagnostic` non incrementa settled/giorni/fold/promotion.
- Nessuno score aggregato di readiness (% unica vietata).
- Soglie policy non overrideabili da FE/query/env.

## Baseline attesa (0 prospective)

- operativo: `official_descriptive_monitored`
- maturità: `prospective_not_started`
- manual review: `not_eligible`
- signals: `blocked`
- decisione: `continue_monitoring`
- `earliest_theoretical_review_at = null`

## Soglie policy (estratto)

- `MIN_PROSPECTIVE_SETTLED_GLOBAL = 1500`
- `MIN_PROSPECTIVE_CALENDAR_DAYS = 90`
- `MIN_TEMPORAL_FOLDS = 3`
- coverage pre-match / book / persistenza ≥ 0.95

## Persistenza

- `cecchino_balance_v5_readiness_snapshots` — unique `(snapshot_date, policy_version, competition_id)`
- `cecchino_balance_v5_governance_decisions`
- Hook fail-soft dopo scan Today, update-results, recompute, job analisi Step 2B

## API

Prefix module-monitoring:

- `GET …/balance-v5/readiness/{overview,gates,pillars,prospective-progress,history,decision-contract,export}`
- `POST …/admin/…/balance-v5/readiness/refresh`
- `POST …/admin/…/balance-v5/governance/decisions` — token `CONFIRM_BALANCE_V5_GOVERNANCE_DECISION`
  - ammesse: `continue_monitoring` | `freeze_as_descriptive` | `request_formula_review`
  - Signal decisions → 422 `signal_integration_requires_separate_explicit_implementation`

## Export

- Forensic ZIP v9 include file readiness (overview/policy/gates CSV/pillars/progress/history/decision/contract/health/governance).
- Dossier dedicato: `SOT_BALANCE_V5_READINESS_<FROM>_<TO>.zip` (non sostituisce forensic).

## UI

Tab **Readiness** (dopo Stabilità, prima Data health): hero, gate matrix, card pilastri, progresso, timeline, governance, storico.
Overview usa label IT; «letture distinte» (non «indipendenti»).

## File chiave

- `cecchino_balance_v5_readiness_policy.py`
- `cecchino_balance_v5_readiness.py`
- modelli + migrazione `20260720180000_cecchino_balance_v5_readiness.py`
- FE: `balance/BalanceReadiness*.tsx`
