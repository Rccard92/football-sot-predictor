export const BREAKDOWN_ROWS: {
  key:
    | 'season_avg_sot_for'
    | 'opponent_season_avg_sot_conceded'
    | 'home_away_avg_sot_for'
    | 'opponent_home_away_avg_sot_conceded'
    | 'last5_avg_sot_for'
    | 'opponent_last5_avg_sot_conceded'
  label: string
}[] = [
  { key: 'season_avg_sot_for', label: 'Media stagionale tiri in porta' },
  { key: 'opponent_season_avg_sot_conceded', label: 'Tiri concessi dall’avversario (stagione)' },
  { key: 'home_away_avg_sot_for', label: 'Media in casa o in trasferta' },
  {
    key: 'opponent_home_away_avg_sot_conceded',
    label: 'Avversario concede in casa o in trasferta',
  },
  { key: 'last5_avg_sot_for', label: 'Forma recente (ultime 5 partite)' },
  { key: 'opponent_last5_avg_sot_conceded', label: 'Avversario ultime 5 partite (concesse)' },
]

