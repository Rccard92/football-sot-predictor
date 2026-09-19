"""Pipeline live V4 su API-Football: client con guardia budget, normalizzazione pura, job.

- `client.py`: `V4ApiClient`, involucro sottile su `ApiFootballClient` con contatore e arresto a
  `settings.api_daily_stop()` chiamate nel giorno (tabella `api_usage_events`).
- `normalize.py`: funzioni pure dalle forme API-Football v3 alle colonne delle tabelle V4.
- `jobs.py`: i job (`fixtures`, `post_match`, `lineups`, `injuries`, `standings`, `odds_snapshot`,
  `odds_closing`, `coverage_scan`, `backfill`) con riga `cecchino_v4_jobs`, heartbeat e recupero
  dei job fermi; helper per GET /engine/data.

Le quote raccolte finiscono solo nel registro (`cecchino_v4_odds_snapshots`): mai nei motori.
"""
