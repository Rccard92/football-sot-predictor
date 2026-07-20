# HANDOFF PER CHATGPT — BALANCE V5 FASE 2B ANALISI EMPIRICA

**Repository:** Rccard92/football-sot-predictor  
**Commit base atteso:** `3984f83009941c6963185141749159a4002e1fa1`  
**Scope:** analisi statistica separata 4 pilastri + API/job + UI + export v7.  
**Invariato:** formule Balance, soglie, classi, Signals, candidate; **no** sync empirico rieseguito.

---

## Versioni

- Analysis: `cecchino_balance_v5_empirical_analysis_v1`
- Policy: `cecchino_balance_v5_statistical_policy_v1`
- Dataset: `cecchino_balance_v5_empirical_dataset_v1`
- Export: `cecchino_module_monitoring_exports_v7`

## Servizi

- `cecchino_balance_v5_empirical_registry.py`
- `cecchino_balance_v5_empirical_analysis_stats.py`
- `cecchino_balance_v5_empirical_analysis.py`
- `cecchino_balance_v5_empirical_analysis_jobs.py`

## API

GET analysis overview/f36/dominance/draw-credibility/gap/stability/data-health/dependency  
POST/GET analysis/jobs (202, ephemeral `/tmp/…`)

## Evidence

Scope tipico runtime: `historical_diagnostic` → status max `exploratory_evidence`.  
`promotion_eligible=false`, `formula_change_recommended=false`.

## Export ZIP Balance v7

File Step 2A + file analisi §31 (summary/CSV per pilastro, dependency, stability, policy, evidence, registry).  
SCI atteso: `exploratory` / `partial_diagnostic` — **non** SCI PASS.

## UI

Viste dedicate Overview/F36/Dominanza/Credibilità X/Gap/Stabilità/Data health + Dataset empirico + Export.  
Lab Credibilità X legacy integrato sotto la vista Credibilità X.

## Report §38 (sintesi)

1–3. Versioni e registry classi da `cecchino_balance_v5.py`  
4–5. Campione settled `is_current`+`analysis_eligible`; coorti segmentate  
6–9. Endpoint per pilastro (risultati runtime = solo se DB locale)  
10–13. Dependency/stability/data_health/evidence  
14–17. API/job/cache/export v7  
18–21. Test unit stats + export; npm build; eslint mirato  
22. Runtime job/ZIP: verificato solo se DB disponibile  
23. Rischi: bootstrap pesante → job; historical_diagnostic non promuove  
24. **Conferma:** nessuna formula/soglia/classe/Signal modificata

## Next

Fase 2C — readiness e decisione Balance v5.
