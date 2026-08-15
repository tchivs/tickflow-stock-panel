// 后端 API 客户端 — 全项目统一入口
//
// Dev:Vite 代理 /api 到 :3018
// Prod:同源(FastAPI 托管前端 dist)

import { toast } from '@/components/Toast'

const BASE = ''

export class ApiRequestError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.detail = detail
  }
}

export async function request<T>(path: string, init?: RequestInit & { silent?: boolean }): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const headers: Record<string, string> = {}
  if (!isFormData) headers['Content-Type'] = 'application/json'
  // 合并调用方传入的 headers (此前会被整体覆盖丢弃)
  Object.assign(headers, init?.headers as Record<string, string> | undefined)
  // silent: 调用方自行处理错误响应 (如 404 属正常状态), 不弹全局错误 toast。
  const { silent, ...fetchInit } = init ?? {}
  const res = await fetch(`${BASE}${path}`, { ...fetchInit, headers })
  if (!res.ok) {
    let detail: unknown = ''
    let message = ''
    try {
      const payload: unknown = JSON.parse(await res.text())
      if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
        const record = payload as Record<string, unknown>
        detail = record.detail ?? record.message ?? ''
      }
      if (Array.isArray(detail)) {
        message = detail.map(item => item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item)).join('; ')
      } else if (typeof detail === 'string') {
        message = detail
      } else if (detail && typeof detail === 'object') {
        message = JSON.stringify(detail)
      }
    } catch { /* ignore */ }
    const safeMessage = message || `${res.status} ${res.statusText}`
    // 401 (未登录/会话过期) 不弹 toast — 由全局认证拦截器统一跳登录页, 避免刷屏
    if (res.status !== 401 && !silent) toast(safeMessage, 'error')
    throw new ApiRequestError(res.status, safeMessage, detail)
  }
  return res.json() as Promise<T>
}

// ===== Capabilities =====
export interface CapabilityLimits {
  rpm: number | null
  batch: number | null
  subscribe: number | null
}

export interface CapabilitiesResponse {
  label: string
  capabilities: Record<string, CapabilityLimits>
}

// ===== 竞价数据探测 (DATA-03) =====
export interface AuctionProbeVerdict {
  status: 'not_configured' | 'available' | 'fail_closed' | 'error'
  source: string | null
  probed_at: string | null
  window: string
  fallback: string
  detail: string
}

// ===== 竞价历史聚合 (CHART-01/02) =====
/** 单日竞价窗口末行 (09:25 最终撮合, 服务端 D1 聚合)。 */
export interface AuctionHistoryRow {
  date: string
  datetime?: string | null
  auction_volume: number | null
  auction_amount: number | null
  /** 可选委托输入列 (CHART-03 源提供才透传; 派生估算, 本图绝不混排) */
  auction_unmatched_volume?: number | null
  auction_virtual_price?: number | null
  /** 窗口内行数 / 首末时间戳 —— 粒度标注 */
  row_count: number
  min_datetime?: string | null
  max_datetime?: string | null
}

export interface AuctionHistoryResponse {
  symbol: string
  name?: string | null
  /** 诚实空态: 湖空 / probe 非 available / guest 掩码 → false (200 非 404) */
  available: boolean
  probe: AuctionProbeVerdict
  mode?: 'vip' | 'guest'
  coverage: number
  window: string
  rows: AuctionHistoryRow[]
  unit?: { auction_volume: string; auction_amount: string }
}

// ===== Financials =====
export interface FinancialStatus {
  available: boolean
  tables: Record<string, { rows: number; symbols: number }>
  last_sync: Record<string, string>
  /** 服务端是否正在同步(手动触发)——驱动"同步中"UI 并防重复点击 */
  syncing?: boolean
}

export interface FinancialMetricRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  eps_basic?: number | null
  eps_diluted?: number | null
  bps?: number | null
  ocfps?: number | null
  roe?: number | null
  roe_diluted?: number | null
  roa?: number | null
  gross_margin?: number | null
  net_margin?: number | null
  debt_to_asset_ratio?: number | null
  revenue_yoy?: number | null
  net_income_yoy?: number | null
  operating_cash_to_revenue?: number | null
  inventory_turnover?: number | null
  [key: string]: any
}

export interface FinancialIncomeRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  revenue?: number | null
  operating_cost?: number | null
  operating_profit?: number | null
  total_profit?: number | null
  net_income?: number | null
  net_income_attributable?: number | null
  basic_eps?: number | null
  diluted_eps?: number | null
  [key: string]: any
}

export interface FinancialBalanceSheetRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  total_assets?: number | null
  total_current_assets?: number | null
  cash_and_equivalents?: number | null
  total_liabilities?: number | null
  total_equity?: number | null
  equity_attributable?: number | null
  [key: string]: any
}

export interface FinancialCashFlowRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  net_operating_cash_flow?: number | null
  net_investing_cash_flow?: number | null
  net_financing_cash_flow?: number | null
  capex?: number | null
  net_cash_change?: number | null
  [key: string]: any
}

/** AI 财务分析历史报告 */
export interface AiFinancialReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  periods?: number
  summary?: string
  created_at: string
}

// ===== 个股分析 =====
export type LevelType = 'sr' | 'pivot' | 'extreme' | 'boll' | 'keltner_s' | 'keltner_m' | 'keltner_l' | 'atr_stop' | 'gap' | 'fib' | 'round'

export interface PriceLevel {
  value: number
  label: string
  type: LevelType
  side: 'resistance' | 'support' | 'neutral'
  strength?: 'strong' | 'medium' | 'weak'
  /** 档位(仅 pivot 有):0=P, 1=R1/S1, 2=R2/S2, 3=R3/S3。前端按"显示到第几档"过滤。 */
  rank?: number
}

/** 带状曲线指标(布林带/Keltner/ATR)的每日时间序列,与 dates 对齐。 */
export interface LevelSeries {
  boll?: { upper: (number | null)[]; lower: (number | null)[]; mid?: (number | null)[] }
  keltner_s?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_m?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_l?: { upper: (number | null)[]; lower: (number | null)[] }
  atr?: { stop_loss: (number | null)[]; take_profit: (number | null)[] }
}

export interface StockLevels {
  levels: Record<LevelType, PriceLevel[]>
  close: number | null
  summary: string
  symbol: string
  /** dates 与 series 对齐;前端按自身 rows 的日期映射,缺失填 null */
  dates?: string[]
  series?: LevelSeries
}

export interface AiStockReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  summary?: string
  close?: number | null
  levels?: Record<LevelType, PriceLevel[]>
  created_at: string
}

// ===== Evidence-backed analysis =====
// The browser only identifies a subject and invokes server-issued review references.
// Provenance, source grades, cross-checks, and lifecycle authority remain server-owned.
export type AnalysisSubjectKind = 'stock' | 'portfolio'

export interface AnalysisSubject {
  kind: AnalysisSubjectKind
  key: string
}

export interface AnalysisRequestSubject {
  kind: 'instrument' | 'account'
  key: string
}

export interface AnalysisRun {
  id: string
  subject_kind: AnalysisRequestSubject['kind']
  subject_key: string
  focus: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  report_id?: string | null
  created_at: string
  updated_at: string
}

export interface AnalysisReportSummary {
  id: string
  subject: AnalysisSubject
  version: number
  status: 'validated' | 'failed'
  generated_at: string
  evidence_limitations?: string[]
}

export interface AnalysisPerspective {
  name: string
  conclusion: string
  evidence_count: number
  limitations: string[]
}

export interface AnalysisScoreDimension {
  name: string
  contribution?: number | null
  weight?: number | null
  evidence_ids: string[]
  rationale: string
  uncertainty?: string | null
}

export interface AnalysisValuation {
  applicable: boolean
  reason?: string | null
  method?: string | null
  inputs?: Record<string, unknown> | null
  as_of?: string | null
  range?: string | null
  limitations?: string[]
}

export interface AnalysisIcMemo {
  thesis: string
  supporting_evidence?: string[]
  risks: string[]
  open_questions: string[]
  valuation_anchor?: string | null
  invalidation_conditions?: string[]
  evidence_limitations?: string[]
}

export interface AnalysisReport extends AnalysisReportSummary {
  signal_id: string
  perspectives: AnalysisPerspective[]
  score?: { value?: number | null; dimensions: AnalysisScoreDimension[] } | null
  valuation?: AnalysisValuation | null
  ic_memo: AnalysisIcMemo
}

export interface AnalysisEvidenceSource {
  id: string
  name: string
  grade: 'A' | 'B' | 'C'
  source_type: string
  retrieved_at: string
  period?: string | null
  definition?: string | null
  independence_group?: string | null
  reference?: string | null
}

export interface AnalysisMaterialNumber {
  id: string
  label: string
  value: number | string | null
  unit: string
  period: string
  source_count: number
  cross_check: 'confirmed' | 'unresolved' | 'conflicting' | 'context_insufficient'
  difference_reason?: string | null
  affected_conclusion_ids?: string[]
}

export interface AnalysisEvidence {
  report_id: string
  sources: AnalysisEvidenceSource[]
  material_numbers: AnalysisMaterialNumber[]
}

export interface AnalysisLifecycleEvent {
  state: 'strengthened' | 'weakened' | 'falsified' | 'priced_in'
  occurred_at: string
  evidence_summary: string
  source_grade?: 'A' | 'B' | 'C' | null
  cross_check?: AnalysisMaterialNumber['cross_check'] | null
}

export interface AnalysisSignalHistory {
  signal_id: string
  current_state: AnalysisLifecycleEvent['state'] | null
  events: AnalysisLifecycleEvent[]
  pending_review_id: string | null
  reviews: AnalysisLifecycleReview[]
  plans: AnalysisObservationPlan[]
  outcome: AnalysisOutcomeSummary | null
}

export type AnalysisReviewStatus = 'pending' | 'confirmed' | 'rejected'

export interface AnalysisLifecycleReview {
  id: string
  prior_state: AnalysisLifecycleEvent['state'] | 'active' | null
  proposed_state: AnalysisLifecycleEvent['state'] | 'rejected'
  status: AnalysisReviewStatus
  evidence_ids: string[]
  rationale: string | null
  created_at: string | null
}

export interface AnalysisObservationOutcome {
  id: string
  plan_id: string
  observed_at: string
  created_at: string
  outcome: {
    status: 'complete' | 'incomplete'
    observed_value?: number | null
    notes?: string
  }
}

export interface AnalysisObservationOutcomeInput {
  status: 'complete' | 'incomplete'
  observed_value: number | null
  notes: string
}

export interface AnalysisObservationPlan {
  id: string
  review_id: string
  event_id: string
  window_days: 20 | 60 | 120
  benchmark: string
  metric: string
  created_at: string
  outcomes: AnalysisObservationOutcome[]
}

export interface AnalysisOutcomeSummary {
  status: 'pending' | 'recorded'
  outcomes?: AnalysisObservationOutcome[]
}

// ===== Controlled advanced research =====
// These DTOs contain only server-projected facts. The browser identifies an
// existing object and allowed task type; it never sends scope or authorization.
export type AdvancedTaskType = 'research_draft' | 'experiment' | 'strategy_evaluation'
export type AdvancedJobStage = 'authorized' | 'frozen' | 'drafted' | 'gates_complete' | 'awaiting_review' | 'recorded' | 'rejected'
export type AdvancedTerminalStatus = 'unevaluable' | 'insufficient_sample' | 'rejected' | 'constraint_failed' | 'awaiting_review' | 'recorded'

export interface AdvancedViewpointEvaluation {
  status: 'evaluated' | 'unevaluable' | 'insufficient_sample'
  reason: string | null
  window_days: 20 | 60 | 120 | null
  benchmark: string | null
  relative_return: number | null
}

export interface AdvancedViewpointRevisionInput {
  conclusion?: string
  direction?: AdvancedViewpoint['direction']
  rating?: AdvancedViewpoint['rating']
  target_range?: [number, number]
  horizon_days?: number
  confidence?: AdvancedViewpoint['confidence']
  evidence?: { id: string; published_at?: string }[]
}

export interface AdvancedViewpointCorrectionInput extends AdvancedViewpointRevisionInput {
  correction_reason: string
}

export interface AdvancedViewpoint {
  id: string
  viewpoint_id: string
  version: number
  status: AdvancedTerminalStatus
  source_profile: string
  instrument: string
  published_at: string
  direction: 'bullish' | 'bearish' | 'neutral'
  rating: 'overweight' | 'neutral' | 'underweight'
  conclusion: string
  target_range: number[]
  horizon_days: number | null
  confidence: 'low' | 'medium' | 'high'
  revision_kind: 'initial' | 'non_material_revision' | 'material_stance_change' | 'correction'
  correction_reason: string | null
  evaluation: AdvancedViewpointEvaluation | null
  audit_reference: string | null
}

export interface AdvancedCalibrationBucket {
  status: 'calibrated' | 'insufficient_sample'
  sample_count: number
  hit_rate: number | null
  mean_relative_return: number | null
  coverage_start: string | null
  coverage_end: string | null
}

export interface AdvancedCalibration {
  low: AdvancedCalibrationBucket
  medium: AdvancedCalibrationBucket
  high: AdvancedCalibrationBucket
  excluded_unevaluable: number
}

export interface AdvancedJob {
  id: string
  subject: AnalysisRequestSubject
  status: AdvancedJobStage
  stage: AdvancedJobStage
  stage_recorded_at: string
  audit_reference: string | null
}

export interface AdvancedAudit {
  reference: string
  decision: 'authorized' | 'rejected' | 'recorded'
  reason: string
}


export interface AdvancedResearchAssetBinding {
  strategy_id: string
  research_asset_id: string
  factor_name: string
  provenance: Record<string, unknown>
}
export interface AdvancedExperimentSpecification {
  id: string
  research_asset_id: string
  version: number
  hypothesis: string
  data_scope: AdvancedFrozenStrategyScope
  method: string
  metrics: string[]
  created_at: string
}

export interface AdvancedExecutionEvidenceWindow {
  run_id: string | null
  governed_input_fingerprint: string | null
  window?: Record<string, string>
  eligible_buy_count: number
  completed_trade_count: number
}

export interface AdvancedExecutionEvidence {
  aggregate: AdvancedExecutionEvidenceWindow
  in_sample: AdvancedExecutionEvidenceWindow
  out_of_sample: AdvancedExecutionEvidenceWindow
}

export interface AdvancedExperimentRun {
  id: string
  specification_id: string
  status: 'completed' | 'validation_failed' | 'timed_out' | 'resource_limited'
  governed_fingerprint: string
  asset_version: string | null
  parameters: Record<string, string | number | boolean | null>
  environment: Record<string, string | number | boolean | null>
  resource_limits: Record<string, string | number | boolean | null>
  metrics: Record<string, string | number | boolean | null>
  artifact_count: number
  constraint_reason: string | null
  created_at: string
  execution_evidence: AdvancedExecutionEvidence
}

export interface AdvancedFrozenStrategyScope {
  market: 'CN-A'
  strategy_id: string
  start: string
  end: string
  symbols?: string[]
  asset_type: 'stock' | 'etf' | 'index'
  parameters: Record<string, string | number | boolean | null>
}

