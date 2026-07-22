import { request } from './api'

export type Phase5ModuleName = 'shadow' | 'thesis' | 'forecast'
export type Phase5HttpStatus = 404 | 409 | 422 | 503

export interface ModuleCapability {
  available: boolean
  code: string
  reason: string | null
  install_hint: string | null
}

export interface OptionalModulesResponse {
  modules: Record<Phase5ModuleName, ModuleCapability>
}

export interface PageMeta {
  offset: number
  limit: number
  total: number
  has_more: boolean
}

export interface ResourcePage<T> extends PageMeta {
  items: T[]
}

export type SafeScalar = string | number | boolean | null
export type SafeJson = SafeScalar | SafeJson[] | { [key: string]: SafeJson }
export type SafeObject = { [key: string]: SafeJson }

export interface ShadowDiagnostic {
  severity?: 'error' | 'warning'
  code?: string
  message: string
  source_row_ordinal?: number | null
}

export interface ShadowPreviewRow {
  broker_fill_id?: string | null
  symbol?: string
  side?: string
  executed_at?: string
  quantity?: number
  price?: number
  fees?: number | null
  currency?: string | null
  source_row_ordinal?: number
  duplicate_group_hash?: string | null
}

export interface ShadowPreviewMapping {
  target: string
  source: string
  sample?: string | number | null
  unit_timezone?: string | null
  status?: string
}

export interface ShadowImportPreview {
  status: string
  encoding: string | null
  mapping_version: string | null
  source_row_count: number
  sample_rows: ShadowPreviewRow[]
  sample_truncated: boolean
  preview_identity: string
  preview_id?: string
  original_filename?: string
  format?: string
  timezone?: string
  mapping?: ShadowPreviewMapping[]
  rows?: ShadowPreviewRow[]
  diagnostics?: Array<ShadowDiagnostic | string>
}

export interface ShadowImportMapping {
  broker_fill_id?: string | null
  symbol: string
  side: string
  executed_at: string
  quantity: string
  price: string
  fees?: string | null
  currency?: string | null
  account_alias?: string | null
}

export interface ShadowImportInput {
  file: File
  mapping: ShadowImportMapping
  source_timezone: string
}

export interface ShadowConfirmImportInput extends ShadowImportInput {
  source_label: string
  preview_identity: string
  supersedes_batch_id?: string | null
}

export interface ShadowBatch {
  id: string
  source_label: string
  content_sha256: string
  importer_version: string
  mapping_version: string
  supersedes_batch_id: string | null
  same_content_as: string | null
  source_row_count: number
  normalized_row_count: number
  rejected_row_count: number
  diagnostics: ShadowDiagnostic[]
  status: string
  created_at: string
  label?: string
  original_filename?: string
  imported_by?: string
  content_digest?: string
  total_rows?: number
  valid_rows?: number
  invalid_rows?: number
  duplicate_groups?: number
  partial_fills?: number
}

export interface ShadowEvidenceExclusionInput {
  trade_id: string
  reason: string
}

export interface ShadowEvidenceSetInput {
  included_batch_ids: string[]
  membership_mode: 'all_authorized_batch_trades'
  exclusions: ShadowEvidenceExclusionInput[]
}

export interface ShadowEvidenceSet {
  id: string
  fingerprint: string
  included_batch_ids: string[]
  included_trade_ids: string[]
  included_trade_count: number
  exclusions: ShadowEvidenceExclusionInput[]
  created_at: string
  batch_count?: number
  trade_count?: number
  duplicate_groups?: number
  partial_fills?: number
  excluded_trade_ids?: string[]
}

export interface ShadowRuleCondition {
  field?: string
  operator?: string
  threshold?: number
}

export interface ShadowRule {
  conditions?: ShadowRuleCondition[]
  prediction?: string
  support?: number
  precision?: number
  recall?: number
  if?: string
  then?: string
}

export interface ShadowEvaluationSummary {
  run_id?: string
  start?: string
  end?: string
  status?: string
  precision?: number | null
  recall?: number | null
  coverage?: number | null
  trades?: number | null
  return?: number | null
  drawdown?: number | null
  after_cost?: number | null
  actual_consistency?: number | null
}

