# Cecchino Today — Report diagnostico partite storiche (2026-06-26)

**Modalità:** solo lettura — nessun DELETE/UPDATE/rescan/cleanup eseguito.

## 1. I dati sono presenti nel DB?

**Parzialmente.** In produzione (oggi `2026-06-26`, timezone `Europe/Rome`):

| Periodo | Stato in DB |
|---------|-------------|
| 2026-06-01 → 2026-06-17 | **Assenti** (timeline: non scansionata, lista vuota, activations=0) |
| 2026-06-18 → 2026-06-26 | **Presenti** (9 giornate con snapshot) |

## 2. Conteggi fixture per giorno (da API produzione ≈ Query 1)

| scan_date | eligible | excluded | note |
|-----------|----------|----------|------|
| 2026-06-18 | 0 | 140 | solo escluse |
| 2026-06-19 | 11 | 90 | |
| 2026-06-20 | 21 | 412 | |
| 2026-06-21 | 34 | 308 | |
| 2026-06-22 | 9 | 71 | |
| 2026-06-23 | 6 | 69 | |
| 2026-06-24 | 1 | 118 | |
| 2026-06-25 | 24 | 108 | |
| 2026-06-26 | 40 | 126 | oggi |
| 2026-06-01…17 | 0 | 0 | nessuna riga |

**Totale eleggibili nel DB (giugno):** 146 (= somma giorni 18–26).

## 3. Conteggi signal activations (giugno)

| Intervallo | activations |
|------------|-------------|
| 2026-06-01 → 2026-06-17 | **0** |
| 2026-06-01 → 2026-06-26 | 463 (tutte da 18–26) |

FK `cecchino_signal_activations.today_fixture_id` → `ON DELETE CASCADE`: eliminazione fixture rimuove activations.

## 4. Endpoint timeline

- `GET /api/cecchino/today/days?timezone=Europe/Rome`
- Lista giorno: `GET /api/cecchino/today?date=YYYY-MM-DD&timezone=Europe/Rome`

## 5. date_from / date_to frontend

**Nessuno.** Il frontend chiama solo `timezone=Europe/Rome`. Il backend genera 61 giorni (`±30`) da `rome_today()`.

## 6. Filtro sbagliato?

**No.** `_aggregate_scan_dates` legge tutto il DB per `scan_date`. Giorni a zero = **nessuna riga** in `cecchino_today_fixtures`.

## 7. Cleanup / delete trovato

**Sì — causa principale.**

```python
# cecchino_today_service.py — cleanup_cecchino_today_snapshots
cutoff = rome_today() - timedelta(days=DEFAULT_RETENTION_DAYS)  # DEFAULT_RETENTION_DAYS = 7
DELETE FROM cecchino_today_fixtures WHERE scan_date < cutoff
```

Invocato **automaticamente a fine ogni `run_scan`** (scan-day). Non collegato alla timeline ±30.

Con oggi = 2026-06-26 → cutoff = **2026-06-19** → tutto prima del 19 viene eliminato al prossimo scan con cleanup.

## 8. DATABASE_URL / Railway

- Backend produzione: `https://backend-production-5f140.up.railway.app`
- `GET /api/health` → `{"status":"ok","database":"connected","environment":"production"}`
- **Stesso DB** usato dall’app (non DB vuoto locale).
- Accesso SQL diretto non disponibile in questa sessione (nessun `DATABASE_URL` locale / Railway CLI).
- Script read-only: `backend/scripts/diagnose_cecchino_timeline.py` (eseguibile con `DATABASE_URL` per Query 1–6 complete).

## 9. Causa probabile

1. **Cleanup retention 7 giorni** ha cancellato snapshot (e activations in CASCADE) per `scan_date` < oggi−7.
2. **Timeline ±30** ha solo **reso visibili** giorni 1–17 giugno già vuoti (prima erano fuori finestra ±7).
3. Monitoraggio Segnali per 1–17 giugno mostra **0** perché i dati non ci sono più; per 18–26 resta operativo.

## 10. Piano di ripristino (senza perdita dati)

### Se serve recuperare 1–17 giugno

1. **Railway Postgres → Backups / Point-in-time recovery** — ripristinare a snapshot **prima** dell’ultimo scan che ha eseguito cleanup (idealmente prima del 19 giugno o prima della prima cancellazione massiva).
2. **Non** lanciare rescan automatico prima del restore.
3. Dopo restore, applicare fix preventivo (punto 11) **prima** di nuovi scan.

### Se accettabile perdere 1–17 giugno

- Nessun restore; continuare con dati dal 18 giugno.
- Eventuale backfill manuale giornate passate (costoso API, non recupera valutazioni segnali già perse).

## 11. Fix preventivo proposto (richiede conferma utente — NON applicato)

Opzioni (scegliere una):

| Opzione | Descrizione |
|---------|-------------|
| A | Rimuovere `cleanup_cecchino_today_snapshots` da `run_scan` (cleanup solo manuale admin) |
| B | Aumentare `DEFAULT_RETENTION_DAYS` (es. 90 o 365) allineato a monitoraggio/backtest |
| C | Retention separata: timeline ±30 solo UI, retention storica indipendente |

**Non modificare** finché non si decide restore vs accettazione perdita.

## 12. Modifiche distruttive eseguite in questa diagnostica

**Nessuna.**
