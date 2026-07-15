import { motion } from 'framer-motion'

export function DrawCredibilityResearchPageHeader() {
  return (
    <motion.header
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="relative overflow-hidden rounded-2xl border border-white/60 bg-gradient-to-br from-violet-50/40 via-white to-indigo-50/30 p-6 shadow-sm"
    >
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-violet-200/20 blur-3xl"
        aria-hidden
      />
      <div className="relative">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-800">
            Cecchino
          </span>
          <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[10px] font-medium text-amber-900 ring-1 ring-amber-200/80">
            Laboratorio di ricerca — non modifica il modello produttivo
          </span>
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">
          Ricerca Credibilità X
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Audit storico offline sulla copertura dati delle fixture Cecchino Today. Verifica quante
          partite sono utilizzabili per costruire il futuro indice interno di Credibilità X.
        </p>
      </div>
    </motion.header>
  )
}
