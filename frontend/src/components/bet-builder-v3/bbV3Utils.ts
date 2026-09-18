import type {
  BbV3Family,
  BbV3Fixture,
  BbV3FixtureItem,
  BbV3IndexRelation,
  BbV3PatternRelation,
} from '../../lib/cecchinoBetBuilderV3Api'
import { MARKET_LABELS } from '../../lib/masterPatternApi'

export type BbV3Tab = 'V2.5' | 'V3' | 'combo'
/** V2.5/V3: giocate dell'indice (predefinito) oppure solo i pattern accesi. */
export type BbV3Source = 'index' | 'pattern'

export const BB_V3_TABS: { key: BbV3Tab; label: string }[] = [
  { key: 'V2.5', label: 'V2.5' },
  { key: 'V3', label: 'V3' },
  { key: 'combo', label: 'Combo' },
]

/** Una giocata consigliata, uguale per V2.5, V3 e Combo. */
export type BbV3Opportunity = {
  key: string
  source: BbV3Source
  todayFixtureId: number
  marketKey: string
  label: string
  family: BbV3Family
  /** Punteggio dell'indice sul mercato (nel cerchio). Pattern: null se l'indice non c'e'. */
  score: number | null
  /** Ordine: punteggio per l'indice, pattern concordi e riuscita storica per i pattern. */
  rank: number
  quota: number | null
  minQuota: number | null
  playable: boolean
  probability: number | null
  baseRate: number | null
  /** V2.5/V3: relazione col pattern del modello. Combo: null (vedi patternV25/patternV3). */
  pattern: BbV3PatternRelation | null
  patternInfo: { patterns_count: number; hist_win_pct: number | null; hist_roi_pct: number | null } | null
  scoreV25: number | null
  scoreV3: number | null
  patternV25: BbV3PatternRelation | null
  patternV3: BbV3PatternRelation | null
  /** Solo pattern: cosa dice l'indice dello stesso modello su questo mercato. */
  indexRelation: BbV3IndexRelation | null
  won: boolean | null
}

export type BbV3Group = { fixture: BbV3Fixture; opportunities: BbV3Opportunity[] }

export type BbV3FamilyFilter = 'all' | BbV3Family
export type BbV3SortKey = 'score_desc' | 'kickoff_asc' | 'quota_desc'
export type BbV3OutcomeFilter = 'all' | 'won' | 'lost' | 'pending'

export type BbV3Filters = {
  family: BbV3FamilyFilter
  search: string
  /** Indice e pattern d'accordo: il mercato ha un pattern acceso che lo conferma. */
  patternAgree: boolean
  playableOnly: boolean
  country: string
  league: string
  minScore: number | null
  sort: BbV3SortKey
  outcome: BbV3OutcomeFilter
}

export const DEFAULT_BB_V3_FILTERS: BbV3Filters = {
  family: 'all',
  search: '',
  patternAgree: false,
  playableOnly: false,
  country: '',
  league: '',
  minScore: null,
  sort: 'score_desc',
  outcome: 'all',
}

export const FAMILY_CHIPS: { key: BbV3FamilyFilter; label: string }[] = [
  { key: 'all', label: 'Tutti' },
  { key: 'esito', label: 'Esito finale' },
  { key: 'gol', label: 'Gol' },
  { key: 'primo_tempo', label: 'Primo tempo' },
]

export function marketLabel(key: string): string {
  return MARKET_LABELS[key] ?? key
}