export interface AdvancedExperimentInput {
  research_asset_id: string
  hypothesis: string
  data_scope: AdvancedFrozenStrategyScope
  method: string
  metrics: string[]
  success_criteria: Record<string, string | number | boolean | null>
  failure_criteria: Record<string, string | number | boolean | null>
}

export interface AdvancedExperimentFeedback {
  id: string
  run_id: string
  conclusion: 'supported' | 'refuted' | 'inconclusive' | 'needs_replication'
  notes: string
  created_at: string
}

export interface AdvancedPromotionGate {
  name: string
  status: 'passed' | 'failed'
  evidence: string
}

export interface AdvancedCandidate {
  id: string
  parent_asset_id: string
  parent_version: string
  mutation: string
  seed: number
  resolved_config: Record<string, string | number | boolean>
  created_at: string
  gates: AdvancedPromotionGate[]
}

export interface AdvancedSandboxValidation {
  status: 'rejected' | 'validated' | 'constraint_failed'
  reason: string
  audit_reference: string
  source_sha256: string
}

export interface AdvancedSandboxRun {
  run_id: string
  status: 'completed' | 'failed'
  terminal_reason: string | null
  proof_fingerprint: string | null
  resources: Record<string, string | number | boolean>
  audit_reference: string | null
  created_at: string
}

export interface AdvancedSandboxSubmissionResult {
  validation?: AdvancedSandboxValidation
  run?: AdvancedSandboxRun
}

// ===== Kline =====
export interface MinuteKlineRow {
  datetime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

export interface KlineRow {
  symbol?: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
  change_pct?: number
  ma5?: number | null
  ma20?: number | null
  ma60?: number | null
  macd_dif?: number | null
  macd_dea?: number | null
  macd_hist?: number | null
  rsi_14?: number | null
  vol_ratio_5d?: number | null
  [key: string]: any
}

// ===== Watchlist =====
export interface WatchlistEntry {
  symbol: string
  added_at: string
  note?: string
  name?: string | null
}

export interface Quote {
  symbol: string
  price?: number
  pct?: number
  close?: number
  change_pct?: number
  [key: string]: any
}

export interface IndexInstrument {
  symbol: string
  name?: string | null
  code?: string | null
  asset_type?: 'index'
  [key: string]: any
}

export interface IndexQuote {
  symbol: string
  name?: string | null
  last_price?: number | null
  close?: number | null
  prev_close?: number | null
  change_pct?: number | null
  change_amount?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  volume?: number | null
  amount?: number | null
  timestamp?: number | null
  [key: string]: any
}

// ===== Screener =====
export interface ScreenerStrategy {
  id: string
  name: string
  description: string
  source?: string
}

export interface StrategyLoadError {
  file: string
  error: string
}

export interface ScreenerResult {
  as_of: string
  strategy: string | null
  rows: any[]
  total: number
  elapsed_ms: number
}

export interface MarketSnapshotRow {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  amount?: number | null
  volume?: number | null
  turnover_rate?: number | null
  vol_ratio_5d?: number | null
  total_shares?: number | null
  float_shares?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  consecutive_limit_ups?: number | null
  [key: string]: any
}

// ===== 股池 Hub (Phase 18 / Phase 23 扩展) =====
/** 服务端冻结的竞价列存在性声明 (OQ-2) — real 只在该快照 probe available 时非空 */
export interface AuctionColumnsDecl {
  real: string[]
  derived: string[]
}

/** 股池可用交易日列表 (POOL-05) — ISO desc; 空 → {dates: [], count: 0, latest: null} */
export interface PoolDatesResponse {
  dates: string[]
  count: number
  latest: string | null
}

/** 股池个股行: 五列 + 交叉共振 + 竞价列透传, 全部服务端投影 (POOL-01/02, 单 as_of 源) */
export interface PoolHubRow {
  symbol: string
  code: string
  /** 股票名称 — VIP 明文; 游客会话由服务端脱敏为固定掩码串, 前端原样渲染 (GUEST-01) */
  name: string
  open_gap: number | null
  change_pct: number | null
  concept_board: string[]
  hit_factors: string[]
  cross_resonance: boolean
  /** 竞价量 (股) — 仅 probe available 日存在; 列存在性由 auction_columns 声明 (guest 永无) */
  auction_volume?: number | null
  /** 竞价金额 (元) — 仅 probe available 日存在 */
  auction_amount?: number | null
  /** 竞价量比 (派生) */
  auction_volume_ratio?: number | null
  /** 虚拟未匹配金额 (元·估算, 派生) */
  auction_unmatched_amount?: number | null
}

export interface PoolHubStrategy {
  id: string
  name: string
  total: number
  rows: PoolHubRow[]
}

export interface PoolHubResponse {
  as_of: string | null
  /** PIT-8 双型容忍: hub=epoch ms / history=ISO 串 / 空态 null */
  updated_at: number | string | null
  /** 服务端声明的展示模式 (GUEST-01) — 前端只消费, 绝不从行值推导 */
  mode: 'guest' | 'vip'
  strategies: PoolHubStrategy[]
  resonance_count: number
  /** 快照缺失诚实空态 (200 语义, 非 404) — 仅 history 缺失日返回 */
  available?: boolean
  /** 服务端冻结的竞价列存在性声明 (OQ-2); guest 响应由掩码剥离, 永无此键 */
  auction_columns?: AuctionColumnsDecl
  /** 概念归属标注 (实时 join 当前 ext, 不冻结历史标签) */
  concept_attribution?: string
  /** 概念归属生效日期 (CONCEPT-07): as_of_snapshot 时 = 分区日 (YYYY-MM-DD); 回退态缺键/Null */
  concept_effective_date?: string | null
  /** 概念分区归档时刻 (CONCEPT-07): as_of_snapshot 时 = manifest.captured_at; 回退态缺键/Null */
  concept_captured_at?: string | null
}

/** 盘前预览载荷 (PM-04) — 扩展 PoolHubResponse: 窗口标注 / provisional / degraded / probe 透传。
 *  服务端空态 200 时 as_of=今日/available:false/strategies:[]/updated_at:null/probe:null 也兼容
 *  (扩展字段全部可选)。与 /hub 同形状投影 — 前端复用既有 strategies/auction_columns/概念筛选/钻取渲染。 */
export interface PremarketPoolResponse extends PoolHubResponse {
  /** 服务端窗口声明 — 盘前预览恒为 'pre_open' (独立于 EOD 归档, 不冒充收盘定稿) */
  window: 'pre_open'
  /** 基于开盘/定盘价, 非收盘定稿 (provisional 语义) */
  provisional?: boolean
  /** 真实竞价列不可用 (probe 非 available) → 前端强制诚实警告分支 (绝不渲染「竞价数据可用」) */
  degraded?: boolean
  /** 服务端冻结的 probe 判定 (与 /api/data/auction-probe 同词汇) */
  probe?: AuctionProbeVerdict | null
}

export interface OverviewDimensionRankItem {
  name: string
  count: number
  avg_pct: number
  up_count: number
  down_count: number
  amount: number
  leader?: {
    symbol?: string | null
    name?: string | null
    change_pct?: number | null
  } | null
}

export interface OverviewMarket {
  as_of: string | null
  quote_status: {
    enabled?: boolean
    running?: boolean
    quote_age_ms?: number | null
    is_trading_hours?: boolean
    [key: string]: any
  }
  indices: IndexQuote[]
  breadth: {
    total: number
    up: number
    down: number
    flat: number
    up_pct: number
    down_pct: number
    avg_pct?: number | null
    median_pct?: number | null
    strong_up?: number
    strong_down?: number
  }
  amount: { total: number; avg: number }
  boards: { board: string; count: number; up: number; down: number; up_pct: number; amount: number }[]
  limit: { limit_up: number; broken: number; failed: number; limit_down: number; max_boards: number; seal_rate?: number; tiers: { boards: number; count: number }[]; sealed_ready?: boolean; fake_up?: number; fake_down?: number }
  distribution: { label: string; count: number; pct: number }[]
  trend: { above_ma5: number; above_ma20: number; above_ma60: number; above_ma5_pct: number; above_ma20_pct: number; above_ma60_pct: number; new_high: number; new_low: number }
  activity: { avg_turnover: number; high_turnover: number; high_vol_ratio: number; vol_ratio: number }
  radar: { key: string; label: string; value: number }[]
  emotion: { score: number; label: string }
  top_gainers: MarketSnapshotRow[]
  top_losers: MarketSnapshotRow[]
  turnover_leaders: MarketSnapshotRow[]
  active_leaders: MarketSnapshotRow[]
  concept_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
  industry_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
}

// ===== 概念涨幅轮动矩阵 =====
// dates: 日期字符串列表(最新在最前); columns: {日期: [[概念名, 涨幅小数], ...]} 每列各自降序
export interface RpsRotationData {
  dates: string[]
  columns: Record<string, [string, number][]>
  concept_count: number
}

// ===== 大盘复盘 =====
export interface AiReviewReport {
  id: string
  as_of: string
  focus?: string
  content: string
  summary?: string
  emotion_score?: number | null
  emotion_label?: string
  created_at: string
}

// ===== Strategy Engine =====
export interface StrategyParamDef {
  id: string
  label: string
  type: 'float' | 'int' | 'select' | 'bool'
  default: number | string | boolean
  min?: number
  max?: number
  step?: number
  options?: string[]
}

export interface StrategyDetail {
  id: string
  name: string
  description: string
  tags: string[]
  source: 'builtin' | 'custom' | 'ai'
  version: string
  basic_filter: Record<string, any>
  params: StrategyParamDef[]
  params_defaults: Record<string, any>
  scoring: Record<string, number>
  entry_signals: string[]
  exit_signals: string[]
  stop_loss: number | null
  take_profit: number | null
  trailing_stop: number | null
  trailing_take_profit_activate: number | null
  trailing_take_profit_drawdown: number | null
  max_hold_days: number | null
  display_limit?: number
  alerts: { field: string; op?: string; value?: number; message: string }[]
  order_by: string
  descending: boolean
  limit: number
}

export interface StrategyBuildResult {
  code: string
  meta: Record<string, any>
  valid: boolean
  error: string | null
}

export type StrategyBuildStreamEvent =
  | { type: 'meta'; strategy_id?: string; step?: number }
  | { type: 'delta'; content: string }
  | ({ type: 'result' } & StrategyBuildResult)
  | { type: 'error'; message: string }

export interface StrategyCodeSaveResult {
  ok: boolean
  strategy_id: string
  source: 'ai' | 'custom'
  path: string
  meta: Record<string, any>
}

// ===== Custom Signals (自定义信号) =====
export interface CustomSignalCondition {
  left: string     // 字段名
  op: string       // > >= < <= == !=
  right: string    // "field:xxx" 或数字字符串
}

export interface CustomSignal {
  id: string
  name: string
  kind: 'entry' | 'exit' | 'both'
  conditions: CustomSignalCondition[]
  enabled: boolean
}

export interface CustomSignalOptions {
  fields: { key: string; label: string }[]
  operators: string[]
  kinds: { key: string; label: string }[]
}

// ===== Monitor (监控规则 + 触发记录) =====
export interface MonitorCondition {
  field: string
  op: string              // truth | > >= < <= == !=
  value?: number | null   // op 非 truth 时必填
}

export type SectorKind = 'index' | 'concept' | 'industry'

export interface SectorMonitorTarget {
  key: string
  kind: SectorKind
  name: string
  symbol?: string
  source_id?: string
  field?: string
  source_field?: string
  value?: string
  level?: number | null
  available: boolean
  member_count: number
}

export interface MonitorRule {
  id: string
  name: string
  enabled: boolean
  // preopen: 09:26 盘前帧竞价白名单字段规则 (30-02 /options 契约)
  type: 'strategy' | 'signal' | 'price' | 'market' | 'position' | 'ladder' | 'preopen' | 'sector'
  asset_type?: 'stock' | 'etf'
  scope: 'symbols' | 'all' | 'sector' | 'positions'
  symbols: string[]
  position_ids?: Array<string | number>
  sector?: string | null
  // 板块监控 (type=sector): 对象种类 / 监控对象 / 触发维度
  sector_kind?: SectorKind | null
  sector_targets?: SectorMonitorTarget[]
  sector_trigger?: 'change_pct' | 'momentum'
  threshold_pct?: number
  window_minutes?: 1 | 3 | 5 | 10 | 15
  strategy_id?: string | null
  direction: 'entry' | 'exit' | 'both' | 'up' | 'down'
  conditions: MonitorCondition[]
  logic: 'and' | 'or'
  cooldown_seconds: number
  active_time_start?: string | null
  active_time_end?: string | null
  bypass_quiet_period?: boolean
  severity: 'info' | 'warn' | 'critical'
  message: string
  webhook_url?: string
  webhook_enabled?: boolean
  webhook_channels?: string[]
  created_at?: string
  metric?: 'sealed_vol' | 'sealed_amount'
  threshold?: number
}

export interface MonitorRuleOptions {
  threshold_fields: { key: string; label: string }[]
  builtin_signals: { key: string; label: string }[]
  custom_signals: { key: string; label: string }[]
  operators: string[]
  types: { key: string; label: string }[]
  scopes: { key: string; label: string }[]
  logics: { key: string; label: string }[]
  severities: { key: string; label: string }[]
  directions: { key: string; label: string }[]
  // 盘前竞价白名单字段 (30-02 /options 外露: PREOPEN_ALLOWED_FIELDS + ENRICHED_COLUMNS 中文标签);
  // 旧后端缺键 → 前端回退空数组零崩溃。
  preopen_threshold_fields?: { key: string; label: string }[]
  // 板块监控对象目录 (type=sector 规则编辑器用), 按 kind 分组。
  sector_targets?: Record<SectorKind, SectorMonitorTarget[]>
}

export type DeliveryStatus = 'pending' | 'sent' | 'failed' | 'skipped'

export interface DeliveryOutcome {
  channel: 'feishu' | 'telegram'
  status: DeliveryStatus
  error: string | null
  created_at?: string
  updated_at?: string
}

export interface AlertHistoryFilters {
  days?: number
  limit?: number
  source?: string
  type?: string
  severity?: 'info' | 'warn' | 'critical'
  delivery_status?: DeliveryStatus
}

export interface AlertEvent {
  id?: string
  ts?: number
  occurred_at?: string
  rule_id?: string
  rule_name?: string
  source: string
  type: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
  severity?: 'info' | 'warn' | 'critical'
  strategy_id?: string
  conditions?: MonitorCondition[]
  logic?: 'and' | 'or'
  account_id?: string | number | null
  position_id?: string | number | null
  valuation_source?: 'shared_quote' | 'governed_close' | 'unavailable' | null
  valuation_as_of?: string | null
  deliveries?: DeliveryOutcome[]
  // 盘前告警增量键 (30-02 _preopen_sse_shape SSE dict): 与后端事件键集对齐;
  // 全部可选 — 旧事件缺键时前端零渲染 (徽标不出现, 零崩溃)。
  window?: string
  provisional?: boolean
  degraded?: boolean
  strategy_ids?: string[]
  preopen_metrics?: Record<string, number | null>
  // 板块告警增量键 (type=sector 事件): 与后端事件键集对齐; 全部可选。
  sector_kind?: SectorKind
  sector_key?: string
  sector_name?: string
  sector_source_field?: string
  sector_value?: string
  sector_level?: number | null
  window_change_pct?: number | null
  coverage_ratio?: number
  valid_count?: number
  total_count?: number
  up_count?: number
  down_count?: number
  leader?: { symbol?: string; name?: string; change_pct?: number } | null
}

// ===== Portfolio =====
export interface PortfolioAccount {
  id: number
  name: string
  available_funds: number
  enabled: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
  notes: string
}

export interface PortfolioAccountInput {
  name: string
  available_funds?: number
  enabled?: boolean
  notes?: string
}

export interface PortfolioPositionInput {
  account_id: number
  instrument_symbol: string
  cost_price: number
  quantity: number
  invested_amount: number
  trading_style: 'short' | 'swing' | 'long'
  enabled?: boolean
  notes?: string
}

export interface PortfolioPosition extends PortfolioPositionInput {
  id: number
  position_id: number
  archived_at: string | null
  created_at: string
  updated_at: string
  market_value: number | null
  unrealized_pnl: number | null
  pnl_pct: number | null
  source: 'shared_quote' | 'governed_close' | 'unavailable'
  as_of: string | null
  fresh: boolean
}

export interface PortfolioSummary {
  account_id: number | null
  available_funds: number
  market_value: number | null
  total_assets: number | null
  unrealized_pnl: number | null
  accounts: PortfolioAccount[]
  positions: PortfolioPosition[]
  unavailable_position_ids: number[]
}

// ===== Decision playbook =====
export interface PlaybookSnapshot {
  symbol: string
  entry_low: number
  entry_high: number
  stop: number
  target1: number
  target2: number
  position_pct: number
  action: string
  score: number
  risk_reward: number
  reason_snapshot: Record<string, string>
}

export interface AdjustmentAudit {
  field: string
  proposed_value: string | null
  final_value: string | null
  disposition: 'applied' | 'clamped' | 'rejected'
  rationale: string
}

export interface DecisionAdjustmentProposal {
  field: string
  value: string
  rationale: string
}

export interface DecisionReviewProposal {
  provider: string
  model: string
  adjustments: DecisionAdjustmentProposal[]
}

export interface DecisionReviewResult {
  review_status: 'available' | 'unavailable'
  final: PlaybookSnapshot
}

export interface DecisionRun {
  id: string
  symbol: string
  data_as_of: string
  engine_config_version: string
  created_at: string
  baseline: PlaybookSnapshot
  final: PlaybookSnapshot
  proposal: DecisionReviewProposal | null
  adjustments: AdjustmentAudit[]
}

export interface DecisionRunInput {
  symbol: string
  as_of: string
  engine_config_version?: string
  configuration?: Record<string, unknown>
}

export interface HistoricalReplay {
  id: string
  as_of: string
  engine_config_version: string
  result_hash: string
  snapshot: Record<string, unknown>
  provider: null
  model: null
  created_at: string
}

/** 生成监控规则 id (时间戳 + 随机后缀), 用户无需手动填写。 */
export function genRuleId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 6)
  return `mr_${ts}_${rand}`
}

