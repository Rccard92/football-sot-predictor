# Pipeline Admin (Serie A) e modelli SOT

Documentazione operativa per la pagina **Admin**: orchestrazione ingestion + generazione previsioni. Le formule v0.4 restano invariate; v1.0 aggiunge solo il termine `expected_goals`.

## Dopo una giornata giocata

1. Apri **Admin**.
2. Usa il pulsante principale **«Aggiorna prossima giornata completa»**.  
   Chiama `POST /api/admin/pipeline/serie-a/{season}/refresh-upcoming-v04` e in sequenza:
   - sincronizza calendario/fixture;
   - importa statistiche squadra sulle partite finite (incluso `expected_goals` se presente nel provider);
   - importa classifica;
   - importa statistiche giocatori e formazioni (se falliscono, la pipeline continua con *warning*);
   - ricalcola profili giocatori (best-effort);
   - genera le previsioni upcoming **baseline_v0_4_offensive_core_sot**;
   - genera **baseline_v1_0_sot** (default `generate_v10=true`);
   - allega `model_status` e sintesi `upcoming_summary` sul **modello raccomandato** (`recommended_model_version`, atteso `baseline_v1_0_sot` se v1.0 completa).

3. Vai su **Prossima giornata**: dopo pipeline o generazione riuscita, la pagina può ricaricarsi automaticamente (`sessionStorage`, entro ~2 minuti).

## Generazione manuale

| Azione | Endpoint |
|--------|----------|
| Solo v0.4 upcoming | `POST /api/predictions/sot/serie-a/{season}/generate-v04-offensive-core-sot` |
| v1.0 (richiede v0.4) | `POST /api/predictions/sot/serie-a/{season}/generate-v10-sot` |

## Verifiche rapide

- **Stato modello**: `GET /api/predictions/sot/serie-a/{season}/model-status`  
  Campi utili: `recommended_model_version`, `xg_applied_count` / `xg_fallback_count` sulla riga v1.0, `warnings`.
- **Prossima giornata**: `GET /api/predictions/sot/serie-a/{season}/upcoming-active?model_version=baseline_v1_0_sot`
- **Copertura xG in DB**: `GET /api/admin/debug/serie-a/{season}/expected-goals-summary`

## Parametro pipeline `generate_v10`

Default **true**. Se la generazione v1.0 fallisce, la pipeline resta `success` con warning nello step `generate_v10_upcoming`.

## Sezione Legacy

I pulsanti **«Legacy: …»** usano ancora baseline v0.1 / pipeline post-matchday storica. Non fanno parte del flusso consigliato.

## Coerenza con MODEL_LEGEND

Significato versioni modello e termine xG: [MODEL_LEGEND.md](./MODEL_LEGEND.md).