export interface ShadowCandidate {
  id: string
  evidence_set_id: string
  evidence_set_fingerprint: string
  distiller_version: string
  rule_schema_version: string
  rules: ShadowRule[] | SafeJson
  features: string[]
  parameters: SafeJson
  exit_assumptions: SafeJson
  holding_assumptions: SafeJson
  source_batch_ids: string[]
  training_window: SafeJson
  seed: number | null
  class_balance: SafeJson
  metrics: SafeJson
  limitations: string[]
  rule_fingerprint: string | null
  created_at: string
  label?: string
  evidence_fingerprint?: string
  eligibility?: string
  assumptions?: string[]
  in_sample?: ShadowEvaluationSummary
  out_of_sample?: ShadowEvaluationSummary
}

export interface ShadowDateWindowInput {
  start: string
  end: string
}

export interface ShadowCostPolicyInput {
  commission_bps: number
  slippage_bps: number
  stamp_duty_bps: number
}

export interface ShadowDistillInput {
  feature_names: Array<'close_return_5d' | 'volume_ratio_20d' | 'intraday_range'>
  seed: number
  max_depth: number
  min_leaf_support: number
  exit_assumptions: {
    kind: 'fixed_holding_days'
    days: number
  }
  holding_assumptions: {
    price_adjustment: 'unadjusted_execution_vs_forward_adjusted_research'
  }
}

export interface ShadowEvaluationInput {
  in_sample_window: ShadowDateWindowInput
  out_of_sample_window: ShadowDateWindowInput
  adjustment_policy: string
  cost_policy: ShadowCostPolicyInput
}

export interface ShadowEvaluationMetrics {
  precision?: number | null
  recall?: number | null
  coverage?: number | null
  candidate_trades?: number | null
  total_return?: number | null
  max_drawdown?: number | null
  costs?: number | null
  actual_trade_consistency?: number | null
}

export interface ShadowArtifact {
  artifact_id?: string
  content_type?: string
  byte_size?: number
  checksum_sha256?: string
  schema_version?: string
  scope_sha256?: string
  created_at?: string
}

export interface ShadowEvaluation {
  id: string
  candidate_id: string
  evidence_set_id: string
  evidence_set_fingerprint: string
  run_id: string | null
  retry_of_evaluation_id: string | null
  split_kind: 'in_sample' | 'out_of_sample' | string
  window: SafeJson
  governed_fingerprint: string
  artifact: ShadowArtifact
  status: string
  metrics: ShadowEvaluationMetrics
  terminal_reason: string | null
  adjustment_policy: string | null
  cost_policy: SafeObject
  created_at: string
}

export interface ShadowRetainInput {
  in_sample_evaluation_id: string
  out_of_sample_evaluation_id: string
  rationale: string
}

export interface ShadowRetention {
  id: string
  candidate_id: string
  evidence_set_id: string
  evidence_set_fingerprint: string
  in_sample_evaluation_id: string
  out_of_sample_evaluation_id: string
  reviewer_principal?: string
  rationale?: string
  status: string
  created_at: string
}

export interface ThesisValuationAssumptionInput {
  name: string
  value: number
  unit: string
}

export interface ThesisValuationAnchorInput {
  method: string
  currency: string
  as_of: string
  low: number
  high: number
  assumptions: ThesisValuationAssumptionInput[]
  limitations: string[]
}

export type ThesisSourceKind = 'market' | 'financial' | 'analysis'
export type ThesisConditionOperator = 'lt' | 'lte' | 'gt' | 'gte' | 'eq' | 'between'
export type ThesisCadence = 'daily' | 'weekly' | 'monthly' | 'quarterly'

export interface ThesisConditionInput {
  source_kind: ThesisSourceKind
  field: string
  operator: ThesisConditionOperator
  threshold: number | [number, number]
  unit: string
  lookback_days: number
  cadence: ThesisCadence
  timezone: 'Asia/Shanghai'
  description: string
}

export interface ThesisVersionInput {
  instrument: string
  core_judgment: string
  rationale: string
  change_reason: string
  anchors: ThesisValuationAnchorInput[]
  conditions: ThesisConditionInput[]
}

