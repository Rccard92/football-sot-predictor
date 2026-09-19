/**
 * Dati di esempio realistici per ogni endpoint V4, con la stessa interfaccia del client reale.
 * Servono ai test e allo sviluppo senza backend. Le date sono relative a oggi (data locale).
 */

import type {
  CecchinoV4Api,
  V4Challenger,
  V4ChallengersResponse,
  V4CoverageRow,
  V4DaysResponse,
  V4EngineData,
  V4Exam,
  V4FixtureCard,
  V4FixtureDetail,
  V4FixturesQuery,
  V4FixturesResponse,
  V4LineupsStatus,
  V4MarketRow,
  V4MeasureSummary,
  V4QualityRow,
  V4ShortlistItem,
  V4ShortlistItemStatus,
  V4ShortlistResponse,
  V4UncertaintyLevel,
  V4Verdict,
} from '../../../lib/cecchinoV4Api'
import { isoDaysAgoLocal, todayLocalIso } from '../../../utils/dateLocal'
import { V4_LEAGUES, V4_VERDICT_LABELS } from '../constants'
import { isoDateRome } from '../format'

// --- Utilita' ---------------------------------------------------------------------------------

function round(v: number, digits: number): number {
  const f = 10 ** digits
  return Math.round(v * f) / f
}

/** ISO UTC di un orario "HH:mm" a Roma nella data data. */
export function romeToIso(date: string, hhmm: string): string {
  const guess = new Date(`${date}T${hhmm}:00Z`)
  const romeHour = Number(
    new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Rome', hour: '2-digit', hour12: false })
      .formatToParts(guess)
      .find((p) => p.type === 'hour')?.value ?? '0',
  ) % 24
  const wanted = Number(hhmm.slice(0, 2))
  let diff = romeHour - wanted
  if (diff > 12) diff -= 24
  if (diff < -12) diff += 24
  return new Date(guess.getTime() - diff * 3_600_000).toISOString()
}

function familyOf(key: string): string {
  if (key.startsWith('STAT:')) return `STAT_${key.split(':')[1]}`
  if (key.startsWith('AH_')) return 'AH'
  if (key.endsWith('_PT')) return 'HT_1X2'
  if (key.startsWith('OVER') || key.startsWith('UNDER')) return 'FT_OVER_UNDER'
  if (['ONE_X', 'X_TWO', 'ONE_TWO'].includes(key)) return 'DOUBLE_CHANCE'
  return 'FT_1X2'
}

function row(
  key: string,
  label: string,
  p: number,
  lo: number,
  hi: number,
  q365: number | null,
  qbf: number | null,
  verdict: V4Verdict,
  over: Partial<V4MarketRow> = {},
): V4MarketRow {
  const p_prudent = round(p - (p - lo) * 0.6, 3)
  const quota_used = q365 ?? qbf ?? null
  const expected_profit = quota_used != null ? round(p_prudent * quota_used - 1, 3) : null
  return {
    market_key: key,
    family: familyOf(key),
    label,
    p,
    lo,
    hi,
    p_prudent,
    quota_bet365: q365,
    quota_betfair: qbf,
    quota_used,
    bookmaker_used: quota_used == null ? null : q365 != null ? 'Bet365' : 'Betfair',
    expected_profit,
    verdict,
    verdict_label: V4_VERDICT_LABELS[verdict],
    ...over,
  }
}

function poisson(lambda: number, k: number): number {
  let f = 1
  for (let i = 2; i <= k; i += 1) f *= i
  return (Math.exp(-lambda) * lambda ** k) / f
}

function scoreMatrix(lh: number, la: number, max = 5): number[][] {
  return Array.from({ length: max + 1 }, (_, h) =>
    Array.from({ length: max + 1 }, (_, a) => round(poisson(lh, h) * poisson(la, a), 4)),
  )
}

type CardSeed = {
  id: number
  league: string
  date: string
  time: string
  home: string
  away: string
  status?: string
  mostLikely: [string, string, number]
  xg: [number, number]
  uncertainty: [number, V4UncertaintyLevel]
  lineups: V4LineupsStatus
  play?: V4MarketRow | null
  reason?: string | null
  result?: V4FixtureCard['result']
}

function card(seed: CardSeed): V4FixtureCard {
  const league = V4_LEAGUES.find((l) => l.code === seed.league)
  return {
    id: seed.id,
    api_fixture_id: 1_400_000 + seed.id,
    league_code: seed.league,
    competition: league?.competition ?? seed.league,
    season_label: '2025/2026',
    kickoff_at: romeToIso(seed.date, seed.time),
    home_team: seed.home,
    away_team: seed.away,
    status: seed.status ?? 'NS',
    most_likely: { market_key: seed.mostLikely[0], label: seed.mostLikely[1], p: seed.mostLikely[2] },
    expected_goals: { home: seed.xg[0], away: seed.xg[1] },
    uncertainty: { score: seed.uncertainty[0], level: seed.uncertainty[1] },
    lineups_status: seed.lineups,
    best_play: seed.play ?? null,
    no_play_reason: seed.play ? null : (seed.reason ?? 'prezzo_giusto'),
    result: seed.result ?? null,
  }
}

// --- La scheda bersaglio: Milan - Inter -----------------------------------------------------------

const INTER_SOT_65 = row(
  'STAT:sot:away:over:6.5',
  'Inter over 6,5 tiri in porta',
  0.61,
  0.55,
  0.66,
  1.85,
  1.9,
  'giocabile',
  { p_prudent: 0.61, expected_profit: 0.13 },
)

