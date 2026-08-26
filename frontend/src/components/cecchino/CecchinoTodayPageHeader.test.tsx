/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoTodayPageHeader } from './CecchinoTodayPageHeader'

const FORBIDDEN_V35_STRINGS = [
  'Acquistabilità V3.5',
  'LIVE SHADOW',
  'structural_v1',
  'Candidate A',
  'Candidate B',
  'Candidate C',
  'Candidate D',
  'Scarica audit V3.5',
  'Scarica dataset V3.5',
]

describe('CecchinoTodayPageHeader daily audit export', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  const baseProps = {
    isScanned: true,
    scanDayLoading: false,
    updateResultsLoading: false,
    onScanDay: vi.fn(),
    onUpdateResults: vi.fn(),
  }

  it('mostra pulsante Scarica audit giornata quando isScanned', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadDailyAudit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-purch-audit-download-btn').textContent).toBe(
      'Scarica audit giornata',
    )
  })

  it('stato preparazione durante loading', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        dailyAuditExportLoading
        onDownloadDailyAudit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-purch-audit-download-btn').textContent).toBe(
      'Preparazione…',
    )
    expect(screen.getByTestId('daily-purch-audit-download-btn').hasAttribute('disabled')).toBe(true)
  })

  it('mostra messaggio errore', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        dailyAuditExportError="Impossibile generare gli audit Acquistabilità della giornata."
        onDownloadDailyAudit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-purch-audit-export-error').textContent).toContain(
      'Impossibile generare gli audit Acquistabilità della giornata.',
    )
  })

  it('click invoca handler', () => {
    const onDownload = vi.fn()
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadDailyAudit={onDownload}
      />,
    )
    fireEvent.click(screen.getByTestId('daily-purch-audit-download-btn'))
    expect(onDownload).toHaveBeenCalledTimes(1)
  })

  it('non mostra pulsante se giornata non scansionata', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        isScanned={false}
        onDownloadDailyAudit={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('daily-purch-audit-download-btn')).toBeNull()
  })
})

describe('CecchinoTodayPageHeader V3.6 evaluation bundle', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  const baseProps = {
    isScanned: true,
    scanDayLoading: false,
    updateResultsLoading: false,
    onScanDay: vi.fn(),
    onUpdateResults: vi.fn(),
  }

  it('mostra pulsante Scarica analisi V3.6', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadV36EvaluationBundle={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v36-evaluation-bundle-download-btn').textContent).toBe(
      'Scarica analisi V3.6',
    )
  })

  it('visibile anche se giornata non scansionata', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        isScanned={false}
        onDownloadV36EvaluationBundle={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v36-evaluation-bundle-download-btn')).toBeTruthy()
  })

  it('stato preparazione analisi durante loading', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        v36EvaluationBundleLoading
        onDownloadV36EvaluationBundle={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v36-evaluation-bundle-download-btn').textContent).toBe(
      'Preparazione analisi…',
    )
    expect(
      screen.getByTestId('v36-evaluation-bundle-download-btn').hasAttribute('disabled'),
    ).toBe(true)
  })

  it('mostra errore download bundle', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        v36EvaluationBundleError="Impossibile generare il bundle analisi V3.6."
        onDownloadV36EvaluationBundle={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v36-evaluation-bundle-export-error').textContent).toContain(
      'Impossibile generare il bundle analisi V3.6.',
    )
  })

  it('click invoca handler bundle', () => {
    const onDownload = vi.fn()
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadV36EvaluationBundle={onDownload}
      />,
    )
    fireEvent.click(screen.getByTestId('v36-evaluation-bundle-download-btn'))
    expect(onDownload).toHaveBeenCalledTimes(1)
  })
})

describe('CecchinoTodayPageHeader production route — no V3.5 UI', () => {
  afterEach(() => {
    cleanup()
  })

  it('non espone controlli o stringhe V3.5', () => {
    render(
      <CecchinoTodayPageHeader
        isScanned
        scanDayLoading={false}
        updateResultsLoading={false}
        onScanDay={vi.fn()}
        onUpdateResults={vi.fn()}
        onDownloadDailyAudit={vi.fn()}
        onDownloadV36EvaluationBundle={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('daily-v35-purch-audit-download-btn')).toBeNull()
    expect(screen.queryByTestId('v35-analysis-export-btn')).toBeNull()
    const body = document.body.textContent ?? ''
    for (const s of FORBIDDEN_V35_STRINGS) {
      expect(body).not.toContain(s)
    }
  })
})
