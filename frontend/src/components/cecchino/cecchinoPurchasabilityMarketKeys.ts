/** Ordine canonico mercati pannello Acquistabilità (19) — neutro, condiviso. */

export const PANEL_MARKET_KEYS: readonly string[] = [
  'HOME',
  'DRAW',
  'AWAY',
  'HOME_PT',
  'DRAW_PT',
  'AWAY_PT',
  'ONE_X',
  'X_TWO',
  'ONE_TWO',
  'OVER_1_5',
  'UNDER_1_5',
  'OVER_2_5',
  'UNDER_2_5',
  'OVER_3_5',
  'UNDER_3_5',
  'OVER_PT_0_5',
  'UNDER_PT_0_5',
  'OVER_PT_1_5',
  'UNDER_PT_1_5',
] as const

export const PANEL_MARKET_ORDER = new Map(PANEL_MARKET_KEYS.map((k, i) => [k, i]))