function milanInterMarkets(): V4MarketRow[] {
  return [
    row('HOME', '1', 0.31, 0.27, 0.35, 3.1, 3.2, 'prezzo_giusto'),
    row('DRAW', 'X', 0.27, 0.24, 0.3, 3.4, 3.5, 'prezzo_giusto'),
    row('AWAY', '2', 0.42, 0.38, 0.46, 2.3, 2.36, 'prezzo_giusto'),
    row('ONE_X', '1X', 0.58, 0.54, 0.62, 1.62, 1.65, 'prezzo_giusto'),
    row('X_TWO', 'X2', 0.69, 0.65, 0.73, 1.36, 1.38, 'prezzo_giusto'),
    row('ONE_TWO', '12', 0.73, 0.7, 0.76, 1.3, 1.31, 'prezzo_giusto'),
    row('OVER_1_5', 'Over 1,5 gol', 0.78, 0.74, 0.82, 1.3, 1.32, 'prezzo_giusto'),
    row('OVER_2_5', 'Over 2,5 gol', 0.55, 0.5, 0.6, 1.8, 1.85, 'prezzo_giusto'),
    row('UNDER_2_5', 'Under 2,5 gol', 0.45, 0.4, 0.5, 2.05, 2.1, 'prezzo_giusto'),
    row('OVER_3_5', 'Over 3,5 gol', 0.31, 0.27, 0.35, 3.0, 3.1, 'prezzo_giusto'),
    row('HOME_PT', '1 primo tempo', 0.3, 0.26, 0.34, 3.3, null, 'prezzo_giusto'),
    row('DRAW_PT', 'X primo tempo', 0.42, 0.38, 0.46, 2.15, null, 'prezzo_giusto'),
    row('AWAY_PT', '2 primo tempo', 0.28, 0.24, 0.32, 3.6, null, 'prezzo_giusto'),
    row('AH_HOME:+0.5', 'Milan +0,5 handicap asiatico', 0.58, 0.54, 0.62, 1.6, 1.63, 'prezzo_giusto'),
    row('AH_AWAY:-0.5', 'Inter −0,5 handicap asiatico', 0.42, 0.38, 0.46, 2.28, 2.34, 'prezzo_giusto'),
    row('STAT:sot:away:over:5.5', 'Inter over 5,5 tiri in porta', 0.74, 0.69, 0.79, 1.44, 1.47, 'prezzo_giusto'),
    INTER_SOT_65,
    row('STAT:sot:away:over:7.5', 'Inter over 7,5 tiri in porta', 0.46, 0.4, 0.52, 2.4, 2.45, 'prezzo_giusto'),
    row('STAT:sot:home:over:3.5', 'Milan over 3,5 tiri in porta', 0.7, 0.65, 0.75, 1.4, 1.42, 'prezzo_giusto'),
    row('STAT:sot:home:over:4.5', 'Milan over 4,5 tiri in porta', 0.55, 0.5, 0.6, 1.7, 1.74, 'prezzo_giusto'),
    row('STAT:sot:home:over:5.5', 'Milan over 5,5 tiri in porta', 0.4, 0.35, 0.45, 2.2, 2.26, 'prezzo_giusto'),
    row('STAT:sot:total:over:9.5', 'Totale over 9,5 tiri in porta', 0.72, 0.67, 0.77, 1.45, 1.48, 'prezzo_giusto'),
    row('STAT:sot:total:over:10.5', 'Totale over 10,5 tiri in porta', 0.6, 0.55, 0.65, 1.75, 1.8, 'prezzo_giusto'),
    row('STAT:shots:away:over:12.5', 'Inter over 12,5 tiri', 0.64, 0.57, 0.71, 1.62, 1.66, 'prezzo_giusto'),
    row('STAT:shots:away:over:14.5', 'Inter over 14,5 tiri', 0.48, 0.41, 0.55, 2.1, 2.16, 'prezzo_giusto'),
    row('STAT:corners:total:over:9.5', 'Totale over 9,5 corner', 0.52, 0.46, 0.58, 1.9, 1.94, 'solo_descrittivo'),
    row('STAT:corners:total:over:10.5', 'Totale over 10,5 corner', 0.4, 0.34, 0.46, 2.3, 2.36, 'solo_descrittivo'),
    row('STAT:cards:total:over:3.5', 'Totale over 3,5 cartellini', 0.63, 0.56, 0.7, null, null, 'non_quotato'),
    row('STAT:cards:total:over:4.5', 'Totale over 4,5 cartellini', 0.47, 0.4, 0.54, null, null, 'non_quotato'),
  ]
}

function milanInterDetail(fixture: V4FixtureCard): V4FixtureDetail {
  return {
    fixture,
    blocks: {
      who: {
        sentence:
          'Inter: terzo attacco della Serie A, difesa sesta, conosciuta bene (34 partite equivalenti). Milan: attacco settimo in calo, difesa nona, conosciuto bene (32 partite equivalenti).',
        home: {
          team: 'Milan',
          attack: 0.12,
          defence: -0.02,
          attack_rank: 7,
          defence_rank: 9,
          teams_in_division: 20,
          evidence: 31.5,
          known: 'bene',
          trend: 'in calo',
          home_advantage: 0.16,
          inherited: 'Forza di partenza dalla stagione 2024/2025 con peso 60%, aggiornata con le 4 partite giocate.',
        },
        away: {
          team: 'Inter',
          attack: 0.3,
          defence: -0.12,
          attack_rank: 3,
          defence_rank: 6,
          teams_in_division: 20,
          evidence: 34.2,
          known: 'bene',
          trend: 'stabile',
          home_advantage: 0.18,
          inherited: 'Forza di partenza dalla stagione 2024/2025 con peso 60%, aggiornata con le 4 partite giocate.',
        },
      },
      how: {
        sentence:
          'Inter 6,8 tiri in porta attesi fuori casa, media divisione 4,9; Milan ne concede 5,1. Sui corner le due squadre sono vicine alla media.',
        rows: [
          { stat: 'sot', label: 'tiri in porta', home_for: 4.9, home_against: 5.1, away_for: 6.8, away_against: 4.2, division_mean: 4.6 },
          { stat: 'shots', label: 'tiri', home_for: 13.2, home_against: 12.8, away_for: 15.1, away_against: 10.9, division_mean: 12.4 },
          { stat: 'corners', label: 'corner', home_for: 5.4, home_against: 4.9, away_for: 6.1, away_against: 4.4, division_mean: 5.0 },
          { stat: 'cards', label: 'cartellini', home_for: 2.1, home_against: 2.6, away_for: 1.9, away_against: 2.3, division_mean: 2.2 },
        ],
      },
      context: {
        sentence: "L'Inter arriva da quattro giorni di riposo dopo la coppa; formazioni non ancora note.",
        form: {
          home: { matches: 5, goals_delta: -0.3, shots_delta: -0.8 },
          away: { matches: 5, goals_delta: 0.2, shots_delta: 1.1 },
        },
        rest: { home_days: 7, away_days: 4 },
        motivation: null,
        lineups: { status: 'non_note', absences: [] },
        referee: null,
      },
      predicts: {
        sentence:
          'Partita da 2,8 gol attesi con Inter favorita al 42%. Il mercato più interessante è quello dei tiri in porta dell’Inter.',
        score_matrix: scoreMatrix(1.2, 1.6),
        max_goals: 5,
        markets: milanInterMarkets(),
        most_likely_score: { home: 1, away: 1, p: 0.12 },
        most_likely: { market_key: 'AWAY', label: '2', p: 0.42 },
        expected_goals: { home: 1.2, away: 1.6 },
      },
      why: {
        play: INTER_SOT_65,
        sentences: [
          "L'Inter tira in porta 6,8 volte fuori casa contro una media di 4,9; il Milan ne concede 5,1.",
          'La linea 6,5 a 1,85 vale il 54%; il modello dice 61% con intervallo 55-66.',
          'Il margine è +13%, sopra il 3% richiesto.',
          'Formazioni non ancora note: la giocata è provvisoria e verrà confermata o ritirata alle 19:30.',
        ],
        would_change: [
          'Assenza di Lautaro Martínez o di Thuram nella formazione ufficiale',
          'Quota Bet365 sotto 1,68',
          "Formazione dell'Inter con più di tre cambi rispetto all'ultima partita",
        ],
      },
      aftermath: null,
    },
  }
}

