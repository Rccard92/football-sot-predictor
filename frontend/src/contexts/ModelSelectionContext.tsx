import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  UI_MODEL_VERSION_SLUGS,
  V21_MODEL,
  isUiModelVersion,
  labelForModelVersion,
  type UiModelVersionSlug,
} from '../lib/modelVersions'

const STORAGE_KEY = 'sot_selected_model_version'

function readStoredModelVersion(): UiModelVersionSlug {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && isUiModelVersion(raw)) return raw as UiModelVersionSlug
  } catch {
    /* ignore */
  }
  return V21_MODEL
}

type ModelSelectionContextValue = {
  selectedModelVersion: UiModelVersionSlug
  selectedModelLabel: string
  setSelectedModelVersion: (version: UiModelVersionSlug) => void
  uiModelOptions: readonly UiModelVersionSlug[]
}

const ModelSelectionContext = createContext<ModelSelectionContextValue | null>(null)

export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  const [selectedModelVersion, setSelectedModelVersionState] = useState<UiModelVersionSlug>(
    readStoredModelVersion,
  )

  const setSelectedModelVersion = useCallback((version: UiModelVersionSlug) => {
    if (!isUiModelVersion(version)) return
    setSelectedModelVersionState(version)
    try {
      localStorage.setItem(STORAGE_KEY, version)
    } catch {
      /* ignore */
    }
  }, [])

  const value = useMemo(
    () => ({
      selectedModelVersion,
      selectedModelLabel: labelForModelVersion(selectedModelVersion),
      setSelectedModelVersion,
      uiModelOptions: UI_MODEL_VERSION_SLUGS,
    }),
    [selectedModelVersion, setSelectedModelVersion],
  )

  return (
    <ModelSelectionContext.Provider value={value}>{children}</ModelSelectionContext.Provider>
  )
}

export function useModelSelection() {
  const ctx = useContext(ModelSelectionContext)
  if (!ctx) {
    throw new Error('useModelSelection must be used within ModelSelectionProvider')
  }
  return ctx
}
