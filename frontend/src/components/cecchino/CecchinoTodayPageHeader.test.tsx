/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoTodayPageHeader } from './CecchinoTodayPageHeader'

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

describe('CecchinoTodayPageHeader daily V3.5 audit export', () => {
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

  it('mostra pulsante Scarica audit V3.5 giornata', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadDailyV35Audit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-v35-purch-audit-download-btn').textContent).toContain(
      'Scarica audit V3.5 giornata',
    )
  })

  it('loading V3.5 indipendente da V3.1', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        dailyV35AuditExportLoading
        onDownloadDailyAudit={vi.fn()}
        onDownloadDailyV35Audit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-purch-audit-download-btn').textContent).toBe(
      'Scarica audit giornata',
    )
    expect(screen.getByTestId('daily-v35-purch-audit-download-btn').textContent).toBe(
      'Preparazione…',
    )
  })

  it('errore V3.5 separato', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        dailyV35AuditExportError="Impossibile scaricare gli audit V3.5 della giornata."
        onDownloadDailyV35Audit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('daily-v35-purch-audit-export-error').textContent).toContain(
      'Impossibile scaricare gli audit V3.5 della giornata.',
    )
  })

  it('click invoca handler V3.5', () => {
    const onDownloadV35 = vi.fn()
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadDailyV35Audit={onDownloadV35}
      />,
    )
    fireEvent.click(screen.getByTestId('daily-v35-purch-audit-download-btn'))
    expect(onDownloadV35).toHaveBeenCalledTimes(1)
  })
})

describe('CecchinoTodayPageHeader V3.5 analysis export', () => {
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

  it('mostra pulsante dataset V3.5 test 20–26/08', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadV35Analysis={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v35-analysis-export-btn').textContent).toContain(
      'Scarica dataset V3.5 test 20–26/08',
    )
    expect(screen.getByTestId('v35-analysis-export-btn').textContent).toContain('ANALYSIS')
  })

  it('loading analysis indipendente', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        v35AnalysisExportLoading
        onDownloadV35Analysis={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v35-analysis-export-btn').textContent).toBe('Preparazione…')
  })

  it('errore analysis separato', () => {
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        v35AnalysisExportError="Errore dataset analysis."
        onDownloadV35Analysis={vi.fn()}
      />,
    )
    expect(screen.getByTestId('v35-analysis-export-error').textContent).toContain(
      'Errore dataset analysis.',
    )
  })

  it('click invoca handler analysis', () => {
    const onDownload = vi.fn()
    render(
      <CecchinoTodayPageHeader
        {...baseProps}
        onDownloadV35Analysis={onDownload}
      />,
    )
    fireEvent.click(screen.getByTestId('v35-analysis-export-btn'))
    expect(onDownload).toHaveBeenCalledTimes(1)
  })
})
