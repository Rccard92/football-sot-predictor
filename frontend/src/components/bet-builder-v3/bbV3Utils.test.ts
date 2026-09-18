import { describe, expect, it } from 'vitest'
import type { BbV3FixtureItem, BbV3Prediction } from '../../lib/cecchinoBetBuilderV3Api'
import { DEFAULT_BB_V3_FILTERS, buildGroups, fixturesCovered, opportunitiesFor, tally } from './bbV3Utils'

function pred(market_key: string, score: number, extra: Partial<BbV3Prediction> = {}): BbV3Prediction {
  return {
    market_key,
    family: market_key.startsWith('OVER') || market_key.startsWith('UNDER') ? 'gol' : 'esito',
    score,
    probability: 0.6,
    base_rate: 0.45,
    quota: 1.9,
    min_quota: 1.67,
    playable: true,
    pattern: 'senza_pattern',
    pattern_info: null,
    won: null,
    ...extra,
  }
}

function item(id: number, v25: BbV3Prediction[], v3: BbV3Prediction[] | null, combo: BbV3FixtureItem['combo'] = []): BbV3FixtureItem {
  const block = (predictions: BbV3Prediction[]) => ({
    available: true,
    status: 'open',
    frozen_at: null,
    predictions,
    patterns: [],
  })
  return {
    fixture: {
      today_fixture_id: id,
      scan_date: '2026-09-18',
      kickoff: `2026-09-18T1${id % 10}:00:00Z`,
      country: 'Brasile',
      league: 'Serie B',
      home: { name: `Casa ${id}`, logo: null },
      away: { name: `Ospite ${id}`, logo: null },
      match_status: 'upcoming',
      score: null,
    },
    models: { 'V2.5': block(v25), V3: v3 ? block(v3) : null },
    combo,
  }
}

const ITEMS: BbV3FixtureItem[] = [
  item(1, [pred('HOME', 82, { pattern: 'confermata' }), pred('OVER_2_5', 75, { quota: 1.3, playable: false })], null),
  item(
    2,
    [pred('AWAY', 71, { won: true, quota: 2.5 })],
    [pred('AWAY', 90, { won: true, quota: 2.4 })],
    [
      {
        market_key: 'AWAY',
        family: 'esito',
        score: 71,
        score_v25: 71,
        score_v3: 90,
        quota: 2.4,
        min_quota: 1.4,
        playable: true,
        pattern_v25: 'senza_pattern',
        pattern_v3: 'confermata',
        won: true,
      },
    ],
  ),
]

describe('bbV3Utils', () => {
  it('ogni scheda legge solo il suo modello', () => {
    expect(opportunitiesFor(ITEMS[0], 'V2.5').map((o) => o.marketKey)).toEqual(['HOME', 'OVER_2_5'])
    expect(opportunitiesFor(ITEMS[0], 'V3')).toEqual([])
    expect(opportunitiesFor(ITEMS[1], 'combo')[0].scoreV3).toBe(90)
  })

  it('partite analizzate: combo solo dove ci sono entrambi i modelli', () => {
    expect(fixturesCovered(ITEMS, 'V2.5')).toBe(2)
    expect(fixturesCovered(ITEMS, 'V3')).toBe(1)
    expect(fixturesCovered(ITEMS, 'combo')).toBe(1)
  })

  it('filtro indice + pattern d’accordo e solo giocabili', () => {
    const agree = buildGroups(ITEMS, 'V2.5', { ...DEFAULT_BB_V3_FILTERS, patternAgree: true })
    expect(agree.map((g) => g.opportunities.map((o) => o.marketKey))).toEqual([['HOME']])
    const playable = buildGroups(ITEMS, 'V2.5', { ...DEFAULT_BB_V3_FILTERS, playableOnly: true })
    expect(playable.flatMap((g) => g.opportunities.map((o) => o.marketKey))).toEqual(['HOME', 'AWAY'])
    const comboAgree = buildGroups(ITEMS, 'combo', { ...DEFAULT_BB_V3_FILTERS, patternAgree: true })
    expect(comboAgree).toHaveLength(1) // confermata dal pattern V3
  })

  it('ordina per punteggio migliore della partita', () => {
    const groups = buildGroups(ITEMS, 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(groups.map((g) => g.fixture.today_fixture_id)).toEqual([1, 2])
  })

  it('riepilogo: vinte, perse, in attesa e ROI a 1 unità', () => {
    const t = tally(buildGroups(ITEMS, 'V2.5', DEFAULT_BB_V3_FILTERS))
    expect(t).toMatchObject({ opportunities: 3, playable: 2, closed: 1, won: 1, pending: 2, priced: 1 })
    expect(t.roiPct).toBeCloseTo(150)
  })
})

describe('bbV3Utils · solo pattern', () => {
  const withPatterns: BbV3FixtureItem = {
    ...item(3, [pred('HOME', 80)], null),
  }
  withPatterns.models['V2.5']!.patterns = [
    {
      market_key: 'HOME',
      family: 'esito',
      patterns_count: 1,
      hist_win_pct: 55,
      hist_roi_pct: 6,
      quota: 1.9,
      playable: true,
      index_score: 80,
      index_probability: 0.6,
      index_base_rate: 0.45,
      index_relation: 'confermato',
      won: null,
    },
    {
      market_key: 'UNDER_2_5',
      family: 'gol',
      patterns_count: 3,
      hist_win_pct: 62,
      hist_roi_pct: 9,
      quota: 1.7,
      playable: true,
      index_score: 58,
      index_probability: 0.5,
      index_base_rate: 0.48,
      index_relation: 'indice_altri_mercati',
      won: false,
    },
  ]

  it('mostra i pattern accesi, prima quelli con più pattern concordi', () => {
    const groups = buildGroups([withPatterns], 'V2.5', DEFAULT_BB_V3_FILTERS, 'pattern')
    expect(groups[0].opportunities.map((o) => o.marketKey)).toEqual(['UNDER_2_5', 'HOME'])
    expect(groups[0].opportunities[0].score).toBe(58) // il cerchio mostra l'indice sul mercato del pattern
  })

  it('pattern + indice d’accordo = indice conferma lo stesso mercato', () => {
    const groups = buildGroups([withPatterns], 'V2.5', { ...DEFAULT_BB_V3_FILTERS, patternAgree: true }, 'pattern')
    expect(groups[0].opportunities.map((o) => o.marketKey)).toEqual(['HOME'])
  })

  it('la modalità indice non cambia', () => {
    const groups = buildGroups([withPatterns], 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(groups[0].opportunities.map((o) => o.marketKey)).toEqual(['HOME'])
  })
})