// ===== Limit Ladder =====
export interface LimitLadderStock {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  consecutive_limit_ups?: number | null
  consecutive_limit_downs?: number | null
  status?: 'limit_up' | 'broken' | 'failed' | 'limit_down' | 'recovery' | null
  /** 五档 sealed: real=真封板, fake=假涨停(已归炸板), pending=待确认, null=降级/无能力 */
  sealed_status?: 'real' | 'fake' | 'pending' | null
  /** 封单量(买一/卖一量), 仅真封板有值 */
  sealed_vol?: number | null
}

export interface LimitLadderTier {
  boards: number
  count: number
  stocks: LimitLadderStock[]
}

export interface LimitLadderResult {
  as_of: string
  tiers: LimitLadderTier[]
  /** 双方向涨跌停计数(修正后, 不论当前 direction) */
  counts?: { up: number; down: number }
  /** 双方向涨跌停原始计数(修正前, 供弹窗对比) */
  counts_raw?: { up: number; down: number }
  /** sealed 数据是否就绪(false→前端显示降级标识) */
  sealed_ready?: boolean
  /** sealed 数据 age(秒), null=盘后定版或无数据 */
  sealed_age?: number | null
  /** sealed 修正统计: real=真封板, fake=假涨停(归炸板), pending=待确认 */
  sealed_counts?: { real: number; fake: number; pending: number }
  /** 涨停侧 sealed 明细 */
  sealed_counts_up?: { real: number; fake: number; pending: number }
  /** 跌停侧 sealed 明细 */
  sealed_counts_down?: { real: number; fake: number; pending: number }
}

// ===== Backtest =====
export interface BacktestResult {
  run_id: string
  config: any
  stats: Record<string, any>
  equity_curve: { date: string; value: number }[]
  trades: any[]
  per_symbol_stats: { symbol: string; total_return: number }[]
}

// ===== Factor Backtest =====
export interface FactorColumn {
  id: string
  label: string
  group: string
  desc: string
}

export interface GroupStat {
  group: number
  label: string
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  win_rate: number
}

export interface FactorBacktestResult {
  run_id: string
  config: Record<string, any>
  ic_mean: number | null
  ic_std: number | null
  ir: number | null
  ic_win_rate: number | null
  ic_series: { date: string; ic: number }[]
  group_stats: GroupStat[]
  group_nav: Record<string, any>[]
  long_short_stats: Record<string, any>
  long_short_nav: { date: string; value: number }[]
  elapsed_ms: number
  n_symbols: number
  n_dates: number
  error: string | null
}

// ===== Strategy Backtest =====
export interface StrategyBacktestTrade {
  symbol: string
  name?: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  pnl_pct: number
  duration: number
  exit_reason: string
  shares?: number
  lots?: number
  position_pct?: number
  entry_value?: number
  exit_value?: number
  pnl_amount?: number
  entry_score?: number | null
  entry_signal_date?: string | null
  exit_signal_date?: string | null
  blocked_exit_days?: number
  entry_signal_id?: string | null
  exit_signal_id?: string | null
}

export interface StrategyBacktestResult {
  run_id: string
  config: Record<string, any>
  stats: Record<string, any>
  equity_curve: { date: string; value: number; cash?: number; positions?: number; exposure?: number }[]
  drawdown_curve: { date: string; value: number }[]
  benchmark_curve?: { date: string; value: number; close?: number; name?: string; symbol?: string }[]
  trades: StrategyBacktestTrade[]
  per_symbol_stats: {
    symbol: string
    n_trades: number
    total_return: number
    win_rate: number
    best: number
    worst: number
  }[]
  strategy_info: {
    id: string
    name: string
    description: string
    entry_signals: string[]
    exit_signals: string[]
    stop_loss: number | null
    take_profit: number | null
    trailing_stop: number | null
    trailing_take_profit_activate: number | null
    trailing_take_profit_drawdown: number | null
    score_min: number | null
    score_max: number | null
    max_hold_days: number | null
    source: string
  }
  elapsed_ms: number
  error: string | null
  research_execution_handle?: string | null
}

// ===== Settings =====

/** 端点发现清单 —— 对应 tickflow.org/endpoints.json */
export interface EndpointItem {
  id: string
  url: string
  label: string
  region?: string
  description?: string
  premium?: boolean
}

export interface EndpointManifest {
  version?: number
  description?: string
  healthPath?: string
  /** 每端点测试轮数,用于 /health 多轮探测取中位数 */
  testRounds?: number
  endpoints: EndpointItem[]
  /** 数据来源:remote=远程拉取 / fallback=内置回退列表 */
  source?: 'remote' | 'fallback'
}

export interface SettingsState {
  mode: 'none' | 'free' | 'api_key'
  tickflow_api_key_masked: string
  has_tickflow_key: boolean
  tier_label: string
  current_endpoint: string
  probe_log: string[]
  missing_caps: string[]
  extras_caps: string[]
  // 首次使用引导
  onboarding_completed: boolean
  // AI 配置
  ai_provider: string
  ai_base_url: string
  ai_api_key_masked: string
  has_ai_key: boolean
  ai_configured?: boolean
  ai_model: string
  ai_codex_command?: string
  ai_user_agent: string
}

/** 保存 TickFlow Key 的响应(先探后存) */
export interface SaveTickflowKeyResult {
  ok: boolean
  /** ok=false 且 key 无效时的原因标识,前端据此提示「Key 无效」 */
  reason?: 'invalid'
  error?: string
  mode?: 'none' | 'free' | 'api_key'
  tier_label?: string
  current_endpoint?: string
  tickflow_api_key_masked?: string
  capabilities_count?: number
}

export interface DataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  path?: string | null
}

/** 内置可选插件数据源 (plugins/ 目录, 需手动装依赖) */
export interface PluginDataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  runtime: string          // node | python | none
  available: boolean       // 依赖是否已安装
  status: string           // 可用性原因 (供 UI 显示)
  description: string
  install_hint: string     // 未装依赖时显示的安装命令
}

export interface DataSourceLoadError {
  name?: string
  path: string
  errors: string[]
}

export interface DataSourcesResponse {
  builtin: DataSourceItem[]
  plugins: PluginDataSourceItem[]
  custom: DataSourceItem[]
  errors: DataSourceLoadError[]
  config_dir: string
}

export interface DataSourceTestResult {
  provider: string
  dataset: string
  rows: number
  columns: string[]
  preview: Record<string, unknown>[]
}

export interface DatasetConfig {
  url: string
  method: string
  batch?: number | null
  rpm?: number | null
  response_path: string
  field_map: Record<string, string>
  transforms?: Record<string, string>
  symbols_param?: string
  start_param?: string
  end_param?: string
}

export interface AuthConfig {
  type: string
  token_env?: string | null
  header?: string
  param?: string
}

export interface CustomSourceConfig {
  name: string
  display_name: string
  auth: AuthConfig
  datasets: Record<string, DatasetConfig>
}

export interface WecomBotStatus {
  enabled: boolean
  running: boolean
  connected: boolean
  bot_id_configured: boolean
  secret_configured: boolean
  last_error: string
}

export interface Preferences {
  realtime_quotes_enabled: boolean
  indices_nav_pinned: boolean
  minute_sync_enabled: boolean
  minute_sync_days: number
  daily_data_provider?: string
  adj_factor_provider?: string
  minute_data_provider?: string
  realtime_data_provider?: string
  financial_data_provider?: string
  /** per-dataset 有序启用链 (首选在前) */
  provider_chains?: Partial<Record<'daily' | 'adj_factor' | 'minute' | 'realtime' | 'financial', string[]>>
  realtime_watchlist_symbols?: string[]
  realtime_pull_stock?: boolean
  realtime_pull_etf?: boolean
  realtime_pull_index?: boolean
  realtime_index_mode?: 'core' | 'all'
  realtime_index_symbols?: string[]
  pipeline_pull_a_share: boolean
  pipeline_pull_etf: boolean
  pipeline_pull_index: boolean
  pipeline_index_symbols: string
  pipeline_schedule: { hour: number; minute: number }
  instruments_schedule: { hour: number; minute: number }
  enriched_batch_size: number
  index_daily_batch_size: number
  limit_ladder_monitor_enabled: boolean
  depth_polling_interval: number
  depth_finalize_time: { hour: number; minute: number }
  review_schedule: { enabled: boolean; hour: number; minute: number }
  review_push_channels: string[]
  sse_refresh_pages: Record<string, boolean>
  strategy_monitor_enabled: boolean
  strategy_monitor_ids: string[]
  system_notify_enabled: boolean
  feishu_webhook_url?: string
  feishu_webhook_secret?: string
  wecom_webhook_url?: string
  telegram_bot_token?: string
  telegram_chat_id?: string
  wecom_bot_id?: string
  wecom_bot_secret?: string
  wecom_bot_enabled?: boolean
  webhook_enabled_default?: boolean
  webhook_default_channels?: string[]
  sidebar_index_symbols: string[]
  nav_order: string[]
  nav_hidden: string[]
  screener_auto_run: boolean
  minute_intraday_refresh: boolean
}
export interface StrategyAlertEvent {
  source: 'strategy' | 'depth'
  type: string
  strategy_id?: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
}

// ===== Phase 2 research =====
export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export interface ResearchDslOptions {
  dsl_version: string
  fields: string[]
  functions: Record<string, string[]>
  operators: string[]
}

export interface ResearchDslValidation {
  valid: true
  normalized_expression: string
  dsl_version: string
  fields: string[]
  operators: string[]
  functions: string[]
}

export interface FactorRevision {
  id: string
  factor_id: string
  revision_number: number
  name: string
  description: string
  hypothesis: string
  canonical_expression: string
  dsl_version: string
  ast_signature: string
  shape_signature: string
  fields: string[]
  operators: string[]
  functions: string[]
  provenance: Record<string, JsonValue>
  created_at: string
}

export interface SimilarityCandidate {
  revision: FactorRevision
  score: number
  components: {
    exact_structural_match: boolean
    shape_match: number
    field_overlap: number
    operator_function_overlap: number
  }
  reason: string
}

export interface ModelProvenance {
  provider: string
  model: string
  model_version: string | null
  provenance: Record<string, JsonValue>
}

export interface HypothesisDraft {
  draft_id: string
  hypothesis: string
  expression: string
  normalized_expression: string
  explanation: string
  assumptions: string[]
  provenance: Record<string, JsonValue>
}

export interface MetricSummary {
  mean: number | null
  std: number | null
  information_ratio: number | null
  positive_rate: number | null
  observations: number
}

export interface MetricPoint {
  date: string
  ic?: number | null
  rank_ic?: number | null
}

export interface GovernedInputManifest {
  [key: string]: JsonValue
}

export interface ResearchArtifact {
  evaluation_run_id: string
  relative_path: string
  content_type: string
  byte_size: number
  checksum_sha256: string
  created_at: string
}

export interface FactorEvaluation {
  evaluation_run_id: string | null
  status: 'completed' | 'failed' | 'invalid'
  factor_revision: FactorRevision | null
  resolved_config: Record<string, JsonValue> | null
  input_manifest: GovernedInputManifest | null
  ic_series: MetricPoint[]
  rank_ic_series: MetricPoint[]
  ic_summary: MetricSummary | null
  rank_ic_summary: MetricSummary | null
  group_stats: Record<string, JsonValue>[]
  group_nav: Record<string, JsonValue>[]
  long_short_stats: Record<string, JsonValue>
  long_short_nav: Record<string, JsonValue>[]
  artifacts: ResearchArtifact[]
  diagnostics: string[]
}

export type ExperimentStatus = 'draft' | 'running' | 'completed' | 'failed' | 'cancelled' | 'invalid'