export interface ThesisRevisionInput {
  expected_predecessor_id: string
  change_reason: string
  core_judgment?: string
  rationale?: string
  anchors?: ThesisValuationAnchorInput[]
  conditions?: ThesisConditionInput[]
}

export interface ThesisSchedule {
  active: boolean
  next_due_at: string
  last_attempt_at: string | null
}

export interface ThesisEvidenceSummary {
  source_id?: string
  source_revision?: string
  source_kind?: string
  field?: string
  observed_value?: number | null
  unit?: string
  as_of?: string
}

export interface ThesisCheck {
  id: string
  version_id: string
  condition_id: string
  due_at: string
  checked_at: string
  result: 'matched' | 'not_matched' | 'insufficient_evidence' | 'error'
  observed_value: number | null
  evidence_fingerprint: string
  evidence: ThesisEvidenceSummary[]
  safe_reason: string | null
}

export interface ThesisCondition extends ThesisConditionInput {
  id: string
  copied_from_condition_id: string | null
  schedule: ThesisSchedule | null
  checks: ThesisCheck[]
}

export interface ThesisAnchor extends Omit<ThesisValuationAnchorInput, 'assumptions'> {
  assumptions: ThesisValuationAssumptionInput[]
}

export interface ThesisVersion {
  id: string
  thesis_id: string
  instrument: string
  version: number
  predecessor_id: string | null
  core_judgment: string
  rationale: string
  change_reason: string
  official_state: string
  anchors: ThesisAnchor[]
  conditions: ThesisCondition[]
  created_at: string
}

export interface ThesisReview {
  id: string
  pending_id: string
  version_id: string
  condition_id: string
  check_id: string
  evidence_fingerprint: string
  decision: 'confirmed' | 'rejected'
  rationale: string
  created_at: string
}

export interface ThesisPending {
  id: string
  thesis_id: string
  version_id: string
  condition_id: string
  check_id: string
  evidence_fingerprint: string
  proposed_state: string
  reason: string
  status: 'pending' | 'confirmed' | 'rejected'
  created_at: string
  review: ThesisReview | null
  state?: 'actionable' | 'superseded' | 'confirmed' | 'rejected' | string
}

export interface ThesisHistory {
  thesis_id: string
  official_state: string
  versions: ThesisVersion[]
  pending: ThesisPending[]
  official_events: ThesisReview[]
}

export type ForecastHorizon = 5 | 20 | 60
export type ForecastJobStatus = 'queued' | 'running' | 'completed' | 'validation_failed' | 'checkpoint_mismatch' | 'artifact_failed' | 'timeout' | 'resource_terminated' | 'interrupted'
export type ForecastStage = 'validating_checkpoint' | 'freezing_input' | 'generating_paths' | 'computing_quantiles' | 'saving_record' | 'completed' | 'validation_failed' | 'checkpoint_mismatch' | 'artifact_failed' | 'timeout' | 'resource_terminated' | 'interrupted'

export interface ForecastCatalogEntry {
  catalog_id: string
  source_repository?: string
  source_revision: string
  model_repo: string
  model_revision: string
  model_weight_sha256: string
  tokenizer_repo: string
  tokenizer_revision: string
  tokenizer_weight_sha256: string
  pairing: string
  max_context: number
  allowed_devices: string[]
  weight_format?: string
  local_files_only: boolean
  trust_remote_code: boolean
  integrity?: string
  available?: boolean
  reason?: string | null
}

export interface ForecastJob {
  id: string
  instrument: string
  horizon: ForecastHorizon
  catalog_id: string
  status: ForecastJobStatus
  stage: ForecastStage
  stage_recorded_at: string
  attempt: number
  created_at: string
  updated_at: string
  retry_of_job_id?: string
  safe_reason?: string
  record_id?: string
}

export interface ForecastArtifactDescriptor {
  artifact_id?: string
  schema_version?: string
  content_type?: string
  byte_size?: number
  checksum_sha256?: string
  scope_sha256?: string
  created_at?: string
  sample_count?: number
  horizon?: number
  feature_count?: number
}