/** Opportunita' di una partita per la scheda scelta (V2.5, V3 o Combo). */
export function opportunitiesFor(item: BbV3FixtureItem, tab: BbV3Tab, source: BbV3Source = 'index'): BbV3Opportunity[] {
  const fid = item.fixture.today_fixture_id
  if (tab === 'combo') {
    return item.combo.map((c) => ({
      key: `${fid}:combo:${c.market_key}`,
      source: 'index' as const,
      todayFixtureId: fid,
      marketKey: c.market_key,
      label: marketLabel(c.market_key),
      family: c.family,
      score: c.score,
      rank: c.score,
      quota: c.quota,
      minQuota: c.min_quota,
      playable: c.playable,
      probability: null,
      baseRate: null,
      pattern: null,
      patternInfo: null,
      scoreV25: c.score_v25,
      scoreV3: c.score_v3,
      patternV25: c.pattern_v25,
      patternV3: c.pattern_v3,
      indexRelation: null,
      won: c.won,
    }))
  }
  const block = item.models[tab]
  if (source === 'pattern') {
    return (block?.patterns ?? []).map((p) => ({
      key: `${fid}:${tab}:pattern:${p.market_key}`,
      source: 'pattern' as const,
      todayFixtureId: fid,
      marketKey: p.market_key,
      label: marketLabel(p.market_key),
      family: p.family,
      score: p.index_score,
      rank: p.patterns_count * 1000 + (p.hist_win_pct ?? 0),
      quota: p.quota,
      minQuota: p.hist_win_pct ? Math.round((10000 / p.hist_win_pct)) / 100 : null,
      playable: p.playable,
      probability: p.index_probability,
      baseRate: p.index_base_rate,
      pattern: 'confermata' as const,
      patternInfo: { patterns_count: p.patterns_count, hist_win_pct: p.hist_win_pct, hist_roi_pct: p.hist_roi_pct },
      scoreV25: null,
      scoreV3: null,
      patternV25: null,
      patternV3: null,
      indexRelation: p.index_relation,
      won: p.won,
    }))
  }
  if (!block?.available) return []
  return block.predictions.map((p) => ({
    key: `${fid}:${tab}:${p.market_key}`,
    source: 'index' as const,
    todayFixtureId: fid,
    marketKey: p.market_key,
    label: marketLabel(p.market_key),
    family: p.family,
    score: p.score,
    rank: p.score,
    quota: p.quota,
    minQuota: p.min_quota,
    playable: p.playable,
    probability: p.probability,
    baseRate: p.base_rate,
    pattern: p.pattern,
    patternInfo: p.pattern_info,
    scoreV25: tab === 'V2.5' ? p.score : null,
    scoreV3: tab === 'V3' ? p.score : null,
    patternV25: tab === 'V2.5' ? p.pattern : null,
    patternV3: tab === 'V3' ? p.pattern : null,
    indexRelation: null,
    won: p.won,
  }))
}

/** Partite che il modello (o entrambi, per Combo) ha analizzato. */
export function fixturesCovered(items: BbV3FixtureItem[], tab: BbV3Tab, source: BbV3Source = 'index'): number {
  return items.filter((i) => {
    if (tab === 'combo') return i.models['V2.5']?.available && i.models.V3?.available
    return source === 'pattern' ? i.models[tab] != null : i.models[tab]?.available
  }).length
}

/** Indice e pattern d'accordo sullo stesso mercato (visto dall'indice o dal pattern). */
export function isPatternAgree(o: BbV3Opportunity): boolean {
  if (o.source === 'pattern') return o.indexRelation === 'confermato'
  return o.pattern === 'confermata' || o.patternV25 === 'confermata' || o.patternV3 === 'confermata'
}

function matchesSearch(f: BbV3Fixture, q: string): boolean {
  if (!q.trim()) return true
  const needle = q.trim().toLowerCase()
  return [f.home.name, f.away.name, f.league, f.country].some((v) => (v ?? '').toLowerCase().includes(needle))
}

export function passesFilters(o: BbV3Opportunity, f: BbV3Filters): boolean {
  if (f.family !== 'all' && o.family !== f.family) return false
  if (f.patternAgree && !isPatternAgree(o)) return false
  if (f.playableOnly && !o.playable) return false
  if (f.minScore != null && (o.score == null || o.score < f.minScore)) return false
  if (f.outcome === 'won' && o.won !== true) return false
  if (f.outcome === 'lost' && o.won !== false) return false
  if (f.outcome === 'pending' && o.won != null) return false
  return true
}

