import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
}

type State = {
  error: Error | null
}

export class SignalsLabErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error('[SignalsLabErrorBoundary]', error, info.componentStack)
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-lg px-4 py-16 text-center">
          <h1 className="text-lg font-semibold text-slate-900">
            Monitoraggio Segnali Lab non disponibile
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            Errore runtime nella pagina sperimentale.
          </p>
          {import.meta.env.DEV && (
            <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-left text-xs text-red-800">
              {this.state.error.message}
            </p>
          )}
        </div>
      )
    }

    return this.props.children
  }
}
