import type { HistoricalRunExclusion } from '../../../lib/cecchinoLabApi'

type Props = { items: HistoricalRunExclusion[]; total: number }

export function HistoricalRunExclusions({ items, total }: Props) {
  return (
    <section>
      <h3 className="mb-2 text-lg font-semibold">Esclusioni</h3>
      <p className="mb-3 text-xs text-[var(--lab-muted)]">
        Totale escluse: {total}. Non contaminano hit rate / ROI / pattern.
      </p>
      <div className="lab-table-wrap overflow-x-auto">
        <table className="lab-table w-full text-xs">
          <thead>
            <tr>
              <th>Motivo</th>
              <th>N</th>
              <th>%</th>
              <th>Atteso</th>
              <th>Qualità dati</th>
              <th>Modulo</th>
              <th>Periodo</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.reason_code}>
                <td>
                  <div>{i.label}</div>
                  <div className="text-[10px] text-[var(--lab-muted)]">{i.reason_code}</div>
                </td>
                <td>{i.total}</td>
                <td>{i.percentage}%</td>
                <td>{i.is_expected ? 'sì' : 'no'}</td>
                <td>{i.is_data_quality_problem ? 'sì' : 'no'}</td>
                <td>{i.related_module}</td>
                <td className="text-[10px]">
                  {i.first_occurrence?.slice(0, 10) ?? '—'} →{' '}
                  {i.last_occurrence?.slice(0, 10) ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
