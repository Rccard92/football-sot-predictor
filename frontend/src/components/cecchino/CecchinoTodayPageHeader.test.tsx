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
