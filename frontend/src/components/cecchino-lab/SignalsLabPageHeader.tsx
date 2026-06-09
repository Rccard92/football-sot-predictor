import { motion } from 'framer-motion'

export function SignalsLabPageHeader() {
  return (
    <motion.header
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="relative overflow-hidden rounded-2xl border border-white/60 bg-gradient-to-br from-indigo-50/40 via-white to-cyan-50/30 p-6 shadow-sm"
    >
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-violet-200/20 blur-3xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -bottom-12 -left-12 h-40 w-40 rounded-full bg-cyan-200/20 blur-3xl"
        aria-hidden
      />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-700">
              Lab
            </span>
            <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[10px] font-medium text-amber-800 ring-1 ring-amber-200/80">
              Sperimentale
            </span>
            <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-medium text-emerald-800 ring-1 ring-emerald-200/80">
              Dati reali
            </span>
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">
            Monitoraggio Segnali Lab
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Backtest visuale dei segnali Cecchino, confronto modelli pesi e rendimento delle prese.
          </p>
        </div>
      </div>
    </motion.header>
  )
}