export interface ForecastQuantiles {
  [horizon: string]: {
    p10?: number
    p50?: number
    p90?: number
  }
}

export interface ForecastRecord {
  id: string
  job_id: string
  instrument: string
  origin_session_id: string
  calendar_id: string
  calendar_revision: string
  future_session_ids: string[]
  input_fingerprint: string
  horizon: ForecastHorizon
  lookback: number
  seed: number
  temperature: number
  top_k: number
  top_p: number
  sample_count: number
  catalog_id: string
  source_revision: string
  source_digest_sha256: string
  model_revision: string
  model_digest_sha256: string
  tokenizer_revision: string
  tokenizer_digest_sha256: string
  paths_checksum_sha256: string
  validation_warnings: string[]
  created_at: string
  input_artifact?: ForecastArtifactDescriptor
  output_artifact?: ForecastArtifactDescriptor
  quantiles?: ForecastQuantiles
}

export interface ForecastPathPoint {
  path_index: number
  session_id: string
  feature: string
  value: number
  warning_code?: string
}

export type ForecastPathPage = ResourcePage<ForecastPathPoint>

export interface ForecastOutcome {
  id: string
  forecast_id: string
  horizon: ForecastHorizon
  status: string
  actual_session_id: string
  actual_close: number | null
  observed_at: string
  actual_fingerprint?: string
  reason?: string
}

export interface ForecastCalibration {
  id: string
  forecast_id: string
  outcome_id: string
  metric_schema: string
  metric_version: number
  close_mae: number | null
  p10_p90_interval_covered: boolean | null
  pinball_p10: number | null
  pinball_p50: number | null
  pinball_p90: number | null
  coverage_start: string | null
  coverage_end: string | null
  created_at: string
}

export interface ForecastProgressEvent {
  job_id: string
  status: ForecastJobStatus
  stage: ForecastStage
  stage_recorded_at: string
  safe_reason?: string
}

function pageParams(offset: number, limit: number): string {
  return new URLSearchParams({ offset: String(offset), limit: String(limit) }).toString()
}

function importForm(input: ShadowImportInput | ShadowConfirmImportInput): FormData {
  const form = new FormData()
  form.set('file', input.file)
  form.set('mapping', JSON.stringify(input.mapping))
  form.set('source_timezone', input.source_timezone)
  if ('source_label' in input) {
    form.set('source_label', input.source_label)
    form.set('preview_identity', input.preview_identity)
    if (input.supersedes_batch_id) form.set('supersedes_batch_id', input.supersedes_batch_id)
  }
  return form
}

function normalizePreview(response: { preview: ShadowImportPreview } | ShadowImportPreview): ShadowImportPreview {
  const preview = 'preview' in response ? response.preview : response
  return {
    ...preview,
    status: preview.status ?? 'preview_ready',
    encoding: preview.encoding ?? null,
    mapping_version: preview.mapping_version ?? null,
    source_row_count: preview.source_row_count ?? preview.rows?.length ?? 0,
    sample_rows: Array.isArray(preview.sample_rows) ? preview.sample_rows : [],
    sample_truncated: preview.sample_truncated ?? false,
    diagnostics: Array.isArray(preview.diagnostics) ? preview.diagnostics : [],
  }
}

function normalizeDiagnostic(value: ShadowDiagnostic | string): ShadowDiagnostic {
  return typeof value === 'string' ? { message: value } : value
}

function normalizeBatch(batch: ShadowBatch): ShadowBatch {
  return {
    ...batch,
    source_label: batch.source_label ?? batch.label ?? 'Shadow import',
    content_sha256: batch.content_sha256 ?? batch.content_digest ?? '',
    importer_version: batch.importer_version ?? '',
    mapping_version: batch.mapping_version ?? '',
    supersedes_batch_id: batch.supersedes_batch_id ?? null,
    same_content_as: batch.same_content_as ?? null,
    source_row_count: batch.source_row_count ?? batch.total_rows ?? 0,
    normalized_row_count: batch.normalized_row_count ?? batch.valid_rows ?? 0,
    rejected_row_count: batch.rejected_row_count ?? batch.invalid_rows ?? 0,
    diagnostics: Array.isArray(batch.diagnostics) ? batch.diagnostics.map(normalizeDiagnostic) : [],
    status: batch.status ?? 'rejected',
    created_at: batch.created_at ?? '',
  }
}

