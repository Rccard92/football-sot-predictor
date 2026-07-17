import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  buildStatisticsFullFilename,
  buildStatisticsSectionExport,
  buildStatisticsSectionFilename,
  downloadJsonFile,
  estimateJsonByteSize,
  sanitizeFilenameFragment,
} from './downloadJsonFile'

describe('downloadJsonFile helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sanitizza frammenti filename', () => {
    expect(sanitizeFilenameFragment('cecchino_draw_credibility_statistics_v1_2')).toBe(
      'cecchino_draw_credibility_statistics_v1_2',
    )
    expect(sanitizeFilenameFragment('2026-01-01')).toBe('2026-01-01')
    expect(sanitizeFilenameFragment('a/b\\c:d')).toMatch(/^a_b_c_d$/)
  })

  it('costruisce filename completo corretto', () => {
    expect(
      buildStatisticsFullFilename(
        'cecchino_draw_credibility_statistics_v1_2',
        '2026-01-01',
        '2026-07-17',
      ),
    ).toBe('cecchino_draw_credibility_statistics_v1_2_2026-01-01_2026-07-17.json')
    expect(buildStatisticsFullFilename('v1_2', '2026-01-01', '2026-07-17')).toBe(
      'cecchino_draw_credibility_statistics_v1_2_2026-01-01_2026-07-17.json',
    )
  })

  it('costruisce filename sezione corretto', () => {
    expect(
      buildStatisticsSectionFilename('candidate_patterns', '2026-01-01', '2026-07-17'),
    ).toBe('cecchino_draw_credibility_candidate_patterns_2026-01-01_2026-07-17.json')
  })

  it('round-trip JSON.parse preserva payload completo', () => {
    const payload = {
      status: 'ok',
      version: 'cecchino_draw_credibility_statistics_v1_2',
      filters: { date_from: '2026-01-01', date_to: '2026-07-17', bin_count: 5 },
      interaction_analysis: [{ interaction_key: 'x_rank_x_under', primary_cells: [] }],
      candidate_patterns: [{ pattern_key: 'p1', primary_count: 40 }],
      pattern_consistency_checks: { market_patterns_using_recomputed_boundaries: 0 },
      market_analysis: { roi: { bets: 10, roi_pct: -12.1 } },
      warnings: ['exploratory'],
      nullable: null,
      flag: true,
    }
    const text = JSON.stringify(payload, null, 2)
    const parsed = JSON.parse(text)
    expect(parsed).toEqual(payload)
    expect(parsed.nullable).toBeNull()
    expect(parsed.filters.bin_count).toBe(5)
    expect(Array.isArray(parsed.interaction_analysis)).toBe(true)
    expect(parsed.candidate_patterns).toHaveLength(1)
    expect(parsed.pattern_consistency_checks.market_patterns_using_recomputed_boundaries).toBe(0)
    expect(parsed.market_analysis.roi.bets).toBe(10)
  })

  it('wrapper sezione: exported_section e data deep-equal alla sezione originale', () => {
    const section = {
      primary: { rows: 731 },
      sensitivity: { rows: 783 },
      market: { rows: 458 },
    }
    const response = {
      status: 'ok',
      version: 'cecchino_draw_credibility_statistics_v1_2',
      filters: { date_from: '2026-01-01', date_to: '2026-07-17' },
      dataset_summary: section,
    }
    const wrap = buildStatisticsSectionExport(response, 'dataset_summary', '2026-07-17T10:00:00.000Z')
    expect(wrap.exported_section).toBe('dataset_summary')
    expect(wrap.status).toBe('ok')
    expect(wrap.version).toBe(response.version)
    expect(wrap.filters).toBe(response.filters)
    expect(wrap.data).toBe(response.dataset_summary)
    expect(wrap.data).toEqual(section)
    expect(wrap.exported_at).toBe('2026-07-17T10:00:00.000Z')
  })

  it('estimateJsonByteSize > 0 per payload non vuoto', () => {
    expect(estimateJsonByteSize({ a: 1 })).toBeGreaterThan(0)
  })

  it('downloadJsonFile revoca URL e gestisce errore ciclico', () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    const click = vi.fn()
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click,
    } as unknown as HTMLAnchorElement)

    downloadJsonFile('test.json', { ok: true })
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock')

    const cyclic: Record<string, unknown> = {}
    cyclic.self = cyclic
    expect(() => downloadJsonFile('bad.json', cyclic)).toThrow(/Serializzazione JSON/)
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })
})
