import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowDown, ArrowUp, Check, ChevronDown, Database, FileWarning,
  Plus, RefreshCw, Shield, Zap,
} from 'lucide-react'
import { api, type DataSourceItem, type DataSourcesResponse, type PluginDataSourceItem, type Preferences } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { toast } from '@/components/Toast'
import { DataSourceEditor } from './DataSourceEditor'
import { DATASET_LABELS, providerDatasets, providerDisplayName } from '@/lib/dataSources'

// 参与启用/禁用 + 排序的数据集 (financial 无免费源, 仍纳入以便统一管理)
const DATASETS: { key: keyof NonNullable<Preferences['provider_chains']>; label: string }[] = [
  { key: 'daily', label: '日K' },
  { key: 'minute', label: '分钟K' },
  { key: 'realtime', label: '实时行情' },
  { key: 'adj_factor', label: '除权因子' },
  { key: 'financial', label: '财务' },
]

const DATASET_HINT: Record<string, string> = {
  daily: '历史日K + 实时覆写',
  minute: '盘中分钟K',
  realtime: '盘中实时行情',
  adj_factor: '复权因子 (默认跟随日K)',
  financial: '财务数据',
}

export function SettingsDataSourcesPanel() {
  const qc = useQueryClient()
  const prefs = usePreferences()
  const sources = useQuery({ queryKey: QK.dataSources, queryFn: api.dataSources })
  const [selected, setSelected] = useState<string>('tickflow') // 右侧管理区编辑的源 name
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>('daily')

  const reload = useMutation({
    mutationFn: api.reloadDataSources,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      toast('配置已重新加载', 'success')
    },
  })

  const remove = useMutation({
    mutationFn: (name: string) => api.deleteDataSource(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      qc.invalidateQueries({ queryKey: QK.preferences })
      setSelected('tickflow')
      setConfirmDelete(null)
      toast('数据源已删除', 'success')
    },
  })

  const editExisting = useMutation({
    mutationFn: (name: string) => api.dataSource(name),
    onSuccess: (_data, name) => setSelected(name),
  })

  const installMut = useMutation({
    mutationFn: (name: string) => api.installPlugin(name),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      if (data.install_ok) {
        toast('插件依赖安装成功', 'success')
      } else {
        toast(data.install_message || '安装失败', 'error')
      }
    },
    onError: (e: Error) => toast(`安装失败: ${e.message}`, 'error'),
  })

  const uninstallMut = useMutation({
    mutationFn: (name: string) => api.uninstallPlugin(name),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      qc.invalidateQueries({ queryKey: QK.preferences })
      if (data.uninstall_ok) {
        toast(data.uninstall_message || '已卸载', 'success')
      } else {
        toast(data.uninstall_message || '卸载失败', 'error')
      }
    },
    onError: (e: Error) => toast(`卸载失败: ${e.message}`, 'error'),
  })

  const saveChain = useMutation({
    mutationFn: (chains: Preferences['provider_chains']) =>
      api.updateDataProviders({ provider_chains: chains }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      toast('数据源链已保存', 'success')
    },
    onError: (e: Error) => toast(`保存失败: ${e.message}`, 'error'),
  })

  const builtin: DataSourceItem[] = sources.data?.builtin ?? []
  const pluginList: PluginDataSourceItem[] = sources.data?.plugins ?? []
  const customList: DataSourceItem[] = sources.data?.custom ?? []
  const errors = sources.data?.errors ?? []

  const pluginMap = new Map(pluginList.map(p => [p.name, p]))
  const pluginNames = new Set(pluginList.map(p => p.name))

  const pluginItems: DataSourceItem[] = pluginList.map(p => ({
    name: p.name, display_name: p.display_name, datasets: p.datasets,
  }))
  const allItems = [...builtin, ...pluginItems, ...customList]

  const selectedCustom = customList.find(s => s.name === selected)

  return (
    <div className="space-y-5 max-w-5xl">
      {/* ===== 顶部: 数据集启用链编辑 ===== */}
      <section className="rounded-card border border-border bg-surface p-4 sm:p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2.5">
            <Database className="h-4 w-4 text-secondary" />
            <h2 className="text-sm font-medium text-foreground">数据源</h2>
            <span
              className="text-[10px] text-muted/40 font-mono truncate hidden lg:inline max-w-[480px]"
              title={sources.data?.config_dir}
            >
              {sources.data?.config_dir}
            </span>
          </div>
          <button
            onClick={() => reload.mutate()}
            disabled={reload.isPending}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-btn px-2.5 py-1 text-xs text-muted transition-colors hover:bg-elevated hover:text-foreground disabled:opacity-50 sm:min-h-0"
          >
            <RefreshCw className={`h-3 w-3 ${reload.isPending ? 'animate-spin' : ''}`} />
            重新加载
          </button>
        </div>
        <p className="mb-4 text-[11px] text-muted/70">
          每个数据集按顺序尝试启用的源, 主源缺数据时自动回退到下一个。
          点击展开可启用/禁用并调整优先级。
        </p>

        {/* 每数据集一行: 折叠 + 展开编辑器 */}
        <div className="space-y-2">
          {DATASETS.map(ds => {
            const isOpen = expanded === ds.key
            return (
              <div key={ds.key} className="rounded-lg border border-border/60 bg-elevated/20">
                <button
                  onClick={() => setExpanded(isOpen ? null : ds.key)}
                  className="w-full flex items-center gap-3 px-3.5 py-3 text-left"
                >
                  <ChevronDown className={`h-3.5 w-3.5 text-muted transition-transform ${isOpen ? '' : '-rotate-90'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{ds.label}</span>
                      <span className="text-[10px] text-muted/50">{DATASET_HINT[ds.key]}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {(prefs.data?.provider_chains?.[ds.key] ?? []).map((name, idx) => (
                        <span
                          key={name}
                          className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-px rounded ${
                            idx === 0
                              ? 'bg-accent/15 text-accent'
                              : 'bg-elevated text-secondary'
                          }`}
                        >
                          {idx === 0 && <Check className="h-2.5 w-2.5" />}
                          {providerDisplayName(sources.data, name)}
                        </span>
                      ))}
                      {!(prefs.data?.provider_chains?.[ds.key] ?? []).length && (
                        <span className="text-[10px] text-muted/40">未配置</span>
                      )}
                    </div>
                  </div>
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="overflow-hidden"
                    >
                      <ChainEditor
                        key={ds.key}
                        dataset={ds.key}
                        sources={sources.data}
                        allItems={allItems}
                        chain={prefs.data?.provider_chains?.[ds.key] ?? []}
                        saving={saveChain.isPending}
                        onSave={(names) =>
                          saveChain.mutate({
                            ...(prefs.data?.provider_chains ?? {}),
                            [ds.key]: names,
                          })
                        }
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>

        {errors.length > 0 && (
          <div className="mt-3 flex items-start gap-1.5 px-3 py-2 rounded-lg bg-danger/5 border border-danger/20">
            <FileWarning className="h-3.5 w-3.5 text-danger shrink-0 mt-0.5" />
            <div className="text-[11px] text-danger/80 leading-relaxed space-y-0.5">
              {errors.map((err, idx) => (
                <div key={idx}>
                  <span className="font-mono">{err.name || err.path}</span>: {err.errors.join('; ')}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted/50">
          <span className="inline-flex items-center gap-1">
            <Check className="h-2.5 w-2.5 text-accent" /> 首选源
          </span>
          <span className="text-muted/30">·</span>
          <span>启用多个源自动回退</span>
          <span className="text-muted/30">·</span>
          <span className="inline-flex items-center gap-1">
            <Shield className="h-2.5 w-2.5" /> TickFlow 始终兜底
          </span>
        </div>
      </section>

      {/* ===== 下方: 数据源管理 (插件/自定义) ===== */}
      <section className="rounded-card border border-border bg-surface p-4 sm:p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-medium text-foreground">数据源管理</h3>
          <span className="text-[10px] text-muted/50">自定义源 / 插件依赖</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 mt-3">
          {allItems.map(item => {
            const plugin = pluginMap.get(item.name)
            const pluginUnavailable = plugin && !plugin.available
            const installing = installMut.isPending && installMut.variables === item.name
            const uninstalling = uninstallMut.isPending && uninstallMut.variables === item.name
            const selectSource = () => {
              if (pluginUnavailable) return
              setSelected(item.name)
              if (customList.some(c => c.name === item.name)) {
                editExisting.mutate(item.name)
              }
            }
            return (
              <div
                key={item.name}
                className={`relative text-left rounded-lg border px-3.5 py-3 transition-all ${
                  pluginUnavailable
                    ? 'border-border/40 bg-elevated/10 opacity-70'
                    : selected === item.name
                      ? 'border-accent/50 bg-accent/5 ring-1 ring-accent/20 cursor-pointer'
                      : 'border-border/60 bg-elevated/20 hover:bg-elevated/40 cursor-pointer'
                }`}
              >
                {/* 整卡主操作: stretched-link 语义按钮 (键盘/读屏可达) — 覆盖全卡, 内容区 pointer-events-none 让点击落在这里 */}
                {!pluginUnavailable && (
                  <button
                    type="button"
                    onClick={selectSource}
                    aria-label={`配置 ${item.display_name}`}
                    className="absolute inset-0 z-0 cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  />
                )}
                <div className="pointer-events-none flex items-center gap-2 mb-1">
                  <span className={`text-sm truncate flex-1 ${selected === item.name ? 'font-medium text-foreground' : 'text-secondary'}`}>
                    {item.display_name}
                  </span>
                  {item.name === 'tickflow' && (
                    <span className="text-[9px] text-muted/50 uppercase tracking-wider shrink-0">内置</span>
                  )}
                  {pluginNames.has(item.name) && (
                    <span className="text-[9px] text-muted/50 uppercase tracking-wider shrink-0">插件</span>
                  )}
                  {pluginUnavailable ? (
                    installing ? (
                      <span className="pointer-events-auto relative z-10 inline-flex items-center gap-1 text-[9px] text-accent shrink-0">
                        <RefreshCw className="h-2.5 w-2.5 animate-spin" /> 安装中...
                      </span>
                    ) : (
                      <button
                        onClick={() => installMut.mutate(item.name)}
                        disabled={installMut.isPending}
                        className="pointer-events-auto relative z-10 inline-flex min-h-11 shrink-0 items-center gap-1 rounded bg-accent/10 px-2.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50 sm:min-h-0 sm:px-1.5 sm:py-0.5 sm:text-[10px]"
                      >
                        <Zap className="h-2.5 w-2.5" /> 安装
                      </button>
                    )
                  ) : plugin ? (
                    <div className="pointer-events-auto relative z-10 flex items-center gap-1 shrink-0">
                      {uninstalling ? (
                        <RefreshCw className="h-2.5 w-2.5 animate-spin text-muted" />
                      ) : (
                        <button
                          onClick={() => uninstallMut.mutate(item.name)}
                          disabled={uninstallMut.isPending}
                          className="min-h-11 px-2 text-xs text-muted/60 transition-colors hover:text-danger disabled:opacity-40 sm:min-h-0 sm:px-0 sm:text-[10px]"
                          title="卸载依赖"
                        >
                          卸载
                        </button>
                      )}
                    </div>
                  ) : item.name === 'tickflow' ? null : null}
                </div>
                <div className="pointer-events-none flex flex-wrap gap-1 ml-0">
                  {item.datasets.length > 0 ? item.datasets.map(ds => (
                    <span key={ds} className="text-[9px] text-muted/60 bg-elevated/60 px-1 py-0.5 rounded">
                      {DATASET_LABELS[ds] || ds}
                    </span>
                  )) : (
                    <span className="text-[9px] text-muted/40">无数据集</span>
                  )}
                </div>
                {pluginUnavailable && plugin?.install_hint && (
                  <div className="pointer-events-none ml-0 mt-1 text-[10px] text-muted/40 font-mono truncate">{plugin.install_hint}</div>
                )}
              </div>
            )
          })}

          <button
            onClick={() => setSelected('__new__')}
            className={`rounded-lg border border-dashed px-3.5 py-3 transition-all flex items-center justify-center gap-1.5 text-sm ${
              selected === '__new__'
                ? 'border-accent/50 bg-accent/5 text-accent'
                : 'border-border/50 text-muted hover:text-foreground hover:border-border hover:bg-elevated/30'
            }`}
          >
            <Plus className="h-3.5 w-3.5" />
            新增自定义数据源
          </button>
        </div>
      </section>

      {/* ===== 编辑区 ===== */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selected}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
        >
          {selected === '__new__' || customList.some(c => c.name === selected) ? (
            <DataSourceEditor
              key={selected}
              initial={null}
              existingName={selected === '__new__' ? undefined : selected}
              onCancel={() => setSelected('tickflow')}
              onSaved={() => {
                qc.invalidateQueries({ queryKey: QK.dataSources })
                if (selected !== '__new__') {
                  qc.removeQueries({ queryKey: ['data-source-detail', selected] })
                }
                if (selected === '__new__') setSelected('tickflow')
              }}
              activeName={''}
              onActivate={() => undefined}
              onDelete={selected !== '__new__' && selectedCustom ? () => setConfirmDelete(selected) : undefined}
            />
          ) : pluginList.find(x => x.name === selected) ? (
            <PluginDetail plugin={pluginList.find(x => x.name === selected)!} />
          ) : (
            <TickFlowDetail />
          )}
        </motion.div>
      </AnimatePresence>

      {/* 删除确认弹窗 */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setConfirmDelete(null)}
          />
          <div className="relative w-[90vw] max-w-[380px] rounded-dialog border border-border bg-base shadow-2xl p-6">
            <h3 className="text-sm font-medium text-foreground mb-2">删除数据源</h3>
            <p className="text-xs text-secondary mb-5">
              确认删除「{customList.find(s => s.name === confirmDelete)?.display_name || confirmDelete}」? 该数据源的配置文件将被移除,此操作不可撤销。
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-3 py-1.5 rounded-btn bg-elevated text-secondary hover:bg-elevated/80 text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => remove.mutate(confirmDelete)}
                disabled={remove.isPending}
                className="px-3 py-1.5 rounded-btn bg-danger/15 text-danger hover:bg-danger/25 text-sm font-medium transition-colors disabled:opacity-50"
              >
                {remove.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** 单个数据集的启用/禁用 + 排序编辑器。 */
function ChainEditor({
  dataset,
  sources,
  allItems,
  chain,
  saving,
  onSave,
}: {
  dataset: keyof NonNullable<Preferences['provider_chains']>
  sources: DataSourcesResponse | undefined
  allItems: DataSourceItem[]
  chain: string[]
  saving: boolean
  onSave: (names: string[]) => void
}) {
  const [draft, setDraft] = useState<string[]>(chain.length ? chain : ['tickflow'])
  const chainSignature = chain.join('\u0000')

  // Preferences arrive after the panel mounts; keep the editor aligned with
  // the server chain without overwriting an in-progress local reorder.
  useEffect(() => {
    setDraft(chain.length ? chain : ['tickflow'])
  }, [dataset, chainSignature])

  // 该数据集可用源: tickflow (全支持) + 声明支持该数据集的源
  const available = allItems.filter(item =>
    item.name === 'tickflow' || providerDatasets(sources, item.name).includes(dataset),
  )
  // 补充 draft 里可能已启用但不在 available 的源 (如卸载后又出现)
  for (const name of draft) {
    if (!available.some(a => a.name === name) && name !== 'tickflow') {
      available.push({ name, display_name: name, datasets: [] })
    }
  }

  const enabled = draft
  const disabled = available.filter(a => !enabled.includes(a.name))

  const toggle = (name: string) => {
    if (name === 'tickflow') return // 兜底不可禁
    setDraft(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name],
    )
  }
  const moveUp = (idx: number) => {
    if (idx <= 0) return
    setDraft(prev => {
      const next = [...prev]
      ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
      return next
    })
  }
  const moveDown = (idx: number) => {
    setDraft(prev => {
      if (idx >= prev.length - 1) return prev
      const next = [...prev]
      ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
      return next
    })
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(chain)

  return (
    <div className="px-4 pb-4 pt-1">
      <div className="mb-2 text-[10px] uppercase tracking-widest text-muted/50">启用顺序 (首选在前)</div>
      <div className="space-y-1.5">
        {enabled.map((name, idx) => (
          <div key={name} className="flex items-center gap-2 rounded-lg border border-border/50 bg-base px-2.5 py-2">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${idx === 0 ? 'bg-accent' : 'bg-muted/40'}`} />
            <span className="flex-1 text-xs truncate">
              <span className={idx === 0 ? 'text-accent font-medium' : 'text-foreground'}>
                {providerDisplayName(sources, name)}
              </span>
              {idx === 0 && <span className="ml-1.5 text-[9px] text-accent/70">首选</span>}
            </span>
            <button
              onClick={() => moveUp(idx)}
              disabled={idx === 0}
              className="p-1 text-muted/50 hover:text-foreground disabled:opacity-25 transition-colors"
              title="上移"
            >
              <ArrowUp className="h-3 w-3" />
            </button>
            <button
              onClick={() => moveDown(idx)}
              disabled={idx >= enabled.length - 1}
              className="p-1 text-muted/50 hover:text-foreground disabled:opacity-25 transition-colors"
              title="下移"
            >
              <ArrowDown className="h-3 w-3" />
            </button>
            {name === 'tickflow' ? (
              <span className="text-[9px] text-muted/40 inline-flex items-center gap-0.5">
                <Shield className="h-2.5 w-2.5" /> 兜底
              </span>
            ) : (
              <button
                onClick={() => toggle(name)}
                className="text-[9px] text-danger/70 hover:text-danger transition-colors"
              >
                停用
              </button>
            )}
          </div>
        ))}
        {enabled.length === 0 && (
          <div className="text-[11px] text-muted/50 px-1 py-2">无启用源 — 将自动使用 TickFlow 兜底</div>
        )}
      </div>

      {disabled.length > 0 && (
        <>
          <div className="mt-3 mb-1.5 text-[10px] uppercase tracking-widest text-muted/50">可启用</div>
          <div className="flex flex-wrap gap-1.5">
            {disabled.map(item => (
              <button
                key={item.name}
                onClick={() => toggle(item.name)}
                className="inline-flex items-center gap-1 rounded border border-border/60 bg-elevated/30 px-2 py-1 text-[11px] text-secondary hover:border-accent/40 hover:text-accent transition-colors"
              >
                <Plus className="h-2.5 w-2.5" />
                {providerDisplayName(sources, item.name)}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => onSave(draft)}
          disabled={!dirty || saving}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-btn bg-accent-solid px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-solid/90 disabled:opacity-40 transition-colors"
        >
          {saving ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
          保存
        </button>
        {dirty && (
          <button
            onClick={() => setDraft(chain.length ? chain : ['tickflow'])}
            className="px-3 py-1.5 rounded-btn text-xs text-muted hover:text-foreground transition-colors"
          >
            重置
          </button>
        )}
      </div>
    </div>
  )
}

function PluginDetail({ plugin }: { plugin: PluginDataSourceItem }) {
  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <div className="flex items-start gap-4 mb-4">
        <div className="h-11 w-11 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
          <Zap className="h-5 w-5 text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-base font-semibold text-foreground">{plugin.display_name}</h3>
            <span className="text-[10px] text-muted/50 uppercase tracking-wider">插件 · {plugin.runtime}</span>
          </div>
          {plugin.description && <p className="text-xs text-secondary leading-relaxed">{plugin.description}</p>}
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {plugin.datasets.map(ds => (
          <span key={ds} className="text-[10px] text-muted/60 bg-elevated/60 px-1.5 py-0.5 rounded">
            {DATASET_LABELS[ds] || ds}
          </span>
        ))}
      </div>
    </section>
  )
}

function TickFlowDetail() {
  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <div className="flex items-start gap-4 mb-5">
        <div className="h-11 w-11 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
          <Database className="h-5 w-5 text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base font-semibold text-foreground">TickFlow</h2>
            <span className="text-[10px] text-muted/60 uppercase tracking-wider border border-border rounded px-1.5 py-0.5">内置默认</span>
            <span className="inline-flex items-center gap-1 text-[10px] text-muted/70 bg-elevated px-1.5 py-0.5 rounded">
              <Shield className="h-2.5 w-2.5" /> 兜底源
            </span>
          </div>
          <p className="text-xs text-secondary mt-1.5 leading-relaxed">
            项目默认数据源。日K、除权因子、实时行情、分钟K、财务均由 TickFlow 提供。
            在「数据源」启用链中始终作为最终兜底, 无需额外配置。
          </p>
        </div>
      </div>
    </section>
  )
}