export function buildGroups(
  items: BbV3FixtureItem[],
  tab: BbV3Tab,
  f: BbV3Filters,
  source: BbV3Source = 'index',
): BbV3Group[] {
  const groups: BbV3Group[] = []
  for (const item of items) {
    const fx = item.fixture
    if (f.country && fx.country !== f.country) continue
    if (f.league && fx.league !== f.league) continue
    if (!matchesSearch(fx, f.search)) continue
    const opportunities = opportunitiesFor(item, tab, source)
      .filter((o) => passesFilters(o, f))
      .sort((a, b) => b.rank - a.rank || Number(b.playable) - Number(a.playable))
    if (opportunities.length) groups.push({ fixture: fx, opportunities })
  }
  const best = (g: BbV3Group) => g.opportunities[0]
  groups.sort((a, b) => {
    if (f.sort === 'kickoff_asc') return (a.fixture.kickoff ?? '').localeCompare(b.fixture.kickoff ?? '')
    if (f.sort === 'quota_desc') return (best(b).quota ?? 0) - (best(a).quota ?? 0)
    return best(b).rank - best(a).rank || (a.fixture.kickoff ?? '').localeCompare(b.fixture.kickoff ?? '')
  })
  return groups
}

/** Conteggi per chip famiglia, con tutti i filtri tranne la famiglia stessa. */
export function familyCounts(
  items: BbV3FixtureItem[],
  tab: BbV3Tab,
  f: BbV3Filters,
  source: BbV3Source = 'index',
): Record<BbV3FamilyFilter, number> {
  const out: Record<BbV3FamilyFilter, number> = { all: 0, esito: 0, gol: 0, primo_tempo: 0 }
  for (const g of buildGroups(items, tab, { ...f, family: 'all' }, source)) {
    for (const o of g.opportunities) {
      out.all += 1
      out[o.family] += 1
    }
  }
  return out
}

export type BbV3Tally = {
  opportunities: number
  playable: number
  closed: number
  won: number
  lost: number
  pending: number
  winPct: number | null
  profit: number
  roiPct: number | null
  priced: number
}

/** Profitto a 1 unita' per giocata alla quota registrata prima della partita. */
export function tally(groups: BbV3Group[]): BbV3Tally {
  const t: BbV3Tally = {
    opportunities: 0,
    playable: 0,
    closed: 0,
    won: 0,
    lost: 0,
    pending: 0,
    winPct: null,
    profit: 0,
    roiPct: null,
    priced: 0,
  }
  for (const g of groups) {
    for (const o of g.opportunities) {
      t.opportunities += 1
      if (o.playable) t.playable += 1
      if (o.won == null) {
        t.pending += 1
        continue
      }
      t.closed += 1
      if (o.won) t.won += 1
      else t.lost += 1
      if (o.quota != null) {
        t.priced += 1
        t.profit += o.won ? o.quota - 1 : -1
      }
    }
  }
  t.winPct = t.closed ? (100 * t.won) / t.closed : null
  t.roiPct = t.priced ? (100 * t.profit) / t.priced : null
  t.profit = Math.round(t.profit * 100) / 100
  return t
}

export function sampleLabel(closed: number): string {
  if (closed < 100) return 'presto per dirlo'
  if (closed < 300) return 'indicativo'
  return 'affidabile'
}

export const PATTERN_RELATION_LABEL: Record<BbV3PatternRelation, string> = {
  confermata: 'Confermata dal pattern',
  in_contrasto: 'In contrasto col pattern',
  altri_pattern: 'Pattern su altri mercati',
  senza_pattern: 'Nessun pattern acceso',
}

export const INDEX_RELATION_LABEL: Record<BbV3IndexRelation, string> = {
  confermato: 'Confermato dall’indice',
  in_contrasto: 'In contrasto con l’indice',
  indice_altri_mercati: 'Indice su altri mercati',
  nessuna_predizione: 'Nessuna predizione dell’indice',
  indice_non_disponibile: 'Indice non disponibile',
}

export function uniqueSorted(values: (string | null | undefined)[]): string[] {
  return [...new Set(values.filter((v): v is string => Boolean(v)))].sort((a, b) => a.localeCompare(b, 'it'))
}

export type BbV3Period = 'today' | 'yesterday' | 'last7' | 'all'

export const PERIOD_OPTIONS: { key: BbV3Period; label: string }[] = [
  { key: 'today', label: 'Oggi' },
  { key: 'yesterday', label: 'Ieri' },
  { key: 'last7', label: 'Ultimi 7 giorni' },
  { key: 'all', label: 'Tutto' },
]
