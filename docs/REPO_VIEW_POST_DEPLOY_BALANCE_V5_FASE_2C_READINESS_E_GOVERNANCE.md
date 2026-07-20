# REPO VIEW POST-DEPLOY — BALANCE V5 FASE 2C READINESS E GOVERNANCE

## Cosa è entrato

- Policy + servizio readiness (gate tecnici/scientifici, pilastri, progress, decision, health, cache TTL 300s)
- Tabelle snapshot + governance + migrazione Alembic
- Hook fail-soft: scan Today, update-results, recompute, job analisi 2B
- API GET readiness/* + admin refresh/decisions
- Export pack **v9** + dossier ZIP dedicato
- FE tab Readiness + label IT + terminologia «letture distinte»

## Verifica post-deploy

1. `alembic upgrade head` include `20260720180000`
2. GET `/api/cecchino/module-monitoring/balance-v5/readiness/overview` → baseline 0 prospective
3. Tab Balance → Readiness carica senza errori
4. Download dossier ZIP non vuoto
5. Forensic analysis-pack contiene file `balance_readiness_*`
6. POST governance con Signal decision → 422

## Non fatto / invariato

- Nessuna modifica formule Balance / soglie / classi
- Nessun sync empirico rieseguito
- Signals non integrati

## Next

Raccolta prospettica fino a soglie policy; eventuale Step successivo solo su decisione esplicita di governance (non automatica).
