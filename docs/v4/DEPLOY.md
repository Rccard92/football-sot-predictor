# Messa online Cecchino V4

Procedura verificata il 20/09/2026 sull'ambiente Railway `staging` (progetto "Serie A SOT Prediction"), che oggi e' l'unico ambiente online. Tutti i servizi pubblicano dal ramo `main`; il backend parte con `alembic upgrade head && uvicorn ...`, quindi la migrazione V4 gira da sola al primo avvio.

## Cosa non cambia

- Nessun file di V2, V2.5, V3, Cecchino Today, Bet Builder, Master Pattern, KPI o Monitoraggio e' stato modificato. Le uniche righe toccate in file esistenti sono le registrazioni (rotta, modelli, voce di menu, roadmap in-app, `.env.example`).
- La migrazione `20260920090000_cecchino_v4` crea solo 13 tabelle nuove con prefisso `cecchino_v4_`. Non tocca, non altera e non legge tabelle esistenti.
- Le rotte V4 sono nuove (`/api/cecchino/v4/*`); le azioni admin stanno sotto la sessione admin gia' in uso. Con `CECCHINO_V4_ENABLED` non impostata la pagina si vede ma nessun job puo' partire.
- Nessuna dipendenza Python nuova: numpy, scipy, scikit-learn, threadpoolctl erano gia' installate.
- Test: 254 backend (`backend/tests/v4`), 17 frontend; `tsc` e `eslint` puliti; le quattro viste provate in locale su un database SQLite con le 158 partite reali del fine settimana.

## Rischio residuo, detto chiaramente

Il rischio non e' negli altri modelli ma nel carico: il primo calcolo V4 (`predict`) rifa' il walk-forward della V3 su cinque stagioni. Con `CECCHINO_V4_WORKERS=1` gira in un solo processo e impiega 15-25 minuti; lanciato dal cron dedicato non tocca il processo web. Non lanciarlo dal backend web finche' non si e' visto il primo cron andare a buon fine.

## Passi (10 minuti)

### 1. Variabili sul servizio `backend` (senza ridistribuire)

| Variabile | Valore |
|---|---|
| `CECCHINO_V4_ENABLED` | `true` |
| `CECCHINO_V4_WORKERS` | `1` |

### 2. Controllo di salute sul servizio `backend`

Settings → Deploy → Healthcheck path `/api/health`, timeout 300 s. Cosi' il traffico passa alla nuova versione solo quando risponde; se l'avvio fallisse, resta online quella attuale.

### 3. Unire il ramo

Pull request `feature/cecchino-v4` → `main` (e' un avanzamento lineare: `main` e' esattamente la base del ramo). Al merge Railway ridistribuisce backend, frontend e i due cron esistenti con lo stesso codice piu' la V4.

Verifica dopo il deploy (2-3 minuti):

```bash
curl -s https://backend-staging-3d1c.up.railway.app/api/health
```

```bash
curl -s https://backend-staging-3d1c.up.railway.app/api/cecchino/v4/status
```

```bash
curl -s "https://backend-staging-3d1c.up.railway.app/api/cecchino/today/days?timezone=Europe/Rome" | head -c 300
```

Poi aprire il frontend: Cecchino Today deve mostrare la scansione come prima; la voce "Cecchino V4" mostra la pagina vuota ("in attesa di calcolo").

### 4. Tre servizi cron nuovi (stesso repo, root `/backend`, ramo `main`, come `cecchino-auto-scan`)

| Servizio | Comando di avvio | Cron (UTC) | Cosa fa |
|---|---|---|---|
| `cecchino-v4-daily` | `python -m app.jobs.cecchino_v4_daily daily` | `0 6 * * *` | partite a 7 giorni, quote del mattino, statistiche post-partita, previsioni + ragionamenti + shortlist, regolamento |
| `cecchino-v4-odds` | `python -m app.jobs.cecchino_v4_daily odds` | `0 12,16 * * *` | istantanee quote pomeriggio e sera, shortlist aggiornata, regolamento |
| `cecchino-v4-prematch` | `python -m app.jobs.cecchino_v4_daily prematch` | `*/30 * * * *` | formazioni ufficiali e quota di chiusura delle partite entro 65 minuti, risultati appena finite |

Variabili per ognuno (riferimenti, nessun valore da copiare a mano):

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
API_FOOTBALL_KEY=${{backend.API_FOOTBALL_KEY}}
API_FOOTBALL_BASE_URL=${{backend.API_FOOTBALL_BASE_URL}}
CECCHINO_V4_ENABLED=true
CECCHINO_V4_WORKERS=1
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
MALLOC_ARENA_MAX=2
```

Restart policy `NEVER` come gli altri cron. Consumo API stimato: circa 340 chiamate al giorno in tutto, contro il limite di 7.500; ogni job si ferma da solo a 7.000.

### 5. Prima corsa e matrice dei mercati

Dal servizio `cecchino-v4-daily` lanciare una corsa manuale (Deploy → Run). Al termine la pagina Cecchino V4 mostra le partite con previsioni e la shortlist provvisoria del giorno. Una volta sola, per sapere in quali divisioni Bet365 quota tiri, corner e cartellini, lanciare da un terminale Railway:

```bash
python -m app.jobs.cecchino_v4_jobs coverage_scan
```

La matrice compare nella vista Motore → Dati.

## Come si torna indietro

- Spegnere la V4 senza toccare il codice: `CECCHINO_V4_ENABLED=false` sul backend e sui tre cron (o disattivare i cron). La pagina resta visibile e ferma.
- Tornare al codice precedente: su Railway "Rollback" all'ultimo deploy del 18/09, oppure `git revert` del merge su `main`. Le tabelle `cecchino_v4_*` restano nel database e non disturbano nessuno.

## Cosa aspettarsi nelle prime settimane

- Mercati classici: sempre etichettati "in osservazione, non consigliati" (esame E4 non superato). Si vedono, non si giocano.
- Mercati speciali: tiri, tiri in porta e falli con verdetto pieno dove Bet365 li quota; corner e cartellini solo descrittivi. Il giudizio sulla redditivita' arriva dalla vista Misura (CLV) dopo almeno otto settimane di shortlist sigillate.
- Le shortlist si sigillano oggi solo a mano (`POST /api/admin/cecchino/v4/shortlist/{data}/seal`); il sigillo automatico all'ora dell'ultima istantanea e' il primo miglioramento da fare quando i cron girano stabilmente.
