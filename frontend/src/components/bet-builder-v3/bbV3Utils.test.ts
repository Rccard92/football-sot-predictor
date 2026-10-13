import { describe, expect, it } from 'vitest'
import type { BbV3FixtureItem, BbV3Prediction } from '../../lib/cecchinoBetBuilderV3Api'
import {
  DEFAULT_BB_V3_FILTERS,
  buildGroups,
  familyCounts,
  fixturesCovered,
  marketOptions,
  oppositeAlerts,
  opportunitiesFor,
  pickEvidenceKey,
  tally,
} from './bbV3Utils'

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

describe('scelta del singolo mercato (come il vecchio Bet Builder)', () => {
  it('elenca i mercati presenti in ordine 1, X, 2, gol, con il numero di opportunità', () => {
    const opts = marketOptions(ITEMS, 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(opts.map((o) => o.key)).toEqual(['HOME', 'AWAY', 'OVER_2_5'])
    expect(opts.find((o) => o.key === 'HOME')?.label).toBe('1')
    expect(opts.every((o) => o.count >= 1)).toBe(true)
  })

  it('filtra le opportunità sul mercato scelto e i conteggi delle famiglie restano completi', () => {
    const f = { ...DEFAULT_BB_V3_FILTERS, market: 'AWAY' }
    const groups = buildGroups(ITEMS, 'V2.5', f)
    expect(groups.flatMap((g) => g.opportunities.map((o) => o.marketKey))).toEqual(['AWAY'])
    const all = familyCounts(ITEMS, 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(familyCounts(ITEMS, 'V2.5', f)).toEqual(all)
    const t = tally(groups)
    expect(t.won).toBe(1)
    expect(t.roiPct).toBeCloseTo(150)
  })

  it('la famiglia restringe la lista dei mercati', () => {
    const opts = marketOptions(ITEMS, 'V2.5', { ...DEFAULT_BB_V3_FILTERS, family: 'gol' })
    expect(opts.map((o) => o.key)).toEqual(['OVER_2_5'])
  })
})

describe('decisioni di Giovanni del 13/10/2026', () => {
  it('giocabile da 1,41: 1,41 sì, 1,40 no', () => {
    const it41 = item(50, [pred('HOME', 80, { quota: 1.41, playable: false }), pred('AWAY', 80, { quota: 1.4, playable: true })], null)
    const ops = opportunitiesFor(it41, 'V2.5')
    expect(ops.find((o) => o.marketKey === 'HOME')?.playable).toBe(true)
    expect(ops.find((o) => o.marketKey === 'AWAY')?.playable).toBe(false)
  })

  it('in evidenza: probabilità più alta tra le giocate con quota >= 1,41 e non sotto la quota minima', () => {
    const it2 = item(
      51,
      [
        pred('OVER_3_5', 100, { probability: 0.48, quota: 2.2, min_quota: 2.08 }),
        pred('OVER_2_5', 80, { probability: 0.72, quota: 1.5, min_quota: 1.39 }),
        pred('OVER_1_5', 76, { probability: 0.88, quota: 1.14, min_quota: 1.14 }),
      ],
      null,
    )
    const ops = opportunitiesFor(it2, 'V2.5')
    // Over 1.5 ha la probabilità più alta ma quota sotto 1,41; Over 2.5 batte Over 3.5 anche con voto più basso
    expect(pickEvidenceKey(ops)).toBe(ops.find((o) => o.marketKey === 'OVER_2_5')?.key)
    const [g] = buildGroups([it2], 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(g.opportunities[0].marketKey).toBe('OVER_2_5')
    expect(g.opportunities[0].evidence).toBe(true)
    expect(g.opportunities.filter((o) => o.evidence)).toHaveLength(1)
  })

  it('nessuna evidenza se nessuna giocata regge quota minima e soglia', () => {
    const it3 = item(52, [pred('HOME', 90, { probability: 0.6, quota: 1.5, min_quota: 1.67 })], null)
    const [g] = buildGroups([it3], 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(g.opportunities[0].evidence).toBe(false)
  })

  it('il filtro mercato non sposta l’evidenza della partita', () => {
    const it4 = item(
      53,
      [pred('HOME', 80, { probability: 0.62, quota: 1.9, min_quota: 1.61 }), pred('OVER_2_5', 75, { probability: 0.55, quota: 2, min_quota: 1.82 })],
      null,
    )
    const [g] = buildGroups([it4], 'V2.5', { ...DEFAULT_BB_V3_FILTERS, market: 'OVER_2_5' })
    expect(g.opportunities).toHaveLength(1)
    expect(g.opportunities[0].evidence).toBe(false)
  })

  it('avviso mercati opposti quando entrambi sono predizioni', () => {
    expect(oppositeAlerts(['HOME_PT', 'AWAY_PT', 'OVER_2_5'])).toEqual(['1 primo tempo e 2 primo tempo'])
    expect(oppositeAlerts(['OVER_2_5', 'UNDER_3_5'])).toEqual([])
    const it5 = item(54, [pred('HOME', 75), pred('AWAY', 72)], null)
    const [g] = buildGroups([it5], 'V2.5', DEFAULT_BB_V3_FILTERS)
    expect(g.alerts).toEqual(['1 e 2'])
  })
})
