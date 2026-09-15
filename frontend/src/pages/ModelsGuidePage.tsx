import { PageShell, Section } from '../components/layout/PageShell'
import {
  GUIDE_BOOK_RULE,
  GUIDE_FLOW,
  GUIDE_GI_LEAGUES,
  GUIDE_GLOSSARY,
  GUIDE_MODELS,
  GUIDE_MODULE_CHECK,
  GUIDE_NEXT,
  GUIDE_PATTERN_RULES,
  GUIDE_UPDATED_AT,
  GUIDE_V2_BUGS,
  type ModelCard,
} from '../config/modelsGuide'

const TEXT_MUTED = 'var(--pi-muted)'

// testo base 16px e titoli più grandi: sovrascrive le misure piccole condivise di PageShell solo in questa pagina
const GUIDE_CSS = `
  .guide-root { font-size: 16px; }
  .guide-root .pi-section { padding: 22px; }
  .guide-root .pi-section-title { font-size: 20px; letter-spacing: 0.06em; }
  .guide-root .pi-chip { font-size: 16px; padding: 4px 12px; }
  .guide-root .pi-tile { padding: 16px 18px; }
  .guide-root .pi-table { font-size: 16px; }
  .guide-root .pi-table th { font-size: 16px; letter-spacing: 0.04em; padding: 10px 12px; }
  .guide-root .pi-table td { padding: 12px; line-height: 1.5; }
`

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-2 pl-6 text-base leading-relaxed">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

function ModelBlock({ model }: { model: ModelCard }) {
  return (
    <Section title={model.name} note={<span className="text-base">{model.status}</span>}>
      <p className="mb-3 text-lg leading-relaxed">{model.inOneLine}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="pi-tile">
          <div className="mb-2 text-base font-bold uppercase tracking-wide" style={{ color: TEXT_MUTED }}>
            Cosa dovrebbe fare
          </div>
          <Bullets items={model.shouldDo} />
        </div>
        <div className="pi-tile">
          <div className="mb-2 text-base font-bold uppercase tracking-wide" style={{ color: TEXT_MUTED }}>
            Come lavora
          </div>
          <Bullets items={model.howItWorks} />
        </div>
        <div className="pi-tile">
          <div className="mb-2 text-base font-bold uppercase tracking-wide" style={{ color: 'var(--pi-warn)' }}>
            Cosa fa realmente
          </div>
          <Bullets items={model.reallyDoes} />
        </div>
      </div>
    </Section>
  )
}

export function ModelsGuidePage() {
  return (
    <PageShell>
      <div className="guide-root">
      <style>{GUIDE_CSS}</style>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">Guida ai modelli Cecchino</h1>
          <span className="pi-chip">Aggiornata al {GUIDE_UPDATED_AT}</span>
        </div>
        <p className="mt-2 max-w-4xl text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
          Come lavorano V2, V2.5 e V3, cosa dovrebbero fare, cosa fanno davvero secondo i dati e quali errori ha la V2.
          Scritta per chi apre il tool per la prima volta.
        </p>
      </header>

      <div className="space-y-5">
        <Section title="Il Cecchino in due righe">
          <p className="text-lg leading-relaxed">
            Il Cecchino analizza le partite di calcio prima che si giochino. Per ogni mercato (1, X, 2, doppia chance, primo tempo,
            Over/Under) stima una probabilità e la confronta con la quota di Bet365. L&apos;obiettivo è uno solo: trovare giocate che
            nel lungo periodo portano profitto.
          </p>
          <p className="mt-2 text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
            Nessun modello è una certezza. Ogni numero del tool va letto come "quante volte su 100", e ogni idea va verificata sulle
            partite reali prima di fidarsi.
          </p>
        </Section>

        <Section title="Parole da conoscere">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {GUIDE_GLOSSARY.map((g) => (
              <div key={g.term} className="pi-tile">
                <div className="text-lg font-semibold">{g.term}</div>
                <div className="mt-1 text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
                  {g.text}
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Come si legge una partita in Cecchino Today">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {GUIDE_FLOW.map((f) => (
              <div key={f.title} className="pi-tile">
                <div className="text-lg font-semibold">{f.title}</div>
                <div className="mt-1 text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
                  {f.text}
                </div>
              </div>
            ))}
          </div>
        </Section>

        {GUIDE_MODELS.map((m) => (
          <ModelBlock key={m.key} model={m} />
        ))}

        <Section title="La quota del bookmaker: dove entra e dove no">
          <div className="grid gap-4 lg:grid-cols-3">
            {GUIDE_BOOK_RULE.map((b) => (
              <div key={b.title} className="pi-tile">
                <div className="mb-2 text-base font-bold uppercase tracking-wide" style={{ color: TEXT_MUTED }}>
                  {b.title}
                </div>
                <Bullets items={b.items} />
              </div>
            ))}
          </div>
        </Section>

        <Section title="Pattern e Master Pattern">
          <Bullets items={GUIDE_PATTERN_RULES} />
        </Section>

        <Section title="Pattern confermato o smentito dai moduli">
          <Bullets items={GUIDE_MODULE_CHECK} />
        </Section>

        <Section title="Gli errori della V2" note={<span className="text-base">{GUIDE_V2_BUGS.length} errori · tutti corretti nella V2.5</span>}>
          <p className="mb-3 text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
            La V2 non viene corretta di proposito: così i suoi risultati restano confrontabili con quelli della V2.5 e si può misurare
            quanto valgono le correzioni.
          </p>
          <div className="pi-scroll" style={{ maxHeight: 'none' }}>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Modulo</th>
                  <th>Cosa fa di sbagliato</th>
                  <th>Cosa provoca</th>
                  <th>Come è corretto nella V2.5</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_V2_BUGS.map((b) => (
                  <tr key={`${b.module}-${b.problem}`}>
                    <td className="whitespace-nowrap font-semibold">{b.module}</td>
                    <td>{b.problem}</td>
                    <td>{b.effect}</td>
                    <td style={{ color: 'var(--pi-pos)' }}>{b.fix}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="Esempio: l'Intensità Goal V2 mescola i campionati" note={<span className="text-base">RUN V2 2025/26 · 4.423 partite</span>}>
          <p className="mb-3 text-base leading-relaxed" style={{ color: TEXT_MUTED }}>
            Se tutte le partite vengono confrontate con un unico calderone, i campionati da tanti gol risultano sempre "alti" e quelli
            da pochi gol sempre "bassi". La classe finisce per dire in che campionato si gioca, informazione che la quota Bet365
            contiene già.
          </p>
          <div className="pi-scroll" style={{ maxHeight: 'none' }}>
            <table className="pi-table">
              <thead>
                <tr>
                  <th>Campionato</th>
                  <th>Gol a partita</th>
                  <th>Over 2.5</th>
                  <th>Classe alta o molto alta</th>
                  <th>Classe bassa o molto bassa</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_GI_LEAGUES.map((r) => (
                  <tr key={r.league}>
                    <td className="font-semibold">{r.league}</td>
                    <td className="tabular-nums">{r.goals}</td>
                    <td className="tabular-nums">{r.over}</td>
                    <td className="tabular-nums">{r.high}</td>
                    <td className="tabular-nums">{r.low}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="Cosa misuriamo nei prossimi mesi">
          <Bullets items={GUIDE_NEXT} />
        </Section>
      </div>
      </div>
    </PageShell>
  )
}