// --- Partita senza giocata: Como - Cagliari -------------------------------------------------------------

function comoCagliariDetail(fixture: V4FixtureCard): V4FixtureDetail {
  return {
    fixture,
    blocks: {
      who: {
        sentence: 'Como: attacco decimo, difesa dodicesima, conosciuto discretamente. Cagliari: attacco sedicesimo, difesa tredicesima.',
        home: { attack: 0.0, defence: 0.03, attack_rank: 10, defence_rank: 12, teams_in_division: 20, evidence: 22.4, known: 'discretamente', home_advantage: 0.14, inherited: null },
        away: { attack: -0.18, defence: 0.05, attack_rank: 16, defence_rank: 13, teams_in_division: 20, evidence: 28.1, known: 'bene', home_advantage: 0.11, inherited: null },
      },
      how: {
        sentence: 'Como sopra la media per tiri, Cagliari sotto per tiri in porta.',
        rows: [
          { stat: 'sot', label: 'tiri in porta', home_for: 4.8, home_against: 4.4, away_for: 3.7, away_against: 5.0, division_mean: 4.6 },
          { stat: 'shots', label: 'tiri', home_for: 14.0, home_against: 11.9, away_for: 10.2, away_against: 13.5, division_mean: 12.4 },
        ],
      },
      context: {
        sentence: 'Formazioni probabili pubblicate, nessuna assenza rilevante.',
        form: null,
        rest: { home_days: 7, away_days: 7 },
        motivation: null,
        lineups: { status: 'probabili', absences: [] },
        referee: null,
      },
      predicts: {
        sentence: 'Como favorito al 46% con 2,4 gol attesi. Nessun mercato supera il margine richiesto: le quote sono in linea con il modello.',
        score_matrix: scoreMatrix(1.4, 1.0),
        max_goals: 5,
        markets: [
          row('HOME', '1', 0.46, 0.41, 0.51, 2.15, 2.2, 'prezzo_giusto'),
          row('DRAW', 'X', 0.28, 0.25, 0.31, 3.3, 3.4, 'prezzo_giusto'),
          row('AWAY', '2', 0.26, 0.22, 0.3, 3.5, 3.6, 'prezzo_giusto'),
          row('OVER_2_5', 'Over 2,5 gol', 0.44, 0.39, 0.49, 2.1, 2.14, 'prezzo_giusto'),
          row('UNDER_2_5', 'Under 2,5 gol', 0.56, 0.51, 0.61, 1.72, 1.75, 'prezzo_giusto'),
          row('STAT:sot:home:over:4.5', 'Como over 4,5 tiri in porta', 0.52, 0.45, 0.59, 1.85, 1.9, 'prezzo_giusto'),
          row('STAT:sot:home:over:5.5', 'Como over 5,5 tiri in porta', 0.37, 0.3, 0.44, 2.4, 2.46, 'prezzo_giusto'),
          row('STAT:corners:total:over:9.5', 'Totale over 9,5 corner', 0.49, 0.42, 0.56, 1.95, 2.0, 'solo_descrittivo'),
        ],
      },
      why: {
        play: null,
        reason: 'prezzo_giusto',
        sentences: ['Nessuna giocata: prezzo giusto. Il mercato migliore, Como over 4,5 tiri in porta a 1,85, vale il 54% contro il 52% del modello.'],
        would_change: [],
      },
      aftermath: null,
    },
  }
}

// --- Partita finita: Bologna - Napoli ----------------------------------------------------------------------

const NAPOLI_SOT_45 = row('STAT:sot:away:over:4.5', 'Napoli over 4,5 tiri in porta', 0.66, 0.6, 0.72, 1.7, 1.74, 'giocabile')

