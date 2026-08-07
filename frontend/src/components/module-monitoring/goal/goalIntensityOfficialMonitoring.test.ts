/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest'
import {
  MONITORING_MODULES,
  getMonitoringModule,
} from '../moduleMonitoringRegistry'
import {
  monitoringStatusLabel,
  operationalStatusLabelIt,
  readinessLabelIt,
  scientificMaturityLabel,
  balanceDecisionLabelIt,
  roleLabelIt,
} from '../moduleMonitoringUi'

describe('Goal Intensity monitoring official labels', () => {
  it('registry shows Supporto ufficiale', () => {
    const mod = getMonitoringModule('goal-intensity-v5')
    expect(mod?.operationalStatus).toBe('Supporto ufficiale')
    expect(mod?.versionLabel).toContain('official_support')
    expect(mod?.views.some((v) => v.id === 'overview')).toBe(true)
    expect(mod?.archiveViews?.some((v) => v.id === 'readiness')).toBe(true)
    expect(mod?.views.find((v) => v.id === 'candidates')).toBeUndefined()
  })

  it('maps official_support and related statuses', () => {
    expect(readinessLabelIt('official_support')).toBe('Supporto ufficiale')
    expect(monitoringStatusLabel('official_support')).toBe('Supporto ufficiale')
    expect(operationalStatusLabelIt('official_support')).toBe('Supporto ufficiale')
    expect(scientificMaturityLabel('external_validation_completed')).toBe(
      'Validazione esterna completata',
    )
    expect(balanceDecisionLabelIt('support_module_active')).toBe('Modulo di supporto attivo')
    expect(balanceDecisionLabelIt('monitor_post_cutover_quality')).toBe(
      'Monitora qualità post-cutover',
    )
    expect(roleLabelIt('contextual_support_only')).toBe(
      'Supporto contestuale mercati goal',
    )
  })

  it('keeps preview labels for archive/research', () => {
    expect(readinessLabelIt('preview_research')).toBe('Preview research')
    expect(readinessLabelIt('preview_monitored')).toBe('Preview monitorata')
  })

  it('modules list includes goal intensity', () => {
    expect(MONITORING_MODULES.some((m) => m.key === 'goal-intensity-v5')).toBe(true)
  })
})
