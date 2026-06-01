import type { RoundAnalysisDetail, RoundAnalysisFixtureRow } from '../../lib/api'
import {
  getRoundAnalysisFixtureReportJson,
  getRoundAnalysisReportJson,
} from '../../lib/api'
import { MODEL_KEYS } from './roundAnalysisUtils'

function slugify(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

export function downloadJsonFile(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function roundAnalysisReportFilename(
  detail: RoundAnalysisDetail,
  competitionName?: string | null,
): string {
  const comp = slugify(competitionName ?? 'competition')
  const season = slugify(detail.season_label.replace('/', '-'))
  return `round-analysis-${comp}-${season}-round-${detail.round_number}-v${detail.analysis_version}.json`
}

export function fixtureReportFilename(
  detail: RoundAnalysisDetail,
  fixture: RoundAnalysisFixtureRow,
  competitionName?: string | null,
): string {
  const comp = slugify(competitionName ?? 'competition')
  const season = slugify(detail.season_label.replace('/', '-'))
  const home = slugify(fixture.home_team_name)
  const away = slugify(fixture.away_team_name)
  return `round-analysis-${comp}-${season}-round-${detail.round_number}-${home}-${away}.json`
}

export async function downloadRoundAnalysisReport(
  detail: RoundAnalysisDetail,
  competitionName?: string | null,
): Promise<void> {
  const data = await getRoundAnalysisReportJson(detail.id)
  downloadJsonFile(roundAnalysisReportFilename(detail, competitionName), data)
}

export async function downloadFixtureReport(
  detail: RoundAnalysisDetail,
  fixture: RoundAnalysisFixtureRow,
  competitionName?: string | null,
): Promise<void> {
  const data = await getRoundAnalysisFixtureReportJson(detail.id, fixture.fixture_id)
  downloadJsonFile(fixtureReportFilename(detail, fixture, competitionName), data)
}

export function buildModelDebugJson(
  fixture: RoundAnalysisFixtureRow,
  modelKey: string,
): Record<string, unknown> {
  const block = fixture.models_json[modelKey]
  if (!block) return { model_key: modelKey, status: 'missing' }
  const expl =
    modelKey === MODEL_KEYS.v21
      ? (fixture.explanation_json?.[MODEL_KEYS.v21] as Record<string, unknown> | undefined)
      : undefined
  return {
    model_version_requested: block.model_version_requested ?? modelKey,
    model_version_used: block.model_version_used,
    model_engine_name: block.model_engine_name,
    status: block.model_status ?? block.status,
    error_code: block.error_code,
    error_message: block.error_message ?? block.message,
    prediction: {
      predicted_home_sot: block.predicted_home_sot,
      predicted_away_sot: block.predicted_away_sot,
      predicted_total_sot: block.predicted_total_sot,
    },
    betting: {
      aggressive: {
        line: block.aggressive_line,
        edge: block.aggressive_edge,
        advice: block.aggressive_advice,
        reason: block.aggressive_reason,
        outcome: block.aggressive_outcome,
      },
      cautious: {
        line: block.cautious_line,
        edge: block.cautious_edge,
        advice: block.cautious_advice,
        reason: block.cautious_reason,
        outcome: block.cautious_outcome,
      },
    },
    trace_summary: block.trace_summary,
    explanation_v21: expl,
    warnings: block.warnings,
  }
}
