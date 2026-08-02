/** 数据源 provider 元数据辅助: 在 builtin + custom 中解析显示名 / 数据集能力。 */
import type { DataSourceItem, DataSourcesResponse } from './api'

/** 数据集 key → 中文标签 (DataSources 卡片徽标 / 状态条用)。 */
export const DATASET_LABELS: Record<string, string> = {
  daily: '日K',
  adj_factor: '除权',
  realtime: '实时',
  minute: '分钟',
  financial: '财务',
  boards: '板块',
  snapshot: '快照',
  margin: '两融',
  calendar: '日历',
  news: '快讯',
}

/**
 * 查 provider 元数据 (builtin 优先, 其次 custom)。返回 {name, display_name, datasets}。
 * 后端 /data-sources 的 builtin + custom 都是 DataSourceItem 形状。
 */
export function providerMeta(
  dataSources: DataSourcesResponse | undefined,
  name: string,
): DataSourceItem | undefined {
  if (!dataSources || !name) return undefined
  const all = [
    ...(dataSources.builtin ?? []),
    ...(dataSources.custom ?? []),
  ]
  return all.find(s => s.name === name)
}

/** provider 显示名: tickflow → 'TickFlow'; 其它查 builtin/custom, 未知回退原名。 */
export function providerDisplayName(
  dataSources: DataSourcesResponse | undefined,
  name: string,
): string {
  if (!name || name === 'tickflow') return 'TickFlow'
  return providerMeta(dataSources, name)?.display_name || name
}

/** provider 支持的数据集列表 (tickflow → 全量 5 类, 其它查 builtin/custom)。 */
export function providerDatasets(
  dataSources: DataSourcesResponse | undefined,
  name: string,
): string[] {
  if (!name || name === 'tickflow') {
    return ['daily', 'adj_factor', 'realtime', 'minute', 'financial']
  }
  return providerMeta(dataSources, name)?.datasets ?? []
}

/** 是否为非 tickflow 自定义/内置源 (用于状态条高亮)。 */
export function isNonTickflow(name: string): boolean {
  return Boolean(name) && name !== 'tickflow'
}
