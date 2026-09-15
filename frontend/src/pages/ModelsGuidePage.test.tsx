/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { GUIDE_V2_BUGS } from '../config/modelsGuide'
import { ModelsGuidePage } from './ModelsGuidePage'

describe('ModelsGuidePage', () => {
  afterEach(() => cleanup())

  it('mostra i tre modelli e tutti gli errori della V2', () => {
    render(<ModelsGuidePage />)
    expect(screen.getByText('Guida ai modelli Cecchino')).toBeTruthy()
    expect(screen.getByText('Cecchino V2 · il modello originale')).toBeTruthy()
    expect(screen.getByText('Cecchino V2.5 · la V2 con i calcoli corretti')).toBeTruthy()
    expect(screen.getByText('Cecchino V3 estesa · il modello nuovo')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(1 + GUIDE_V2_BUGS.length + 1 + 5)
  })
})
