import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, BookmarkCheck, FlaskConical, Library, Route, ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { FactorDiscovery } from './backtest/FactorDiscovery'
import { ResearchCandidatesDialog } from './backtest/ResearchCandidatesDialog'
import { RobustnessValidation } from './backtest/RobustnessValidation'
import { StrategyBacktest } from './backtest/StrategyBacktest'
import { ResearchLibrary } from './backtest/ResearchLibrary'
import { ExperimentComparison } from './backtest/ExperimentComparison'
import { ShadowAccount } from './backtest/ShadowAccount'
import { AdvancedResearchPanels } from '@/components/advanced/AdvancedResearchPanels'
import { ModelLibrary } from './backtest/ModelLibrary'
import { WalkForward } from './backtest/WalkForward'
import { ResearchFold } from './backtest/ResearchFold'

type Tab = 'factor' | 'strategy' | 'robustness' | 'library' | 'walkforward'

const MODES: Record<Tab, { title: string; subtitle: string; icon: typeof BarChart3; hint?: string }> = {
  factor: {
    title: '因子',
    subtitle: '批量筛选与单因子检验',
    icon: BarChart3,
  },
  strategy: {
    title: '策略',
    subtitle: '现有策略评估与候选沉淀',
    icon: FlaskConical,
  },
  robustness: {
    title: '验证',
    subtitle: '参数敏感性与滚动样本外',
    icon: ShieldCheck,
  },
  library: {
    title: '模型库',
    subtitle: '已准入因子与组合模型',
    hint: '因子目录携带 IC / RankIC 证据，组合模型展示权重与谱系。',
    icon: Library,
  },
  walkforward: {
    title: '走步验证',
    subtitle: '固定窗口折叠与保留 OOS',
    hint: '看 train / gap / test 几何、OOS 参数搜索与验证门槛结果。',
    icon: Route,
  }
}

export function Backtest() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null)
  const binding = useQuery({
    queryKey: QK.advancedResearchAssetBinding(selectedStrategyId ?? ''),
    queryFn: () => api.advancedResearchAssetBinding(selectedStrategyId!),
    enabled: Boolean(selectedStrategyId),
  })

  // 旧链接兼容: 挖掘已升级为一级路由 /mining, 保留 run/candidate 参数重定向
  if (requestedTab === 'mining') {
    const next = new URLSearchParams(searchParams)
    next.delete('tab')
    const search = next.toString()
    return <Navigate to={search ? `/mining?${search}` : '/mining'} replace />
  }

  const activeTab: Tab = requestedTab && requestedTab in MODES
    ? requestedTab as Tab
    : 'strategy'

  const changeTab = (tab: Tab) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="flex min-h-full flex-col bg-base">
      <PageHeader
        title="量化研究"
        subtitle={<span className="hidden md:inline">{MODES[activeTab].subtitle}</span>}
        className="shrink-0 flex-wrap gap-x-4 gap-y-2 bg-base/95 px-3 lg:flex-nowrap lg:px-5"
        right={(
          <div className="flex w-full min-w-0 items-center gap-1.5 sm:gap-2 lg:w-auto">
            <button
              type="button"
              onClick={() => setCandidatesOpen(true)}
              aria-label="打开候选方案"
              title="候选方案"
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-btn border border-border bg-surface px-2 text-[11px] font-medium text-secondary transition-colors hover:border-accent/40 hover:text-accent sm:px-2.5 sm:text-xs"
            >
              <BookmarkCheck className="h-3.5 w-3.5" />
              <span>候选方案</span>
            </button>
            <span className="h-5 w-px shrink-0 bg-border" aria-hidden="true" />
            <nav className="min-w-0 flex-1 overflow-x-auto lg:flex-none" aria-label="量化研究视图">
              <div className="inline-flex min-w-max items-center gap-0.5 rounded-btn border border-border bg-surface/80 p-0.5">
                {(Object.keys(MODES) as Tab[]).map(tab => {
                  const mode = MODES[tab]
                  const Icon = mode.icon
                  const active = activeTab === tab
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => changeTab(tab)}
                      aria-current={active ? 'page' : undefined}
                      className={`inline-flex h-7 items-center gap-1 rounded-[5px] px-1.5 text-[11px] font-medium transition-colors sm:gap-1.5 sm:px-2.5 sm:text-xs ${active
                        ? 'bg-accent text-white shadow-sm'
                        : 'text-secondary hover:bg-elevated hover:text-foreground'
                      }`}
                    >
                      <Icon className="hidden h-3.5 w-3.5 sm:block" />
                      {mode.title}
                    </button>
                  )
                })}
              </div>
            </nav>
          </div>
        )}
      />

      <main className="min-h-0 flex-1 px-3 pb-3 pt-3 lg:px-4 lg:pb-4">
        {activeTab === 'factor' && (
          <div className="space-y-4">
            <FactorDiscovery />
            <ResearchFold storageKey="bt-fold-research-factor" title="研究工具 · 因子库与实验对比"><ResearchLibrary /><ExperimentComparison /></ResearchFold>
          </div>
        )}
        {/* Keep the main configuration mounted so mode switching does not discard an in-progress run. */}
        <div id="backtest-mode-panel-strategy" hidden={activeTab !== 'strategy'} className="space-y-4">
          <StrategyBacktest onStrategyChange={setSelectedStrategyId} />
          {activeTab === 'strategy' && <>
            <ResearchFold storageKey="bt-fold-research-strategy" title="研究工具 · 因子库与实验对比"><ResearchLibrary /><ExperimentComparison /></ResearchFold>
            <ResearchFold storageKey="bt-fold-shadow" title="影子账户 · 模拟跟踪"><ShadowAccount /></ResearchFold>
            <ResearchFold storageKey="bt-fold-advanced" title="高级研究 · 服务器研究资产"><AdvancedResearchPanels binding={binding.data?.binding ?? null} bindingError={selectedStrategyId ? (binding.isLoading ? '正在解析服务器研究资产绑定。' : binding.isError ? '服务器研究资产绑定不可用；高级研究操作已禁用。' : null) : '请选择已安装策略以解析服务器研究资产绑定。'} /></ResearchFold>
          </>}
        </div>
        {activeTab === 'robustness' && <RobustnessValidation />}
        {activeTab === 'library' && <ModelLibrary />}
        {activeTab === 'walkforward' && <WalkForward />}
      </main>

      {candidatesOpen && <ResearchCandidatesDialog onClose={() => setCandidatesOpen(false)} />}
    </div>
  )
}