function bolognaNapoliDetail(fixture: V4FixtureCard): V4FixtureDetail {
  return {
    fixture,
    blocks: {
      who: {
        sentence: 'Napoli: secondo attacco della Serie A, difesa prima, conosciuto molto bene. Bologna: attacco ottavo, difesa quinta.',
        home: { attack: 0.08, defence: -0.15, attack_rank: 8, defence_rank: 5, teams_in_division: 20, evidence: 33.0, known: 'bene', home_advantage: 0.2, inherited: null },
        away: { attack: 0.34, defence: -0.28, attack_rank: 2, defence_rank: 1, teams_in_division: 20, evidence: 35.5, known: 'molto bene', home_advantage: 0.17, inherited: null },
      },
      how: {
        sentence: 'Napoli 5,4 tiri in porta attesi fuori casa; il Bologna ne concede 4,1.',
        rows: [
          { stat: 'sot', label: 'tiri in porta', home_for: 4.5, home_against: 4.1, away_for: 5.4, away_against: 3.6, division_mean: 4.6 },
          { stat: 'corners', label: 'corner', home_for: 5.8, home_against: 4.6, away_for: 5.9, away_against: 4.0, division_mean: 5.0 },
        ],
      },
      context: {
        sentence: 'Formazioni ufficiali senza assenze pesanti; arbitro con media cartellini alta.',
        form: { home: { matches: 5, goals_delta: 0.1, shots_delta: 0.4 }, away: { matches: 5, goals_delta: 0.3, shots_delta: 0.9 } },
        rest: { home_days: 7, away_days: 6 },
        motivation: null,
        lineups: { status: 'ufficiali', absences: [{ team: 'home', player: 'Ferguson', role: 'centrocampista', impact: -0.1 }] },
        referee: { name: 'Marco Guida', cards_per_match: 4.8 },
      },
      predicts: {
        sentence: 'Napoli favorito al 45% con 2,8 gol attesi.',
        score_matrix: scoreMatrix(1.3, 1.5),
        max_goals: 5,
        markets: [
          row('HOME', '1', 0.29, 0.25, 0.33, 3.4, 3.5, 'prezzo_giusto'),
          row('DRAW', 'X', 0.26, 0.23, 0.29, 3.5, 3.6, 'prezzo_giusto'),
          row('AWAY', '2', 0.45, 0.41, 0.49, 2.2, 2.26, 'prezzo_giusto'),
          row('OVER_2_5', 'Over 2,5 gol', 0.54, 0.49, 0.59, 1.85, 1.9, 'prezzo_giusto'),
          row('STAT:sot:away:over:3.5', 'Napoli over 3,5 tiri in porta', 0.8, 0.75, 0.85, 1.32, 1.35, 'prezzo_giusto'),
          NAPOLI_SOT_45,
          row('STAT:sot:away:over:5.5', 'Napoli over 5,5 tiri in porta', 0.49, 0.42, 0.56, 2.2, 2.26, 'prezzo_giusto'),
        ],
      },
      why: {
        play: NAPOLI_SOT_45,
        sentences: [
          'Il Napoli tira in porta 5,4 volte fuori casa contro una media di 4,6; il Bologna ne concede 4,1.',
          'La linea 4,5 a 1,70 vale il 59%; il modello dice 66% con intervallo 60-72.',
          'Il margine è +5%, sopra il 3% richiesto.',
          'Formazioni ufficiali confermate: la giocata è confermata.',
        ],
        would_change: ['Quota Bet365 sotto 1,62', 'Espulsione nel primo tempo'],
      },
      aftermath: {
        sentence: 'Finita 1-2. Il Napoli ha tirato in porta 7 volte: la giocata è vinta con merito, il risultato è in linea con i gol attesi.',
        result: fixture.result,
        goals: { expected_home: 1.3, expected_away: 1.5, actual_home: 1, actual_away: 2 },
        stats: [
          { stat: 'sot', label: 'tiri in porta', expected_home: 4.5, expected_away: 5.4, actual_home: 3, actual_away: 7 },
          { stat: 'corners', label: 'corner', expected_home: 5.8, expected_away: 5.9, actual_home: 4, actual_away: 6 },
        ],
        play: { label: NAPOLI_SOT_45.label, market_key: NAPOLI_SOT_45.market_key, outcome: 'vinta', profit_units: 0.7 },
        luck: 'Merito più che fortuna: i gol attesi della partita sono stati 1,1 contro 1,9.',
      },
    },
  }
}

// --- Dettaglio generico per le altre schede -----------------------------------------------------------

function genericDetail(fixture: V4FixtureCard): V4FixtureDetail {
  const xg = fixture.expected_goals ?? { home: 1.3, away: 1.2 }
  const total = xg.home + xg.away
  const pOver = round(Math.min(0.85, Math.max(0.15, 0.25 + (total - 2.0) * 0.25)), 2)
  const markets: V4MarketRow[] = [
    row('HOME', '1', 0.4, 0.35, 0.45, 2.4, 2.46, fixture.no_play_reason === 'incertezza_alta' ? 'incertezza_alta' : 'prezzo_giusto'),
    row('DRAW', 'X', 0.28, 0.24, 0.32, 3.3, 3.4, 'prezzo_giusto'),
    row('AWAY', '2', 0.32, 0.27, 0.37, 3.0, 3.1, 'prezzo_giusto'),
    row('OVER_2_5', 'Over 2,5 gol', pOver, round(pOver - 0.05, 2), round(pOver + 0.05, 2), 1.9, 1.95, 'prezzo_giusto'),
    row('UNDER_2_5', 'Under 2,5 gol', round(1 - pOver, 2), round(0.95 - pOver, 2), round(1.05 - pOver, 2), 1.9, 1.95, 'prezzo_giusto'),
    row(
      'STAT:sot:home:over:4.5',
      `${fixture.home_team} over 4,5 tiri in porta`,
      0.5,
      0.43,
      0.57,
      1.9,
      1.95,
      fixture.no_play_reason === 'formazioni_non_note' ? 'formazioni_non_note' : 'prezzo_giusto',
    ),
    row('STAT:sot:home:over:5.5', `${fixture.home_team} over 5,5 tiri in porta`, 0.35, 0.28, 0.42, 2.5, 2.56, 'prezzo_giusto'),
  ]
  if (fixture.best_play) markets.unshift(fixture.best_play)
  return {
    fixture,
    blocks: {
      who: {
        sentence: `${fixture.home_team} e ${fixture.away_team}: forze vicine, conoscenza discreta del modello.`,
        home: { attack: 0.05, defence: 0.0, attack_rank: 9, defence_rank: 10, teams_in_division: 20, evidence: 24.0, known: 'discretamente', home_advantage: 0.15, inherited: null },
        away: { attack: 0.0, defence: 0.02, attack_rank: 11, defence_rank: 12, teams_in_division: 20, evidence: 23.0, known: 'discretamente', home_advantage: 0.13, inherited: null },
      },
      how: {
        sentence: 'Entrambe vicine alla media della divisione per tiri in porta.',
        rows: [{ stat: 'sot', label: 'tiri in porta', home_for: 4.7, home_against: 4.5, away_for: 4.4, away_against: 4.8, division_mean: 4.6 }],
      },
      context: {
        sentence: '',
        form: null,
        rest: null,
        motivation: null,
        lineups: { status: fixture.lineups_status, absences: [] },
        referee: null,
      },
      predicts: {
        sentence: `Partita da ${String(round(total, 1)).replace('.', ',')} gol attesi.`,
        score_matrix: scoreMatrix(xg.home, xg.away),
        max_goals: 5,
        markets,
      },
      why: fixture.best_play
        ? {
            play: fixture.best_play,
            sentences: [
              `${fixture.best_play.label}: il modello dice ${Math.round(fixture.best_play.p * 100)}% contro il ${Math.round((1 / (fixture.best_play.quota_used ?? 2)) * 100)}% della quota.`,
              'Il margine supera il 3% richiesto.',
            ],
            would_change: ['Quota sotto la soglia di margine'],
          }
        : null,
      aftermath: null,
    },
  }
}

