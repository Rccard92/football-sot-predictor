# Stato lavori Cecchino V4

Aggiornato ad ogni passo. Serve a riprendere il lavoro senza contesto.

## Vincoli operativi di questa sessione
- Nessun accesso a database online, chiavi API o segreti: gli esami storici usano i CSV pubblici football-data.co.uk (16 campionati, 5 stagioni) in `backend/app/data/v4/football_data/`, identici alla fonte del Lab.
- Le pipeline live API-Football sono scritte e testate con risposte registrate; si accendono al deploy con `CECCHINO_V4_ENABLED=true`.
- Nessuna migrazione eseguita su database online; la migrazione V4 è additiva e gira al deploy.

## Avanzamento
- [x] Ramo `feature/cecchino-v4` da `cleanup/sot-removal`
- [x] `docs/v4/ROADMAP.md`, `docs/v4/REGOLE.md`
- [x] CSV storici scaricati (80 file, 0 errori) + stagione in corso 2026/27 (16 file) + fixtures.csv pubblico (partite in programma con quote Bet365/Betfair classiche)
- [x] Caricatori `history/football_data.py` (24.945 partite di giudizio, identiche al Lab) e `history/fixtures_csv.py`; test verdi
- [x] Fase 0: modelli, migrazione additiva, rotte lettura `/api/cecchino/v4/*`, admin `/api/admin/cecchino/v4/*` sotto sessione, pagina `/cecchino-v4` con quattro viste; job `coverage_scan` pronto (si esegue al deploy con la chiave API)
- [x] Fase 1: motore gol V4 (`engine_goals`) = V3 Fase 4 come libreria + handicap asiatico + ratings; **esame E1 non superato**: nessuna delle cinque novita' (vantaggio casa per squadra, rho per divisione, binomiale negativa, incertezza, isotonica) migliora la V3 entro tolleranza; configurazione adottata scritta in `engine_goals/config.py`
- [x] Fase 2: motore statistiche (`engine_stats`); **esame E2**: tiri, tiri in porta e falli superati (precisione e informazione oltre il mercato in ogni stagione); corner e cartellini non superati per la sola parte (a), restano "solo descrittivo"
- [x] Fase 3 (codice): pipeline live API-Football con 9 job, guardia budget a 7.000, mappa squadre 316/316, registro quote; test con risposte registrate. L'accensione avviene al deploy (`CECCHINO_V4_ENABLED=true`, job `daily` + `odds_snapshot` x3 + `lineups`/`odds_closing`)
- [x] Fase 4 (codice): regola del profitto, shortlist sigillata con impronta, regolamento, ragionamento in sei blocchi, misura CLV/ROI/CUSUM; **esame E4 non superato** (11.307 giocate classiche 2022/23-2024/25 alla chiusura Bet365: ROI -10,3%, IC90 -12,8%/-7,8%; profitto positivo solo in Championship): le giocate classiche restano visibili con `advised=false` e banner in Shortlist; il giudizio sui mercati speciali e' solo prospettico (G6)
- [ ] Fase 5: contesto e arena (struttura tabelle e vista pronte; sfidanti da registrare)
- [ ] Fase 6: paper trading prospettico: parte con il primo giorno di shortlist sigillata online; verdetto G6 dopo almeno 8 settimane
- [x] Test backend (254) e frontend (17) verdi, tsc e eslint puliti; verifica visiva locale delle quattro viste con dati reali del fine settimana (SQLite + fixtures.csv)
- [x] Push su GitHub e messa online (20/09/2026 08:17 Roma): main avanzato a 104fa8b, migrazione V4 eseguita all'avvio del backend, backend e frontend online con healthcheck `/api/health`; variabili `CECCHINO_V4_ENABLED=true`, `CECCHINO_V4_WORKERS=1`; tre servizi cron Railway `cecchino-v4-daily` (06:00 UTC), `cecchino-v4-odds` (12:00 e 16:00 UTC), `cecchino-v4-prematch` (ogni 30 min) con root `/backend` e variabili per riferimento
