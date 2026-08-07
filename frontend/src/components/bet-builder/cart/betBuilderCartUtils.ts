/**
 * BET-03 — utils pure carrello schedina (composizione manuale).
 * Snapshot localStorage = UX only; dati analitici sempre dalla response BET-01 corrente.
 */

import type { BetBuilderOpportunity } from '../../../lib/cecchinoBetBuilderApi'

export const BET_BUILDER_CART_VERSION = 'bet_builder_cart_v1' as const

export const BET_BUILDER_CART_STORAGE_PREFIX = 'sot.betBuilder.cart.v1:'

export type BetBuilderCartTeamSnapshot = {
  name: string | null
  logo?: string | null
}

/** Snapshot persistito — non source-of-truth analitica. */
export type BetBuilderCartStoredItem = {
  date: string
  today_fixture_id: number
  opportunity_key: string
  market_key: string
  market_label: string
  home: BetBuilderCartTeamSnapshot
  away: BetBuilderCartTeamSnapshot
  country?: string | null
  league?: string | null
  added_at: string
  added_book_odds: number | null
  added_source_revision: string | null
}

export type BetBuilderCartState = {
  version: typeof BET_BUILDER_CART_VERSION
  date: string
  items: BetBuilderCartStoredItem[]
}

export type BetBuilderCartItemStatus = 'current' | 'stale'

export type BetBuilderCartResolvedItem = {
  stored: BetBuilderCartStoredItem
  status: BetBuilderCartItemStatus
  /** Opportunity live se current; null se stale. */
  current: BetBuilderOpportunity | null
  current_book_odds: number | null
  odds_changed: boolean
}

export type BetBuilderCartCtaKind = 'add' | 'added' | 'replace'

export type BetBuilderCartCtaState = {
  kind: BetBuilderCartCtaKind
  label: string
  ariaLabel: string
  bookOddsMissing: boolean
  existingLabel?: string
  incomingLabel?: string
}

export function cartStorageKey(date: string): string {
  return `${BET_BUILDER_CART_STORAGE_PREFIX}${date}`
}

