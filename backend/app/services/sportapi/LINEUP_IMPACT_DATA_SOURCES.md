# Lineup Impact — fonti dati (audit/simulazione)

## Statistiche giocatore (API-Football / API-Sports)

**Non duplicare.** Per SOT per giocatore usare:

| Uso | Tabella | Note |
|-----|---------|------|
| Raw per partita | `fixture_player_stats` | Ingestion API-Football |
| Aggregato stagione | `player_sot_profiles` | Build da `PlayerSotProfileService` su `fixture_player_stats` |

Metriche derivate calcolate in `sportapi_lineup_impact_service` (non nuove tabelle):

- `sot_per_90` ← `shots_on_target_per90`
- `team_sot_share` ← `team_sot_share_pct / 100`
- `is_top3` / `is_top5` ← rank per squadra+stagione

Alternative (Player DB layer): `player_season_profiles`, `player_match_stats` — **non** usate per Lineup Impact in questa fase.

## Lineup / indisponibili (SportAPI — solo debug)

- `fixture_provider_lineups`, `fixture_provider_lineup_players`, `fixture_missing_players`
- Mapping evento: `fixture_provider_mappings`
- Mapping giocatore: `player_provider_mappings` (SportAPI `provider_player_id` ↔ `players.api_player_id`)

## Modello predittivo

`USE_SPORTAPI_LINEUP_IMPACT_IN_MODEL=false` — la simulazione non modifica `team_sot_predictions`.
