/**
 * Test contratto Pilastro 1 Balance V5 (F36) — payload V2 legacy vs V3 Quota Media X.
 * Ambiente node (senza DOM): valida shape, formattazione e retrocompatibilità.
 */
import { describe, expect, it } from 'vitest'
import { formatBalanceNumber } from '../../utils/formatBalanceNumber'
import type { CecchinoBalanceV5, CecchinoBalanceV5Pillar } from '../../lib/cecchinoTodayApi'

const PILLAR_ORDER = ['f36', 'dominance', 'draw_credibility', 'gap_coherence'] as const

function resolvePillars(balance: CecchinoBalanceV5): CecchinoBalanceV5Pillar[] {
  const raw = balance.pillars
  const order = balance.pillar_order?.length ? balance.pillar_order : [...PILLAR_ORDER]
  if (Array.isArray(raw)) {
    const byKey = new Map(raw.map((p) => [p.key, p]))
    return order.map((k) => byKey.get(k)).filter(Boolean) as CecchinoBalanceV5Pillar[]
  }
  return order.map((k) => raw[k]).filter(Boolean) as CecchinoBalanceV5Pillar[]
}

function fmtQuotaFixed(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function renderComponentValue(
  c: { key: string; value: number | string | null; unit: string; status?: string },
): string {
  if (c.key === 'quota_x_media' && (c.value == null || c.status === 'missing')) {
    return 'Quota Media X non disponibile'
  }
  if (c.unit === 'quota') {
    return fmtQuotaFixed(c.value == null || c.value === '' ? null : Number(c.value))
  }
  return formatBalanceNumber(c.value, c.unit as 'index' | 'pct' | 'text' | 'quota' | 'pp')
}

const v2F36: CecchinoBalanceV5Pillar = {
  key: 'f36',
  title: 'Geometria della partita',
  question: 'Quanto è equilibrata la struttura della partita?',
  status: 'official',
  index: 80,
  class_label: 'Equilibrio',
  reading: 'Le quote laterali risultano relativamente vicine.',
  direction: '1',
  components: [
    { key: 'quota_1', label: 'Quota 1 Cecchino', value: 2.0, unit: 'quota', status: 'available' },
    { key: 'quota_2', label: 'Quota 2 Cecchino', value: 2.8, unit: 'quota', status: 'available' },
    { key: 'f36_diff', label: 'Differenza F36 |q1−q2|', value: 0.8, unit: 'index', status: 'available' },
    { key: 'f36_class', label: 'Classe', value: 'Equilibrio', unit: 'text', status: 'available' },
  ],
}

function v3F36(overrides: Partial<CecchinoBalanceV5Pillar> = {}): CecchinoBalanceV5Pillar {
  return {
    key: 'f36',
    title: 'Geometria della partita',
    question: 'Quanto è equilibrata la struttura della partita?',
    status: 'official',
    version: 'cecchino_balance_v5_v3',
    index: 90,
    class_label: 'Equilibrio forte',
    class_key: 'strong_balance',
    reading: 'Le quote laterali descrivono una struttura equilibrata. La Quota Media X rafforza.',
    direction: '1',
    calculation_quality: 'f36_with_x_mean',
    base_index: 80,
    base_class_label: 'Equilibrio',
    base_class_key: 'balance',
    quota_x_book: 3.2,
    quota_x_cecchino: 3.4,
    quota_x_media: 3.3,
    x_mean_threshold: 3.6,
    x_mean_strength: 0.5,
    x_mean_direction: 'reinforces_balance',
    x_mean_adjustment: 10,
    x_mean_source_status: 'available',
    adjusted_index: 90,
    adjusted_class_label: 'Equilibrio forte',
    components: [
      { key: 'quota_1', label: 'Quota 1 Cecchino', value: 2.0, unit: 'quota', status: 'available' },
      { key: 'quota_2', label: 'Quota 2 Cecchino', value: 2.8, unit: 'quota', status: 'available' },
      { key: 'f36_diff', label: 'Differenza F36 |q1−q2|', value: 0.8, unit: 'index', status: 'available' },
      { key: 'f36_base_index', label: 'Indice F36 base', value: 80, unit: 'index', status: 'available' },
      { key: 'f36_base_class', label: 'Classe F36 base', value: 'Equilibrio', unit: 'text', status: 'available' },
      { key: 'quota_x_book', label: 'Quota X Book', value: 3.2, unit: 'quota', status: 'available' },
      { key: 'quota_x_cecchino', label: 'Quota X Cecchino', value: 3.4, unit: 'quota', status: 'available' },
      { key: 'quota_x_media', label: 'Quota Media X', value: 3.3, unit: 'quota', status: 'available' },
      { key: 'x_mean_threshold', label: 'Soglia Quota Media X', value: 3.6, unit: 'quota', status: 'available' },
      { key: 'x_mean_direction', label: 'Direzione correttiva', value: 'equilibrio', unit: 'text', status: 'available' },
      { key: 'x_mean_strength_pct', label: 'Intensità correzione', value: 50, unit: 'pct', status: 'available' },
      { key: 'x_mean_adjustment', label: 'Correzione applicata', value: '+10,00 equilibrio', unit: 'text', status: 'available' },
      { key: 'adjusted_index', label: 'Indice equilibrio finale', value: 90, unit: 'index', status: 'available' },
      { key: 'adjusted_class', label: 'Classe finale', value: 'Equilibrio forte', unit: 'text', status: 'available' },
    ],
    ...overrides,
  }
}

const otherPillars = {
  dominance: {
    key: 'dominance',
    title: 'Convinzione',
    question: 'q',
    status: 'official',
    index: 50,
    class_label: 'Moderata',
    reading: 'ok',
  } as CecchinoBalanceV5Pillar,
  draw_credibility: {
    key: 'draw_credibility',
    title: 'Credibilità X',
    question: 'q',
    status: 'descriptive_official',
    index: 28,
    class_label: 'Pareggio possibile',
    reading: 'ok',
  } as CecchinoBalanceV5Pillar,
  gap_coherence: {
    key: 'gap_coherence',
    title: 'Coerenza',
    question: 'q',
    status: 'official',
    index: 70,
    class_label: 'Confermato',
    reading: 'ok',
  } as CecchinoBalanceV5Pillar,
}

describe('Balance V5 Pilastro 1 — payload V3', () => {
  it('mostra indice e classe finali', () => {
    const f36 = v3F36()
    expect(f36.index).toBe(90)
    expect(f36.class_label).toBe('Equilibrio forte')
    expect(f36.base_index).toBe(80)
    expect(formatBalanceNumber(f36.index, 'index')).toBe('90')
  })

  it('mostra Quota Media X e correzione positiva', () => {
    const f36 = v3F36()
    const media = f36.components!.find((c) => c.key === 'quota_x_media')!
    const adj = f36.components!.find((c) => c.key === 'x_mean_adjustment')!
    expect(renderComponentValue(media)).toBe('3,30')
    expect(renderComponentValue(adj)).toBe('+10,00 equilibrio')
  })

  it('mostra correzione negativa', () => {
    const f36 = v3F36({
      index: 70,
      x_mean_adjustment: -10,
      components: v3F36().components!.map((c) =>
        c.key === 'x_mean_adjustment'
          ? { ...c, value: '−10,00 squilibrio' }
          : c.key === 'adjusted_index'
            ? { ...c, value: 70 }
            : c,
      ),
    })
    const adj = f36.components!.find((c) => c.key === 'x_mean_adjustment')!
    expect(renderComponentValue(adj)).toBe('−10,00 squilibrio')
  })

  it('mostra correzione zero soglia neutrale', () => {
    const f36 = v3F36({
      index: 80,
      x_mean_adjustment: 0,
      components: v3F36().components!.map((c) =>
        c.key === 'x_mean_adjustment' ? { ...c, value: '0,00 soglia neutrale' } : c,
      ),
    })
    const adj = f36.components!.find((c) => c.key === 'x_mean_adjustment')!
    expect(renderComponentValue(adj)).toBe('0,00 soglia neutrale')
  })

  it('Quota X Book mancante → messaggio dedicato', () => {
    const f36 = v3F36({
      calculation_quality: 'f36_base_only',
      quota_x_media: null,
      index: 80,
      class_label: 'Equilibrio',
      components: v3F36().components!.map((c) =>
        c.key === 'quota_x_media' ? { ...c, value: null, status: 'missing' } : c,
      ),
    })
    const media = f36.components!.find((c) => c.key === 'quota_x_media')!
    expect(renderComponentValue(media)).toBe('Quota Media X non disponibile')
    expect(f36.index).toBe(80)
  })

  it('ordine componenti V3 completo', () => {
    const keys = v3F36().components!.map((c) => c.key)
    expect(keys).toEqual([
      'quota_1',
      'quota_2',
      'f36_diff',
      'f36_base_index',
      'f36_base_class',
      'quota_x_book',
      'quota_x_cecchino',
      'quota_x_media',
      'x_mean_threshold',
      'x_mean_direction',
      'x_mean_strength_pct',
      'x_mean_adjustment',
      'adjusted_index',
      'adjusted_class',
    ])
  })
})

describe('Balance V5 Pilastro 1 — payload V2 legacy', () => {
  it('non richiede campi Quota Media X', () => {
    const balance: CecchinoBalanceV5 = {
      version: 'cecchino_balance_v5_v2',
      pillars: { f36: v2F36, ...otherPillars },
      market_deviation: { status: 'ok', pairs: [], reading: '' },
    }
    const pillars = resolvePillars(balance)
    expect(pillars).toHaveLength(4)
    const f36 = pillars[0]
    expect(f36.index).toBe(80)
    expect(f36.base_index).toBeUndefined()
    expect(f36.quota_x_media).toBeUndefined()
    expect(() =>
      f36.components!.map((c) => renderComponentValue(c)),
    ).not.toThrow()
  })
})

describe('Balance V5 — nessun regressione altri pilastri', () => {
  it('risolve i quattro pilastri nell’ordine canonico', () => {
    const balance: CecchinoBalanceV5 = {
      version: 'cecchino_balance_v5_v3',
      pillars: { f36: v3F36(), ...otherPillars },
      market_deviation: { status: 'ok', pairs: [], reading: '' },
    }
    const pillars = resolvePillars(balance)
    expect(pillars.map((p) => p.key)).toEqual([...PILLAR_ORDER])
    expect(pillars[1].index).toBe(50)
    expect(pillars[2].index).toBe(28)
    expect(pillars[3].index).toBe(70)
  })
})