// --- Il giorno --------------------------------------------------------------------------------------------

type Dataset = {
  today: string
  days: V4DaysResponse
  fixturesByDate: Map<string, V4FixtureCard[]>
  details: Map<number, V4FixtureDetail>
  shortlist: V4ShortlistResponse
}

const BAYERN_AH = row('AH_HOME:-1.5', 'Bayern −1,5 handicap asiatico', 0.56, 0.51, 0.61, 2.0, 2.04, 'giocabile', {
  p_prudent: 0.53,
  expected_profit: 0.06,
})
const PSG_SOT = row('STAT:sot:away:over:5.5', 'PSG over 5,5 tiri in porta', 0.66, 0.6, 0.72, 1.68, 1.72, 'giocabile', {
  p_prudent: 0.62,
  expected_profit: 0.042,
})
const ARSENAL_SOT = row('STAT:sot:home:over:5.5', 'Arsenal over 5,5 tiri in porta', 0.63, 0.57, 0.69, 1.72, 1.76, 'giocabile', {
  p_prudent: 0.6,
  expected_profit: 0.032,
})

function buildDataset(today: string): Dataset {
  const d = (offset: number) => isoDaysAgoLocal(-offset)
  const cards: V4FixtureCard[] = [
    card({ id: 12, league: 'I1', date: d(0), time: '20:45', home: 'Milan', away: 'Inter', mostLikely: ['AWAY', '2', 0.42], xg: [1.2, 1.6], uncertainty: [0.22, 'bassa'], lineups: 'non_note', play: INTER_SOT_65 }),
    card({ id: 13, league: 'I1', date: d(0), time: '18:00', home: 'Como', away: 'Cagliari', mostLikely: ['HOME', '1', 0.46], xg: [1.4, 1.0], uncertainty: [0.35, 'media'], lineups: 'probabili', reason: 'prezzo_giusto' }),
    card({ id: 14, league: 'I1', date: d(0), time: '15:00', home: 'Bologna', away: 'Napoli', status: 'FT', mostLikely: ['AWAY', '2', 0.45], xg: [1.3, 1.5], uncertainty: [0.18, 'bassa'], lineups: 'ufficiali', play: NAPOLI_SOT_45, result: { ft_home: 1, ft_away: 2, ht_home: 0, ht_away: 1 } }),
    card({ id: 15, league: 'E0', date: d(0), time: '17:30', home: 'Arsenal', away: 'Chelsea', mostLikely: ['HOME', '1', 0.48], xg: [1.6, 1.1], uncertainty: [0.24, 'bassa'], lineups: 'probabili', reason: 'prezzo_giusto' }),
    card({ id: 16, league: 'E1', date: d(0), time: '16:00', home: 'Leeds', away: 'Sunderland', mostLikely: ['HOME', '1', 0.44], xg: [1.5, 1.2], uncertainty: [0.41, 'media'], lineups: 'non_note', reason: 'formazioni_non_note' }),
    card({ id: 17, league: 'D1', date: d(0), time: '18:30', home: 'Bayern', away: 'Dortmund', mostLikely: ['HOME', '1', 0.61], xg: [2.3, 1.1], uncertainty: [0.2, 'bassa'], lineups: 'probabili', play: BAYERN_AH }),
    card({ id: 18, league: 'SP1', date: d(0), time: '21:00', home: 'Getafe', away: 'Osasuna', mostLikely: ['DRAW', 'X', 0.33], xg: [1.0, 0.9], uncertainty: [0.72, 'alta'], lineups: 'non_note', reason: 'incertezza_alta' }),
    card({ id: 19, league: 'I1', date: d(0), time: '12:30', home: 'Genoa', away: 'Cremonese', status: 'FT', mostLikely: ['HOME', '1', 0.47], xg: [1.4, 0.9], uncertainty: [0.55, 'media'], lineups: 'ufficiali', reason: 'prezzo_giusto', result: { ft_home: 2, ft_away: 2, ht_home: 1, ht_away: 0 } }),
    card({ id: 20, league: 'E0', date: d(1), time: '15:00', home: 'Liverpool', away: 'Everton', mostLikely: ['HOME', '1', 0.62], xg: [2.1, 0.9], uncertainty: [0.19, 'bassa'], lineups: 'non_note', reason: 'prezzo_giusto' }),
    card({ id: 21, league: 'F1', date: d(1), time: '20:45', home: 'Marseille', away: 'PSG', mostLikely: ['AWAY', '2', 0.51], xg: [1.2, 1.9], uncertainty: [0.23, 'bassa'], lineups: 'non_note', play: PSG_SOT }),
    card({ id: 22, league: 'P1', date: d(1), time: '19:00', home: 'Porto', away: 'Braga', mostLikely: ['HOME', '1', 0.5], xg: [1.7, 1.0], uncertainty: [0.3, 'media'], lineups: 'non_note', reason: 'prezzo_giusto' }),
    card({ id: 23, league: 'T1', date: d(2), time: '19:00', home: 'Galatasaray', away: 'Fenerbahçe', mostLikely: ['HOME', '1', 0.45], xg: [1.6, 1.3], uncertainty: [0.38, 'media'], lineups: 'non_note', reason: 'non_quotato' }),
    card({ id: 24, league: 'N1', date: d(3), time: '14:30', home: 'Ajax', away: 'PSV', mostLikely: ['AWAY', '2', 0.4], xg: [1.5, 1.7], uncertainty: [0.27, 'bassa'], lineups: 'non_note', play: ARSENAL_SOT }),
  ]
  const fixturesByDate = new Map<string, V4FixtureCard[]>()
  for (const c of cards) {
    const date = isoDateRome(c.kickoff_at)
    const list = fixturesByDate.get(date) ?? []
    list.push(c)
    fixturesByDate.set(date, list)
  }
  const details = new Map<number, V4FixtureDetail>()
  for (const c of cards) {
    if (c.id === 12) details.set(c.id, milanInterDetail(c))
    else if (c.id === 13) details.set(c.id, comoCagliariDetail(c))
    else if (c.id === 14) details.set(c.id, bolognaNapoliDetail(c))
    else details.set(c.id, genericDetail(c))
  }
  const days: V4DaysResponse = {
    days: Array.from({ length: 7 }, (_, i) => {
      const date = d(i)
      const list = fixturesByDate.get(date) ?? []
      return {
        date,
        fixtures: list.length,
        plays: list.filter((f) => f.best_play).length,
        finished: list.filter((f) => f.result).length,
      }
    }),
  }
  return { today, days, fixturesByDate, details, shortlist: buildShortlist(today, cards) }
}

