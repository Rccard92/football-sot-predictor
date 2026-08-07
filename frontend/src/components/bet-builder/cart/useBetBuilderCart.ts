/**
 * BET-03 — hook carrello schedina: persistenza per data, reconcile su response completa,
 * toast moderati, sync storage multi-tab.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { BetBuilderOpportunity } from '../../../lib/cecchinoBetBuilderApi'
import {
  addCartSelection,
  calculateCombinedOdds,
  cartStorageKey,
  clearCart,
  diffCartReconcile,
  formatCombinedOddsDisplay,
  formatOddsDisplay,
  getCartCtaState,
  loadCartFromStorage,
  reconcileCart,
  removeCartSelection,
  removeCartSelectionByFixture,
  replaceFixtureSelection,
  saveCartToStorage,
  type BetBuilderCartCtaState,
  type BetBuilderCartResolvedItem,
  type BetBuilderCartState,
  type BetBuilderCartStoredItem,
} from './betBuilderCartUtils'

type UseBetBuilderCartArgs = {
  date: string
  /** Sempre data.opportunities completa — mai filteredOpportunities. */
  opportunities: BetBuilderOpportunity[]
  sourceRevision: string | null
}

export type UseBetBuilderCartResult = {
  cart: BetBuilderCartState
  resolvedItems: BetBuilderCartResolvedItem[]
  selectionCount: number
  combinedOdds: number | null
  combinedOddsDisplay: string
  isOpen: boolean
  setOpen: (open: boolean) => void
  getCtaFor: (opportunity: BetBuilderOpportunity) => BetBuilderCartCtaState
  isInCart: (opportunityKey: string) => boolean
  fixtureHasSelection: (todayFixtureId: number) => boolean
  fixtureCartLabel: (todayFixtureId: number) => string | undefined
  add: (opportunity: BetBuilderOpportunity) => void
  replace: (opportunity: BetBuilderOpportunity) => void
  remove: (identity: { today_fixture_id: number; opportunity_key: string }) => void
  removeByFixture: (todayFixtureId: number) => void
  clear: () => void
  restoreItems: (items: BetBuilderCartStoredItem[]) => void
}