function isFinitePositiveOdds(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

export function isValidBookOdds(value: number | null | undefined): value is number {
  return isFinitePositiveOdds(value)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseTeamSnapshot(value: unknown): BetBuilderCartTeamSnapshot | null {
  if (!isPlainObject(value)) return null
  const name = value.name
  if (name !== null && typeof name !== 'string') return null
  const logo = value.logo
  if (logo !== undefined && logo !== null && typeof logo !== 'string') return null
  return {
    name: typeof name === 'string' ? name : null,
    logo: typeof logo === 'string' ? logo : logo === null ? null : undefined,
  }
}

function parseStoredItem(value: unknown, expectedDate: string): BetBuilderCartStoredItem | null {
  if (!isPlainObject(value)) return null
  if (value.date !== expectedDate || typeof value.date !== 'string') return null
  if (typeof value.today_fixture_id !== 'number' || !Number.isFinite(value.today_fixture_id)) {
    return null
  }
  if (typeof value.opportunity_key !== 'string' || !value.opportunity_key) return null
  if (typeof value.market_key !== 'string' || !value.market_key) return null
  if (typeof value.market_label !== 'string') return null
  if (typeof value.added_at !== 'string') return null
  const home = parseTeamSnapshot(value.home)
  const away = parseTeamSnapshot(value.away)
  if (!home || !away) return null

  const addedBook = value.added_book_odds
  if (
    addedBook !== null &&
    addedBook !== undefined &&
    (typeof addedBook !== 'number' || !Number.isFinite(addedBook))
  ) {
    return null
  }

  const revision = value.added_source_revision
  if (revision !== null && revision !== undefined && typeof revision !== 'string') return null

  return {
    date: value.date,
    today_fixture_id: value.today_fixture_id,
    opportunity_key: value.opportunity_key,
    market_key: value.market_key,
    market_label: value.market_label,
    home,
    away,
    country: typeof value.country === 'string' ? value.country : value.country === null ? null : undefined,
    league: typeof value.league === 'string' ? value.league : value.league === null ? null : undefined,
    added_at: value.added_at,
    added_book_odds: typeof addedBook === 'number' ? addedBook : null,
    added_source_revision: typeof revision === 'string' ? revision : null,
  }
}

export function emptyCartState(date: string): BetBuilderCartState {
  return {
    version: BET_BUILDER_CART_VERSION,
    date,
    items: [],
  }
}

/** Parser safe: JSON corrotto / versione sconosciuta / shape invalida → cart vuoto. */
export function parseStoredCart(raw: string | null | undefined, date: string): BetBuilderCartState {
  const empty = emptyCartState(date)
  if (raw == null || raw === '') return empty
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return empty
  }
  if (!isPlainObject(parsed)) return empty
  if (parsed.version !== BET_BUILDER_CART_VERSION) return empty
  if (parsed.date !== date || typeof parsed.date !== 'string') return empty
  if (!Array.isArray(parsed.items)) return empty

  const items: BetBuilderCartStoredItem[] = []
  const seenFixtures = new Set<number>()
  for (const entry of parsed.items) {
    const item = parseStoredItem(entry, date)
    if (!item) continue
    if (seenFixtures.has(item.today_fixture_id)) continue
    seenFixtures.add(item.today_fixture_id)
    items.push(item)
  }
  return { version: BET_BUILDER_CART_VERSION, date, items }
}

export function serializeStoredCart(state: BetBuilderCartState): string {
  return JSON.stringify({
    version: BET_BUILDER_CART_VERSION,
    date: state.date,
    items: state.items,
  })
}

export function loadCartFromStorage(date: string, storage: Storage = localStorage): BetBuilderCartState {
  try {
    return parseStoredCart(storage.getItem(cartStorageKey(date)), date)
  } catch {
    return emptyCartState(date)
  }
}

export function saveCartToStorage(state: BetBuilderCartState, storage: Storage = localStorage): void {
  try {
    storage.setItem(cartStorageKey(state.date), serializeStoredCart(state))
  } catch {
    // Quota / private mode — silent; UI resta in-memory.
  }
}

export function findCartItemByFixture(
  state: BetBuilderCartState,
  todayFixtureId: number,
): BetBuilderCartStoredItem | undefined {
  return state.items.find((i) => i.today_fixture_id === todayFixtureId)
}

export function findCartItemByOpportunity(
  state: BetBuilderCartState,
  opportunityKey: string,
): BetBuilderCartStoredItem | undefined {
  return state.items.find((i) => i.opportunity_key === opportunityKey)
}

export function opportunityToStoredItem(
  opportunity: BetBuilderOpportunity,
  date: string,
  sourceRevision: string | null,
  addedAt: string = new Date().toISOString(),
): BetBuilderCartStoredItem {
  return {
    date,
    today_fixture_id: opportunity.fixture.today_fixture_id,
    opportunity_key: opportunity.opportunity_key,
    market_key: opportunity.market.market_key,
    market_label: opportunity.market.label,
    home: {
      name: opportunity.fixture.home.name ?? null,
      logo: opportunity.fixture.home.logo ?? null,
    },
    away: {
      name: opportunity.fixture.away.name ?? null,
      logo: opportunity.fixture.away.logo ?? null,
    },
    country: opportunity.fixture.country ?? null,
    league: opportunity.fixture.league ?? null,
    added_at: addedAt,
    added_book_odds: isValidBookOdds(opportunity.price_value.quota_book)
      ? opportunity.price_value.quota_book
      : opportunity.price_value.quota_book ?? null,
    added_source_revision: sourceRevision,
  }
}

/**
 * Aggiunge una selection se la fixture è libera.
 * Se la stessa exact opportunity è già presente → no-op.
 * Se altra opportunity stessa fixture → throw (usare replace).
 */
export function addCartSelection(
  state: BetBuilderCartState,
  opportunity: BetBuilderOpportunity,
  sourceRevision: string | null,
  addedAt?: string,
): BetBuilderCartState {
  const fixtureId = opportunity.fixture.today_fixture_id
  const existing = findCartItemByFixture(state, fixtureId)
  if (existing) {
    if (existing.opportunity_key === opportunity.opportunity_key) {
      return state
    }
    throw new Error('FIXTURE_ALREADY_SELECTED')
  }
  const item = opportunityToStoredItem(opportunity, state.date, sourceRevision, addedAt)
  return { ...state, items: [...state.items, item] }
}

/** Sostituisce esplicitamente la selection della stessa fixture. */
export function replaceFixtureSelection(
  state: BetBuilderCartState,
  opportunity: BetBuilderOpportunity,
  sourceRevision: string | null,
  addedAt?: string,
): BetBuilderCartState {
  const fixtureId = opportunity.fixture.today_fixture_id
  const item = opportunityToStoredItem(opportunity, state.date, sourceRevision, addedAt)
  const without = state.items.filter((i) => i.today_fixture_id !== fixtureId)
  return { ...state, items: [...without, item] }
}

export function removeCartSelection(
  state: BetBuilderCartState,
  identity: { today_fixture_id: number; opportunity_key: string },
): BetBuilderCartState {
  return {
    ...state,
    items: state.items.filter(
      (i) =>
        !(
          i.today_fixture_id === identity.today_fixture_id &&
          i.opportunity_key === identity.opportunity_key
        ),
    ),
  }
}

export function removeCartSelectionByFixture(
  state: BetBuilderCartState,
  todayFixtureId: number,
): BetBuilderCartState {
  return {
    ...state,
    items: state.items.filter((i) => i.today_fixture_id !== todayFixtureId),
  }
}

export function clearCart(state: BetBuilderCartState): BetBuilderCartState {
  return { ...state, items: [] }
}

function resolveCurrentOdds(op: BetBuilderOpportunity | null): number | null {
  if (!op) return null
  const q = op.price_value.quota_book
  return typeof q === 'number' && Number.isFinite(q) ? q : null
}

export function reconcileCart(
  state: BetBuilderCartState,
  opportunities: BetBuilderOpportunity[],
): BetBuilderCartResolvedItem[] {
  const byKey = new Map<string, BetBuilderOpportunity>()
  for (const op of opportunities) {
    byKey.set(`${op.fixture.today_fixture_id}::${op.opportunity_key}`, op)
  }

  return state.items.map((stored) => {
    const key = `${stored.today_fixture_id}::${stored.opportunity_key}`
    const current = byKey.get(key) ?? null
    const current_book_odds = resolveCurrentOdds(current)
    const status: BetBuilderCartItemStatus = current ? 'current' : 'stale'
    const odds_changed =
      status === 'current' &&
      stored.added_book_odds != null &&
      current_book_odds != null &&
      stored.added_book_odds !== current_book_odds

    return {
      stored,
      status,
      current,
      current_book_odds,
      odds_changed,
    }
  })
}

/**
 * Prodotto quote Book CURRENT solo se TUTTE le selection sono current
 * con quota finita e > 0. Altrimenti null (UI: N/D). Nessun prodotto parziale.
 */
export function calculateCombinedOdds(items: BetBuilderCartResolvedItem[]): number | null {
  if (items.length === 0) return null
  let product = 1
  for (const item of items) {
    if (item.status !== 'current') return null
    if (!isValidBookOdds(item.current_book_odds)) return null
    product *= item.current_book_odds
  }
  return product
}

/** Arrotonda SOLO per display (2 decimali). Non usare nei passaggi intermedi. */
export function formatCombinedOddsDisplay(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return 'N/D'
  return value.toFixed(2)
}

export function formatOddsDisplay(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

export function getCartCtaState(
  cart: BetBuilderCartState,
  opportunity: BetBuilderOpportunity,
): BetBuilderCartCtaState {
  const bookOddsMissing = !isValidBookOdds(opportunity.price_value.quota_book)
  const existing = findCartItemByFixture(cart, opportunity.fixture.today_fixture_id)
  const marketLabel = opportunity.market.label

  if (!existing) {
    return {
      kind: 'add',
      label: '+ Aggiungi alla schedina',
      ariaLabel: `Aggiungi ${marketLabel} alla schedina`,
      bookOddsMissing,
    }
  }

  if (existing.opportunity_key === opportunity.opportunity_key) {
    return {
      kind: 'added',
      label: '✓ Aggiunta',
      ariaLabel: `${marketLabel} già aggiunta alla schedina`,
      bookOddsMissing,
      existingLabel: existing.market_label,
    }
  }

  return {
    kind: 'replace',
    label: `Sostituisci ${existing.market_label} con ${marketLabel}`,
    ariaLabel: `Sostituisci ${existing.market_label} con ${marketLabel} nella schedina`,
    bookOddsMissing,
    existingLabel: existing.market_label,
    incomingLabel: marketLabel,
  }
}

export type CartReconcileChange =
  | { type: 'odds_updated'; item: BetBuilderCartResolvedItem; from: number; to: number }
  | { type: 'became_stale'; item: BetBuilderCartResolvedItem }
  | { type: 'became_current'; item: BetBuilderCartResolvedItem }

/** Diff per toast: solo cambiamenti reali sulle selection del cart. */
export function diffCartReconcile(
  prev: BetBuilderCartResolvedItem[],
  next: BetBuilderCartResolvedItem[],
): CartReconcileChange[] {
  const prevByKey = new Map(
    prev.map((i) => [`${i.stored.today_fixture_id}::${i.stored.opportunity_key}`, i]),
  )
  const changes: CartReconcileChange[] = []

  for (const item of next) {
    const key = `${item.stored.today_fixture_id}::${item.stored.opportunity_key}`
    const before = prevByKey.get(key)
    if (!before) continue

    if (before.status === 'current' && item.status === 'stale') {
      changes.push({ type: 'became_stale', item })
      continue
    }
    if (before.status === 'stale' && item.status === 'current') {
      changes.push({ type: 'became_current', item })
      continue
    }
    if (
      before.status === 'current' &&
      item.status === 'current' &&
      before.current_book_odds != null &&
      item.current_book_odds != null &&
      before.current_book_odds !== item.current_book_odds
    ) {
      changes.push({
        type: 'odds_updated',
        item,
        from: before.current_book_odds,
        to: item.current_book_odds,
      })
    }
  }
  return changes
}

export function signalsSummaryLabel(opportunity: BetBuilderOpportunity | null): string {
  if (!opportunity?.signals) return '—'
  const s = opportunity.signals
  if (!s.available && !s.present) return '—'
  if (s.available_count > 0) {
    return `${s.yes_count}/${s.available_count} SI`
  }
  return `${s.yes_count} SI`
}

export function purchasabilitySummaryLabel(opportunity: BetBuilderOpportunity | null): string {
  if (!opportunity) return '—'
  const score = opportunity.purchasability_v31.score
  if (score == null || !Number.isFinite(score)) return '—'
  return String(Math.round(score))
}
