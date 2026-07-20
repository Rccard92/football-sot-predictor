# Balance v5 — Analisi empirica (Fase 2/3 Step 2B)

Analisi statistica **separata** dei quattro pilastri sul dataset empirico Step 2A.
Sola lettura su `cecchino_balance_v5_evaluations`. Nessuna modifica a formule/soglie/classi.

## Scientific Consistency Fix (export v8)

Allineamento evidenza/bootstrap tra job, overview e ZIP:

- Export pack: `cecchino_module_monitoring_exports_v8` (bootstrap export = `BOOTSTRAP_ITERATIONS_DEFAULT` 2000, non piu 500).
- `pillar_evidence_status` canonico da analisi pilastro complete (`build_balance_full_pillar_evidence_status`); UI legge prima il top-level job, poi `evidence` del pilastro.
- Stati: `analysis_not_run`, `descriptive_only`, `exploratory_evidence`, `evidence_inconsistent`, ecc.; warning overview senza fake "nessuna win-rate Step 2B".
- Formule Balance invariate; nessuna promozione automatica.

## Versioni

| Artefatto | Valore |
|-----------|--------|
| Analysis | `cecchino_balance_v5_empirical_analysis_v1` |
| Policy | `cecchino_balance_v5_statistical_policy_v1` |
| Dataset | `cecchino_balance_v5_empirical_dataset_v1` |
| Export | `cecchino_module_monitoring_exports_v8` |

## Policy (immutabile)

`MIN_SETTLED_GLOBAL=300`, soglie classe/bin/competizione/mese, bootstrap 2000 (500–10000), CI 95%, 10 bin calibrazione.
Non modificabile da FE/query/env.

## Status evidenza

Max con `historical_diagnostic`: `exploratory_evidence`.
Mai promozione automatica nello Step 2B.

## API

`GET …/balance-v5/empirical/analysis/{overview|f36|dominance|draw-credibility|gap|stability|data-health|dependency}`  
`POST …/analysis/jobs` (202) · `GET …/analysis/jobs/{id}`

## Launcher UI job statistico (micro-fix)

Posizione: **Balance → Overview**, card «Analisi statistica completa» subito dopo il banner Overview e prima dei filtri.

| Comando | Cosa fa |
|---------|---------|
| **Avvia analisi completa** | POST job asincrono (bootstrap, test, stabilità). Non modifica formule. |
| **Scarica risultato statistico JSON** | File locale dal payload GET job (`SOT_BALANCE_V5_JOB_…json`). |
| **Scarica analisi** (Export / post-job) | ZIP forensic Balance **v8** via `MonitoringExportMenu` — distinto dal JSON. |

Polling: usa `poll_after_ms` (default 2000). Stati: In coda / In elaborazione / Completata / Non riuscita.  
409 `job_already_running` → riprende `active_job_id`.  
404 → risultato `/tmp` perso (redeploy); messaggio IT a riprovare.  
Persistenza sessione: `sessionStorage` chiave `cecchino_balance_v5_analysis_job_v1` (non localStorage).  
Bootstrap UI: 500 / **2000 Consigliato** / 5000 / 10000. Nessun auto-start al mount.

## Interpretazioni vietate

Score aggregato, ranking pilastri, ROI, promozione da diagnostic, «formula validata».

## Next

Step 2C — readiness e decisione Balance v5.

