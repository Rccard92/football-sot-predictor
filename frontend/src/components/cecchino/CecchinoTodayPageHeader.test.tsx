/** @vitest-environment jsdom */
import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CecchinoTodayPageHeader } from './CecchinoTodayPageHeader'

describe('CecchinoTodayPageHeader', () => {
  afterEach(() => {
    cleanup()
  })

  const baseProps = {
    isScanned: true,
    scanDayLoading: false,
    updateResultsLoading: false,
    onScanDay: vi.fn(),
    onUpdateResults: vi.fn(),
  }

  it('giornata scansionata: solo aggiorna risultati e riscansiona', () => {
    render(<CecchinoTodayPageHeader {...baseProps} />)
    const labels = screen.getAllByRole('button').map((b) => b.textContent)
    expect(labels).toEqual(['Aggiorna risultati giornata', 'Riscansiona giornata'])
  })

  it('riscansiona forza la scansione', () => {
    const onScanDay = vi.fn()
    render(<CecchinoTodayPageHeader {...baseProps} onScanDay={onScanDay} />)
    fireEvent.click(screen.getByText('Riscansiona giornata'))
    expect(onScanDay).toHaveBeenCalledWith(true)
  })

  it('giornata non scansionata: avvia scansione', () => {
    render(<CecchinoTodayPageHeader {...baseProps} isScanned={false} />)
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Avvia scansione giornata'])
  })
})
