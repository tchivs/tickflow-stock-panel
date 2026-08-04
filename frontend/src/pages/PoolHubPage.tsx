import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, RefreshCw, ScanSearch } from 'lucide-react'
import { api, type PoolHubStrategy } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { cn } from '@/lib/cn'

const RESEARCH_FOOTER = '本页面仅用于研究参考，不提供任何交易执行功能。'
const COLUMNS = ['代码', '开盘涨幅', '涨跌幅', '概念板块', '关联因子'] as const

export function PoolHubPage() {
  const [activeId, setActiveId] = useState<string | null>(null)

  const hubQuery = useQuery({
    queryKey: QK.poolHub(),
    queryFn: () => api.poolHub(),
    retry: 1,
  })

  const data = hubQuery.data
  const asOf = data?.as_of ?? null
  // 单 as_of 载荷: 卡片计数与明细行来自同一个 strategies 数组 (PITFALL #10 无漂移)。
  // 默认选中第一个策略, 进入页面即可看到明细表。
  const activeStrategy: PoolHubStrategy | null =
    data?.strategies.find(s => s.id === activeId) ?? data?.strategies[0] ?? null

  const pending = hubQuery.isFetching
  const refresh = () => {
    void hubQuery.refetch()
  }

  const errorMessage = hubQuery.error instanceof Error
    ? hubQuery.error.message
    : String(hubQuery.error ?? '未知错误')

  return (
    <>
      <PageHeader
        title="股池"
        subtitle={asOf ? `竞价策略 · 数据日期 ${asOf} · 仅研究参考` : '竞价策略 · 仅研究参考'}
        right={
          <button
            onClick={refresh}
            disabled={pending}
            title="重新读取当前数据日期的股池"
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-btn
              border border-border bg-surface text-xs font-medium text-secondary
              hover:text-accent hover:border-accent/50 transition-colors cursor-pointer
              disabled:opacity-50 disabled:cursor-wait max-md:min-h-11 max-md:min-w-11"
          >
            {pending
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              : <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
            刷新股池
          </button>
        }
      />

      <div className="px-4 py-4 space-y-3 sm:px-6 lg:px-8">
        {/* Hub 加载中: 文本 + 骨架占位, 预留布局高度 */}
        {hubQuery.isPending && !data && (
          <div role="status" className="flex flex-col gap-3" aria-live="polite">
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              股池加载中…
            </div>
            <div className="flex flex-wrap gap-2">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-44 h-20 rounded-card border border-border bg-surface animate-pulse" />
              ))}
            </div>
          </div>
        )}

        {/* Hub 加载失败: 危险色容器 + 重试 */}
        {hubQuery.isError && !data && (
          <div role="alert" className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-btn px-3 py-2">
            <span className="mr-2">股池加载失败：{errorMessage}。请检查数据源后重试。</span>
            <button
              onClick={refresh}
              className="inline-flex items-center gap-1 h-6 px-2 rounded text-xs font-medium
                bg-surface border border-border text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer"
            >
              重试
            </button>
          </div>
        )}

        {/* 当日无股池结果 */}
        {data && data.strategies.length === 0 && (
          <EmptyState
            icon={ScanSearch}
            title="当日无股池结果"
            hint={`截至 ${asOf ?? '—'}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。`}
          />
        )}

        {/* 有结果: 卡片网格 + 明细表 (tracer 为内联最小实现, Task 2 替换为组件树) */}
        {data && data.strategies.length > 0 && (
          <>
            <section aria-label="策略卡片">
              <div className="flex flex-wrap gap-2">
                {data.strategies.map(s => (
                  <button
                    key={s.id}
                    onClick={() => setActiveId(s.id)}
                    className={cn(
                      'flex flex-col items-start gap-1 w-44 p-3 rounded-card border text-left',
                      'transition-colors duration-150 ease-smooth cursor-pointer',
                      activeStrategy?.id === s.id
                        ? 'border-accent bg-accent/5'
                        : 'border-border bg-surface hover:border-accent/40',
                    )}
                  >
                    <span className="w-full text-sm font-semibold truncate text-foreground">{s.name}</span>
                    <span className={cn('text-xs', activeStrategy?.id === s.id ? 'text-accent' : 'text-secondary')}>
                      当日池 <span className="num tabular-nums">{s.total}</span> 只
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {activeStrategy && (
              <section aria-label={`${activeStrategy.name} · 股池明细`}>
                <h2 className="text-sm font-semibold text-foreground">{activeStrategy.name} · 股池明细</h2>
                <div className="mt-2 rounded-card border border-border overflow-x-auto">
                  <table className="w-full text-sm" style={{ minWidth: 720 }}>
                    <thead className="bg-elevated">
                      <tr className="text-left text-secondary">
                        {COLUMNS.map(c => (
                          <th key={c} scope="col" className="px-3 py-2.5 font-medium">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {activeStrategy.rows.map(row => (
                        <tr key={row.symbol} className="border-t border-border hover:bg-elevated/50">
                          <td className="px-4 py-2"><span className="num tabular-nums text-secondary">{row.code}</span></td>
                          <td className="px-3 py-2"><span className="num tabular-nums text-secondary">{row.open_gap != null ? `${row.open_gap > 0 ? '+' : ''}${(row.open_gap * 100).toFixed(2)}%` : '—'}</span></td>
                          <td className="px-3 py-2"><span className="num tabular-nums text-secondary">{row.change_pct != null ? `${row.change_pct > 0 ? '+' : ''}${(row.change_pct * 100).toFixed(2)}%` : '—'}</span></td>
                          <td className="px-3 py-2 text-secondary">{row.concept_board.length > 0 ? row.concept_board.join('、') : '—'}</td>
                          <td className="px-3 py-2 text-secondary">{row.hit_factors.length > 0 ? row.hit_factors.join('、') : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-2 text-xs text-muted">
                  共 <span className="num tabular-nums">{activeStrategy.total}</span> 只
                </div>
              </section>
            )}
          </>
        )}

        {/* 研究参考声明 (POOL-03) */}
        <footer className="pt-4 text-xs text-muted">{RESEARCH_FOOTER}</footer>
      </div>
    </>
  )
}
