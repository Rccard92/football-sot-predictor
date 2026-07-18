# Indice di Acquistabilità — Research

Modulo **indipendente** dal Rating. Risponde a: *quanto è statisticamente affidabile acquistare il valore individuato dal modello?*  
Non risponde a: *quanto valore ha questa quota?* (competenza del Rating).

## Fase 1 — Audit e dataset storico (`cecchino_purchasability_audit_v1` / `cecchino_purchasability_dataset_v1`)

Obiettivo: inventario KPI, audit di indipendenza, mappa mercati opposti, dataset storico pre-match, readiness Fase 2. **Nessuna formula 0–100**, nessun peso, nessuna classe qualitativa, nessun betting.

### Sorgente canonica

- `CecchinoTodayFixture.kpi_panel_json.rows[]` da `build_cecchino_kpi_panel_v2_betfair` (`cecchino_kpi_v2_betfair`).
- **Non** la coorte `cecchino_kpi_signal_activations` (rating ≥ 50 → selection bias).
- Snapshot: un solo panel per Today fixture (overwrite). `source_snapshot_at = updated_at` (fallback `odds_checked_at`); ammissione se strettamente `< kickoff`.

### Unità di analisi

`partita + mercato + selezione + snapshot KPI + quota + risultato` (una riga per selezione, non una per partita).

### Rating = benchmark

Formula invariata in `cecchino_kpi_panel_v2_betfair._compute_rating`:

`raw = (prob_cecchino*100)*0.5 + (vantaggio_prob*100)*2.0 + edge_pct` → clamp 0–100.

Classificato `benchmark_candidate`. Dependency map esportata; non è input obbligatorio dell’Indice.

### Mappa opposizioni

Modulo `cecchino_market_opposition.py`: comparatore ≠ complemento; stesso periodo/linea/famiglia. Unsupported (fuori core): Over 1.5 senza Under 1.5, Under 3.5 senza Over 3.5, X PT incompleto, GG/No Goal assenti dal pannello, Over PT 0.5 senza Under.

### Target research

Stake = 1 unità. Win: `odds - 1`; Loss: `-1`; Void: `0`. Void escluso dal denominatore Win Rate; incluso a profitto 0 nel ROI. Missing settlement escluso dalle metriche.

### API (read-only)

- `GET /api/admin/cecchino/research/purchasability/audit`
- `GET /api/admin/cecchino/research/purchasability/dataset`
- `GET /api/admin/cecchino/research/purchasability/markets`
- `GET /api/admin/cecchino/research/purchasability/export/{kind}`

### Frontend

Tab **Acquistabilità — Audit** su `/segnali-kpi`. Nessuna colonna produttiva Acquistabilità.

### Limiti

- Nessuno storico multi-versione del panel KPI.
- Nessuna migration / scrittura DB in Fase 1.
- Normalizzazione book solo su mercato completo nello stesso snapshot.

### Roadmap macro-fasi

1. Audit + dataset (questa fase)
2. Ricerca statistica (associazioni vs settlement/ROI)
3. Costruzione Indice 0–100 (solo dopo evidenza)
4. Integrazione monitorata (senza sostituire Rating)

## Non modificare

Rating, Score, Edge, Segnali KPI, Cecchino Today eligibility, altri moduli research produttivi.
