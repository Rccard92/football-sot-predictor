# REPO VIEW POST-DEPLOY — FIX DOWNLOAD DOSSIER READINESS BALANCE V5

## Cosa è entrato

- Serializzazione dossier readiness con `jsonable_encoder` (date → YYYY-MM-DD).
- Log `balance_readiness_dossier_{started,completed,failed}` sull'endpoint export.
- Toast Sonner su fallimento download; pulsante riabilitato in `finally`.
- Test builder con date reali + test endpoint ZIP.

## Verifica post-deploy

1. Tab Balance → Readiness → **Scarica dossier readiness**.
2. HTTP 200, ZIP scaricato `SOT_BALANCE_V5_READINESS_<FROM>_<TO>.zip`.
3. Aprire `metadata.json` → `filters.date_from` / `date_to` stringhe coerenti con UI.
4. Nessun errore CORS se il backend risponde 200.
5. Altri endpoint readiness (overview/gates/…) invariati.

## Non toccato

Formule Balance, policy readiness, governance, dataset, sync, Signals, CORS middleware, export forensic v9.