export function useBetBuilderCart({
  date,
  opportunities,
  sourceRevision,
}: UseBetBuilderCartArgs): UseBetBuilderCartResult {
  const [cart, setCart] = useState<BetBuilderCartState>(() => loadCartFromStorage(date))
  const [isOpen, setOpen] = useState(false)
  const prevResolvedRef = useRef<BetBuilderCartResolvedItem[] | null>(null)
  const skipToastOnceRef = useRef(true)
  const writingRef = useRef(false)

  // Cambio data → carica cart di quella giornata.
  useEffect(() => {
    skipToastOnceRef.current = true
    prevResolvedRef.current = null
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync date → localStorage cart
    setCart(loadCartFromStorage(date))
  }, [date])

  // Persistenza su ogni mutazione.
  useEffect(() => {
    writingRef.current = true
    saveCartToStorage(cart)
    // Microtask: evita echo storage event dalla stessa tab dove supportato.
    queueMicrotask(() => {
      writingRef.current = false
    })
  }, [cart])

  const resolvedItems = useMemo(
    () => reconcileCart(cart, opportunities),
    [cart, opportunities],
  )

  // Toast solo su cambiamenti reali post-reconcile (non spam polling).
  useEffect(() => {
    const prev = prevResolvedRef.current
    prevResolvedRef.current = resolvedItems
    if (skipToastOnceRef.current) {
      skipToastOnceRef.current = false
      return
    }
    if (!prev || prev.length === 0) return
    const changes = diffCartReconcile(prev, resolvedItems)
    for (const change of changes) {
      const label = change.item.stored.market_label
      const match = `${change.item.stored.home.name ?? '?'} – ${change.item.stored.away.name ?? '?'}`
      if (change.type === 'odds_updated') {
        toast.message('Quota aggiornata', {
          description: `${match} · ${label}: ${formatOddsDisplay(change.from)} → ${formatOddsDisplay(change.to)}`,
        })
      } else if (change.type === 'became_stale') {
        toast.message('Selezione non più disponibile', {
          description: `${match} · ${label} non è più nel Bet Builder corrente`,
        })
      } else if (change.type === 'became_current') {
        toast.message('Selezione di nuovo disponibile', {
          description: `${match} · ${label}`,
        })
      }
    }
  }, [resolvedItems])

  // Sync multi-tab via storage event.
  useEffect(() => {
    const key = cartStorageKey(date)
    const onStorage = (e: StorageEvent) => {
      if (e.key !== key || writingRef.current) return
      if (e.storageArea && e.storageArea !== localStorage) return
      setCart(loadCartFromStorage(date))
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [date])

  const combinedOdds = useMemo(() => calculateCombinedOdds(resolvedItems), [resolvedItems])
  const combinedOddsDisplay = useMemo(
    () => formatCombinedOddsDisplay(combinedOdds),
    [combinedOdds],
  )

  const getCtaFor = useCallback(
    (opportunity: BetBuilderOpportunity) => getCartCtaState(cart, opportunity),
    [cart],
  )

  const isInCart = useCallback(
    (opportunityKey: string) => cart.items.some((i) => i.opportunity_key === opportunityKey),
    [cart.items],
  )

  const fixtureHasSelection = useCallback(
    (todayFixtureId: number) => cart.items.some((i) => i.today_fixture_id === todayFixtureId),
    [cart.items],
  )

  const fixtureCartLabel = useCallback(
    (todayFixtureId: number) =>
      cart.items.find((i) => i.today_fixture_id === todayFixtureId)?.market_label,
    [cart.items],
  )

  const add = useCallback(
    (opportunity: BetBuilderOpportunity) => {
      setCart((prev) => {
        try {
          const next = addCartSelection(prev, opportunity, sourceRevision)
          if (next === prev) return prev
          toast.success('Aggiunta alla schedina', {
            description: `${opportunity.market.label} · ${opportunity.fixture.home.name ?? ''} – ${opportunity.fixture.away.name ?? ''}`,
          })
          return next
        } catch {
          return prev
        }
      })
    },
    [sourceRevision],
  )

  const replace = useCallback(
    (opportunity: BetBuilderOpportunity) => {
      setCart((prev) => {
        const existing = prev.items.find(
          (i) => i.today_fixture_id === opportunity.fixture.today_fixture_id,
        )
        const next = replaceFixtureSelection(prev, opportunity, sourceRevision)
        toast.success('Sostituita nella schedina', {
          description: existing
            ? `${existing.market_label} → ${opportunity.market.label}`
            : opportunity.market.label,
        })
        return next
      })
    },
    [sourceRevision],
  )

  const remove = useCallback(
    (identity: { today_fixture_id: number; opportunity_key: string }) => {
      setCart((prev) => {
        const item = prev.items.find(
          (i) =>
            i.today_fixture_id === identity.today_fixture_id &&
            i.opportunity_key === identity.opportunity_key,
        )
        const next = removeCartSelection(prev, identity)
        if (item) {
          toast.message('Rimossa dalla schedina', {
            description: item.market_label,
          })
        }
        return next
      })
    },
    [],
  )

  const removeByFixture = useCallback((todayFixtureId: number) => {
    setCart((prev) => removeCartSelectionByFixture(prev, todayFixtureId))
  }, [])

  const restoreItems = useCallback((items: BetBuilderCartStoredItem[]) => {
    setCart((prev) => ({ ...prev, items: [...items] }))
  }, [])

  const clear = useCallback(() => {
    setCart((prev) => {
      if (prev.items.length === 0) return prev
      const snapshot = [...prev.items]
      toast.message('Schedina svuotata', {
        action: {
          label: 'Annulla',
          onClick: () => {
            setCart((current) => ({ ...current, items: snapshot }))
          },
        },
      })
      return clearCart(prev)
    })
  }, [])

  return {
    cart,
    resolvedItems,
    selectionCount: cart.items.length,
    combinedOdds,
    combinedOddsDisplay,
    isOpen,
    setOpen,
    getCtaFor,
    isInCart,
    fixtureHasSelection,
    fixtureCartLabel,
    add,
    replace,
    remove,
    removeByFixture,
    clear,
    restoreItems,
  }
}