// --- Shortlist -----------------------------------------------------------------------------------------------

function slItem(
  rank: number,
  fx: V4FixtureCard,
  market: V4MarketRow,
  status: V4ShortlistItemStatus,
  extra: Partial<V4ShortlistItem> = {},
): V4ShortlistItem {
  return {
    ...market,
    fixture_id: fx.id,
    home_team: fx.home_team,
    away_team: fx.away_team,
    kickoff_at: fx.kickoff_at,
    rank,
    top: rank <= 15,
    status,
    withdraw_reason: null,
    result: null,
    clv: null,
    advised: !market.market_key.startsWith('STAT:') ? false : true,
    ...extra,
  }
}

function buildShortlist(today: string, cards: V4FixtureCard[]): V4ShortlistResponse {
  const byId = new Map(cards.map((c) => [c.id, c]))
  const fx = (id: number) => byId.get(id) as V4FixtureCard
  const extra = (id: number, home: string, away: string, league: string, time: string): V4FixtureCard =>
    card({ id, league, date: today, time, home, away, mostLikely: ['HOME', '1', 0.45], xg: [1.4, 1.1], uncertainty: [0.3, 'media'], lineups: 'probabili' })
  const others = [
    extra(101, 'Atalanta', 'Fiorentina', 'I1', '18:00'),
    extra(102, 'Villarreal', 'Sevilla', 'SP1', '16:15'),
    extra(103, 'Lyon', 'Lille', 'F1', '17:00'),
    extra(104, 'Feyenoord', 'Utrecht', 'N1', '14:30'),
    extra(105, 'Club Brugge', 'Genk', 'B1', '18:30'),
    extra(106, 'Sporting', 'Benfica', 'P1', '20:30'),
    extra(107, 'Leverkusen', 'Stuttgart', 'D1', '15:30'),
    extra(108, 'Palermo', 'Venezia', 'I2', '15:00'),
    extra(109, 'Hamburg', 'Köln', 'D2', '13:30'),
    extra(110, 'Real Sociedad', 'Betis', 'SP1', '18:30'),
    extra(111, 'Ipswich', 'Norwich', 'E1', '12:30'),
    extra(112, 'Trabzonspor', 'Beşiktaş', 'T1', '19:00'),
    extra(113, 'Saint-Étienne', 'Metz', 'F2', '19:00'),
    extra(114, 'Wrexham', 'Bolton', 'E2', '15:00'),
  ]
  const stat = (side: 'home' | 'away', line: string, p: number, q: number, profit: number, team: string) =>
    row(
      `STAT:sot:${side}:over:${line}`,
      `${team} over ${line.replace('.', ',')} tiri in porta`,
      p,
      round(p - 0.06, 2),
      round(p + 0.06, 2),
      q,
      round(q + 0.03, 2),
      'giocabile',
      { p_prudent: round((1 + profit) / q, 3), expected_profit: profit },
    )
  const classic = (key: string, label: string, p: number, q: number, profit: number) =>
    row(key, label, p, round(p - 0.05, 2), round(p + 0.05, 2), q, round(q + 0.04, 2), 'giocabile', { p_prudent: round((1 + profit) / q, 3), expected_profit: profit })

  const items: V4ShortlistItem[] = [
    slItem(1, fx(12), INTER_SOT_65, 'confermata'),
    slItem(2, others[0], stat('home', '5.5', 0.64, 1.8, 0.09, 'Atalanta'), 'confermata'),
    slItem(3, others[1], classic('OVER_2_5', 'Over 2,5 gol', 0.6, 1.85, 0.08), 'confermata'),
    slItem(4, fx(14), NAPOLI_SOT_45, 'regolata', { result: 'vinta', clv: 0.04 }),
    slItem(5, others[2], stat('home', '4.5', 0.6, 1.85, 0.07, 'Lyon'), 'ritirata', {
      withdraw_reason: 'Formazione ufficiale: Lacazette non titolare',
    }),
    slItem(6, fx(17), BAYERN_AH, 'confermata'),
    slItem(7, others[3], stat('home', '6.5', 0.58, 1.9, 0.065, 'Feyenoord'), 'regolata', { result: 'persa', clv: -0.01 }),
    slItem(8, others[4], classic('HOME', '1', 0.5, 2.15, 0.06), 'confermata'),
    slItem(9, others[5], stat('away', '4.5', 0.59, 1.8, 0.055, 'Benfica'), 'confermata'),
    slItem(10, others[6], stat('home', '5.5', 0.6, 1.76, 0.05, 'Leverkusen'), 'regolata', { result: 'void', clv: 0.0 }),
    slItem(11, others[7], classic('UNDER_2_5', 'Under 2,5 gol', 0.58, 1.82, 0.048), 'confermata'),
    slItem(12, others[8], stat('home', '4.5', 0.61, 1.72, 0.045, 'Hamburg'), 'regolata', { result: 'vinta', clv: 0.03 }),
    slItem(13, others[9], classic('X_TWO', 'X2', 0.7, 1.5, 0.042), 'confermata'),
    slItem(14, others[10], stat('home', '4.5', 0.6, 1.75, 0.04, 'Ipswich'), 'regolata', { result: 'persa', clv: 0.02 }),
    slItem(15, others[11], stat('home', '3.5', 0.68, 1.55, 0.038, 'Trabzonspor'), 'confermata'),
    slItem(16, others[12], classic('OVER_1_5', 'Over 1,5 gol', 0.78, 1.34, 0.036), 'confermata'),
    slItem(17, others[13], stat('home', '4.5', 0.58, 1.8, 0.034, 'Wrexham'), 'provvisoria'),
    slItem(18, fx(15), ARSENAL_SOT, 'provvisoria'),
  ]
  return {
    date: today,
    status: 'confermata',
    sealed_at: romeToIso(today, '11:30'),
    digest: 'sha256:abcd1234ef567890aa11bb22cc33dd44ee55ff6600112233445566778899aabb',
    items,
    advised: false,
    banner: 'Esame E4 non superato: giocate classiche in osservazione, non consigliate',
    abstentions: [
      { reason: 'prezzo_giusto', label: 'prezzo giusto', count: 6, examples: ['Como - Cagliari', 'Arsenal - Chelsea', 'Genoa - Cremonese'] },
      { reason: 'incertezza_alta', label: 'incertezza alta', count: 3, examples: ['Getafe - Osasuna'] },
      { reason: 'formazioni_non_note', label: 'formazioni non note', count: 2, examples: ['Leeds - Sunderland'] },
      { reason: 'non_quotato', label: 'mercato non quotato', count: 1, examples: ['Galatasaray - Fenerbahçe'] },
    ],
  }
}

