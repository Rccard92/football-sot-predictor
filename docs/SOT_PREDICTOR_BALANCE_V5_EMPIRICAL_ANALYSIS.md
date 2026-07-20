# Balance v5 — Analisi empirica (Fase 2/3 Step 2B)

Analisi statistica **separata** dei quattro pilastri sul dataset empirico Step 2A.
Sola lettura su `cecchino_balance_v5_evaluations`. Nessuna modifica a formule/soglie/classi.

## Versioni

| Artefatto | Valore |
|-----------|--------|
| Analysis | `cecchino_balance_v5_empirical_analysis_v1` |
| Policy | `cecchino_balance_v5_statistical_policy_v1` |
| Dataset | `cecchino_balance_v5_empirical_dataset_v1` |
| Export | `cecchino_module_monitoring_exports_v7` |

## Policy (immutabile)

`MIN_SETTLED_GLOBAL=300`, soglie classe/bin/competizione/mese, bootstrap 2000 (500–10000), CI 95%, 10 bin calibrazione.
Non modificabile da FE/query/env.

## Status evidenza

Max con `historical_diagnostic`: `exploratory_evidence`.
Mai promozione automatica nello Step 2B.

## API

`GET …/balance-v5/empirical/analysis/{overview|f36|dominance|draw-credibility|gap|stability|data-health|dependency}`  
`POST …/analysis/jobs` (202) · `GET …/analysis/jobs/{id}`

## Interpretazioni vietate

Score aggregato, ranking pilastri, ROI, promozione da diagnostic, «formula validata».

## Next

Step 2C — readiness e decisione Balance v5.