function normalizeEvidenceSet(evidenceSet: ShadowEvidenceSet): ShadowEvidenceSet {
  return {
    ...evidenceSet,
    included_batch_ids: Array.isArray(evidenceSet.included_batch_ids) ? evidenceSet.included_batch_ids : [],
    included_trade_ids: Array.isArray(evidenceSet.included_trade_ids) ? evidenceSet.included_trade_ids : [],
    included_trade_count: evidenceSet.included_trade_count ?? evidenceSet.trade_count ?? 0,
    exclusions: Array.isArray(evidenceSet.exclusions) ? evidenceSet.exclusions : [],
    created_at: evidenceSet.created_at ?? '',
  }
}

function normalizeCandidate(candidate: ShadowCandidate): ShadowCandidate {
  return {
    ...candidate,
    evidence_set_fingerprint: candidate.evidence_set_fingerprint ?? candidate.evidence_fingerprint ?? '',
    distiller_version: candidate.distiller_version ?? '',
    rule_schema_version: candidate.rule_schema_version ?? '',
    rules: candidate.rules ?? [],
    features: Array.isArray(candidate.features) ? candidate.features : [],
    parameters: candidate.parameters ?? {},
    exit_assumptions: candidate.exit_assumptions ?? {},
    holding_assumptions: candidate.holding_assumptions ?? {},
    source_batch_ids: Array.isArray(candidate.source_batch_ids) ? candidate.source_batch_ids : [],
    training_window: candidate.training_window ?? {},
    seed: candidate.seed ?? null,
    class_balance: candidate.class_balance ?? {},
    metrics: candidate.metrics ?? {},
    limitations: Array.isArray(candidate.limitations) ? candidate.limitations : [],
    rule_fingerprint: candidate.rule_fingerprint ?? null,
    created_at: candidate.created_at ?? '',
  }
}

function normalizeRetention(retention: ShadowRetention): ShadowRetention {
  return {
    ...retention,
    evidence_set_id: retention.evidence_set_id ?? '',
    evidence_set_fingerprint: retention.evidence_set_fingerprint ?? '',
    in_sample_evaluation_id: retention.in_sample_evaluation_id ?? '',
    out_of_sample_evaluation_id: retention.out_of_sample_evaluation_id ?? '',
    status: retention.status ?? 'retained_research_only',
    created_at: retention.created_at ?? '',
  }
}