// --- Misura e motore --------------------------------------------------------------------------------------

export const MOCK_MEASURE: V4MeasureSummary = {
  by_league: [
    { league_code: 'I1', plays: 14, profit_units: 0.57, roi: 0.041, roi_lo: -0.02, roi_hi: 0.1, clv: 0.031, alarm: false },
    { league_code: 'E0', plays: 11, profit_units: -0.42, roi: -0.038, roi_lo: -0.11, roi_hi: 0.03, clv: 0.012, alarm: false },
    { league_code: 'D1', plays: 9, profit_units: 0.2, roi: 0.022, roi_lo: -0.06, roi_hi: 0.1, clv: 0.02, alarm: false },
    { league_code: 'SP1', plays: 8, profit_units: -0.56, roi: -0.07, roi_lo: -0.15, roi_hi: 0.01, clv: -0.004, alarm: false },
    { league_code: 'F1', plays: 10, profit_units: 0.15, roi: 0.015, roi_lo: -0.07, roi_hi: 0.09, clv: 0.028, alarm: false },
    { league_code: 'F2', plays: 10, profit_units: -0.62, roi: -0.062, roi_lo: -0.14, roi_hi: 0.02, clv: -0.011, alarm: true },
  ],
  by_market: [
    { market_family: 'STAT_sot', label: 'Tiri in porta', plays: 31, profit_units: 0.56, roi: 0.018, roi_lo: -0.03, roi_hi: 0.06, clv: 0.034, alarm: false },
    { market_family: 'FT_OVER_UNDER', label: 'Over/Under gol', plays: 12, profit_units: -0.25, roi: -0.021, roi_lo: -0.09, roi_hi: 0.04, clv: 0.008, alarm: false },
    { market_family: 'AH', label: 'Handicap asiatico', plays: 9, profit_units: -0.5, roi: -0.055, roi_lo: -0.14, roi_hi: 0.03, clv: 0.002, alarm: false },
    { market_family: 'STAT_corners', label: 'Corner', plays: 10, profit_units: -0.4, roi: -0.04, roi_lo: -0.12, roi_hi: 0.03, clv: -0.009, alarm: true },
  ],
  totals: { plays: 62, profit_units: -0.74, roi: -0.012, roi_lo: -0.04, roi_hi: 0.018, clv: 0.021 },
  alerts: [
    {
      scope: 'market',
      key: 'STAT_corners',
      plays: 30,
      alarm_at: '2026-09-12T21:30:00Z',
      roi: -0.04,
      sentence: 'CUSUM oltre la soglia: dieci giocate consecutive con CLV negativo, ritiro proposto il 27/09.',
    },
  ],
  postmortem: [
    'I tiri in porta restano il gruppo migliore: CLV medio +3,4% su 31 giocate.',
    "L'handicap asiatico paga il prezzo di due rimonte nel finale: nessun segnale di modello sbagliato.",
    'Quota di esiti sfortunati (gol attesi a favore, giocata persa): 4 su 62.',
  ],
}

export const MOCK_EXAMS: V4Exam[] = [
  {
    code: 'E1',
    title: 'Motore gol contro V3 Fase 4',
    passed: true,
    preregistration: 'docs/v4/PREREGISTRAZIONE_FASE_1.md',
    result: {
      stagioni: '2022/23, 2023/24, 2024/25',
      brier: { v4: 0.2041, v3: 0.2063 },
      log_loss: { v4: 0.5921, v3: 0.5968 },
      calibrazione_non_peggiore: true,
      incertezza_predice_errore: true,
    },
    computed_at: '2026-09-18T16:20:00Z',
  },
  {
    code: 'E2',
    title: 'Motore statistiche: baseline e test oltre il mercato',
    passed: false,
    preregistration: 'docs/v4/PREREGISTRAZIONE_FASE_2.md',
    result: {
      tiri_in_porta: 'superato',
      tiri: 'superato',
      corner: 'non_superato',
      cartellini: 'in_attesa',
      coefficiente_modello_sot: { '2022/23': 0.41, '2023/24': 0.38, '2024/25': 0.44 },
      coefficiente_modello_corner: { '2022/23': 0.12, '2023/24': -0.03, '2024/25': 0.08 },
    },
    computed_at: '2026-09-19T09:05:00Z',
  },
  {
    code: 'E4',
    title: 'Regola del profitto sui mercati classici con quote storiche',
    passed: null,
    preregistration: 'docs/v4/PREREGISTRAZIONE_FASE_4.md',
    result: {},
    computed_at: null,
  },
]