export interface ResearchExperiment {
  id: string
  originating_run_id: string
  status: ExperimentStatus
  validated: boolean
  retained_at: string | null
  subject: { kind: 'factor'; revision_id: string } | { kind: 'strategy'; id: string; version: string }
  resolved_config: Record<string, JsonValue>
  input_manifest: GovernedInputManifest
  prediction_signals: Record<string, JsonValue>
  metrics: {
    ic_series?: MetricPoint[]
    rank_ic_series?: MetricPoint[]
    ic_summary?: MetricSummary
    rank_ic_summary?: MetricSummary
    [key: string]: JsonValue | MetricPoint[] | MetricSummary | undefined
  }
  artifacts: ResearchArtifact[]
  diagnostics: Record<string, JsonValue>
  model_provenance: ModelProvenance | null
  created_at: string
}

export interface ExperimentComparison {
  experiments: ResearchExperiment[]
  deltas: Record<string, Record<string, JsonValue>>
  warnings: string[]
}

export interface FactorEvaluationRequest {
  universe: string
  symbols: string[]
  asset_type: 'stock' | 'etf'
  start: string
  end: string
  forward_return_horizon: number
  rebalance: 'daily' | 'weekly' | 'monthly'
  missing_data_treatment: 'drop'
  warmup_treatment: 'exclude'
  warmup_days: number
  n_groups: number
  weight: 'equal' | 'factor_weight'
  fees_pct: number
  slippage_bps: number
}
// ===== API surface =====
export const api = {
  health: () => request<{ status: string; version: string; mode: string }>('/health'),

  // ===== Auth (访问认证) =====
  authStatus: () =>
    request<{ configured: boolean; authenticated: boolean }>('/api/auth/status'),
  authSetup: (password: string) =>
    request<{ ok: boolean }>('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  authLogin: (password: string) =>
    request<{ ok: boolean }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  authLogout: () =>
    request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  authChangePassword: (oldPassword: string, newPassword: string) =>
    request<{ ok: boolean }>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),

  settings: () => request<SettingsState>('/api/settings'),
  saveTickflowKey: (api_key: string) =>
    request<SaveTickflowKeyResult>('/api/settings/tickflow-key', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
    }),
  clearTickflowKey: () =>
    request<any>('/api/settings/tickflow-key', { method: 'DELETE' }),

  /** 标记首次使用向导完成（持久化到后端 preferences） */
  completeOnboarding: () =>
    request<{ ok: boolean; onboarding_completed: boolean }>(
      '/api/settings/onboarding/complete', { method: 'POST' },
    ),

  /** 保存 AI 配置 */
  saveAiSettings: (ai: { provider?: string; base_url?: string; api_key?: string; model?: string; codex_command?: string; user_agent?: string }) =>
    request<{ ok: boolean; ai_provider?: string; ai_model?: string; ai_codex_command?: string; ai_configured?: boolean }>('/api/settings/ai', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  /** 一键清空 AI 配置(保留自定义 UA) */
  clearAiSettings: () =>
    request<{ ok: boolean }>('/api/settings/ai', { method: 'DELETE' }),

  preferences: () => request<Preferences>('/api/settings/preferences'),
  dataSources: () => request<DataSourcesResponse>('/api/settings/data-sources'),
  dataSource: (name: string) => request<CustomSourceConfig>(`/api/settings/data-sources/${encodeURIComponent(name)}`),
  saveDataSource: (config: CustomSourceConfig) =>
    request<DataSourcesResponse>('/api/settings/data-sources', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  deleteDataSource: (name: string) =>
    request<DataSourcesResponse>(`/api/settings/data-sources/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  reloadDataSources: () => request<DataSourcesResponse>('/api/settings/data-sources/reload', { method: 'POST' }),
  installPlugin: (name: string) => {
    // npm install 可能耗时较长, 用 6 分钟超时
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 360_000)
    return request<DataSourcesResponse & { install_ok: boolean; install_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'POST', signal: controller.signal },
    ).finally(() => clearTimeout(timer))
  },
  uninstallPlugin: (name: string) =>
    request<DataSourcesResponse & { uninstall_ok: boolean; uninstall_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'DELETE' },
    ),
  testDataSource: (provider: string, dataset: string, symbols?: string[]) =>
    request<DataSourceTestResult>('/api/settings/data-sources/test', {
      method: 'POST',
      body: JSON.stringify({ provider, dataset, symbols }),
    }),
  updateDataProviders: (cfg: Partial<Pick<Preferences, 'daily_data_provider' | 'adj_factor_provider' | 'minute_data_provider' | 'realtime_data_provider' | 'financial_data_provider'>> & { provider_chains?: Preferences['provider_chains'] }) =>
    request<Preferences['provider_chains'] & Pick<Preferences, 'daily_data_provider' | 'adj_factor_provider' | 'minute_data_provider' | 'realtime_data_provider' | 'financial_data_provider'>>(
      '/api/settings/preferences/data-providers',
      { method: 'PUT', body: JSON.stringify(cfg) },
    ),
  updateMinuteSync: (enabled: boolean, days: number) =>
    request<Preferences>('/api/settings/preferences/minute-sync', {
      method: 'PUT',
      body: JSON.stringify({ minute_sync_enabled: enabled, minute_sync_days: days }),
    }),
  updatePipelinePullTypes: (cfg: Partial<Pick<Preferences, 'pipeline_pull_a_share' | 'pipeline_pull_etf' | 'pipeline_pull_index'>>) =>
    request<{
      pipeline_pull_a_share: boolean
      pipeline_pull_etf: boolean
      pipeline_pull_index: boolean
    }>('/api/settings/preferences/pipeline-pull-types', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updatePipelineIndexSymbols: (symbols: string) =>
    request<{ pipeline_index_symbols: string }>('/api/settings/preferences/pipeline-index-symbols', {
      method: 'PUT',
      body: JSON.stringify({ symbols }),
    }),
  updateRealtimeQuotes: (enabled: boolean) =>
    request<{ realtime_quotes_enabled: boolean; realtime_allowed?: boolean; mode?: string; error?: string }>('/api/settings/preferences/realtime-quotes', {
      method: 'PUT',
      body: JSON.stringify({ realtime_quotes_enabled: enabled }),
    }),
  updateRealtimeQuoteScope: (cfg: Partial<Pick<Preferences, 'realtime_pull_stock' | 'realtime_pull_etf' | 'realtime_pull_index' | 'realtime_index_mode' | 'realtime_index_symbols'>>) =>
    request<Partial<Preferences>>('/api/settings/preferences/realtime-quote-scope', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updateIndicesNavPinned: (pinned: boolean) =>
    request<{ indices_nav_pinned: boolean }>('/api/settings/preferences/indices-nav-pinned', {
      method: 'PUT',
      body: JSON.stringify({ indices_nav_pinned: pinned }),
    }),
  quoteStatus: () =>
    request<{
      enabled: boolean
      running: boolean
      paused?: boolean
      mode?: 'none' | 'watchlist' | 'full_market'
      realtime_allowed?: boolean
      interval_s: number
      symbol_count: number
      watchlist_symbol_count?: number
      index_symbol_count?: number
      etf_symbol_count?: number
      quote_age_ms: number | null
      is_trading_hours: boolean
      is_polling_window?: boolean
      market_phase?: string
      final_sync_done?: boolean
      final_sync_failed?: string | null
      last_fetch_ms: number | null
    }>('/api/intraday/status'),
  quoteInterval: () =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
    ),
  updateQuoteInterval: (interval: number) =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
      { method: 'PUT', body: JSON.stringify({ interval }) },
    ),
  intradayRefresh: () => request<{ status: string }>('/api/intraday/refresh', { method: 'POST' }),
  indexQuotes: (symbols?: string[]) =>
    request<{ rows: IndexQuote[]; count: number }>(
      `/api/intraday/indices${symbols?.length ? `?symbols=${encodeURIComponent(symbols.join(','))}` : ''}`,
    ),
  updateRealtimeMonitorConfig: (cfg: {
    sse_refresh_pages?: Record<string, boolean>
    strategy_monitor_enabled?: boolean
    strategy_monitor_ids?: string[]
    sidebar_index_symbols?: string[]
    screener_auto_run?: boolean
    minute_intraday_refresh?: boolean
  }) =>
    request<{
      sse_refresh_pages: Record<string, boolean>
      strategy_monitor_enabled: boolean
      strategy_monitor_ids: string[]
      sidebar_index_symbols: string[]
      screener_auto_run: boolean
      minute_intraday_refresh: boolean
    }>('/api/settings/preferences/realtime-monitor', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updateSystemNotify: (enabled: boolean) =>
    request<{ system_notify_enabled: boolean }>('/api/settings/preferences/system-notify', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateFeishuWebhook: (url: string, secret: string = '') =>
    request<{ feishu_webhook_url: string; feishu_webhook_secret: string }>('/api/settings/preferences/feishu-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url, secret }),
    }),
  updateWecomWebhook: (url: string) =>
    request<{ wecom_webhook_url: string }>('/api/settings/preferences/wecom-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url }),
    }),
  updateTelegramBot: (botToken: string, chatId: string) =>
    request<{ telegram_bot_token: string; telegram_chat_id: string }>('/api/settings/preferences/telegram-bot', {
      method: 'PUT',
      body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
    }),
  updateWecomBot: (botId: string, secret: string, enabled: boolean = true) =>
    request<{
      wecom_bot_id: string
      wecom_bot_secret: string
      wecom_bot_enabled: boolean
      wecom_bot_status: WecomBotStatus
    }>('/api/settings/preferences/wecom-bot', {
      method: 'PUT',
      body: JSON.stringify({ bot_id: botId, secret, enabled }),
    }),
  toggleWecomBot: (enabled: boolean) =>
    request<{ wecom_bot_enabled: boolean; wecom_bot_status: WecomBotStatus }>('/api/settings/preferences/wecom-bot-toggle', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateWebhookDefault: (enabled: boolean) =>
    request<{ webhook_enabled_default: boolean }>('/api/settings/preferences/webhook-enabled-default', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateWebhookDefaultChannels: (channels: string[]) =>
    request<{ webhook_default_channels: string[] }>('/api/settings/preferences/webhook-default-channels', {
      method: 'PUT',
      body: JSON.stringify({ channels }),
    }),
  updatePipelineSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/pipeline-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateReviewSchedule: (enabled: boolean, hour: number, minute: number) =>
    request<{ enabled: boolean; hour: number; minute: number }>('/api/settings/preferences/review-schedule', {
      method: 'PUT',
      body: JSON.stringify({ enabled, hour, minute }),
    }),
  updateReviewPush: (channels: string[]) =>
    request<{ review_push_channels: string[] }>('/api/settings/preferences/review-push', {
      method: 'PUT',
      body: JSON.stringify({ channels }),
    }),
  updateDepthPollingInterval: (interval: number) =>
    request<{ depth_polling_interval: number }>('/api/settings/preferences/depth-polling-interval', {
      method: 'PUT',
      body: JSON.stringify({ interval }),
    }),
  updateLimitLadderMonitor: (enabled: boolean) =>
    request<{ limit_ladder_monitor_enabled: boolean }>('/api/settings/preferences/limit-ladder-monitor', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  runLimitLadderFix: () =>
    request<{ ok: boolean; count: number; msg: string }>('/api/settings/preferences/limit-ladder-monitor/run', {
      method: 'POST',
    }),
  updateDepthFinalizeTime: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/depth-finalize-time', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  saveNavOrder: (nav_order: string[]) =>
    request<{ nav_order: string[] }>('/api/settings/preferences/nav-order', {
      method: 'PUT',
      body: JSON.stringify({ nav_order }),
    }),
  saveNavHidden: (nav_hidden: string[]) =>
    request<{ nav_hidden: string[] }>('/api/settings/preferences/nav-hidden', {
      method: 'PUT',
      body: JSON.stringify({ nav_hidden }),
    }),
  updateInstrumentsSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/instruments-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateEnrichedBatchSize: (size: number) =>
    request<{ enriched_batch_size: number }>('/api/settings/preferences/enriched-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),
  updateIndexDailyBatchSize: (size: number) =>
    request<{ index_daily_batch_size: number }>('/api/settings/preferences/index-daily-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),

  // 自选列表列配置
  watchlistColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/watchlist-columns'),
  updateWatchlistColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/watchlist-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  // 策略结果列表列配置
  screenerResultColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/screener-result-columns'),
  updateScreenerResultColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/screener-result-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  capabilities: () => request<CapabilitiesResponse>('/api/capabilities'),
  version: () => request<{ version: string }>('/api/data/version'),
  redetectCapabilities: () =>
    request<CapabilitiesResponse>('/api/capabilities/redetect', { method: 'POST' }),

  klineDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }, extColumns?: string) =>
    request<{
      symbol: string
      name?: string
      stock_info?: { name?: string; total_shares?: number; float_shares?: number; ext?: Record<string, unknown> }
      rows: KlineRow[]
      source?: string
    }>(
      (dateRange
        ? `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`)
      + (extColumns ? `&ext_columns=${encodeURIComponent(extColumns)}` : ''),
    ),
  /** 竞价历史聚合 (CHART-02): 多日竞价量/额趋势, 只读 GET。 */
  auctionHistory: (symbol: string, days = 30) =>
    request<AuctionHistoryResponse>('/api/kline/auction/history?symbol=' + encodeURIComponent(symbol) + '&days=' + days),
  klineDailyBatch: (symbols: string[], days = 12) =>
    request<{ data: Record<string, KlineRow[]> }>('/api/kline/daily-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, days }),
    }),
  klineMinuteBatch: (symbols: string[], date?: string) =>
    request<{ data: Record<string, MinuteKlineRow[]> }>('/api/kline/minute-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, date }),
    }),
  instrumentSearch: (q: string, limit = 20, assetTypes?: string) =>
    request<{ results: { symbol: string; name: string; code: string; asset_type?: string }[] }>(
      `/api/kline/instruments/search?q=${encodeURIComponent(q)}&limit=${limit}${assetTypes ? `&asset_types=${encodeURIComponent(assetTypes)}` : ''}`,
    ),

  /** 批量查股票名称 (传入 symbol 列表, 返回 {symbol: name}) */
  instrumentNames: (symbols: string[]) =>
    request<{ names: Record<string, string> }>('/api/kline/instruments/names', {
      method: 'POST',
      body: JSON.stringify(symbols),
    }),
  klineMinute: (symbol: string, date?: string) =>
    request<{
      symbol: string
      name?: string
      stock_info?: { name?: string; total_shares?: number; float_shares?: number }
      date: string | null
      rows: MinuteKlineRow[]
      source?: 'local' | 'live' | 'none'
    }>(
      `/api/kline/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}`,
    ),
  indexList: () => request<{ results: IndexInstrument[]; count: number }>('/api/index/list'),
  indexSearch: (q: string, limit = 20) =>
    request<{ results: IndexInstrument[] }>(
      `/api/index/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  indexDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }) =>
    request<{
      symbol: string
      name?: string
      index_info?: IndexInstrument
      rows: KlineRow[]
      source?: string
    }>(
      dateRange
        ? `/api/index/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/index/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    ),
  indexMinute: (symbol: string, date?: string) =>
    request<{
      symbol: string
      name?: string
      index_info?: IndexInstrument
      date: string | null
      rows: MinuteKlineRow[]
      source?: string
    }>(
      `/api/index/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}`,
    ),
  syncIndexInstruments: () =>
    request<{ status: string; count: number }>('/api/index/sync_instruments', { method: 'POST' }),
  syncIndexDaily: (days = 365) =>
    request<{ status: string; index_count: number; rows_written: number }>(
      `/api/index/sync_daily?days=${days}`,
      { method: 'POST' },
    ),
  syncSymbol: (symbol: string, days = 250) =>
    request<{ symbol: string; rows_written: number }>(
      `/api/kline/sync?symbol=${encodeURIComponent(symbol)}&days=${days}`,
      { method: 'POST' },
    ),
  syncMinute: () =>
    request<{ status: string; job_id: string }>('/api/kline/sync_minute', { method: 'POST' }),
  extendHistory: (value: number, unit: 'day' | 'month' | 'year') =>
    request<{ status: string; job_id: string }>('/api/kline/extend_history', {
      method: 'POST',
      body: JSON.stringify({ value, unit }),
    }),
  repairDaily: (startDate: string) =>
    request<{ status: string; job_id: string }>('/api/kline/repair_daily', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate }),
    }),
  extendMinuteHistory: (value: number, unit: 'day' | 'month') =>
    request<{ status: string; job_id: string }>('/api/kline/extend_minute_history', {
      method: 'POST',
      body: JSON.stringify({ value, unit }),
    }),
  rebuildEnriched: () =>
    request<{ status: string; job_id: string }>('/api/kline/rebuild_enriched', {
      method: 'POST',
    }),

  watchlistList: () => request<{ symbols: WatchlistEntry[] }>('/api/watchlist'),
  watchlistAdd: (symbol: string, note = '') =>
    request<{ symbols: WatchlistEntry[] }>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol, note }),
    }),
  watchlistBatchAdd: (symbols: string[], note = '') =>
    request<{ symbols: WatchlistEntry[]; added: number }>('/api/watchlist/batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, note }),
    }),
  watchlistRemove: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}`,
      { method: 'DELETE' },
    ),
  watchlistMoveToTop: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}/top`,
      { method: 'POST' },
    ),
  watchlistClear: () =>
    request<{ removed: number }>('/api/watchlist', { method: 'DELETE' }),
  watchlistQuotes: () => request<{ quotes: Quote[] }>('/api/watchlist/quotes'),
  watchlistEnriched: (extColumns?: string) =>
    request<{ rows: any[]; as_of: string | null; elapsed_ms: number }>(
      extColumns
        ? `/api/watchlist/enriched?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/watchlist/enriched',
    ),

  screenerStrategies: (assetType: 'stock' | 'etf' = 'stock') =>
    request<{ presets: ScreenerStrategy[]; load_errors?: StrategyLoadError[] }>(`/api/screener/strategies?asset_type=${assetType}`),
  screenerRunPreset: (strategy_id: string, pool?: string[], asOf?: string, extColumns?: string, assetType: 'stock' | 'etf' = 'stock') =>
    request<ScreenerResult>('/api/screener/run_preset', {
      method: 'POST',
      body: JSON.stringify({ strategy_id, pool, as_of: asOf ?? null, ext_columns: extColumns || null, asset_type: assetType }),
    }),
  screenerRunCustom: (conditions: string[], orderBy?: string, limit = 30, pool?: string[], extColumns?: string, assetType: 'stock' | 'etf' = 'stock') =>
    request<ScreenerResult>('/api/screener/run', {
      method: 'POST',
      body: JSON.stringify({ conditions, order_by: orderBy, limit, pool, ext_columns: extColumns || null, asset_type: assetType }),
    }),
  screenerRunAll: (asOf?: string, strategyIds?: string[], extColumns?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string; rows: any[] }> }>(
      '/api/screener/run_all', { method: 'POST', body: JSON.stringify({ as_of: asOf ?? null, strategy_ids: strategyIds ?? null, ext_columns: extColumns || null }) },
    ),

  screenerCached: (extColumns?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string; rows: any[] }>; today_ever_matched: Record<string, string[]> | null; today_ever_rows: Record<string, Record<string, any>> | null; updated_at: number | null }>(
      extColumns
        ? `/api/screener/cached?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/screener/cached',
    ),
  marketSnapshot: () =>
    request<{ as_of: string | null; rows: MarketSnapshotRow[] }>('/api/screener/market-snapshot'),
  overviewMarket: (asOf?: string) => request<OverviewMarket>(`/api/overview/market${asOf ? `?as_of=${asOf}` : ''}`),

  // 概念涨幅轮动矩阵: 每列(日期)各自把所有概念按当天涨幅从高到低排序
  rpsRotation: (days: number) =>
    request<RpsRotationData>(`/api/rps/rotation?days=${days}`),

  limitLadder: (asOf?: string, extColumns?: string, direction?: 'up' | 'down') => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    if (extColumns) params.set('ext_columns', extColumns)
    if (direction === 'down') params.set('direction', 'down')
    const qs = params.toString()
    return request<LimitLadderResult>(
      `/api/screener/limit-ladder${qs ? `?${qs}` : ''}`,
    )
  },

  // 股池 Hub: 单 as_of 只读投影 (POOL-01/02; concept 为可选, 前端默认客户端投影不传)
  poolHub: (asOf?: string, concept?: string) => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    if (concept) params.set('concept', concept)
    const qs = params.toString()
    return request<PoolHubResponse>(
      `/api/pool/hub${qs ? `?${qs}` : ''}`,
    )
  },

  // Phase 23 (FRONT-01): 股池可用交易日列表 (POOL-05) — source of truth = screener_results/date=* 分区
  poolDates: () => request<PoolDatesResponse>('/api/pool/dates'),

  // Phase 23 (FRONT-01/02, PIT-1 最高危防线): 历史 as_of 独立只读取池 —
  // 历史必走 /api/pool/history, 绝不用 /hub?as_of= (反漂移会静默返回最新日)
  poolHistory: (asOf: string) =>
    request<PoolHubResponse>(`/api/pool/history?as_of=${encodeURIComponent(asOf)}`),

  // Phase 27 (PM-04): 盘前预览只读端点 — 固定今日, 无参数; 缺失 → 200 available:false 诚实空态 (非 404)
  poolPremarket: () => request<PremarketPoolResponse>('/api/pool/premarket'),

  backtestStatus: () => request<{ available: boolean }>('/api/backtest/status'),

  backtestRun: (payload: {
    symbols: string[]
    entries: string[]
    exits: string[]
    start?: string
    end?: string
    stop_loss_pct?: number
    max_hold_days?: number
    matching?: 'close_t' | 'open_t+1'
    asset_type?: 'stock' | 'etf'
  }) =>
    request<BacktestResult>('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  factorColumns: () =>
    request<{ columns: FactorColumn[] }>('/api/backtest/factor/columns'),

  factorRun: (payload: {
    factor_name: string
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    n_groups?: number
    rebalance?: 'daily' | 'weekly' | 'monthly'
    weight?: 'equal' | 'factor_weight'
    fees_pct?: number
    slippage_bps?: number
    asset_type?: 'stock' | 'etf'
  }) =>
    request<FactorBacktestResult>('/api/backtest/factor/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  researchDslOptions: () => request<ResearchDslOptions>('/api/research/dsl/options'),
  validateResearchDsl: (expression: string) => request<ResearchDslValidation>('/api/research/dsl/validate', {
    method: 'POST', body: JSON.stringify({ expression }),
  }),
  researchFactors: () => request<{ factors: FactorRevision[] }>('/api/research/factors'),
  researchFactorRevisions: (factorId: string) => request<{ revisions: FactorRevision[] }>(`/api/research/factors/${factorId}/revisions`),
  saveResearchFactor: (payload: Pick<FactorRevision, 'name'> & { expression: string; description?: string; hypothesis?: string }) =>
    request<FactorRevision>('/api/research/factors', { method: 'POST', body: JSON.stringify(payload) }),
  reviseResearchFactor: (factorId: string, payload: Pick<FactorRevision, 'name'> & { expression: string; description?: string; hypothesis?: string }) =>
    request<FactorRevision>(`/api/research/factors/${factorId}/revisions`, { method: 'POST', body: JSON.stringify(payload) }),
  researchSimilarity: (payload: { expression: string; limit?: number; exclude_revision_id?: string }) =>
    request<{ candidates: SimilarityCandidate[] }>('/api/research/factors/similarity', { method: 'POST', body: JSON.stringify(payload) }),
  draftResearchHypothesis: (hypothesis: string, options?: Record<string, string>) =>
    request<HypothesisDraft>('/api/research/hypotheses/drafts', { method: 'POST', body: JSON.stringify({ hypothesis, options }) }),
  saveReviewedHypothesis: (payload: { draft_id: string; name: string; expression: string; explanation: string; provenance: Record<string, JsonValue>; reviewed: true; factor_id?: string; description?: string }) =>
    request<FactorRevision>('/api/research/hypotheses/reviewed-factor', { method: 'POST', body: JSON.stringify(payload) }),
  evaluateResearchFactor: (revisionId: string, payload: FactorEvaluationRequest) =>
    request<{ evaluation: FactorEvaluation; experiment: ResearchExperiment }>(`/api/research/factor-revisions/${revisionId}/evaluate`, { method: 'POST', body: JSON.stringify(payload) }),
  researchExperiments: () => request<{ experiments: ResearchExperiment[] }>('/api/research/experiments'),
  researchExperiment: (experimentId: string) => request<ResearchExperiment>(`/api/research/experiments/${experimentId}`),
  retainResearchExperiment: (experimentId: string) => request<ResearchExperiment>(`/api/research/experiments/${experimentId}/retain`, { method: 'POST' }),
  researchComparisonCandidates: () => request<{ experiments: ResearchExperiment[] }>('/api/research/comparison/candidates'),
  compareResearchExperiments: (experimentIds: string[]) => request<ExperimentComparison>('/api/research/comparison', {
    method: 'POST', body: JSON.stringify({ experiment_ids: experimentIds }),
  }),
  retainStrategyResearchExecution: (handle: string) => request<ResearchExperiment>(`/api/research/strategy-executions/${handle}/retain`, { method: 'POST' }),

  strategyBacktestRun: (payload: {
    strategy_id: string
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    params?: Record<string, any> | null
    overrides?: Record<string, any> | null
    matching?: 'close_t' | 'open_t+1'
    entry_fill?: 'close_t' | 'open_t+1' | null
    exit_fill?: 'close_t' | 'open_t+1' | null
    fees_pct?: number
    commission_pct?: number
    stamp_tax_pct?: number
    slippage_bps?: number
    max_positions?: number
    initial_capital?: number
    position_sizing?: 'equal' | 'score_weight'
    asset_type?: 'stock' | 'etf'
  }) =>
    request<StrategyBacktestResult>('/api/backtest/strategy/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  pipelineRun: () => request<{ job_id: string; reused: boolean }>(
    '/api/pipeline/run', { method: 'POST' },
  ),
  pipelineJob: (id: string) => request<PipelineJob>(`/api/pipeline/jobs/${id}`),
  pipelineJobs: (limit = 20) =>
    request<{ active_id: string | null; jobs: PipelineJobSummary[] }>(
      `/api/pipeline/jobs?limit=${limit}`,
    ),

  dataStatus: () => request<DataStatus>('/api/data/status'),

  auctionProbe: () => request<AuctionProbeVerdict>('/api/data/auction-probe'),
  redetectAuctionProbe: () =>
    request<AuctionProbeVerdict>('/api/data/auction-probe/redetect', { method: 'POST' }),
  dataClear: () => request<{ deleted_files: number }>('/api/data/clear', { method: 'POST' }),
  refreshCache: () => request<{ ok: boolean }>('/api/data/refresh-cache', { method: 'POST' }),
  enrichedSchema: (table: string) => request<EnrichedField[]>(`/api/data/schema/${table}`),

  testEndpoint: (url: string, rounds?: number) =>
    request<{
      ok: boolean
      url: string
      rounds: number
      success: number
      median_ms: number | null
      min_ms?: number | null
      max_ms?: number | null
      /** 兼容旧字段,等于 median_ms */
      latency_ms?: number | null
      error?: string
    }>(
      '/api/settings/test_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url, rounds }),
      },
    ),

  // 端点发现 —— 后端代理拉取 tickflow.org/endpoints.json(前端无法跨域直连)
  listEndpoints: () =>
    request<EndpointManifest>('/api/settings/endpoints'),

  switchEndpoint: (url: string) =>
    request<{ ok: boolean; current_endpoint: string; error?: string }>(
      '/api/settings/switch_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url }),
      },
    ),

  // ===== 扩展数据 =====
  extDataList: () =>
    request<{ items: ExtDataConfig[] }>('/api/ext-data'),

  extDataRows: (id: string, opts?: { date?: string; limit?: number; columns?: string[] }) => {
    const qs = new URLSearchParams()
    if (opts?.date) qs.set('date', opts.date)
    if (opts?.limit) qs.set('limit', String(opts.limit))
    if (opts?.columns?.length) qs.set('columns', opts.columns.join(','))
    const suffix = qs.toString()
    return request<ExtDataRowsResult>(`/api/ext-data/${encodeURIComponent(id)}/rows${suffix ? `?${suffix}` : ''}`)
  },

  analysisMenus: () =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus'),

  analysisMenu: (id: string) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`),

  analysisMenuSave: (id: string, body: Omit<AnalysisMenu, 'id' | 'created_at' | 'updated_at' | 'builtin'>) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  analysisMenuReorder: (ids: string[]) =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus/reorder', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  analysisMenuDelete: (id: string) =>
    request<{ status: string }>(`/api/analysis-menus/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  extDataCreate: (body: { id: string; label: string; mode: 'snapshot' | 'timeseries'; fields: { name: string; dtype: string; label: string }[]; description?: string; symbol_map?: Record<string, string>; code_map?: Record<string, string> }) =>
    request<ExtDataConfig>('/api/ext-data', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  extDataUpdate: (id: string, body: { label?: string; fields?: { name: string; dtype: string; label: string }[]; description?: string }) =>
    request<ExtDataConfig>(`/api/ext-data/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  extDataDelete: (id: string) =>
    request<{ status: string }>(`/api/ext-data/${id}`, { method: 'DELETE' }),

  extDataUpload: (id: string, file: File, snapshotDate?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/upload${snapshotDate ? `?snapshot_date=${snapshotDate}` : ''}`,
      { method: 'POST', body: fd },
    )
  },

  extDataIngest: (id: string, body: { date?: string; rows: Record<string, unknown>[] }) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/ingest`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  extDataSchemaAll: () =>
    request<{ items: { id: string; label: string; mode: string; columns: { name: string; type: string; label: string }[] }[] }>('/api/ext-data/schema-all'),

  extDataPullConfig: (id: string, body: {
    url: string; method?: string; headers?: Record<string, string>; body?: string;
    response_path?: string; field_map?: Record<string, string>;
    schedule_minutes?: number; enabled?: boolean;
  }) =>
    request<{ status: string; pull: PullConfig }>(
      `/api/ext-data/${id}/pull`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  extDataPullTest: (id: string) =>
    request<{ status: string; total_rows: number; preview: Record<string, unknown>[]; has_symbol: boolean }>(
      `/api/ext-data/${id}/pull/test`,
      { method: 'POST' },
    ),

  extDataPullRun: (id: string) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/pull/run`,
      { method: 'POST' },
    ),

  // 内置预设 (概念/行业) 手动获取数据: 走结构转换, 保证 schema 一致
  extDataPresetFetch: (id: string) =>
    request<{ status: string; rows: number }>(
      `/api/ext-data/presets/${id}/fetch`,
      { method: 'POST' },
    ),

  extDataDetectFields: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ fields: { name: string; dtype: string; label: string }[]; rows: number; symbol_candidates: string[]; code_candidates: string[] }>(
      '/api/ext-data/detect-fields',
      { method: 'POST', body: fd },
    )
  },

  extDataDetectUrl: (body: ExtDataDetectUrlRequest) =>
    request<ExtDataDetectUrlResult>('/api/ext-data/detect-url', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  extDataFixSymbol: (id: string) =>
    request<{ status: string; fixed_files: number }>(
      `/api/ext-data/${id}/fix-symbol`,
      { method: 'POST' },
    ),

  // ===== Financials =====
  financialStatus: () =>
    request<FinancialStatus>('/api/financials/status'),

  financialMetrics: (symbol?: string) =>
    request<{ data: FinancialMetricRecord[] }>(
      `/api/financials/metrics${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialIncome: (symbol?: string) =>
    request<{ data: FinancialIncomeRecord[] }>(
      `/api/financials/income${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialBalanceSheet: (symbol?: string) =>
    request<{ data: FinancialBalanceSheetRecord[] }>(
      `/api/financials/balance-sheet${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialCashFlow: (symbol?: string) =>
    request<{ data: FinancialCashFlowRecord[] }>(
      `/api/financials/cash-flow${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  /** 触发财务数据同步(后台异步执行,接口立即返回 started 状态) */
  financialSync: (table: string) =>
    request<{ status: string; synced: { started: boolean; reason?: string } }>(
      `/api/financials/sync/${table}`, { method: 'POST' },
    ),

  /** AI 分析报告 CRUD */
  financialReportsList: () =>
    request<{ reports: AiFinancialReport[] }>('/api/financials/reports'),

  financialReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    periods?: number; summary?: string
  }) =>
    request<{ ok: boolean; report: AiFinancialReport }>('/api/financials/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  financialReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/financials/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 财务分析 — 流式调用。
   *
   * 返回一个可逐行读取的 async generator,每行是 JSON:
   *   {type:"meta",symbol,summary,periods}
   *   {type:"delta",content:"..."}    ← 文本片段,逐个累加
   *   {type:"error",message:"..."}
   *   {type:"done"}
   *
   * 用 ReadableStream 解析(而非 SSE EventSource),支持 POST body 且更简单。
   */
  async *financialAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    periods?: number
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/financials/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 按行分割(保留最后不完整的行在 buf)
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try {
          yield JSON.parse(s)
        } catch {
          // 忽略无法解析的行
        }
      }
    }
    // 处理残余
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 个股分析 =====
  stockAnalysisLevels: (symbol: string, days = 120) =>
    request<StockLevels>(`/api/stock-analysis/levels?symbol=${encodeURIComponent(symbol)}&days=${days}`),

  stockAnalysisReportsList: () =>
    request<{ reports: AiStockReport[] }>('/api/stock-analysis/reports'),

  stockAnalysisReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    summary?: string; close?: number | null
    levels?: Record<LevelType, PriceLevel[]>
  }) =>
    request<{ ok: boolean; report: AiStockReport }>('/api/stock-analysis/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  stockAnalysisReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/stock-analysis/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 个股四维分析 — 流式调用(NDJSON,与财务分析同协议)。
   * meta 里额外带 levels(关键价位)供图表回放。
   */
  async *stockAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    levels?: Record<LevelType, PriceLevel[]>
    close?: number | null
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/stock-analysis/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 大盘复盘 =====
  reviewReportsList: () =>
    request<{ reports: AiReviewReport[] }>('/api/market-recap/reports'),

  reviewReportSave: (r: {
    as_of: string; focus?: string; content: string
    summary?: string; emotion_score?: number | null; emotion_label?: string
  }) =>
    request<{ ok: boolean; report: AiReviewReport }>('/api/market-recap/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  reviewReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/market-recap/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 大盘复盘 — 流式调用(NDJSON,与个股/财务分析同协议)。
   * meta 里带 as_of / emotion_score / emotion_label / summary,供前端先渲染信号灯。
   */
  async *reviewStream(asOf?: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    as_of?: string
    emotion_score?: number
    emotion_label?: string
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/market-recap/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ as_of: asOf ?? null, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  /** AI 概念轮动分析 — 流式 NDJSON。 */
  async *rotationAnalyzeStream(days: number, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    days?: number
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/rps/rotation-analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== Strategy Engine =====
  strategyList: () =>
    request<{ strategies: StrategyDetail[] }>('/api/strategies'),

  strategyGet: (id: string) =>
    request<StrategyDetail>(`/api/strategies/${id}`),

  strategyRun: (strategyId: string, params?: Record<string, any>, asOf?: string, pool?: string[]) =>
    request<ScreenerResult>('/api/strategies/run', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, params, as_of: asOf ?? null, pool }),
    }),

  strategyRunAll: (asOf?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string }> }>(
      '/api/strategies/run-all',
      { method: 'POST', body: JSON.stringify({ as_of: asOf ?? null }) },
    ),

  strategySaveConfig: (strategyId: string, overrides: Record<string, any>) =>
    request<{ ok: boolean }>('/api/strategies/config', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, overrides }),
    }),

  strategyResetConfig: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/config/${strategyId}`, { method: 'DELETE' }),

  /** 删除自定义策略（内置策略不可删除） */
  strategyDelete: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/${strategyId}`, { method: 'DELETE' }),

  strategyReload: () =>
    request<{ ok: boolean; count: number }>('/api/strategies/reload', { method: 'POST' }),

  // ===== Custom Signals (自定义信号) =====
  customSignalsList: () =>
    request<{ signals: CustomSignal[] }>('/api/custom-signals'),

  customSignalsOptions: () =>
    request<CustomSignalOptions>('/api/custom-signals/options'),

  customSignalSave: (signal: CustomSignal) =>
    request<{ ok: boolean; signal: CustomSignal }>('/api/custom-signals', {
      method: 'POST',
      body: JSON.stringify(signal),
    }),

  customSignalDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/custom-signals/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // ===== Portfolio =====
  portfolioAccounts: (includeArchived = false) =>
    request<{ accounts: PortfolioAccount[] }>(
      `/api/portfolio/accounts?include_archived=${includeArchived}`,
    ),
  portfolioCreateAccount: (account: Pick<PortfolioAccountInput, 'name' | 'available_funds' | 'notes'>) =>
    request<{ account: PortfolioAccount }>('/api/portfolio/accounts', {
      method: 'POST',
      body: JSON.stringify(account),
    }),
  portfolioUpdateAccount: (accountId: number, account: PortfolioAccountInput) =>
    request<{ account: PortfolioAccount }>(`/api/portfolio/accounts/${encodeURIComponent(String(accountId))}`, {
      method: 'PUT',
      body: JSON.stringify(account),
    }),
  portfolioArchiveAccount: (accountId: number) =>
    request<{ account: PortfolioAccount }>(`/api/portfolio/accounts/${encodeURIComponent(String(accountId))}/archive`, {
      method: 'POST',
    }),
  portfolioDeleteAccount: (accountId: number) =>
    request<{ ok: boolean }>(`/api/portfolio/accounts/${encodeURIComponent(String(accountId))}`, {
      method: 'DELETE',
    }),
  portfolioHoldings: (accountId?: number, includeArchived = false) => {
    const params = new URLSearchParams({ include_archived: String(includeArchived) })
    if (accountId != null) params.set('account_id', String(accountId))
    return request<{ positions: PortfolioPosition[] }>(`/api/portfolio/positions?${params}`)
  },
  portfolioCreateHolding: (position: PortfolioPositionInput) =>
    request<{ position: PortfolioPosition }>('/api/portfolio/positions', {
      method: 'POST',
      body: JSON.stringify(position),
    }),
  portfolioUpdateHolding: (positionId: number, position: Partial<Omit<PortfolioPositionInput, 'account_id'>>) =>
    request<{ position: PortfolioPosition }>(`/api/portfolio/positions/${encodeURIComponent(String(positionId))}`, {
      method: 'PUT',
      body: JSON.stringify(position),
    }),
  portfolioArchiveHolding: (positionId: number) =>
    request<{ position: PortfolioPosition }>(`/api/portfolio/positions/${encodeURIComponent(String(positionId))}/archive`, {
      method: 'POST',
    }),
  portfolioDeleteHolding: (positionId: number) =>
    request<{ ok: boolean }>(`/api/portfolio/positions/${encodeURIComponent(String(positionId))}`, {
      method: 'DELETE',
    }),
  portfolioSummary: (accountId?: number, includeArchived = false) => {
    const params = new URLSearchParams({ include_archived: String(includeArchived) })
    if (accountId != null) params.set('account_id', String(accountId))
    return request<PortfolioSummary>(`/api/portfolio/summary?${params}`)
  },

  // ===== Evidence-backed analysis =====
  analysisStartRun: (subject: AnalysisRequestSubject, focus?: string) =>
    request<{ run: AnalysisRun }>('/api/analysis/runs', {
      method: 'POST',
      body: JSON.stringify({ subject_kind: subject.kind, subject_key: subject.key, focus }),
    }),
  analysisReports: (subject: AnalysisRequestSubject) =>
    request<{ reports: AnalysisReportSummary[] }>(
      `/api/analysis/subjects/${encodeURIComponent(subject.kind)}/${encodeURIComponent(subject.key)}/reports`,
    ),
  analysisReport: (reportId: string) =>
    request<{ report: AnalysisReport }>(`/api/analysis/reports/${encodeURIComponent(reportId)}`),
  analysisEvidence: (reportId: string) =>
    request<AnalysisEvidence>(`/api/analysis/reports/${encodeURIComponent(reportId)}/evidence`),
  analysisSignalHistory: (signalId: string) =>
    request<AnalysisSignalHistory>(`/api/analysis/signals/${encodeURIComponent(signalId)}/history`),
  analysisConfirmReview: (reviewId: string, windowDays: 20 | 60 | 120) =>
    request<{ review: { id: string; status: 'confirmed' } }>(`/api/analysis/reviews/${encodeURIComponent(reviewId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ window_days: windowDays }),
    }),
  analysisRejectReview: (reviewId: string) =>
    request<{ review: { id: string; status: 'rejected' } }>(`/api/analysis/reviews/${encodeURIComponent(reviewId)}/reject`, {
      method: 'POST',
    }),
  analysisRecordOutcome: (planId: string, payload: AnalysisObservationOutcomeInput) =>
    request<{ outcome: AnalysisObservationOutcome }>(`/api/analysis/plans/${encodeURIComponent(planId)}/outcomes`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ===== Controlled advanced research =====
  advancedViewpoints: (subject: AnalysisRequestSubject) =>
    request<{ viewpoints: AdvancedViewpoint[] }>(`/api/advanced/viewpoints?instrument=${encodeURIComponent(subject.key)}`),
  advancedViewpointVersions: (viewpointId: string) =>
    request<{ versions: AdvancedViewpoint[] }>(`/api/advanced/viewpoints/${encodeURIComponent(viewpointId)}/versions`),
  advancedReviseViewpoint: (viewpointId: string, payload: AdvancedViewpointRevisionInput) =>
    request<{ viewpoint: AdvancedViewpoint }>(`/api/advanced/viewpoints/${encodeURIComponent(viewpointId)}/revisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  advancedCorrectViewpoint: (viewpointId: string, payload: AdvancedViewpointCorrectionInput) =>
    request<{ viewpoint: AdvancedViewpoint }>(`/api/advanced/viewpoints/${encodeURIComponent(viewpointId)}/corrections`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  advancedEvaluateViewpoint: (viewpointVersionId: string) =>
    request<{ viewpoint: AdvancedViewpoint }>(`/api/advanced/viewpoints/versions/${encodeURIComponent(viewpointVersionId)}/evaluate`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  advancedCalibration: (sourceProfile: string) =>
    request<{ calibration: AdvancedCalibration }>(`/api/advanced/viewpoints/calibration/${encodeURIComponent(sourceProfile)}`),
  advancedStartJob: (subject: AnalysisRequestSubject, taskType: AdvancedTaskType) =>
    request<{ job: AdvancedJob }>(`/api/advanced/subjects/${encodeURIComponent(subject.key)}/jobs`, {
      method: 'POST',
      body: JSON.stringify({ task_type: taskType }),
    }),
  advancedJob: (jobId: string) =>
    request<{ job: AdvancedJob }>(`/api/advanced/jobs/${encodeURIComponent(jobId)}`),
  advancedAudit: (auditReference: string) =>
    request<{ audit: AdvancedAudit }>(`/api/advanced/audits/${encodeURIComponent(auditReference)}`),
  advancedResearchAssetBinding: async (strategyId: string) => {
    // 内置/未绑定研究资产的策略返回 404 属正常, 不应弹全局错误 toast。
    // silent=true: request() 不再为 404 弹 toast, 由这里静默降级。
    try {
      return await request<{ binding: AdvancedResearchAssetBinding }>(`/api/advanced/research-assets/strategies/${encodeURIComponent(strategyId)}`, { silent: true })
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) return { binding: null }
      throw err
    }
  },
  advancedExperiments: () =>
    request<{ specifications: AdvancedExperimentSpecification[]; runs: AdvancedExperimentRun[]; feedback: AdvancedExperimentFeedback[] }>('/api/advanced/experiments'),
  advancedCreateExperiment: (payload: AdvancedExperimentInput) =>
    request<{ specification: AdvancedExperimentSpecification }>('/api/advanced/experiments/specifications', { method: 'POST', body: JSON.stringify(payload) }),
  advancedRunExperiment: (specificationId: string) =>
    request<{ run: AdvancedExperimentRun }>(`/api/advanced/experiments/specifications/${encodeURIComponent(specificationId)}/runs`, { method: 'POST' }),
  advancedRetryExperiment: (runId: string) =>
    request<{ run: AdvancedExperimentRun }>(`/api/advanced/experiments/runs/${encodeURIComponent(runId)}/retry`, { method: 'POST' }),
  advancedRecordFeedback: (runId: string, conclusion: AdvancedExperimentFeedback['conclusion'], notes: string) =>
    request<{ feedback: AdvancedExperimentFeedback }>(`/api/advanced/experiments/runs/${encodeURIComponent(runId)}/feedback`, { method: 'POST', body: JSON.stringify({ conclusion, notes }) }),
  advancedCandidates: () => request<{ candidates: AdvancedCandidate[] }>('/api/advanced/evolution/candidates'),
  advancedCreateCandidate: (payload: { completed_run_id: string; mutation_operation: 'adjust_signal_threshold' | 'parameter_adjustment' | 'feature_subset' | 'signal_threshold' | 'portfolio_constraint'; seed: number; resolved_configuration: Record<string, string | number | boolean | null> }) =>
    request<{ candidate: AdvancedCandidate }>('/api/advanced/evolution/candidates', { method: 'POST', body: JSON.stringify(payload) }),
  advancedEvaluateCandidateGate: (candidateId: string, gate: 'contract_sandbox_safety' | 'provenance' | 'in_sample_out_of_sample_evidence' | 'robustness' | 'cost_feasibility') =>
    request<{ gate: AdvancedPromotionGate }>(`/api/advanced/evolution/candidates/${encodeURIComponent(candidateId)}/gates/${encodeURIComponent(gate)}`, { method: 'POST', body: JSON.stringify({}) }),
  advancedPromoteCandidate: (candidateId: string, rationale: string) =>
    request<{ approval: { created_at: string }; registered_strategy: { id: string; status: 'registered_research_only' } }>(`/api/advanced/evolution/candidates/${encodeURIComponent(candidateId)}/promote`, { method: 'POST', body: JSON.stringify({ rationale }) }),
  advancedSubmitSandbox: (payload: { contract: { contract_version: 'advanced-strategy-v1'; parent_asset_id: string; declared_inputs: ['governed_panel']; declared_imports: string[]; timeout_seconds: number; memory_limit_mb: number; source_sha256: string }; source: string }) =>
    request<AdvancedSandboxSubmissionResult>('/api/advanced/sandbox/submissions', { method: 'POST', body: JSON.stringify(payload) }),
  advancedSandboxValidations: () => request<{ validations: AdvancedSandboxValidation[] }>('/api/advanced/sandbox/validations'),
  advancedSandboxRuns: () => request<{ runs: AdvancedSandboxRun[] }>('/api/advanced/sandbox/runs'),
  advancedSandboxRun: (runId: string) => request<{ run: AdvancedSandboxRun }>(`/api/advanced/sandbox/runs/${encodeURIComponent(runId)}`),

  // ===== Decision playbook =====
  decisionGenerate: (payload: DecisionRunInput) =>
    request<DecisionRun>('/api/decision/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  decisionRun: (runId: string) =>
    request<DecisionRun>(`/api/decision/runs/${encodeURIComponent(runId)}`),
  decisionReview: (runId: string) =>
    request<DecisionReviewResult>(`/api/decision/runs/${encodeURIComponent(runId)}/review`, {
      method: 'POST',
    }),
  decisionAdjustments: (runId: string, proposal: Record<string, { value: string; rationale: string }>) =>
    request<DecisionRun>(`/api/decision/runs/${encodeURIComponent(runId)}/adjustments`, {
      method: 'POST',
      body: JSON.stringify({ proposal }),
    }),
  decisionReplay: (runIds: string[], asOf: string) =>
    request<HistoricalReplay>('/api/decision/replay', {
      method: 'POST',
      body: JSON.stringify({ run_ids: runIds, as_of: asOf }),
    }),

  // ===== Monitor Rules (监控规则) =====
  monitorRulesList: () =>
    request<{ rules: MonitorRule[] }>('/api/monitor-rules'),

  monitorRuleOptions: () =>
    request<MonitorRuleOptions>('/api/monitor-rules/options'),

  monitorRuleSave: (rule: MonitorRule) =>
    request<{ ok: boolean; rule: MonitorRule }>('/api/monitor-rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),

  monitorRuleDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/monitor-rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** 模拟触发 ladder 封单监控 (Dev 调试, 不落盘不推送) */
  monitorRuleTestLadder: () =>
    request<{
      ok: boolean
      as_of: string
      sealed_count: number
      triggered: Array<{
        rule_id: string; rule_name: string; symbol: string; name?: string
        type: string; message: string; severity: string
        sealed_value: number; sealed_metric: string
        current_sealed_vol?: number; current_sealed_amount?: number
      }>
      not_triggered: Array<{
        rule_id: string; rule_name: string; symbol: string
        metric: string; threshold: number; current_value: number | null
        current_sealed_vol?: number; current_sealed_amount?: number | null
        reason: string
      }>
    }>('/api/monitor-rules/test-ladder', { method: 'POST' }),

  /** 真实触发 ladder 预警 (落盘+飞书+SSE), Dev 调试用 */
  monitorRuleTriggerLadder: () =>
    request<{
      ok: boolean
      triggered: number
      events: Array<{ symbol: string; name: string; message: string }>
    }>('/api/monitor-rules/trigger-ladder', { method: 'POST' }),

  /** 生成演示监控规则 (Dev 页用) */
  monitorRuleSeed: () =>
    request<{ ok: boolean; generated: number }>('/api/monitor-rules/seed', { method: 'POST' }),

  // ===== Alerts (触发记录) =====
  alertsList: (params?: AlertHistoryFilters) => {
    const qs = new URLSearchParams()
    if (params?.days) qs.set('days', String(params.days))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.source) qs.set('source', params.source)
    if (params?.type) qs.set('type', params.type)
    if (params?.severity) qs.set('severity', params.severity)
    if (params?.delivery_status) qs.set('delivery_status', params.delivery_status)
    const s = qs.toString()
    return request<{ alerts: AlertEvent[]; total: number }>(`/api/alerts${s ? `?${s}` : ''}`)
  },
  alertDeliveryDetails: (eventId: string) =>
    request<{ deliveries: DeliveryOutcome[] }>(`/api/alerts/${encodeURIComponent(eventId)}/deliveries`),

  alertsClear: () =>
    request<{ ok: boolean; cleared: number }>('/api/alerts', { method: 'DELETE' }),

  alertDelete: (ts: number) =>
    request<{ ok: boolean }>(`/api/alerts/${ts}`, { method: 'DELETE' }),

  /** 生成演示触发记录 (Dev 页用) */
  alertSeed: (count = 12, recent = true) =>
    request<{ ok: boolean; generated: number }>(`/api/alerts/seed?count=${count}&recent=${recent}`, { method: 'POST' }),

  /** 检查 AI 配置状态 */
  strategyAiStatus: () =>
    request<{ configured: boolean; has_key: boolean; has_model: boolean; provider?: string }>('/api/strategies/ai/status'),

  /** 测试 AI 连通性 */
  strategyAiTest: () =>
    request<{ ok: boolean; error?: string; model?: string; response?: string; usage?: { prompt: number; completion: number } }>(
      '/api/strategies/ai/test',
      { method: 'POST' },
    ),

  /** 获取策略源文件内容 */
  strategyGetSource: (id: string) =>
    request<{ code: string; source: string }>(`/api/strategies/${id}/source`),
  strategyBuild: (step: number, payload: Record<string, any>) =>
    request<StrategyBuildResult>(
      '/api/strategies/build',
      { method: 'POST', body: JSON.stringify({ step, ...payload }) },
    ),

  async *strategyBuildStream(step: number, payload: Record<string, any>): AsyncGenerator<StrategyBuildStreamEvent> {
    const res = await fetch('/api/strategies/build/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step, ...payload }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  strategyValidateCode: (payload: { code: string; strategy_id?: string; name?: string; description?: string; strict?: boolean }) =>
    request<StrategyBuildResult>('/api/strategies/code/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  strategySaveCodeV2: (payload: {
    strategy_id: string
    code: string
    target_source: 'ai' | 'custom'
    mode: 'create' | 'update'
    name?: string
    description?: string
    strict?: boolean
  }) =>
    request<StrategyCodeSaveResult>('/api/strategies/code/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** 保存 AI 生成的策略文件 */
  strategySaveCode: (strategyId: string, code: string, meta?: { name?: string; description?: string }) =>
    request<{ ok: boolean; path: string }>('/api/strategies/ai/save', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, code, name: meta?.name ?? '', description: meta?.description ?? '' }),
    }),
  // ===== Phase 15 Panel Routes =====
  listOptimizationRuns: (params?: { objective?: string; as_of?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.objective) qs.set('objective', params.objective)
    if (params?.as_of) qs.set('as_of', params.as_of)
    qs.set('limit', String(params?.limit ?? 200))
    return request<OptimizationRunDTO[]>(`/api/portfolio/optimization-runs?${qs}`)
  },
  getOptimizationRun: (runId: string) =>
    request<OptimizationRunDTO>(`/api/portfolio/optimization-runs/${encodeURIComponent(runId)}`),
  listAttribution: (params?: { run_id?: string; attribution_type?: string; risk_model?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.run_id) qs.set('run_id', params.run_id)
    if (params?.attribution_type) qs.set('attribution_type', params.attribution_type)
    if (params?.risk_model) qs.set('risk_model', params.risk_model)
    qs.set('limit', String(params?.limit ?? 200))
    return request<AttributionEvidenceDTO[]>(`/api/portfolio/attribution?${qs}`)
  },
  listRebalancePlans: (params?: { run_id?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.run_id) qs.set('run_id', params.run_id)
    qs.set('limit', String(params?.limit ?? 200))
    return request<RebalancePlanDTO[]>(`/api/portfolio/rebalance-plans?${qs}`)
  },
  getPaperState: (planId: string) =>
    request<PaperStateDTO>(`/api/portfolio/rebalance-plans/${encodeURIComponent(planId)}/paper`),
  approveRebalance: (planId: string, idempotencyKey: string) =>
    request<PaperActionResponse>(`/api/portfolio/rebalance-plans/${encodeURIComponent(planId)}/approve`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }),
    }),
  rejectRebalance: (planId: string, idempotencyKey: string) =>
    request<PaperActionResponse>(`/api/portfolio/rebalance-plans/${encodeURIComponent(planId)}/reject`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }),
    }),

  // ===== Research panel routes (UI-01) =====
  listModels: (params?: { limit?: number }) => {
    const qs = new URLSearchParams()
    qs.set('limit', String(params?.limit ?? 200))
    return request<ModelDefinitionDTO[]>(`/api/research/models?${qs}`)
  },
  listModelComposites: (modelId: string) =>
    request<ModelCompositeDTO[]>(`/api/research/models/${encodeURIComponent(modelId)}/composites`),
  listFactors: (params?: { limit?: number }) => {
    const qs = new URLSearchParams()
    qs.set('limit', String(params?.limit ?? 200))
    // /factor-catalog: the legacy /factors route (dict envelope) stays owned
    // by the factor-backtest workspace; this is the strict typed panel surface.
    return request<FactorRevisionDTO[]>(`/api/research/factor-catalog?${qs}`)
  },
  getAdmissionVerdict: (revisionId: string, policyVersion = 'v1') =>
    request<AdmissionVerdictDTO>(`/api/research/factors/${encodeURIComponent(revisionId)}/verdict?policy_version=${encodeURIComponent(policyVersion)}`),
  listWfPlans: (params?: { limit?: number }) => {
    const qs = new URLSearchParams()
    qs.set('limit', String(params?.limit ?? 200))
    return request<WfPlanDTO[]>(`/api/research/wf/plans?${qs}`)
  },
  listWfFolds: (params?: { plan_id?: string; is_oos?: boolean; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.plan_id) qs.set('plan_id', params.plan_id)
    if (params?.is_oos !== undefined) qs.set('is_oos', String(params.is_oos))
    qs.set('limit', String(params?.limit ?? 200))
    return request<WfFoldDTO[]>(`/api/research/wf/folds?${qs}`)
  },
  listWfSearchRuns: (params?: { plan_id?: string; strategy_id?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.plan_id) qs.set('plan_id', params.plan_id)
    if (params?.strategy_id) qs.set('strategy_id', params.strategy_id)
    qs.set('limit', String(params?.limit ?? 200))
    return request<WfSearchRunDTO[]>(`/api/research/wf/search-runs?${qs}`)
  },
  listWfValidated: (params?: { strategy_id?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.strategy_id) qs.set('strategy_id', params.strategy_id)
    qs.set('limit', String(params?.limit ?? 200))
    return request<WfValidatedStrategyDTO[]>(`/api/research/wf/validated?${qs}`)
  },
  runWfPlan: (planId: string) =>
    request<{ ok: boolean; key: string; plan_id: string; folds: number; oos: number }>(
      `/api/research/wf/plans/${encodeURIComponent(planId)}/run`,
      { method: 'POST' },
    ),
  listWfEnsembles: (params?: { limit?: number }) => {
    const qs = new URLSearchParams()
    qs.set('limit', String(params?.limit ?? 200))
    return request<WfEnsembleDTO[]>(`/api/research/wf/ensembles?${qs}`)
  },
}

// ===== Phase 50: Replay Workbench (AF-REQ-18/20/22/24) =====
// Typed fetchers + shared interfaces mirroring the backend DTOs from 50-01/02.
// Each fetcher wraps the existing request<T> transport (api.ts:22-52); the live
// progress stream uses native EventSource over alphaRunStreamUrl (no new
// transport/dependency — WalkForward.tsx native-EventSource precedent).

export type AlphaRunStatus =
  | 'queued'
  | 'preflight_failed'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'completed'
  | 'failed'

/** Safe public run projection — mirrors AlphaRunReadDTO (no principal/internals). */
export interface AlphaRunRead {
  id: string
  status: AlphaRunStatus
  transition_version: number
  last_event_seq: number
  candidate_attempts_total: number
  candidate_attempts_completed: number
  folds_total: number
  folds_completed: number
  snapshot_sha256: string
  manifest_sha256: string
  started_at: string | null
  finished_at: string | null
  terminal_reason: string | null
  retry_of_run_id: string | null
  retry_attempt: number
  created_at: string
}

/** One append-only ledger event — mirrors AlphaRunEventDTO. */
export interface AlphaRunEvent {
  id: string
  seq: number
  event_type: string
  entity_kind: string
  entity_id: string
  occurred_at: string
  source: string
  producer_version: string
  created_at: string
}

/** The four bounded progress counters — mirrors AlphaProgressDTO. */
export interface AlphaProgress {
  candidate_attempts_total: number
  candidate_attempts_completed: number
  folds_total: number
  folds_completed: number
}

/** One candidate-attempt projection — mirrors AlphaCandidateDTO. */
export interface AlphaCandidate {
  id: string
  attempt_ordinal: number
  candidate_digest: string
  canonical_expression: string
  dsl_version: string
  operation: string
  seed: number
  step: number
  status: string
  created_at: string
}

/** One parent→child lineage edge — mirrors AlphaLineageEdgeDTO (SC2). */
export interface AlphaLineageEdge {
  lineage_id: string
  edge_ordinal: number
  operation: string
  created_at: string
  child: AlphaCandidate
  parent: AlphaCandidate
}

/** Ordered lineage edges for one run — mirrors AlphaLineageDTO (SC2 read half). */
export interface AlphaLineage {
  run_id: string
  edges: AlphaLineageEdge[]
}

/** SC4 temporal/degradation classification — the clean flag binds the data-quality banner. */
export interface EvidenceClassification {
  data_date: string | null
  source_label: string | null
  cache_state: 'fresh' | 'stale' | 'degraded'
  missing_fields: string[]
  membership_coverage: number
  evidence_role: 'exploratory' | 'selection_fold' | 'selection_oos' | 'final_blind_unavailable'
  fixture: boolean
  clean: boolean
}

/**
 * One candidate's side-by-side comparison record (SC3, AF-REQ-22).
 * Every requested candidate is exposed equally — there is NEVER an opaque
 * aggregate winner/rank/score field (the backend omits it, deny-by-default).
 */
export interface AlphaCandidateComparison {
  candidate_id: string
  candidate_digest: string
  config: Record<string, unknown>
  fold_evidence: Record<string, unknown>[]
  admission_verdict: string | null
  gate_trail_digest: string | null
  policy_version: string | null
  artifact_refs: Record<string, unknown>[]
  diversity: Record<string, unknown> | null
}

/** Side-by-side comparison page — all candidates, no opaque winner (SC3). */
export interface AlphaCompare {
  run_id: string
  candidates: AlphaCandidateComparison[]
}

/** The frozen cost-diagnostics baseline row (zero recomputation). */
export interface StressMatrixBaseline {
  total_turnover: number
  cost_rate: number
  cost_drag: number
  raw_long_short_return: number
  net_long_short_return: number
}

/** One Tier-1 stress row — pure arithmetic over stored turnover (AF-REQ-20). */
export interface StressMatrixRow {
  axis: 'fee_bps' | 'slippage_bps' | 'rebalance'
  value: number | string
  total_turnover: number
  cost_rate: number
  cost_drag: number
  net_long_short_return: number
}

/** Tier-1 stress matrix — fee/slippage/rebalance re-projection (AF-REQ-20). */
export interface StressMatrix {
  candidate_id: string
  baseline: StressMatrixBaseline
  matrix: StressMatrixRow[]
}

/** Branch-replay result — new child run sharing the parent's frozen inputs (SC2). */
export interface ReplayBranchResult {
  parent_run_id: string
  child_run_id: string
  parent_step: number
  shared_snapshot_sha256: string
  shared_manifest_sha256: string
  replayed_prefix_digests: string[]
}

/** Clone result — new/parent run id + field-level diff (SC2 clone half). */
export interface CloneResult {
  parent_run_id: string
  clone_run_id: string
  parent_manifest_sha256: string
  clone_manifest_sha256: string
  changed_dimensions: string[]
  no_op: boolean
}

/** Bounded branch-replay intent body (POST /replay-branch). */
export interface ReplayBranchBody {
  idempotency_key: string
  parent_step: number
  max_candidates?: number
}

/** Bounded clone intent body (POST /clone). */
export interface CloneBody {
  idempotency_key: string
  overrides?: Record<string, unknown>
}

/** Declared Tier-1 stress axes (fee/slippage/rebalance). */
export interface StressAxes {
  fee_bps?: number[]
  slippage_bps?: number[]
  rebalance?: string[]
}

/**
 * The durable Last-Event-ID SSE stream URL for native EventSource (SC1 UI half).
 * The browser auto-sends Last-Event-ID on every reconnect; the server honors it
 * durably (50-01-04), so reconnect resumes from the acknowledged seq losslessly.
 */
export function alphaRunStreamUrl(runId: string): string {
  return `/api/research/alpha/runs/${encodeURIComponent(runId)}/stream`
}

/** List the principal's runs (runs-list selector). */
export function fetchAlphaRuns(): Promise<AlphaRunRead[]> {
  return request<AlphaRunRead[]>('/api/research/alpha/runs')
}

/** Bounded-polling fallback: the four progress counters (SC1 'SSE or bounded polling'). */
export function fetchAlphaProgress(runId: string): Promise<AlphaProgress> {
  return request<AlphaProgress>(`/api/research/alpha/runs/${encodeURIComponent(runId)}/progress`)
}

/** One principal-scoped run projection (selected-run panel + polling terminal check). */
export function fetchAlphaRun(runId: string): Promise<AlphaRunRead> {
  return request<AlphaRunRead>(`/api/research/alpha/runs/${encodeURIComponent(runId)}`)
}

/** A run's candidate attempts (compare/stress/quality candidate selectors). */
export function fetchAlphaCandidates(runId: string): Promise<AlphaCandidate[]> {
  return request<AlphaCandidate[]>(`/api/research/alpha/runs/${encodeURIComponent(runId)}/candidates`)
}

/** Ordered parent→child lineage edges for one run (SC2 read half). */
export function fetchAlphaLineage(runId: string): Promise<AlphaLineage> {
  return request<AlphaLineage>(`/api/research/alpha/runs/${encodeURIComponent(runId)}/lineage`)
}

/** SC4 temporal/degradation classification + clean flag for one candidate. */
export function fetchEvidenceClassification(
  runId: string,
  candidateId: string,
): Promise<EvidenceClassification> {
  return request<EvidenceClassification>(
    `/api/research/alpha/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(candidateId)}/evidence-classification`,
  )
}

/** Side-by-side comparison of every requested candidate (SC3, no opaque winner). */
export function fetchAlphaCompare(runId: string, candidateIds: string[]): Promise<AlphaCompare> {
  const candidates = candidateIds.map(encodeURIComponent).join(',')
  return request<AlphaCompare>(
    `/api/research/alpha/runs/${encodeURIComponent(runId)}/compare?candidates=${candidates}`,
  )
}

/** Tier-1 stress matrix — pure arithmetic over stored turnover (AF-REQ-20). */
export function fetchStressMatrix(
  runId: string,
  candidateId: string,
  axes: StressAxes,
): Promise<StressMatrix> {
  const qs = new URLSearchParams()
  qs.set('candidate_id', candidateId)
  for (const v of axes.fee_bps ?? []) qs.append('fee_bps', String(v))
  for (const v of axes.slippage_bps ?? []) qs.append('slippage_bps', String(v))
  for (const v of axes.rebalance ?? []) qs.append('rebalance', String(v))
  return request<StressMatrix>(
    `/api/research/alpha/runs/${encodeURIComponent(runId)}/stress-matrix?${qs}`,
  )
}

/** Replay one branch into a NEW child run sharing the parent's inputs (SC2). */
export function postReplayBranch(runId: string, body: ReplayBranchBody): Promise<ReplayBranchResult> {
  return request<ReplayBranchResult>(
    `/api/research/alpha/runs/${encodeURIComponent(runId)}/replay-branch`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

/** Clone a run overriding declared scoring/costs/budgets only (SC2). */
export function postClone(runId: string, body: CloneBody): Promise<CloneResult> {
  return request<CloneResult>(
    `/api/research/alpha/runs/${encodeURIComponent(runId)}/clone`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

// ===== Pipeline =====
export interface PipelineJob {
  id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  stage: string
  progress: number          // 0-100 整体进度
  stage_pct: number         // 0-100 当前阶段内进度
  log: { ts: string; stage: string; msg: string }[]
  started_at: string | null
  finished_at: string | null
  duration_s: number | null
  result: {
    universe_size: number
    daily_days: number
    adj_factor_symbols: number
    enriched_days: number
    index_count?: number
    index_daily_rows?: number
    minute_rows: number
    skipped_stages?: string[]
  } | null
  error: string | null
}

export type PipelineJobSummary = Omit<PipelineJob, 'log'>

// ===== Data status =====
interface TableStats {
  rows: number
  earliest_date: string | null
  latest_date: string | null
  symbols_covered: number
  trading_days: number
}

interface InstrumentsStats {
  rows: number
  symbols_covered: number
  latest_as_of: string | null
  named: number
}

export interface DataStatus {
  daily: TableStats | null
  enriched: TableStats | null
  index_daily: TableStats | null
  index_enriched: TableStats | null
  index_instruments: InstrumentsStats | null
  etf_daily: TableStats | null
  etf_enriched: TableStats | null
  etf_instruments: InstrumentsStats | null
  minute: TableStats | null
  adj_factor: TableStats | null
  instruments: InstrumentsStats | null
  financials: { rows: number; tables: Record<string, { rows: number; symbols: number }> } | null
  storage: {
    daily_files: number
    daily_size_mb: number
    enriched_files: number
    enriched_size_mb: number
    index_daily_files?: number
    index_daily_size_mb?: number
    index_enriched_files?: number
    index_enriched_size_mb?: number
    index_instruments_files?: number
    index_instruments_size_mb?: number
    etf_daily_files?: number
    etf_daily_size_mb?: number
    etf_enriched_files?: number
    etf_enriched_size_mb?: number
    etf_instruments_files?: number
    etf_instruments_size_mb?: number
    etf_adj_factor_files?: number
    etf_adj_factor_size_mb?: number
    minute_files: number
    minute_size_mb: number
    adj_factor_files: number
    adj_factor_size_mb: number
    instruments_files: number
    instruments_size_mb: number
    financials_files?: number
    financials_size_mb?: number
    ext_data_files?: number
    ext_data_size_mb?: number
    total_size_mb: number
  }
  next_pipeline_run: string | null
  next_instruments_run: string | null
  last_pipeline_run: string | null
  last_instruments_run: string | null
  checked_at: string
  indicators_ready?: boolean
}

export interface EnrichedField {
  name: string
  type: string
  desc: string
}

// ===== 扩展数据 =====
export interface ExtDataField {
  name: string
  dtype: string
  label: string
}

export interface PullConfig {
  url: string
  method: string
  headers?: Record<string, string>
  body?: string | null
  response_path: string
  field_map?: Record<string, string>
  schedule_minutes: number
  enabled: boolean
  last_run?: string | null
  last_status?: string | null
  last_message?: string | null
  last_rows?: number | null
  next_run?: string | null
}

export interface ExtDataDetectUrlRequest {
  url: string
  method?: string
  headers?: Record<string, string>
  body?: string
  response_path?: string
  field_map?: Record<string, string>
}

export interface ExtDataDetectUrlResult {
  status: string
  total_rows: number
  response_path: string
  response_path_candidates: string[]
  fields: ExtDataField[]
  symbol_candidates: string[]
  code_candidates: string[]
  preview: Record<string, unknown>[]
}

export interface ExtDataConfig {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  fields: ExtDataField[]
  description?: string
  symbol_map?: Record<string, string>
  code_map?: Record<string, string>
  created_at: string
  updated_at: string
  latest_sync_date?: string | null
  date_range?: string[] | null
  pull?: PullConfig | null
}

export interface ExtDataRowsResult {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  date: string | null
  total: number
  limit: number
  fields: ExtDataField[]
  rows: Record<string, any>[]
}

export interface AnalysisColumn {
  field: string
  label?: string
  type?: 'string' | 'number' | 'percent' | 'amount' | 'date'
  width?: number | null
  sortable?: boolean
  precision?: number | null
  format?: string | null
  aggregate?: 'count' | 'avg' | 'sum' | 'min' | 'max' | null
  visible?: boolean
}

export interface AnalysisMenu {
  id: string
  label: string
  icon: string
  data_source: string
  template: 'dimension_rank' | 'ranking' | 'table'
  dimension_field?: string | null
  rank_field?: string | null
  group_columns: AnalysisColumn[]
  detail_columns: AnalysisColumn[]
  default_sort?: { field: string; order: 'asc' | 'desc' } | null
  visible: boolean
  order: number
  created_at?: string | null
  updated_at?: string | null
  builtin?: boolean
}

// ===== Phase 15 Panel DTOs (strict, server-owned) =====
export interface OptimizationRunDTO {
  id: string
  objective: string
  as_of: string
  universe: string
  model_id: string | null
  composite_snapshot_id: string | null
  input_snapshot_sha256: string
  expected_return_method: string
  risk_model: string
  risk_model_detail: Record<string, unknown> | null
  constraint_stack: Record<string, unknown> | null
  solver_name: string
  solver_version: string
  solver_options: Record<string, unknown> | null
  problem_status: string
  failure_reason: string | null
  output_weights: Record<string, number> | null
  baseline_weights: Record<string, number> | null
  output_sha256: string
  weights_artifact_relative_path: string | null
  created_at: string
}

export interface AttributionEvidenceDTO {
  id: string
  run_id: string
  attribution_type: string
  risk_model: string | null
  contributions: Record<string, unknown> | null
  reconciliation: Record<string, unknown> | null
  output_sha256: string | null
  artifact_relative_path: string | null
  created_at: string
}

export interface RebalancePlanDTO {
  id: string
  optimization_run_id: string
  input_snapshot_sha256: string
  as_of: string
  target_weights: Record<string, number> | null
  discrete_weights: Record<string, number> | null
  lot_sizes: Record<string, unknown> | null
  cash_residue: number
  turnover_cost: number
  blocked_instruments: Record<string, unknown> | null
  discretization_rmse: number
  rmse_definition: string
  expires_at: string
  output_sha256: string
  artifact_relative_path: string | null
  created_at: string
}

export interface PaperTransitionDTO {
  id: number
  plan_id: string
  transition: string
  idempotency_key: string
  previous_state: string | null
  paper_position_delta: Record<string, unknown> | null
  created_at: string
}

export interface PaperStateDTO {
  plan_id: string
  current_state: string | null
  transitions: PaperTransitionDTO[]
}

export interface PaperActionResponse {
  plan_id: string
  transition: string
  current_state: string
  idempotent: boolean
}

// ===== Research panel DTOs (UI-01, strict server-owned) =====
export interface FactorRevisionDTO {
  id: string
  factor_id: string
  revision_number: number
  name: string
  expression: string
  description: string
  status: string
  // IC (Pearson) and RankIC (Spearman) are DISTINCT metrics — never collapsed.
  ic: number | null
  rank_ic: number | null
  fields: string[] | null
  operators: string[] | null
  functions: string[] | null
  provenance: Record<string, unknown> | null
  created_at: string
}

export interface AdmissionVerdictDTO {
  revision_id: string
  policy_version: string
  admitted: boolean
  reason: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface ModelDefinitionDTO {
  model_id: string
  name: string
  weighting: string
  revision_ids: string[]
  weights: Record<string, number> | null
  input_snapshot_sha256: string | null
  created_at: string
}

export interface ModelCompositeDTO {
  id: string
  model_id: string
  input_snapshot_sha256: string
  output_sha256: string
  output_artifact_relative_path: string | null
  mean_ic: number | null
  membership_fingerprint: string | null
  created_at: string
}

export interface WfPlanDTO {
  id: string
  strategy_id: string | null
  n_folds: number
  train_size: number
  test_size: number
  gap: number
  oos_start: string | null
  oos_end: string | null
  pinned: boolean
  created_at: string
}

export interface WfFoldDTO {
  id: string
  plan_id: string
  fold_index: number
  train_start: string
  train_end: string
  test_start: string
  test_end: string
  is_oos: boolean
  created_at: string
}

export interface WfSearchRunDTO {
  id: string
  plan_id: string | null
  strategy_id: string | null
  n_trials: number
  best_score: number | null
  best_params: Record<string, unknown> | null
  score_distribution: Record<string, unknown> | null
  status: string
  created_at: string
}

export interface WfValidatedStrategyDTO {
  id: string
  strategy_id: string
  plan_id: string | null
  validated: boolean
  oos_score: number | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface WfEnsembleDTO {
  id: string
  name: string
  strategy_ids: string[]
  method: string
  output_snapshot_sha256: string | null
  created_at: string
}
