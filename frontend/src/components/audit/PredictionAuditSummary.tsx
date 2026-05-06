import type { AuditResponse } from './types'
import { fmtNum, fmtSigned } from './mapping'

function sum2(a: number | null, b: number | null): number | null {
  if (a == null || b == null) return null
  return a + b
}

export function PredictionAuditSummary({ data }: { data: AuditResponse }) {
  const fx = data.fixture
  const s = data.model_inputs_summary

  const totalV01 = sum2(s.home_team_expected_sot_v01, s.away_team_expected_sot_v01)
  const totalV02 = sum2(s.home_team_expected_sot_v02, s.away_team_expected_sot_v02)

  const dHome =
    s.home_team_expected_sot_v01 != null && s.home_team_expected_sot_v02 != null
      ? s.home_team_expected_sot_v02 - s.home_team_expected_sot_v01
      : null
  const dAway =
    s.away_team_expected_sot_v01 != null && s.away_team_expected_sot_v02 != null
      ? s.away_team_expected_sot_v02 - s.away_team_expected_sot_v01
      : null
  const dTotal = totalV01 != null && totalV02 != null ? totalV02 - totalV01 : null

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Output previsione</h2>
      <p className="mt-2 text-sm text-slate-600">
        Numeri principali (baseline v0.1 e v0.2 player adjusted se disponibile).
      </p>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <article className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{fx.home_team.name}</p>
          <div className="mt-2 grid gap-1 text-sm text-slate-700">
            <p>
              <span className="text-slate-500">v0.1:</span>{' '}
              <strong className="text-slate-900">{fmtNum(s.home_team_expected_sot_v01)}</strong>
            </p>
            <p>
              <span className="text-slate-500">v0.2:</span>{' '}
              <strong className="text-slate-900">{fmtNum(s.home_team_expected_sot_v02)}</strong>
            </p>
            <p className="text-xs text-slate-600">
              Player impact: <strong>{fmtSigned(dHome)}</strong>
            </p>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{fx.away_team.name}</p>
          <div className="mt-2 grid gap-1 text-sm text-slate-700">
            <p>
              <span className="text-slate-500">v0.1:</span>{' '}
              <strong className="text-slate-900">{fmtNum(s.away_team_expected_sot_v01)}</strong>
            </p>
            <p>
              <span className="text-slate-500">v0.2:</span>{' '}
              <strong className="text-slate-900">{fmtNum(s.away_team_expected_sot_v02)}</strong>
            </p>
            <p className="text-xs text-slate-600">
              Player impact: <strong>{fmtSigned(dAway)}</strong>
            </p>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Totale match</p>
          <div className="mt-2 grid gap-1 text-sm text-slate-700">
            <p>
              <span className="text-slate-500">v0.1:</span>{' '}
              <strong className="text-slate-900">{fmtNum(totalV01)}</strong>
            </p>
            <p>
              <span className="text-slate-500">v0.2:</span>{' '}
              <strong className="text-slate-900">{fmtNum(totalV02)}</strong>
            </p>
            <p className="text-xs text-slate-600">
              Differenza: <strong>{fmtSigned(dTotal)}</strong>
            </p>
          </div>
        </article>
      </div>
    </section>
  )
}

