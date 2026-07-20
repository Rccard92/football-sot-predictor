# HANDOFF PER CHATGPT — INTENSITÀ GOAL AVANZATA V5 CONSOLIDAMENTO FINALE

**Repository:** Rccard92/football-sot-predictor  
**Scope:** Fase 3/3 — facade, Today alias, readiness, API, export v10, workspace FE, cleanup legacy UI.  
**Invariato:** candidate definitions, ECDF, calibration payload, bundle hash, frozen_at, snapshot storici, Goal Engine, Signals, KPI, Balance, formule v4/v5. Tabelle `*_preview_*` non rinominate.

---

## Versioni

| Chiave | Valore |
|--------|--------|
| Bundle | `cecchino_goal_intensity_v5_preview_v1_1` |
| Monitoring | `cecchino_goal_intensity_v5_monitoring_v1` |
| Readiness | `cecchino_goal_intensity_v5_readiness_v1` |
| Policy | `cecchino_goal_intensity_v5_readiness_policy_v1` |
| Export modulo | `cecchino_goal_intensity_v5_export_v1` |
| Export pack | `cecchino_module_monitoring_exports_v10` |
| Soglia prospetti | `MINIMUM_PROSPECTIVE_MATCHES = 200` |

## Servizi

- `cecchino_goal_intensity_v5.py` — facade
- `cecchino_goal_intensity_v5_readiness_policy.py`
- `cecchino_goal_intensity_v5_readiness.py` (cache TTL 300s; dossier con `jsonable_encoder` + `allow_nan=False`)
- Motore: `cecchino_goal_intensity_v5_preview.py` (solo delega)

## Today + pipeline

- Campo `goal_intensity_v5` + alias `goal_intensity_v5_preview` deprecated
- `goal_intensity_analysis` (v4) resta nel JSON, non in UI
- update-results → `attach_results_for_rows` fail-soft
- Scan → `safe_preview_after_today_scan` (invariato)

## API

`GET …/goal-intensity-v5/{overview,dimensions,candidates,prospective-results,calibration,stability,readiness,data-health,export}`  
`POST …/admin/…/goal-intensity-v5/readiness/refresh`

## Export

Forensic **v10** con file `goal_*` + dossier `SOT_GOAL_INTENSITY_V5_READINESS_<FROM>_<TO>.zip`

## UI

- Panel Today canonico; workspace 9 viste; status **Preview monitorata**
- Redirect lab → overview (non research)
- Rimossi AnalysisPanel / PreviewPanel / pagina Ricerca Intensità Goal

## Baseline attesa (0 completed)

TECH pass/fail su bundle · SCI `prospective_not_started` · DECISION `continue_monitoring` · SIGNALS blocked

## Conferma

Nessuna formula/candidato/hash/Signals modificata. Nessuna promozione automatica.

## Doc

`docs/SOT_PREDICTOR_GOAL_INTENSITY_V5_MONITORING.md`  
`docs/SOT_PREDICTOR_GOAL_INTENSITY_V5_ARCHITECTURE_AUDIT.md`

## Report 27 punti (checklist consolidamento)

1. Pre-flight git/HEAD verificato  
2. Bundle attivo invariato (`preview_v1_1`)  
3. Hash / frozen_at non toccati  
4. Snapshot storici immutati  
5. Facade pubblica senza formule duplicate  
6. Today `goal_intensity_v5` canonico  
7. Alias preview deprecated identico  
8. v4 ancora nel JSON Today  
9. attach_results fail-soft post update-results  
10. Scan single-flight invariato  
11. Policy immutable + soglia 200  
12. Readiness stati maturità  
13. Signals sempre blocked  
14. Decision default continue_monitoring  
15. earliest_review null se 0 completed  
16. API overview…export canoniche  
17. Admin readiness refresh (solo cache)  
18. Export pack v10  
19. SCHEMA_CONTRACTS goal_*  
20. Dossier ZIP serializzabile (date)  
21. FE Panel Today rinominato  
22. Workspace 9 viste (no research)  
23. Client API senza «Preview» nei nomi pubblici  
24. Redirect lab → overview  
25. Legacy UI rimossa  
26. Test consolidation + assert v10  
27. Docs / HANDOFF / REPO VIEW aggiornati  