export const MOCK_CHALLENGERS: V4Challenger[] = [
  {
    name: 'Indice di assenza',
    status: 'candidato',
    description: 'Plus-minus regolarizzato sui minuti dei giocatori, ricalcolo alle formazioni ufficiali.',
    exam: { code: 'E5.1', computed_at: null },
  },
  {
    name: 'Motivazione da classifica',
    status: 'candidato',
    description: 'Punti da salvezza, promozione o playoff in walk-forward.',
    exam: { code: 'E5.2', computed_at: null },
  },
  {
    name: 'Boosting sui residui',
    status: 'non_superato',
    description: 'Gradient boosting sui residui del motore gol.',
    exam: {
      code: 'E5.5',
      result: { brier_sfidante: 0.2049, brier_campione: 0.2041, stagioni_migliori: 1, stagioni_totali: 3 },
      computed_at: '2026-09-19T12:40:00Z',
    },
  },
]

function coverage(): V4CoverageRow[] {
  return V4_LEAGUES.map((l) => ({
    league_code: l.code,
    markets: {
      FT_1X2: true,
      FT_OVER_UNDER: true,
      DOUBLE_CHANCE: true,
      HT_1X2: l.tier <= 2,
      AH: l.tier <= 2,
      'STAT:sot': l.tier === 1,
      'STAT:shots': ['E0', 'I1', 'SP1', 'D1', 'F1'].includes(l.code),
      'STAT:corners': l.tier <= 2 && l.code !== 'T1',
      'STAT:cards': l.tier === 1 && l.code !== 'T1' && l.code !== 'B1',
      'STAT:fouls': false,
    },
  }))
}

function quality(): V4QualityRow[] {
  return V4_LEAGUES.map((l, i) => ({
    league_code: l.code,
    fixtures: l.tier === 1 ? 30 + (i % 3) * 10 : 36 + (i % 4) * 12,
    missing_stats_pct: round(l.tier === 1 ? 0.4 + (i % 3) * 0.4 : 2.1 + (i % 4) * 1.3, 1),
    missing_lineups_pct: round(l.tier === 1 ? 4.0 : 11.5 + (i % 3) * 2, 1),
    missing_odds_pct: round(l.tier === 1 ? 0 : 1.2 + (i % 2) * 0.9, 1),
  }))
}

function engineData(today: string): V4EngineData {
  return {
    coverage: coverage(),
    quality: quality(),
    api_budget: { date: today, calls: 412, stop_at: 7000 },
    odds_registry: { snapshots_today: 96, last_taken_at: romeToIso(today, '14:00') },
  }
}

// --- Il client mock -----------------------------------------------------------------------------------------

let cached: Dataset | null = null

export function mockDataset(): Dataset {
  const today = todayLocalIso()
  if (!cached || cached.today !== today) cached = buildDataset(today)
  return cached
}

function abortError(): Error {
  const e = new Error('Richiesta annullata')
  e.name = 'AbortError'
  return e
}

function respond<T>(signal: AbortSignal | undefined, produce: () => T): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError())
      return
    }
    const t = setTimeout(() => {
      if (signal?.aborted) reject(abortError())
      else resolve(produce())
    }, 0)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(abortError())
    })
  })
}

function applyFilters(items: V4FixtureCard[], q: V4FixturesQuery): V4FixtureCard[] {
  let out = items
  if (q.league) out = out.filter((f) => f.league_code === q.league)
  if (q.only_plays) out = out.filter((f) => f.best_play != null)
  if (q.only_lineups) out = out.filter((f) => f.lineups_status !== 'non_note')
  out = [...out]
  if (q.sort === 'profit') {
    out.sort((a, b) => (b.best_play?.expected_profit ?? -1) - (a.best_play?.expected_profit ?? -1))
  } else {
    out.sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at))
  }
  return out
}

export const mockCecchinoV4Api: CecchinoV4Api = {
  getDays: (params, signal) =>
    respond(signal, () => {
      const ds = mockDataset()
      const n = params.days ?? 7
      const start = ds.days.days.findIndex((d) => d.date === params.from)
      const from = start >= 0 ? start : 0
      return { days: ds.days.days.slice(from, from + n) }
    }),
  getFixtures: (params, signal) =>
    respond<V4FixturesResponse>(signal, () => {
      const ds = mockDataset()
      const all = ds.fixturesByDate.get(params.date) ?? []
      const abstentions: Record<string, number> = {}
      for (const f of all) {
        if (f.best_play) continue
        const r = f.no_play_reason ?? 'prezzo_giusto'
        abstentions[r] = (abstentions[r] ?? 0) + 1
      }
      return { date: params.date, items: applyFilters(all, params), abstentions }
    }),
  getFixtureDetail: (id, signal) =>
    respond(signal, () => {
      const detail = mockDataset().details.get(id)
      if (!detail) throw new Error(`Partita ${id} non trovata`)
      return detail
    }),
  getShortlist: (date, signal) =>
    respond<V4ShortlistResponse>(signal, () => {
      const ds = mockDataset()
      if (date === ds.today) return ds.shortlist
      const items = (ds.fixturesByDate.get(date) ?? [])
        .filter((f) => f.best_play)
        .map((f, i) => slItem(i + 1, f, f.best_play as V4MarketRow, 'provvisoria'))
      return { date, status: 'provvisoria', sealed_at: null, digest: null, items, abstentions: [] }
    }),
  getMeasureSummary: (_params, signal) => respond(signal, () => MOCK_MEASURE),
  getExams: (signal) => respond(signal, () => ({ items: MOCK_EXAMS })),
  getChallengers: (signal) => respond<V4ChallengersResponse>(signal, () => ({ items: MOCK_CHALLENGERS })),
  getEngineData: (signal) => respond(signal, () => engineData(mockDataset().today)),
}
