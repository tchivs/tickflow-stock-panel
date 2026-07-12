import { useState, type KeyboardEvent } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { FactorBacktest } from './backtest/FactorBacktest'
import { StrategyBacktest } from './backtest/StrategyBacktest'
import { StrategyOptimizer } from './backtest/StrategyOptimizer'
import { ResearchLibrary } from './backtest/ResearchLibrary'
import { ExperimentComparison } from './backtest/ExperimentComparison'
import { AdvancedResearchPanels } from '@/components/advanced/AdvancedResearchPanels'
import { BarChart3, FlaskConical, SlidersHorizontal } from 'lucide-react'

type Tab = 'factor' | 'strategy' | 'optimizer'

const MODES: Record<Tab, { title: string; subtitle: string; hint: string }> = {
  factor: {
    title: '因子回测',
    subtitle: '验证单个因子是否有预测能力',
    hint: '看 IC / IR、分层收益和多空组合，适合先筛掉无效指标。',
  },
  strategy: {
    title: '策略回测',
    subtitle: '验证完整选股和交易规则',
    hint: '看净值曲线、回撤、胜率和交易明细，适合判断策略是否可执行。',
  },
  optimizer: {
    title: '参数优化',
    subtitle: '网格搜索最优参数组合',
    hint: '并行回测所有参数组合，按夏普/索提诺等目标排序，找到最优参数。',
  },
}

const TAB_ICONS: Record<Tab, typeof BarChart3> = {
  factor: BarChart3,
  strategy: FlaskConical,
  optimizer: SlidersHorizontal,
}

export function Backtest() {
  const [activeTab, setActiveTab] = useState<Tab>('strategy')
  const [selectedResearchAsset, setSelectedResearchAsset] = useState<string | null>(null)

  const handleModeKeyDown = (event: KeyboardEvent<HTMLButtonElement>, tab: Tab) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const tabs = ['factor', 'strategy', 'optimizer'] as const
    const next = tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]
    setActiveTab(next)
    document.getElementById(`backtest-mode-tab-${next}`)?.focus()
  }

  const modeSwitch = (
    <div role="tablist" aria-label="回测模式" className="inline-flex rounded-btn border border-border bg-surface/80 p-0.5 shadow-sm">
      {(['factor', 'strategy', 'optimizer'] as const).map(tab => {
        const Icon = TAB_ICONS[tab]
        const active = activeTab === tab
        return (
          <button
            key={tab}
            id={`backtest-mode-tab-${tab}`}
            role="tab"
            aria-selected={active}
            aria-controls={`backtest-mode-panel-${tab}`}
            tabIndex={active ? 0 : -1}
            onClick={() => setActiveTab(tab)}
            onKeyDown={event => handleModeKeyDown(event, tab)}
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-base ${
              active
                ? 'bg-accent text-white shadow-sm'
                : 'text-secondary hover:bg-elevated hover:text-foreground'
            }`}
          >
            <Icon aria-hidden="true" className="h-3.5 w-3.5" />
            {MODES[tab].title}
            {tab === 'optimizer' && (
              <span className={`rounded border px-1 py-px text-[8px] font-semibold uppercase ${
                active ? 'border-white/40 bg-white/15 text-white' : 'border-amber-400/30 bg-amber-400/10 text-amber-400'
              }`}>
                Beta
              </span>
            )}
          </button>
        )
      })}
    </div>
  )

  return (
    <div className="min-h-full bg-base flex flex-col">
      <PageHeader
        title="回测工作台"
        subtitle={`${MODES[activeTab].title} · ${MODES[activeTab].hint}`}
        right={modeSwitch}
        className="shrink-0 bg-base/95"
      />

      <main className="flex-1 min-h-0 px-3 pb-3 pt-3 lg:px-4 lg:pb-4">
        {activeTab === 'factor' && <div id="backtest-mode-panel-factor" role="tabpanel" aria-labelledby="backtest-mode-tab-factor" className="space-y-4"><FactorBacktest /><ResearchLibrary /><ExperimentComparison /></div>}
        {activeTab === 'strategy' && <div id="backtest-mode-panel-strategy" role="tabpanel" aria-labelledby="backtest-mode-tab-strategy" className="space-y-4"><StrategyBacktest onResearchAssetChange={setSelectedResearchAsset} /><ResearchLibrary /><ExperimentComparison /><AdvancedResearchPanels researchAssetId={selectedResearchAsset} /></div>}
        {activeTab === 'optimizer' && <div id="backtest-mode-panel-optimizer" role="tabpanel" aria-labelledby="backtest-mode-tab-optimizer"><StrategyOptimizer /></div>}
      </main>
    </div>
  )
}
