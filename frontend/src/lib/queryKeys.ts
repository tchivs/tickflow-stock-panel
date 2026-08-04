/**
 * 集中管理所有 React Query key。
 *
 * - 新增查询只需在此加一行，所有消费方自动引用。
 * - SSE invalidation 基于 SSE_INVALIDATE_PREFIXES 列表，新增 key 无需改 useQuoteStream。
 */

// ===== Query Key 工厂 =====

export const QK = {
  // 全局 / 共享 (Layout 预取)
  capabilities:   ['capabilities'] as const,
  settings:       ['settings'] as const,
  endpoints:      ['endpoints'] as const,
  version:        ['version'] as const,
  preferences:    ['preferences'] as const,
  dataSources:    ['data-sources'] as const,
  quoteStatus:    ['quote-status'] as const,
  quoteInterval:  ['quote-interval'] as const,
  overviewMarket: (asOf?: string) => ['overview-market', asOf ?? 'latest'] as const,
  indexQuotes:    ['index-quotes'] as const,
  indexList:      ['index-list'] as const,

  // Watchlist
  watchlist:            ['watchlist'] as const,
  watchlistQuotes:      ['watchlist-quotes'] as const,
  watchlistEnriched:    (ext?: string) => ['watchlist-enriched', ext] as const,
  watchlistKlineBatch:  (symbols: string) => ['watchlist-kline-batch', symbols] as const,
  // 不用 watchlist- 前缀: 避免被 SSE quotes_updated 高频失效(expert 1s/pro 2s)
  // 导致每次都拉 TickFlow 触限流。分时图用固定 refetchInterval 刷新即可。
  minuteBatch:          (symbols: string) => ['minute-batch', symbols] as const,
  instrumentSearch:     (q: string, assetTypes?: string) => ['instrument-search', q, assetTypes ?? 'stock'] as const,

  // Screener
  screener:             ['screener'] as const,
  screenerStrategies:   (assetType: string = 'stock') => ['screener-strategies', assetType] as const,
  screenerCached:       (ext?: string) => ['screener-cached', ext] as const,
  screenerKlineBatch:   (symbols: string) => ['screener-kline-batch', symbols] as const,
  marketSnapshot:       ['market-snapshot'] as const,
  limitLadder:          (asOf?: string) => ['limit-ladder', asOf] as const,

  // Backtest
  backtestStatus:       ['backtest-status'] as const,
  strategyDetail:       (id: string) => ['strategy-detail', id] as const,

  // Research workspace — preserve independent cache ownership by resource.
  researchDslOptions: ['research', 'dsl-options'] as const,
  researchFactors: ['research', 'factors'] as const,
  researchFactor: (factorId: string) => ['research', 'factors', factorId] as const,
  researchFactorRevisions: (factorId: string) => ['research', 'factors', factorId, 'revisions'] as const,
  researchSimilarity: (expression: string) => ['research', 'similarity', expression] as const,
  researchExperiments: ['research', 'experiments'] as const,
  researchExperiment: (experimentId: string) => ['research', 'experiments', experimentId] as const,
  researchComparisonCandidates: ['research', 'comparison', 'candidates'] as const,
  researchComparison: (experimentIds: string[]) => ['research', 'comparison', ...experimentIds] as const,

  // Evidence-backed analysis — subject remains in every key so one object's
  // progress event cannot clear another object's independently read panels.
  analysisReports: (subjectKind: string, subjectKey: string) => ['analysis', 'reports', subjectKind, subjectKey] as const,
  analysisReport: (subjectKind: string, subjectKey: string, reportId: string) => ['analysis', 'report', subjectKind, subjectKey, reportId] as const,
  analysisEvidence: (subjectKind: string, subjectKey: string, reportId: string) => ['analysis', 'evidence', subjectKind, subjectKey, reportId] as const,
  analysisSignalHistory: (subjectKind: string, subjectKey: string, signalId: string) => ['analysis', 'signal-history', subjectKind, subjectKey, signalId] as const,
  analysisRun: (subjectKind: string, subjectKey: string, runId: string) => ['analysis', 'run', subjectKind, subjectKey, runId] as const,

  // Controlled advanced research resources remain isolated by the authorized
  // display subject plus immutable version, job, and audit references.
  advancedViewpoints: (subjectKind: string, subjectKey: string) => ['advanced', 'viewpoints', subjectKind, subjectKey] as const,
  advancedViewpoint: (subjectKind: string, subjectKey: string, viewpointId: string, version: number) => ['advanced', 'viewpoint', subjectKind, subjectKey, viewpointId, version] as const,
  advancedViewpointVersions: (subjectKind: string, subjectKey: string, viewpointId: string) => ['advanced', 'viewpoint-versions', subjectKind, subjectKey, viewpointId] as const,
  advancedCalibration: (subjectKind: string, subjectKey: string, sourceProfile: string) => ['advanced', 'calibration', subjectKind, subjectKey, sourceProfile] as const,
  advancedJob: (subjectKind: string, subjectKey: string, jobId: string) => ['advanced', 'job', subjectKind, subjectKey, jobId] as const,
  advancedAudit: (subjectKind: string, subjectKey: string, auditReference: string) => ['advanced', 'audit', subjectKind, subjectKey, auditReference] as const,
  advancedResearchAssetBinding: (strategyId: string) => ['advanced', 'research-asset-binding', strategyId] as const,
  advancedExperiments: (researchAssetId: string) => ['advanced', 'experiments', researchAssetId] as const,
  advancedExperimentRun: (researchAssetId: string, runId: string) => ['advanced', 'experiment-run', researchAssetId, runId] as const,
  advancedCandidates: (researchAssetId: string) => ['advanced', 'candidates', researchAssetId] as const,
  advancedCandidate: (researchAssetId: string, candidateId: string) => ['advanced', 'candidate', researchAssetId, candidateId] as const,
  advancedSandboxValidations: ['advanced', 'sandbox', 'validations'] as const,
  advancedSandboxRuns: (researchAssetId: string) => ['advanced', 'sandbox-runs', researchAssetId] as const,
  advancedSandboxRun: (researchAssetId: string, runId: string) => ['advanced', 'sandbox-run', researchAssetId, runId] as const,

  // Optional Phase 05 modules — every key owns its module, research object,
  // immutable record identity, and bounded page. No module shares a broad cache.
  phase5Capabilities: ['phase5', 'capabilities'] as const,
  shadow: {
    all: ['phase5', 'shadow'] as const,
    batches: (offset = 0, limit = 50) => ['phase5', 'shadow', 'batches', offset, limit] as const,
    batch: (batchId: string) => ['phase5', 'shadow', 'batch', batchId] as const,
    evidenceSets: (offset = 0, limit = 50) => ['phase5', 'shadow', 'evidence-sets', offset, limit] as const,
    evidenceSet: (evidenceSetId: string) => ['phase5', 'shadow', 'evidence-set', evidenceSetId] as const,
    candidates: (offset = 0, limit = 50) => ['phase5', 'shadow', 'candidates', offset, limit] as const,
    candidate: (candidateId: string) => ['phase5', 'shadow', 'candidate', candidateId] as const,
    evaluations: (candidateId: string | null, offset = 0, limit = 50) => ['phase5', 'shadow', 'evaluations', candidateId ?? 'all', offset, limit] as const,
    evaluation: (evaluationId: string) => ['phase5', 'shadow', 'evaluation', evaluationId] as const,
    retentions: (candidateId: string | null, offset = 0, limit = 50) => ['phase5', 'shadow', 'retentions', candidateId ?? 'all', offset, limit] as const,
    retention: (retentionId: string) => ['phase5', 'shadow', 'retention', retentionId] as const,
  },
  thesis: {
    all: ['phase5', 'thesis'] as const,
    subject: (instrument: string) => ['phase5', 'thesis', instrument] as const,
    versionsRoot: (instrument: string) => ['phase5', 'thesis', instrument, 'versions'] as const,
    versions: (instrument: string, offset = 0, limit = 25) => ['phase5', 'thesis', instrument, 'versions', offset, limit] as const,
    version: (instrument: string, versionId: string) => ['phase5', 'thesis', instrument, 'version', versionId] as const,
    conditions: (instrument: string, versionId: string) => ['phase5', 'thesis', instrument, 'conditions', versionId] as const,
    condition: (instrument: string, versionId: string, conditionId: string) => ['phase5', 'thesis', instrument, 'condition', versionId, conditionId] as const,
    checksRoot: (instrument: string) => ['phase5', 'thesis', instrument, 'checks'] as const,
    checks: (instrument: string, offset = 0, limit = 50) => ['phase5', 'thesis', instrument, 'checks', offset, limit] as const,
    pendingRoot: (instrument: string) => ['phase5', 'thesis', instrument, 'pending'] as const,
    pending: (instrument: string, offset = 0, limit = 50) => ['phase5', 'thesis', instrument, 'pending', offset, limit] as const,
    historyRoot: (instrument: string) => ['phase5', 'thesis', instrument, 'history'] as const,
    history: (instrument: string, offset = 0, limit = 50) => ['phase5', 'thesis', instrument, 'history', offset, limit] as const,
  },
  forecast: {
    all: ['phase5', 'forecast'] as const,
    catalog: ['phase5', 'forecast', 'catalog'] as const,
    subject: (instrument: string) => ['phase5', 'forecast', instrument] as const,
    jobsRoot: (instrument: string) => ['phase5', 'forecast', instrument, 'jobs'] as const,
    jobs: (instrument: string, offset = 0, limit = 25) => ['phase5', 'forecast', instrument, 'jobs', offset, limit] as const,
    job: (instrument: string, jobId: string) => ['phase5', 'forecast', instrument, 'job', jobId] as const,
    recordsRoot: (instrument: string) => ['phase5', 'forecast', instrument, 'records'] as const,
    records: (instrument: string, offset = 0, limit = 25) => ['phase5', 'forecast', instrument, 'records', offset, limit] as const,
    record: (instrument: string, recordId: string) => ['phase5', 'forecast', instrument, 'record', recordId] as const,
    pathsRoot: (instrument: string, recordId: string) => ['phase5', 'forecast', instrument, 'record', recordId, 'paths'] as const,
    paths: (instrument: string, recordId: string, offset = 0, limit = 100) => ['phase5', 'forecast', instrument, 'record', recordId, 'paths', offset, limit] as const,
    calibration: (instrument: string, recordId: string) => ['phase5', 'forecast', instrument, 'record', recordId, 'calibration'] as const,
  },

  // Data / Pipeline
  dataStatus:           ['data-status'] as const,
  pipelineJobs:         ['pipeline-jobs'] as const,
  pipelineJob:          (id: string) => ['pipeline-job', id] as const,
  extData:              ['ext-data'] as const,
  extDataRows:          (id: string, date?: string, limit?: number, columns?: string) => ['ext-data-rows', id, date, limit, columns] as const,
  analysisMenus:        ['analysis-menus'] as const,
  analysisMenu:         (id: string) => ['analysis-menu', id] as const,

  // Kline
  kline:                (symbol: string, start: string, end: string, extColumns?: string) =>
                           ['kline', symbol, start, end, extColumns ?? ''] as const,
  stockLevels:          (symbol: string, days?: number) => ['stock-levels', symbol, days ?? 120] as const,
  klineMinute:          (symbol: string, date: string) =>
                             ['kline-minute', symbol, date] as const,
  indexDaily:           (symbol: string, start: string, end: string) =>
                           ['index-daily', symbol, start, end] as const,
  indexMinute:          (symbol: string, date: string) =>
                           ['index-minute', symbol, date] as const,

  // Schema
  extDataSchemaAll:     ['ext-data-schema-all'] as const,
  tableSchema:          (table: string) => ['table-schema', table] as const,

  // Custom Signals
  customSignals:        ['custom-signals'] as const,
  customSignalsOptions: ['custom-signals-options'] as const,

  // Monitor (监控规则 + 触发记录)
  monitorRules:         ['monitor-rules'] as const,
  monitorRuleOptions:   ['monitor-rule-options'] as const,
  // 触发记录: 三个筛选维度都进 key; 失效仍用前缀 ['alerts'] 一次命中全部变体
  alerts:               (source?: string, severity?: string, delivery?: string) => ['alerts', source ?? '', severity ?? '', delivery ?? ''] as const,
  // Dashboard 小组件的精简列表 (limit 不同) — 独立 key, 避免与监控中心全量列表互相覆盖缓存
  alertsRecent:         (limit = 10) => ['alerts', 'recent', limit] as const,
  monitorDelivery:      (eventId: string) => ['monitor-delivery', eventId] as const,

  // Portfolio
  portfolioAccounts:    (includeArchived = false) => ['portfolio-accounts', includeArchived] as const,
  portfolioSummary:     (accountId?: number) => ['portfolio-summary', accountId ?? 'all'] as const,
  portfolioHoldings:    (accountId?: number) => ['portfolio-holdings', accountId ?? 'all'] as const,

  // Decision playbook
  decisionPlaybook:     (runId: string) => ['decision-playbook', runId] as const,
  decisionReplay:       (runIds: string[], asOf: string) => ['decision-replay', asOf, ...runIds] as const,

  // AI 大盘复盘
  reviewReports:        ['review-reports'] as const,

  // 概念涨幅轮动矩阵
  rpsRotation:          (days: number) => ['rps-rotation', days] as const,

  // ===== Phase 15 Panels =====
  optimizationRuns:     (objective?: string) => ['optimization-runs', objective ?? 'all'] as const,
  optimizationRun:      (runId: string) => ['optimization-run', runId] as const,
  attribution:          (runId?: string) => ['attribution', runId ?? 'all'] as const,
  rebalancePlans:       (runId?: string) => ['rebalance-plans', runId ?? 'all'] as const,
  paperState:           (planId: string) => ['paper-state', planId] as const,

  // Research panels (UI-01) — distinct 'research-panel' prefix so the panel
  // queries never collide with the legacy research workspace cache.
  panelModels:          () => ['research-panel', 'models'] as const,
  panelModelComposites: (modelId: string) => ['research-panel', 'models', modelId, 'composites'] as const,
  panelFactors:         () => ['research-panel', 'factors'] as const,
  panelFactorVerdict:   (revisionId: string) => ['research-panel', 'factors', revisionId, 'verdict'] as const,
  panelWfPlans:         () => ['research-panel', 'wf', 'plans'] as const,
  panelWfFolds:         (planId?: string) => ['research-panel', 'wf', 'folds', planId ?? 'all'] as const,
  panelWfSearchRuns:    (planId?: string) => ['research-panel', 'wf', 'search-runs', planId ?? 'all'] as const,
  panelWfValidated:     () => ['research-panel', 'wf', 'validated'] as const,
  panelWfEnsembles:     () => ['research-panel', 'wf', 'ensembles'] as const,
  wfPlanStream:         (planId: string) => ['research-panel', 'wf', 'stream', planId] as const,
} as const

// ===== SSE 应该 invalidate 的 key 前缀列表 =====
// 新增需要 SSE 推送的查询，只需在此加一行
//
// 注意: 策略页 (screener-cached) 不在此列表 —— 行情刷新时策略结果不变
// (非监控策略读盘后静态缓存, 监控策略由独立的 strategy_results_updated 事件在
// 重算完成后刷新)。若加入 'screener', 会导致每个行情 tick 双重刷新策略页,
// 且在 monitor "重算" 窗口内读到空结果, 造成策略列表闪烁 (变 0 → 空失效 → 又出现)。

export const SSE_INVALIDATE_PREFIXES = [
  'watchlist',
  'quote-status',
  'index-quotes',
  'overview-market',
  'limit-ladder',
  'portfolio-summary',
  'portfolio-holdings',
  'optimization-runs',
  'rebalance-plans',
  'paper',
] as const
