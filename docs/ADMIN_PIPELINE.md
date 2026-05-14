# Pipeline Admin (Serie A) e modello v0.4

Documentazione operativa per la pagina **Admin** del frontend: nessuna modifica a formule, `expected_sot`, baseline v0.4 o catalogo API; solo orchestrazione e chiamate già esistenti.

## Dopo una giornata giocata

1. Apri **Admin**.
2. Usa il pulsante principale **«Aggiorna prossima giornata completa»** (sezione *Modello attivo v0.4*).  
   Chiama `POST /api/admin/pipeline/serie-a/{season}/refresh-upcoming-v04` e in sequenza:
   - sincronizza calendario/fixture;
   - importa statistiche squadra sulle partite finite;
   - importa classifica;
   - importa statistiche giocatori e formazioni (formazioni e disponibilità: se falliscono, la pipeline continua con *warning*);
   - ricalcola profili giocatori (best-effort);
   - genera le previsioni upcoming con **baseline_v0_4_offensive_core_sot**;
   - allega `model_status` e sintesi `upcoming_summary`.

3. Vai su **Prossima giornata**: dopo una pipeline o una generazione v0.4 riuscita, la pagina può ricaricarsi automaticamente grazie al flag in `sessionStorage` (entro ~2 minuti dalla navigazione).

## Solo generazione previsioni v0.4

Pulsante **«Genera previsioni v0.4 prossima giornata»** →  
`POST /api/predictions/sot/serie-a/{season}/generate-v04-offensive-core-sot`

Usalo quando i dati di base sono già aggiornati e serve solo rigenerare le previsioni upcoming per il modello v0.4.

## Verifiche rapide

- **Stato modello attivo** (card in alto): `GET /api/predictions/sot/serie-a/{season}/model-status`
- **Prossima giornata attiva**: `GET /api/predictions/sot/serie-a/{season}/upcoming-active` (parametro `model_version` opzionale; la UI admin preferisce v0.4 dopo la pipeline).

## Sezione Legacy

I pulsanti prefissati **«Legacy: …»** (accordion chiuso) usano ancora:

- pipeline **post-matchday** v0.1 (include feature/predizioni completate, backtest, upcoming v0.1);
- `build` / `generate` stagione completata v0.1;
- `build-upcoming` + `generate-upcoming` con default **baseline_v0_1**.

Non fanno parte del flusso consigliato per la dashboard v0.4.

## Timeout e errori lato client

Le chiamate admin usano timeout configurabili (es. pipeline ~15 minuti). Se compare **Timeout operazione**, il server può ancora essere al lavoro: controlla **Mostra ultimi ingestion runs** e i log server.

In caso di errore HTTP, il pannello **Risultato ultima operazione** mostra status, durata e JSON di risposta (se presente).

## Coerenza con MODEL_LEGEND

Per il significato delle versioni modello e dei campi esposti in lettura, resta valida la [MODEL_LEGEND.md](./MODEL_LEGEND.md).
