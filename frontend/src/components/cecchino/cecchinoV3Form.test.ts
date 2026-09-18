import { describe, expect, it } from 'vitest'
import { FORM_LEVEL_LABEL, formLevel, formPercent, formReading } from './cecchinoV3Form'

describe('lettura indice Forma V3', () => {
  it('Oulu (casa) - Inter Turku (ospite): valori reali della scheda', () => {
    const home = { gioco: 0.07, risultati: -0.14 }
    const away = { gioco: -0.09, risultati: 0.14 }
    expect(FORM_LEVEL_LABEL[formLevel(home.gioco, 'gioco')]).toBe('Leggermente sopra le attese')
    expect(FORM_LEVEL_LABEL[formLevel(home.risultati, 'risultati')]).toBe('Leggermente sotto le attese')
    expect(FORM_LEVEL_LABEL[formLevel(away.risultati, 'risultati')]).toBe('Leggermente sopra le attese')
    expect(formPercent(away.risultati)).toBe(15)
    expect(formPercent(away.gioco)).toBe(-9)
    const reading = formReading(home, away)
    expect(reading).toContain('favorisce la squadra di casa')
    expect(reading).toContain("L'ospite raccoglie più di quanto produce")
    expect(reading).toContain('La squadra di casa produce più di quanto raccoglie')
  })

  it('soglie: in linea, sopra, molto sopra', () => {
    expect(formLevel(0.02, 'gioco')).toBe('in_linea')
    expect(formLevel(0.15, 'gioco')).toBe('sopra')
    expect(formLevel(0.3, 'gioco')).toBe('molto_sopra')
    expect(formLevel(-0.45, 'risultati')).toBe('molto_sotto')
  })

  it('squadre alla pari nel gioco', () => {
    expect(formReading({ gioco: 0.05, risultati: 0 }, { gioco: 0.04, risultati: 0 })).toContain('alla pari')
    expect(formReading(null, { gioco: 0, risultati: 0 })).toContain('non disponibile')
  })
})
