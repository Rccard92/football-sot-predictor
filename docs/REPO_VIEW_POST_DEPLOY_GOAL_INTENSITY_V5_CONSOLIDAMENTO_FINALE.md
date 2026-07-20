# REPO VIEW POST-DEPLOY — INTENSITÀ GOAL AVANZATA V5 CONSOLIDAMENTO FINALE

## Cosa è entrato

- Facade `cecchino_goal_intensity_v5.py` (delega al preview frozen)
- Today: `goal_intensity_v5` + alias deprecated; attach fail-soft su update-results
- Policy + readiness + dossier ZIP (`jsonable_encoder`)
- API canoniche `goal-intensity-v5/*` + admin readiness/refresh
- Export pack **v10** con artifact `goal_*`
- FE: Panel Today, workspace 9 viste, client API, redirect lab → overview
- Cleanup: AnalysisPanel, PreviewPanel, pagina Ricerca Intensità Goal, hooks/API research FE

## Verifica post-deploy

1. GET Today detail espone `goal_intensity_v5` e alias `deprecated: true`
2. GET `/api/cecchino/module-monitoring/goal-intensity-v5/overview` risponde
3. GET `…/readiness` → Signals blocked, decision continue_monitoring
4. Tab Goal workspace: overview…export senza tab research
5. Redirect `/cecchino/ricerca-intensita-goal` → overview
6. Download dossier readiness ZIP non vuoto
7. Analysis pack forensic contiene `goal_overview.json` / `goal_readiness.json`
8. Manifest export version contiene `v10`
9. v4 `goal_intensity_analysis` ancora presente nel JSON Today
10. Nessun cambio hash bundle / frozen_at

## Non fatto / invariato

- Formule, candidati, ECDF, calibrazione, Signals, Balance, KPI
- Rinomina tabelle `*_preview_*`
- Promozione Primary / integrazione Signals
- Dichiarazione «validato» sotto 200 completed

## Next

Raccolta prospettica fino a 200 completed; eventuale revisione manuale solo dopo gate policy (non automatica).
