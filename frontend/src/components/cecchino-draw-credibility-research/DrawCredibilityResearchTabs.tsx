type TabId = 'audit' | 'dataset'

type Props = {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
}

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'audit', label: 'Audit copertura' },
  { id: 'dataset', label: 'Dataset storico' },
]

export function DrawCredibilityResearchTabs({ activeTab, onTabChange }: Props) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-1">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            activeTab === tab.id
              ? 'bg-violet-100 text-violet-900'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
