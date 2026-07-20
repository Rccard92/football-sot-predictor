# HANDOFF PER CHATGPT — BALANCE V5 FASE 2C READINESS E GOVERNANCE

**Repository:** Rccard92/football-sot-predictor  
**Scope:** readiness prospettica, gate, snapshot, governance, tab UI, export v9.  
**Invariato:** formule Balance, soglie, classi, Signals, candidate, Today KPI; **no** sync empirico rieseguito.

---

## Versioni

- Readiness: `cecchino_balance_v5_readiness_v1`
- Policy: `cecchino_balance_v5_readiness_policy_v1`
- Governance: `cecchino_balance_v5_governance_v1`
- Decision contract: `cecchino_balance_v5_decision_contract_v1`
- Export: `cecchino_module_monitoring_exports_v9`

## Servizi / modelli

- `cecchino_balance_v5_readiness_policy.py`
- `cecchino_balance_v5_readiness.py`
- `CecchinoBalanceV5ReadinessSnapshot` / `CecchinoBalanceV5GovernanceDecision`
- Migrazione `20260720180000_cecchino_balance_v5_readiness.py`

## API

GET readiness overview/gates/pillars/prospective-progress/history/decision-contract/export  
POST admin readiness/refresh + governance/decisions (token `CONFIRM_BALANCE_V5_GOVERNANCE_DECISION`)

## Baseline 0 prospective

`official_descriptive_monitored` · `prospective_not_started` · Signals `blocked` · `continue_monitoring` · earliest review `null`

## Export

Forensic v9 + dossier `SOT_BALANCE_V5_READINESS_<FROM>_<TO>.zip`

## UI

Tab Readiness dopo Stabilità; «letture distinte»; scarica dossier.

## Conferma

Nessuna formula/soglia/classe/Signal modificata. Nessuna promozione automatica Signals.

## Doc

`docs/SOT_PREDICTOR_BALANCE_V5_READINESS_GOVERNANCE.md`