export const phase5Api = {
  capabilities: () => request<OptionalModulesResponse>('/api/optional-modules'),

  shadowPreviewImport: async (input: ShadowImportInput) => {
    const response = await request<{ preview: ShadowImportPreview } | ShadowImportPreview>('/api/shadow/imports/preview', {
      method: 'POST',
      body: importForm(input),
    })
    return normalizePreview(response)
  },
  shadowConfirmImport: async (input: ShadowConfirmImportInput) => {
    const response = await request<{ batch: ShadowBatch }>('/api/shadow/imports/confirm', { method: 'POST', body: importForm(input) })
    return { batch: normalizeBatch(response.batch) }
  },
  shadowBatches: async (offset = 0, limit = 50) => {
    const response = await request<{ batches: ShadowBatch[]; page?: PageMeta }>(`/api/shadow/batches?${pageParams(offset, limit)}`)
    return { ...response, batches: response.batches.map(normalizeBatch) }
  },
  shadowBatch: async (batchId: string) => {
    const response = await request<{ batch: ShadowBatch }>(`/api/shadow/batches/${encodeURIComponent(batchId)}`)
    return { batch: normalizeBatch(response.batch) }
  },
  shadowEvidenceSets: async (offset = 0, limit = 50) => {
    const response = await request<{ evidence_sets: ShadowEvidenceSet[]; page?: PageMeta }>(`/api/shadow/evidence-sets?${pageParams(offset, limit)}`)
    return { ...response, evidence_sets: response.evidence_sets.map(normalizeEvidenceSet) }
  },
  shadowEvidenceSet: async (evidenceSetId: string) => {
    const response = await request<{ evidence_set: ShadowEvidenceSet }>(`/api/shadow/evidence-sets/${encodeURIComponent(evidenceSetId)}`)
    return { evidence_set: normalizeEvidenceSet(response.evidence_set) }
  },
  shadowCreateEvidenceSet: async (input: ShadowEvidenceSetInput) => {
    const response = await request<{ evidence_set: ShadowEvidenceSet }>('/api/shadow/evidence-sets', { method: 'POST', body: JSON.stringify(input) })
    return { evidence_set: normalizeEvidenceSet(response.evidence_set) }
  },
  shadowCandidates: async (offset = 0, limit = 50) => {
    const response = await request<{ candidates: ShadowCandidate[]; page?: PageMeta }>(`/api/shadow/candidates?${pageParams(offset, limit)}`)
    return { ...response, candidates: response.candidates.map(normalizeCandidate) }
  },
  shadowCandidate: async (candidateId: string) => {
    const response = await request<{ candidate: ShadowCandidate }>(`/api/shadow/candidates/${encodeURIComponent(candidateId)}`)
    return { candidate: normalizeCandidate(response.candidate) }
  },
  shadowDistill: async (evidenceSetId: string, input: ShadowDistillInput) => {
    const response = await request<{ candidate: ShadowCandidate }>(`/api/shadow/evidence-sets/${encodeURIComponent(evidenceSetId)}/candidates`, { method: 'POST', body: JSON.stringify(input) })
    return { candidate: normalizeCandidate(response.candidate) }
  },
  shadowEvaluations: (candidateId?: string, offset = 0, limit = 50) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (candidateId) params.set('candidate_id', candidateId)
    return request<{ evaluations: ShadowEvaluation[]; page?: PageMeta }>(`/api/shadow/evaluations?${params}`)
  },
  shadowEvaluation: (evaluationId: string) =>
    request<{ evaluation: ShadowEvaluation }>(`/api/shadow/evaluations/${encodeURIComponent(evaluationId)}`),
  shadowEvaluate: (evidenceSetId: string, candidateId: string, input: ShadowEvaluationInput) =>
    request<{ evaluations: { in_sample: ShadowEvaluation; out_of_sample: ShadowEvaluation } }>(`/api/shadow/evidence-sets/${encodeURIComponent(evidenceSetId)}/candidates/${encodeURIComponent(candidateId)}/evaluations`, { method: 'POST', body: JSON.stringify(input) }),
  shadowRetryEvaluation: (evaluationId: string) =>
    request<{ evaluation: ShadowEvaluation }>(`/api/shadow/evaluations/${encodeURIComponent(evaluationId)}/retry`, { method: 'POST', body: JSON.stringify({}) }),
  shadowRetentions: async (candidateId?: string, offset = 0, limit = 50) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    if (candidateId) params.set('candidate_id', candidateId)
    const response = await request<{ retentions: ShadowRetention[]; page?: PageMeta }>(`/api/shadow/retentions?${params}`)
    return { ...response, retentions: response.retentions.map(normalizeRetention) }
  },
  shadowRetention: async (retentionId: string) => {
    const response = await request<{ retention: ShadowRetention }>(`/api/shadow/retentions/${encodeURIComponent(retentionId)}`)
    return { retention: normalizeRetention(response.retention) }
  },
  shadowRetain: async (evidenceSetId: string, candidateId: string, input: ShadowRetainInput) => {
    const response = await request<{ retention: ShadowRetention }>(`/api/shadow/evidence-sets/${encodeURIComponent(evidenceSetId)}/candidates/${encodeURIComponent(candidateId)}/retain`, { method: 'POST', body: JSON.stringify(input) })
    return { retention: normalizeRetention(response.retention) }
  },

  thesisVersions: (instrument: string, offset = 0, limit = 25) =>
    request<ResourcePage<ThesisVersion>>(`/api/theses/instruments/${encodeURIComponent(instrument)}/versions?${pageParams(offset, limit)}`),
  thesisVersion: (versionId: string) =>
    request<{ version: ThesisVersion }>(`/api/theses/versions/${encodeURIComponent(versionId)}`),
  thesisCreateVersion: (instrument: string, input: ThesisVersionInput) =>
    request<{ version: ThesisVersion }>(`/api/theses/instruments/${encodeURIComponent(instrument)}/versions`, { method: 'POST', body: JSON.stringify(input) }),
  thesisReviseVersion: (versionId: string, input: ThesisRevisionInput) =>
    request<{ version: ThesisVersion }>(`/api/theses/versions/${encodeURIComponent(versionId)}`, { method: 'POST', body: JSON.stringify(input) }),
  thesisChecks: (instrument: string, offset = 0, limit = 50) =>
    request<ResourcePage<ThesisCheck>>(`/api/theses/instruments/${encodeURIComponent(instrument)}/checks?${pageParams(offset, limit)}`),
  thesisPending: (instrument: string, offset = 0, limit = 50) =>
    request<ResourcePage<ThesisPending>>(`/api/theses/instruments/${encodeURIComponent(instrument)}/pending?${pageParams(offset, limit)}`),
  thesisHistory: (instrument: string, offset = 0, limit = 50) =>
    request<ResourcePage<ThesisPending>>(`/api/theses/instruments/${encodeURIComponent(instrument)}/history?${pageParams(offset, limit)}`),
  thesisConfirm: (pendingId: string, rationale: string) =>
    request<{ review: ThesisReview; official_status: string }>(`/api/theses/pending/${encodeURIComponent(pendingId)}/confirm`, { method: 'POST', body: JSON.stringify({ rationale }) }),
  thesisReject: (pendingId: string, rationale: string) =>
    request<{ review: ThesisReview; official_status: string }>(`/api/theses/pending/${encodeURIComponent(pendingId)}/reject`, { method: 'POST', body: JSON.stringify({ rationale }) }),

  forecastCatalog: () => request<{ entries: ForecastCatalogEntry[] }>('/api/forecast/catalog'),
  forecastCreateJob: (instrument: string, input: { horizon: ForecastHorizon; catalog_id: string; idempotency_key: string }) =>
    request<{ job: ForecastJob }>(`/api/forecast/instruments/${encodeURIComponent(instrument)}/jobs`, { method: 'POST', body: JSON.stringify(input) }),
  forecastRetryJob: (jobId: string, idempotencyKey: string) =>
    request<{ job: ForecastJob }>(`/api/forecast/jobs/${encodeURIComponent(jobId)}/retry`, { method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }) }),
  forecastJob: (jobId: string) =>
    request<{ job: ForecastJob }>(`/api/forecast/jobs/${encodeURIComponent(jobId)}`),
  forecastJobs: (instrument: string, offset = 0, limit = 25) =>
    request<{ jobs: ForecastJob[]; page: PageMeta }>(`/api/forecast/instruments/${encodeURIComponent(instrument)}/jobs?${pageParams(offset, limit)}`),
  forecastRecords: (instrument: string, offset = 0, limit = 25) =>
    request<{ records: ForecastRecord[]; page?: PageMeta; latest_governed_session_id?: string | null }>(`/api/forecast/instruments/${encodeURIComponent(instrument)}/records?${pageParams(offset, limit)}`),
  forecastRecord: (recordId: string) =>
    request<{ record: ForecastRecord }>(`/api/forecast/records/${encodeURIComponent(recordId)}`),
  forecastPaths: async (recordId: string, offset = 0, limit = 100) => {
    const response = await request<{ paths: ForecastPathPage }>(`/api/forecast/records/${encodeURIComponent(recordId)}/paths?${pageParams(offset, limit)}`)
    return response.paths
  },
  forecastCalibration: (recordId: string) =>
    request<{ outcomes?: ForecastOutcome[]; calibration: ForecastCalibration[] }>(`/api/forecast/records/${encodeURIComponent(recordId)}/calibration`),
  forecastRefreshCalibration: (recordId: string) =>
    request<{ outcomes?: ForecastOutcome[]; calibration: ForecastCalibration[] }>(`/api/forecast/records/${encodeURIComponent(recordId)}/calibration`, { method: 'POST', body: JSON.stringify({}) }),
} as const
