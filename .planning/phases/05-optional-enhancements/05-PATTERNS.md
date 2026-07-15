# Phase 05: Optional Enhancements - Pattern Map

**映射日期：** 2026-07-15  
**权威输入：** `05-CONTEXT.md`、`05-RESEARCH.md`  
**分析范围：** Phase 05 三个可选域、共享主机接缝、SQLite/Parquet 工件、任务/SSE、统一类型客户端、现有 Backtest/Analysis 工作区与对应测试  
**映射结论：** 现有代码可提供不可变事实、版本链、人工确认、受治理数据、受限子进程、SSE 安全投影和对象局部缓存模式；Kronos 未平均样本轴、受治理未来交易日历、批准 checkpoint 目录没有现成实现。

## 权威边界与不可破坏约束

以下不是设计建议，而是 Phase 05 规划必须保留的用户决定：

1. Shadow Account 只从本地实际成交日志导入；每次导入都是新的不可变、可归属批次。修正通过新批次/新 evidence-set 表达，不能 upsert 或覆盖。
2. Shadow 候选保留的是可审阅规则、特征、参数、来源和限制；必须有独立、按时间顺序冻结的 IS/OOS 评估。`retained` 不能注册策略、监控、playbook、position 或 broker action。
3. Thesis 的版本、估值锚、条件、检查、pending conclusion、confirm/reject 都是审计事实；只有 condition schedule/lease 是窄可变恢复游标。自动检查只能提出 pending，用户确认前 official state 不变。
4. Forecast 只面向单个 A 股标的、受治理日线 OHLCV、固定 `5|20|60` 交易日 horizon；必须保留 P10/P50/P90 和真实 sampled paths。
5. Forecast 运行冻结 Kronos source、model、tokenizer 的 immutable revision 与 digest；运行期不得跟随远程 `latest`，不得自动下载。
6. Forecast record 不可变；成熟后的 actual outcome/calibration 追加到原 identity。Forecast 不得改变 thesis、strategy、decision plan、monitor 或市场动作。
7. 三个模块独立可用/不可用；缺少 sklearn、torch、checkpoint 或 Kronos 源码只能让相应模块返回 typed unavailable，不能阻止默认 v1 启动。
8. 时序数据继续使用 governed Parquet/DuckDB/Polars；业务元数据、血缘、调度游标和审计事实继续使用同一个 `operational.db`。不引入第二数据湖、数据库、队列或容器。

## File Classification

### Shadow Account

| 新建/修改文件 | Role | Data Flow | Clos近现有 analog | 匹配质量 |
|---|---|---|---|---|
| `backend/app/shadow/schemas.py` | model / schema | request-response + transform | `backend/app/advanced/schemas.py::StrictAdvancedModel`, `FrozenStrategyScope` | exact role |
| `backend/app/shadow/artifacts.py` | artifact store | file-I/O | `backend/app/backtest/frozen_panel.py::FrozenPanelArtifactStore`; raw bytes descriptor 补充参考 `backend/app/research/artifacts.py::EvaluationArtifactService` | exact flow |
| `backend/app/shadow/repository.py` | repository | CRUD（append-only facts） | `backend/app/advanced/repository.py::AdvancedRepository` | exact role/flow |
| `backend/app/shadow/importer.py` | service / importer | file-I/O + transform | `backend/app/api/ext_data.py::upload_data`, `detect_fields`; 编码参考 `backend/app/services/ext_data.py::ensure_utf8_csv` | partial；现有实现不是不可变证据导入 |
| `backend/app/shadow/distillation.py` | service / transform | batch transform | `backend/app/research/factor_dsl.py` 的 allowlisted AST/compile；门禁参考 `advanced/evolution.py` | partial；无现成 sklearn distiller |
| `backend/app/shadow/evaluation.py` | service / collaborator | batch + spawned task | `advanced/governed_runner.py::StrategyBacktestExperimentCollaborator`, `GovernedExperimentRunner` | exact flow |
| `backend/app/shadow/service.py` | domain service | request-response + batch | `advanced/viewpoints.py::ViewpointService`; `advanced/evolution.py::EvolutionService` | role-match |
| `backend/app/shadow/projections.py` | safe projection | transform | `advanced/projections.py::experiment_run`, `candidate` | exact role |
| `backend/app/shadow/api.py` | route/controller | request-response + multipart + task | `advanced/api.py` 的 scope/service/opaque-ID helpers；上传形状参考 `api/ext_data.py` | role-match |

### Thesis lifecycle

| 新建/修改文件 | Role | Data Flow | Clos近现有 analog | 匹配质量 |
|---|---|---|---|---|
| `backend/app/theses/schemas.py` | model / schema | request-response + transform | `advanced/schemas.py::ViewpointRequest`, `ViewpointRevisionRequest`, `analysis/api.py::ConfirmReviewRequest` | exact role |
| `backend/app/theses/repository.py` | repository | append-only CRUD + monotonic cursor | `advanced/repository.py::append_viewpoint_version`, `transition_job_with_audit`; `analysis/repository.py` lifecycle facts | exact role/flow |
| `backend/app/theses/evidence.py` | governed adapter | transform | `analysis/evidence_loader.py::GovernedEvidenceLoader` | exact role/flow |
| `backend/app/theses/conditions.py` | deterministic evaluator | transform | `research/factor_dsl.py` fixed AST/allowlist；`analysis/lifecycle.py::_eligible` | role-match；condition schema 必须独立 |
| `backend/app/theses/scheduler.py` | scheduler / cursor scanner | batch + event-driven | `jobs/daily_pipeline.py::start_scheduler`; 持久 cursor 则参考 `advanced_jobs` guarded transition | partial；无现成 per-condition due ledger |
| `backend/app/theses/service.py` | domain service | request-response + event-driven | `advanced/viewpoints.py::ViewpointService`; `analysis/lifecycle.py::LifecycleRuleService` | exact domain pattern |
| `backend/app/theses/projections.py` | safe projection | transform | `analysis/projections.py::signal_history`; `advanced/projections.py::viewpoint` | exact role |
| `backend/app/theses/api.py` | route/controller | request-response | `analysis/api.py` confirm/reject + opaque-ID scope；`advanced/api.py` revisions | exact role/flow |

### Kronos Forecast

| 新建/修改文件 | Role | Data Flow | Clos近现有 analog | 匹配质量 |
|---|---|---|---|---|
| `backend/app/forecast/catalog.py` | config / capability factory | file-I/O + transform | `services/backtest.py::_get_vbt/is_available`; deployment manifest validation参考 `main.py::_load_advanced_host_fixture` | partial；无 checkpoint catalog |
| `backend/app/forecast/calendar.py` | governed data adapter | file-I/O + request-response | `tickflow/repository.py::KlineRepository.get_daily_asset` 的 governed Parquet boundary | no close analog；当前无 CN-A future-session dataset |
| `backend/app/forecast/input.py` | service / freezer | request-response + file-I/O | `StrategyBacktestService.freeze_panel_artifact`, `_governed_input_manifest`; `KlineRepository.get_daily` | exact flow |
| `backend/app/forecast/kronos_adapter.py` | model adapter | batch transform | `advanced/governed_runner.py::ServerOwnedBacktestCollaborator` 只提供边界形状 | no implementation analog；必须新增 pre-mean sample-axis adapter |
| `backend/app/forecast/runner.py` | task runner | spawned process + batch | `advanced/governed_runner.py::GovernedExperimentRunner` | exact role/flow |
| `backend/app/forecast/artifacts.py` | artifact store | file-I/O | `backtest/frozen_panel.py::FrozenPanelArtifactStore`; descriptor 参考 `research/artifacts.py` | exact role/flow |
| `backend/app/forecast/repository.py` | repository | append-only CRUD + guarded job cursor | `advanced/repository.py::acquire_job`, `transition_job_with_audit`, `append_viewpoint_evaluation` | exact role/flow |
| `backend/app/forecast/calibration.py` | service / evaluator | scheduled batch + transform | `advanced/viewpoints.py::record_evaluation`, `calibration`, `_terminal_outcome` | role/flow match |
| `backend/app/forecast/projections.py` | safe projection | transform | `advanced/projections.py::experiment_run`, `sandbox_run` | exact role |
| `backend/app/forecast/api.py` | route/controller + SSE | request-response + streaming | `advanced/api.py` safe scope；`api/intraday.py::quote_stream`；task reconnect 语义参考 Backtest stream | role-match |

### 共享主机、持久化、类型客户端、任务和 UI

| 新建/修改文件 | Role | Data Flow | Clos近现有 analog | 匹配质量 |
|---|---|---|---|---|
| `backend/app/optional_modules.py`（规划时建议采用的共享 host/factory 名称） | provider / capability host | startup + request-response | `services/backtest.py::_get_vbt/is_available`; `main.py` lifespan `app.state` wiring | role-match；当前无三模块共享 host |
| `backend/app/operational/migrations.py` | migration | CRUD / schema evolution | 同文件 `MIGRATIONS` 中 advanced immutable triggers 与 guarded transition | exact |
| `backend/app/main.py` | config / lifespan wiring | startup/shutdown | 当前 `lifespan` 中 analysis/advanced 装配 | exact；只能做窄注册 |
| `backend/pyproject.toml` | config | packaging | `[project.optional-dependencies].backtest` | exact |
| `Dockerfile`, `docker-compose.yml` | config | build-time | `BACKEND_EXTRAS` 现有循环 | exact；研究显示大概率无需行为改动 |
| `frontend/src/lib/phase5Api.ts`（建议新建 typed domain slice） | typed API client | request-response + multipart | `frontend/src/lib/api.ts` lines 2617-2697 | exact role；避免继续膨胀 `api.ts` |
| `frontend/src/lib/api.ts` | unified façade / existing client | request-response | 现有 `request<T>` 与 `api` method shape | exact；只保留最小统一入口接缝，不承载 Phase 05 全部 DTO/实现 |
| `frontend/src/lib/queryKeys.ts` | query-key factory | transform/cache | `QK.analysis*`, `QK.advanced*` | exact |
| `frontend/src/lib/forecastTask.ts`（若采用独立 forecast SSE） | task client / hook | streaming + event-driven | `frontend/src/lib/backtestTask.ts::connectSSE`, `tryReconnect` | exact role/flow |
| `frontend/src/pages/backtest/ShadowAccount.tsx` | component / workspace panel | request-response + task | `components/advanced/AdvancedResearchPanels.tsx`; host 参考 `pages/Backtest.tsx` | role-match |
| `frontend/src/components/analysis/ThesisPanel.tsx` | component | request-response + event-driven | `components/advanced/ViewpointPanel.tsx`; `components/analysis/LifecyclePanel.tsx` | exact role |
| `frontend/src/components/analysis/ForecastPanel.tsx` | component/chart | request-response + streaming | query/mutation 参考 `ViewpointPanel`; ECharts hook 参考 `pages/backtest/charts/useECharts.ts` | role-match；sample paths 无现成 UI |
| `frontend/src/pages/Backtest.tsx` | workspace host | request-response | 同文件 strategy tab + `AdvancedResearchPanels` composition | exact；只挂载 panel |
| `frontend/src/components/analysis/AnalysisWorkspace.tsx` | workspace host | request-response + cache | 同文件 object-first subject mapping | exact；只挂载 Thesis/Forecast panel |
| `frontend/src/pages/StockAnalysis.tsx` | page host | request-response | 同文件 `AnalysisWorkspace` integration | exact；不在 Portfolio 启用 Forecast v1 |

### 测试文件

| 计划文件 | Role | Data Flow | Clos近现有 analog | 必守合同 |
|---|---|---|---|---|
| `backend/tests/shadow/test_imports.py` | integration test | file-I/O + CRUD | `tests/backtest/test_frozen_panel_artifact.py`; ext-data upload tests | 同内容/修正导入仍产生新 batch；raw bytes/trades 不可变 |
| `backend/tests/shadow/test_evidence_sets.py` | unit/integration | CRUD | advanced viewpoint lineage tests | partial fills 不合并；排除项只写新 manifest |
| `backend/tests/shadow/test_distillation.py` | unit | transform | `tests/research/test_factor_dsl.py` | allowlist、固定 seed、导出 JSON，无 pickle/code |
| `backend/tests/shadow/test_evaluation_retention.py` | integration | spawned batch + CRUD | `tests/advanced/test_evolution.py`; governed runner tests | IS/OOS 不重叠且都完成；retain 无 activation side effect |
| `backend/tests/theses/test_contracts.py` | unit | transform | `tests/test_analysis_lifecycle.py` | valuation range+assumptions；AST 拒绝字段/运算符注入 |
| `backend/tests/theses/test_versions.py` | integration | CRUD | `tests/advanced/test_viewpoints.py` | predecessor/version/anchor/condition append-only |
| `backend/tests/theses/test_scheduler.py` | integration | scheduled batch | scheduler focused tests + advanced job transition tests | `(condition_id,due_at)` 幂等、重启恢复、checks append-only |
| `backend/tests/theses/test_lifecycle.py` | integration/API | event-driven + request-response | `tests/test_analysis_lifecycle.py`, `tests/test_analysis_api.py` | matched 只 pending；server principal confirm；reject 不变更 official state |
| `backend/tests/forecast/test_catalog.py` | unit | file-I/O | optional backtest availability tests / production host tests | moving ref、错配 pairing、digest mismatch fail closed；缺模块不阻塞 v1 |
| `backend/tests/forecast/test_input.py` | unit/integration | file-I/O + transform | `tests/test_market_data_fixture_contract.py`, frozen panel tests | stock daily only、5/20/60、calendar session 与 fingerprint 冻结 |
| `backend/tests/forecast/test_kronos_adapter.py` | unit | batch transform | 无直接 analog；结构参考 factor DSL pure tests | 32 paths；quantile 从 path axis 计算，不从 mean path 伪造 |
| `backend/tests/forecast/test_runner.py` | integration | spawned process | advanced governed-runner/sandbox tests | timeout/OOM/shape fail 不写 record；Queue manifest 有界；进程被回收 |
| `backend/tests/forecast/test_calibration.py` | integration | scheduled batch + CRUD | `tests/advanced/test_viewpoints.py` | outcome/calibration append；每 forecast+horizon 唯一；缺价不用 0 |
| `backend/tests/test_phase5_optional_host.py` | host integration | startup/request-response | `tests/advanced/test_production_host.py` | default/Shadow/Forecast/combined availability；v1 启动；no live execution |
| `frontend/e2e/phase5-optional-enhancements.spec.ts` | browser contract | request-response + streaming | `frontend/e2e/phase4-advanced-capabilities.spec.ts` | immutable history、pending confirm、P10/50/90、sample paths、unavailable、SSE reconnect、无外部请求 |

## Pattern Assignments

### 1. 严格 DTO 与浏览器最小权威

**适用：** `shadow/schemas.py`、`theses/schemas.py`、Forecast request DTO、所有 Phase 05 POST/PUT body。  
**Analog：** `backend/app/advanced/schemas.py:10-48,65-98,153-155`。

```python
class StrictAdvancedModel(BaseModel):
    """Reject undeclared fields at every browser or provider trust boundary."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ViewpointRequest(StrictAdvancedModel):
    instrument: Identifier = Field(min_length=1, max_length=32,
                                   pattern=r"^[0-9A-Z.\-]+$")
    target_range: tuple[float, float]
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _target_range_is_ordered(self) -> ViewpointRequest:
        if self.target_range[0] > self.target_range[1]:
            raise ValueError("target_range must be ordered")
        return self
```

**复用不变量：**

- 每个 trust boundary 使用 `extra="forbid"`、长度/数量/数值上界、`Literal` 枚举和 cross-field validator。
- 浏览器只发送 bounded selector：文件、字段 mapping、instrument、horizon、catalog id、用户 rationale/confirm。浏览器不得发送 batch fingerprint、checkpoint digest、quantile、evidence verdict、reviewer principal 或 authorization scope。
- Thesis valuation anchor 必须是 `low/high/currency/as_of/assumptions`；`high >= low` 在 Pydantic 和 SQLite 两层校验。
- Empty request body 可以像 `GateEvaluationRequest` 一样明确存在，用于表达“服务端拥有全部评估权威”。

### 2. Managed immutable artifact

**适用：** `shadow/artifacts.py`、`forecast/artifacts.py`、Shadow frozen evidence set、Forecast input/output Parquet。  
**主 analog：** `backend/app/backtest/frozen_panel.py:37-74,76-114,117-137`。  
**descriptor/权限 analog：** `backend/app/research/artifacts.py:21-33,36-70,72-120`。

```python
class FrozenPanelArtifactStore:
    def create(self, *, scope: Mapping[str, object], panel: pl.DataFrame) -> dict[str, str]:
        artifact_id = uuid4().hex
        artifact_dir = self.root / artifact_id
        temporary_dir = self.root / f".{artifact_id}.tmp"
        scope_checksum = _checksum(_canonical_json(dict(scope)))
        temporary_dir.mkdir()
        panel_path = temporary_dir / "panel.parquet"
        panel.write_parquet(panel_path)
        panel_checksum = _checksum(panel_path.read_bytes())
        (temporary_dir / "metadata.json").write_bytes(_canonical_json(metadata))
        temporary_dir.rename(artifact_dir)
```

```python
@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    evaluation_run_id: str
    relative_path: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    created_at: str
```

**复用不变量：**

- 所有路径由服务端 UUID/opaque id 派生；对 client filename 只保存安全 display metadata，不使用其路径。
- namespace/exact file 必须 exclusive-create 或 temp-directory→atomic rename；碰撞是错误，不是覆盖/复用理由。
- descriptor 只返回相对 managed path、size、content type、SHA-256、schema version、created_at；safe projection 不返回本地绝对路径。
- load 时验证 descriptor 字段集合、identifier 格式、metadata checksum、scope checksum、payload checksum，缺文件/partial/tamper 全部 fail closed。
- Forecast output Parquet 先保存全部 sampled paths，再由同一 paths 计算 quantiles；SQLite 只持有 descriptor、配置、provenance 和 digest。
- Shadow 相同内容的再次导入也要创建新 batch namespace；content SHA 只能写 `same_content_as`，不能返回旧 batch。

### 3. 单一 operational.db 的 append-only repository

**适用：** 三个 domain repository、Phase 05 migration。  
**Analog：** `backend/app/advanced/repository.py:45-68,347-392,434-512,585-621`。

```python
class AdvancedRepository:
    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()
```

```python
def transition_job_with_audit(...):
    with self._connection() as connection, connection:
        connection.execute("INSERT INTO advanced_security_audit ...", (...,))
        changed = connection.execute(
            """UPDATE advanced_jobs SET status = ?, ...
               WHERE id = ? AND status = ?""", (..., from_status)
        ).rowcount
        if changed != 1:
            raise ValueError("advanced job state changed; refresh and retry")
```

```python
def append_viewpoint_version(...):
    """Append the next immutable viewpoint version and its evidence atomically."""
    with self._connection() as connection, connection:
        next_version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 ... WHERE viewpoint_id = ?",
            (viewpoint_id,),
        ).fetchone()[0]
        connection.execute("INSERT INTO advanced_viewpoint_versions ...", (...,))
        for item in evidence:
            connection.execute("INSERT INTO advanced_viewpoint_evidence ...", (...,))
```

**复用不变量：**

- short-lived parameterized connections；所有 insert/guarded update 在一个 `with connection` transaction 中。
- 所有事实表 `ON DELETE RESTRICT`，并有 `BEFORE UPDATE` 与 `BEFORE DELETE` abort trigger。
- 仅 `forecast_jobs` 与 condition/forecast due schedule 可窄更新；更新必须 CAS（`WHERE id=? AND status=?`）并受合法 transition/monotonic trigger 约束。
- 唯一键负责重启幂等：Shadow row identity/evidence-set fingerprint、`(condition_id,due_at)`、pending-per-check、`(forecast_id,horizon)`。
- repository 返回 persisted row，不返回调用方 payload；official state 从 immutable event 派生。

### 4. Migration 形状：事实不可变，cursor 受限

**适用：** `backend/app/operational/migrations.py` 新增 Phase 05 migration entry。  
**Analog：** `backend/app/operational/migrations.py:403-450,451-498,573-625,653-659,773-783`。

```sql
CREATE TABLE advanced_viewpoint_versions (
    id TEXT PRIMARY KEY,
    viewpoint_id TEXT NOT NULL REFERENCES advanced_viewpoints(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    target_low REAL NOT NULL,
    target_high REAL NOT NULL CHECK (target_high >= target_low),
    UNIQUE(viewpoint_id, version)
);

CREATE TRIGGER advanced_viewpoint_versions_no_update
BEFORE UPDATE ON advanced_viewpoint_versions
BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
CREATE TRIGGER advanced_viewpoint_versions_no_delete
BEFORE DELETE ON advanced_viewpoint_versions
BEGIN SELECT RAISE(ABORT, 'advanced facts are immutable'); END;
```

```sql
CREATE TRIGGER advanced_jobs_valid_transition BEFORE UPDATE ON advanced_jobs
WHEN NOT (
    OLD.status = 'queued' AND NEW.status IN ('authorized', 'rejected')
    OR OLD.status = 'authorized' AND NEW.status IN ('frozen', 'rejected')
    ...
)
BEGIN SELECT RAISE(ABORT, 'advanced job cannot transition from its current state'); END;
```

**复用不变量：** migration 只能追加到 `MIGRATIONS`；`migrate_operational_db()` 使用 `PRAGMA user_version` 严格按序执行。Phase 05 不创建独立 DB。

### 5. Shadow import：只复制 parsing seam，不复制可变 ext-data 语义

**适用：** `shadow/importer.py`、Shadow upload/preview endpoints。  
**Partial analog：** `backend/app/api/ext_data.py:414-478,652-696`。

```python
suffix = Path(file.filename or "").suffix.lower()
if suffix not in (".csv", ".xlsx", ".xls"):
    raise HTTPException(400, "仅支持 CSV / Excel 文件")

if suffix == ".csv":
    df = pl.read_csv(ensure_utf8_csv(tmp_path), infer_schema_length=10000)
elif suffix in (".xlsx", ".xls"):
    df = pl.read_excel(tmp_path)
```

**只可复制：** `UploadFile`、suffix allowlist、server temp path、Polars CSV/XLSX parsing、GB18030/GBK→UTF-8 normalization、`finally` cleanup、字段 preview。  
**绝对不可复制：** ext-data 的“读取全部 bytes 后覆盖快照、刷新 view”语义。Shadow 必须先实施 byte/row/column/cell limits，保存 raw artifact descriptor，再原子追加 batch/trades/diagnostics；解析失败也保留 attributable batch diagnosis，但不能进入 evidence set。

### 6. Allowlisted explainable transform

**适用：** `shadow/distillation.py`、`theses/conditions.py`。  
**Analog：** `backend/app/research/factor_dsl.py:18-42,45-138,157-180,232-256`。

```python
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset({
    "open", "high", "low", "close", "volume", "amount", ...
})

@dataclass(frozen=True, slots=True)
class ParsedFactor:
    expression: Expression
    canonical_expression: str
    dsl_version: str
    features: FactorFeatures

    def compile(self) -> pl.Expr:
        return compile_ast(self.expression)
```

```python
if token.value not in ALLOWED_FIELDS:
    raise FactorDslError(
        f"unknown governed numeric field {token.value!r}", token.location
    )
```

**复用不变量：** parse/validate 先于任何 Polars/sklearn allocation；无 `eval`、无 arbitrary Python；字段、operator、function 固定 allowlist；canonical JSON/schema version/fingerprint 可重放。  
**Shadow 专属：** shallow tree 训练后立即导出叶路径 JSON，再通过 Phase 2/自有 allowlist 编译验证；不保存 estimator/pickle/joblib。  
**Thesis 专属：** 不复用 Factor DSL schema；建立 `source_kind/field/operator/typed threshold/range/unit/lookback/cadence/timezone` 固定 AST，每个 source kind 有独立 allowlist。

### 7. Governed OHLCV 和 input fingerprint

**适用：** Shadow feature panel、Thesis market evidence、Forecast input、Forecast maturity actual。  
**Analog：** `backend/app/tickflow/repository.py:1123-1159,1220-1234`; `backend/app/backtest/strategy.py:89-114,207-231,363-393`。

```python
def get_daily(
    self, symbol: str, start: date, end: date,
    columns: list[str] | None = None,
) -> pl.DataFrame: ...

def get_daily_asset(
    self, asset_type: str, symbol: str, start: date, end: date,
    columns: list[str] | None = None,
) -> pl.DataFrame:
    if asset_type == "stock":
        return self.get_daily(symbol, start, end, columns)
    ...
```

```python
def _governed_input_manifest(loaded, config, *, frozen_reference=None):
    source_reference = {
        "source_kind": "frozen_governed_panel" if frozen_reference
                       else "governed_enriched_parquet",
        "asset_type": config.asset_type,
        "schema": schema,
        "observed_start": str(observed_start),
        "observed_end": str(observed_end),
        "loaded_row_count": loaded.height,
    }
    return {
        **source_reference,
        "revision": sha256(encode(schema)).hexdigest(),
        "fingerprint": sha256(encode(source_reference)).hexdigest(),
    }
```

**复用不变量：** 只通过 repository 读取 governed lake；server 解析 asset type、date/as-of、columns、sorting、uniqueness、coverage、adjustment semantics 和 fingerprint。不得在 `KlineRepository` 添加 Shadow/Thesis/Forecast domain 方法。

### 8. 冻结输入后 spawn；子进程只返回有界 manifest

**适用：** `shadow/evaluation.py`、`forecast/runner.py`。  
**Analog：** `backend/app/advanced/governed_runner.py:24-41,78-147,302-354,357-490`。

```python
class ServerOwnedBacktestCollaborator(Protocol):
    def run(self, *, specification: dict[str, object]) -> dict[str, object]: ...

# parent side
prepare = getattr(self.collaborator, "prepare", None)
prepared_specification = prepare(specification=dict(specification))
context = multiprocessing.get_context("spawn")
output = context.Queue(maxsize=1)
worker = context.Process(
    target=_worker,
    args=(self.collaborator, prepared_specification, self._limits, output),
)
```

```python
# worker side
_configure_worker_runtime()
os.setsid()
applied = _install_limits(limits)
result = collaborator.run(specification=specification)
output.put({"kind": "success", "result": result, "limits": applied})
```

```python
@staticmethod
def _reap(worker: multiprocessing.Process) -> None:
    os.killpg(worker.pid, signal.SIGTERM)
    worker.join(0.5)
    if worker.is_alive():
        os.killpg(worker.pid, signal.SIGKILL)
        worker.join()
```

**复用不变量：**

- 父进程完成 authorization、instrument/calendar resolution、governed reads、validation、freeze/fingerprint；DuckDB/Polars repository connection 不跨进程。
- `spawn` 而不是 `fork`；worker 自建需要的不可 pickle service。
- 安装 CPU/memory/thread/wall-clock/output/queue bounds；timeout 或 worker 早退必须 kill process group。
- Queue 只传 capped JSON manifest；大 paths 由 worker 写 temp artifact，父进程校验后原子转正。
- failure 返回安全 terminal status/reason/resources；不得泄漏 traceback/host path，也不得创建伪 forecast record。

### 9. Shadow IS/OOS 与 retention gate

**适用：** `shadow/evaluation.py`、`shadow/service.py`。  
**Analog：** `advanced/governed_runner.py::StrategyBacktestExperimentCollaborator` lines 78-147,205-234；`advanced/evolution.py:75-119,121-152`。

```python
in_sample_scope, out_of_sample_scope = self._split_scopes(scope)
in_sample = self._split_evaluation(result=..., scope=in_sample_scope)
out_of_sample = self._split_evaluation(result=..., scope=out_of_sample_scope)
```

```python
if not self._evidence_matrix_is_complete(run=run, specification=specification):
    raise ValueError("completed run lacks required immutable evolution evidence")
```

**复用不变量：** IS 与 OOS 必须分别执行、分别保存 run id/fingerprint/window/artifact/metrics，日期不重叠；full-sample metric 不可代替。Shadow retention 写独立 `shadow_retention_event`，不能调用 `EvolutionService.approve()`，因为后者最终会注册 research strategy。Phase 05 测试还要断言 monitor/strategy/playbook/position/broker repository 没有变化。

### 10. Thesis version chain、pending conclusion 与人工确认

**适用：** `theses/service.py`、`theses/repository.py`、`theses/api.py`。  
**Version analog：** `backend/app/advanced/viewpoints.py:34-71,199-227`。  
**Pending/confirm analog：** `backend/app/analysis/lifecycle.py:33-77,132-168`。

```python
def revise_viewpoint(self, *, viewpoint_id: str, **changes):
    previous = self._latest(viewpoint_id)
    request = ViewpointRevisionRequest.model_validate(changes)
    return self._append_revision(previous, request, ...)
```

```python
def propose(...):
    if current_state != prior_state:
        return None
    if not frozen_evidence or not self._eligible(...):
        return None
    return repository.append_lifecycle_proposal(...)
```

```python
def confirm(...):
    reviewer_principal = self._resolve_reviewer(session_token)
    review = self._repository.get_lifecycle_review(review_id)
    if not self._eligible(...):
        raise ValueError("lifecycle review no longer satisfies its evidence threshold")
    confirmed = self._repository.confirm_lifecycle_review(...)
    return {"official_state": confirmed["event"]["next_state"], **confirmed}
```

**复用不变量：**

- 新 version 原子复制未变字段并写 predecessor/supersedes；旧 version、anchors、conditions、checks 不更新。
- 每次 check FK 指向 exact version/condition，不能只指向 thesis id。
- `matched` 只创建 evidence-linked pending conclusion；confirm 时重新验证 current official state 与 evidence threshold，并从 authenticated middleware 取 opaque principal。
- reject 追加 event，official state 不变；重复/过期 review 返回 conflict。
- version 激活后旧 condition 不再被 due scanner 选择，但历史 schedule/check 保留可读。

### 11. Governed evidence resolver

**适用：** `theses/evidence.py`。  
**Analog：** `backend/app/analysis/evidence_loader.py:45-67,106-141,143-172`。

```python
class GovernedEvidenceLoader:
    """Build JSON-safe facts without accepting browser or external-provider evidence."""

    def __call__(self, subject_kind: str, subject_key: str, _focus: str):
        if subject_kind == "instrument":
            return self._instrument_records(subject_key)
        if subject_kind == "account":
            return self._account_records(subject_key)
        raise ValueError("analysis subject kind is unsupported")
```

**复用不变量：** source id、origin、independence group、value/unit/period/definition/retrieved_at/as_of/source locator 全由服务端 governed sources 构造；非 finite 和 missing evidence 被过滤/标记为 `insufficient_evidence`，绝不转换成 `0` 或 `False`。

### 12. Scheduler 是 recovery cursor，不是证据 authority

**适用：** `theses/scheduler.py`、Forecast maturity scan。  
**APScheduler analog：** `backend/app/jobs/daily_pipeline.py:899-908,911-1021`。

```python
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
scheduler.add_job(
    task,
    trigger=IntervalTrigger(minutes=60),
    id="reprobe_capabilities",
    misfire_grace_time=600,
    replace_existing=True,
)
```

**复用不变量：** lifespan 只注册一个 bounded due scanner，而不是每个 condition 一个进程/job；scanner 从 SQLite 租约有限 due rows。`(condition_id,due_at)` / `(forecast_id,horizon)` 唯一约束提供重启幂等。失败也追加 check/error fact 并单调推进 cursor；scheduler 自身时间不是 evidence。不要把 domain scan 逻辑放进已经 1051 行的 `daily_pipeline.py`。

### 13. Optional module host 与 typed unavailable

**适用：** 共享 optional host、Forecast catalog availability、Shadow sklearn availability、router 503。  
**Lazy import analog：** `backend/app/services/backtest.py:23-57`。

```python
_vbt = None
_vbt_unavailable_reason: str | None = None

def _get_vbt():
    try:
        import vectorbt as vbt
        return vbt
    except ImportError as e:
        raise VectorbtUnavailable(reason) from e

def is_available() -> bool:
    try:
        _get_vbt()
        return True
    except VectorbtUnavailable:
        return False
```

**HTTP analog：** `advanced/api.py:69-99`。

```python
def _service(request: Request, name: str) -> Any:
    service = getattr(request.app.state, name, None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="advanced service is temporarily unavailable",
        )
    return service
```

**复用不变量：** base import/lifespan 不 import sklearn/torch/Kronos；capability probe 只检查 package spec/local dirs/manifest/digests，不下载、不初始化模型。每个模块公开 `{available, code, reason, install_hint}` 的 typed status。缺 module/service 的业务 endpoint 返回 safe 503；foreign opaque id 仍返回 404。三个模块分别建立 service state，不能用一个全局 boolean。

**Packaging analog：** `backend/pyproject.toml:39-52` 已有 named extra；`Dockerfile:80-84` 已逐项把 `BACKEND_EXTRAS` 转成 `uv sync --extra`；`docker-compose.yml:8-9` 已透传。因此 Phase 05 只需新增 `shadow`/`forecast` extra 和 lock，通常无需第二 service/container。

### 14. Approved checkpoint catalog 与 Kronos adapter：没有现成实现

**适用：** `forecast/catalog.py`、`forecast/kronos_adapter.py`。  
**Closest structural analog：** optional host + strict deployment fixture validation；没有模型/样本轴代码可以复制。

规划必须显式创建以下 contract：

```text
catalog_id
kronos_source_revision
model_repo / model_revision / model_weight_sha256 / local_model_dir
tokenizer_repo / tokenizer_revision / tokenizer_weight_sha256 / local_tokenizer_dir
pairing / max_context / allowed_devices
```

**必须新增的不变量：**

- catalog 是 deployment-owned allowlist；model/tokenizer pairing 固定并在 startup lightweight probe 与 task 前复验。
- local dirs 必须落在 server-owned root，权重 digest 匹配；只允许 safetensors，禁止 `trust_remote_code` 和网络 fallback。
- adapter 针对固定 upstream commit，在 upstream `np.mean(axis=1)` 之前返回 `[sample_count,horizon,feature]`。
- 保存 seed/T/top_k/top_p/sample_count/lookback、source/model/tokenizer revisions+digests。
- P10/P50/P90 对每个 future session/feature 沿 path axis 计算；NaN/Inf/shape mismatch 硬失败。OHLC/volume 经济异常写 warning，不能静默 clamp。

### 15. Forecast calibration 追加原 identity

**适用：** `forecast/calibration.py`、`forecast/repository.py`。  
**Analog：** `backend/app/advanced/viewpoints.py:146-183,185-197`; repository `append_viewpoint_evaluation` lines 585-621。

```python
def record_evaluation(...):
    if status == "evaluated" and relative_return is None:
        raise ValueError(...)
    if status == "unevaluable" and not reason:
        raise ValueError(...)
    return repository.append_viewpoint_evaluation(...)

def _terminal_outcome(version, evaluation):
    """Project a persisted terminal fact without revisiting governed market inputs."""
```

**复用不变量：** 先查 canonical terminal outcome；已存在就投影 persisted fact，不重新读市场覆盖结果。Forecast outcome/calibration 是 `(forecast_id,horizon)` 唯一 append facts；记录 actual session/fingerprint、MAE、P10-P90 coverage、P10/P50/P90 pinball loss、metric schema/version。聚合必须显示 sample count 与 coverage period。

### 16. Safe API：先从 opaque id 解析 persisted object，再 scope

**适用：** 三个 domain API。  
**Analog：** `backend/app/advanced/api.py:69-135,162-216,192-205,535-559`; confirm/reject 参考 `analysis/api.py:205-230`。

```python
def _owned_viewpoint_version(request: Request, viewpoint_version_id: str):
    record = service.get_viewpoint_version(viewpoint_version_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=404, detail="advanced viewpoint not found")
    _require_instrument(request, record.get("instrument"))
    return record
```

```python
class SessionBoundJobStartRequest(BaseModel):
    """The browser selects only an allowlisted task type for an existing object."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task_type: Literal[...]
```

**复用不变量：**

- 不接受 browser-supplied owner/scope/principal/digest/fingerprint/status。
- opaque record id → repository lookup → persisted instrument/account → request scope；未知与 foreign 都是同一安全 404。
- module/service 不可用是 503；state/CAS/idempotency conflict 是 409；bounded validation 是 400/422；不回传 raw exception。
- upload API 限制 bytes/rows/columns/cell size，并返回 safe diagnostics，不返回 temp/raw path。

### 17. Deny-by-default public projection

**适用：** 三个 `projections.py`。  
**Analog：** `backend/app/advanced/projections.py:8-44,56-83,126-143,177-200`。

```python
def job(record: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": str(record["id"]),
        "subject": {"kind": ..., "key": ...},
        "status": str(record["status"]),
        "stage": str(record["stage"]),
        "stage_recorded_at": str(record["stage_recorded_at"]),
        "audit_reference": _optional_text(record.get("audit_reference")),
    }
```

```python
def experiment_run(record):
    """Return an allowlisted manifest that cannot disclose runner diagnostics."""
    return {
        "status": str(record["status"]),
        "parameters": _safe_mapping(...),
        "resource_limits": _safe_mapping(...),
        "metrics": _safe_mapping(...),
        "artifact_count": ...,
    }
```

**复用不变量：** 手写 allowlist，不做 `dict(record)` 直出；不暴露 raw trade/account secret、local path、policy、checkpoint local dir、worker traceback、uncommitted output。Forecast sampled paths 由受权 artifact endpoint/分页投影读取，不把全部路径塞进 job JSON/SSE。

### 18. Task/SSE：投影已提交状态、严格解析、对象局部 invalidation

**服务端 shared-stream analog：** `backend/app/services/quote_service.py:43-106,161-180`; `backend/app/api/intraday.py:158-211`。

```python
def push_advanced_progress(self, progress: dict[str, str]) -> None:
    """Queue only committed, allowlisted advanced state for the bound scope."""
    if scope is None or not scope.allows(...):
        return
    self._advanced_progress.append(progress)
    self._advanced_progress = self._advanced_progress[-max_count:]
```

```python
for progress in data["advanced_progress"]:
    yield {"event": "advanced_progress", "data": json.dumps(progress)}
```

**独立任务重连 analog：** `frontend/src/lib/backtestTask.ts:161-273,275-335,373-388`。

```typescript
function connectSSE(url: string): void {
  const es = new EventSource(url)
  es.addEventListener('done', event => {
    const payload: unknown = JSON.parse(event.data)
    if (!isStrategyBacktestResult(payload)) throw new Error('Malformed result')
    localStorage.removeItem(RECONNECT_KEY)
  })
  es.addEventListener('error', event => {
    // terminal error and transport disconnect are distinct
    // reconnect is visible and bounded
  })
}
```

**严格客户端投影 analog：** `frontend/src/lib/useQuoteStream.ts:10-39,160-177,240-243,288-301`。

```typescript
if (Object.keys(event).some(key => !ADVANCED_PROGRESS_KEYS.has(key))) return null
if (!SAFE_REFERENCE.test(String(event.job_id))) return null
...
qc.setQueryData(QK.advancedJob(subjectKind, subjectKey, event.job_id), ...)
qc.invalidateQueries({ queryKey: QK.advancedViewpoints(subjectKind, subjectKey) })
```

**复用不变量：** 只有已提交的 coarse job stage 进入 SSE；每订阅者独立有界队列并按 server scope 过滤；payload exact-key validation；完成后只 invalidate 对应 instrument/job/record keys。Forecast 大结果绝不通过 SSE，SSE 只传 job id/stage/timestamps/safe reason/artifact-ready reference。独立 forecast stream 必须支持刷新 reconnect、transport retry 上界和 terminal error 区分。

### 19. Typed API/query 与对象局部缓存

**Typed request analog：** `frontend/src/lib/api.ts:10-36,346-469,2617-2697`。  
**Query key analog：** `frontend/src/lib/queryKeys.ts:46-80`。

```typescript
advancedViewpoint:
  (subjectKind, subjectKey, viewpointId, version) =>
    ['advanced', 'viewpoint', subjectKind, subjectKey, viewpointId, version] as const
advancedJob:
  (subjectKind, subjectKey, jobId) =>
    ['advanced', 'job', subjectKind, subjectKey, jobId] as const
```

**复用不变量：**

- DTO 使用 literal unions 和 nullable fields 表达 terminal/unavailable/insufficient 状态；不新增 `any`。
- API path 中每个 id `encodeURIComponent`；multipart 交给统一 `request<T>` 自动省略 JSON content type。
- `shadow/*` keys 含 batch/evidence-set/candidate/evaluation id；`thesis/*` 含 instrument/thesis/version/condition；`forecast/*` 含 instrument/job/forecast/horizon/catalog。
- mutation success 只 invalidate 精确资源及直接派生历史；不能用全局 `['analysis']` 清空所有对象。

### 20. UI workspace：挂到现有对象，不创建第二 shell

**Backtest host analog：** `frontend/src/pages/Backtest.tsx:40-47,94-106`。  
**Analysis host analog：** `frontend/src/components/analysis/AnalysisWorkspace.tsx:16-30,45-64`; `frontend/src/pages/StockAnalysis.tsx:135-150`。  
**Version/pending UI analog：** `frontend/src/components/advanced/ViewpointPanel.tsx:25-79,81-111`。

```tsx
const serverSubject: AnalysisRequestSubject = {
  kind: subject.kind === 'stock' ? 'instrument' : 'account',
  key: subject.key,
}

const reportsQuery = useQuery({
  queryKey: QK.analysisReports(subject.kind, subject.key),
  queryFn: () => api.analysisReports(serverSubject),
  placeholderData: keepPreviousData,
})
```

**复用不变量：**

- Shadow 作为 Backtest workspace 的独立 panel/tab，不创建顶级 app shell，也不把 imported logs 变成 Portfolio account。
- Thesis 与 Forecast 挂在当前 stock `AnalysisWorkspace`；Forecast v1 不在 portfolio subject 渲染。
- 每个 panel 明确 loading/error/empty/stale/unavailable/terminal 状态；不可用模块不能遮断 v1 内容。
- immutable history 用版本/批次/record 时间线；pending conclusion 提供 confirm/reject，且 UI 文案说明自动化没有 authority。
- Forecast 主图可强调 close uncertainty band，但 sampled paths 必须可选择检查；显示 P10/P50/P90、horizon、as-of、checkpoint revisions/digests、warnings、later calibration。
- 表格小屏沿用 `overflow-x-auto` + scroll instruction；交互控件最小高度 44px。

### 21. 测试模式：先保护 observable invariant

**Backend analog：** `backend/tests/test_analysis_lifecycle.py:7-13,85-130,133-170,189-239`; `backend/tests/backtest/test_frozen_panel_artifact.py:34-75`。

```python
repository = AnalysisRepository(tmp_path / "operational.db")
repository.migrate()
...
assert repeated["id"] == proposal["id"]
assert repository.current_lifecycle_state(...) == "active"
assert repository.list_events(...) == []
```

```python
@pytest.mark.parametrize(
    "failure", ["absent", "partial", "tampered", "version", "scope", "checksum"]
)
def test_artifact_fails_closed(...):
    ...
    with pytest.raises(FrozenPanelArtifactError):
        store.load(...)
```

**Browser analog：** `frontend/e2e/phase4-advanced-capabilities.spec.ts:35-109`; real-host analog `phase4-advanced-capabilities.host.spec.ts:156-205`。

```typescript
await page.route('**/api/**', route => route.fulfill({ status: 500, ... }))
page.on('request', request => { /* collect unexpected external requests */ })
...
expect(externalRequests).toEqual([])
```

**复用不变量：**

- fixtures 用 `tmp_path` SQLite/server-owned artifact root 和 deterministic CSV/XLSX/Parquet/sample tensor；常规 suite 不联网、不下载 checkpoint。
- 除 happy path 外，必须直接尝试 SQL UPDATE/DELETE、tamper checksum、duplicate/restart、foreign opaque id、browser authority injection、worker timeout/shape error。
- 真实 host E2E 启动同一个 FastAPI container，覆盖 default/no-extra 和 enabled combinations；viewport matrix 至少 desktop/1024/375。
- no-live-execution 测试观察相关 repositories/collaborator call counts，而不是只检查 UI 文案。

## Shared Patterns

### Authentication / authorization

**Source：** `backend/app/main.py:642-673`, `analysis/api.py:58-74`, `advanced/api.py:96-112`。  
**Apply to：** 三域 API、SSE subscription、confirm/reject。

- authenticated middleware 写 `request.state.reviewer_principal`；浏览器不能提交 principal。
- list/create 先 scope instrument/account；opaque child id 先查 persisted parent，再 scope。
- foreign 与 missing 都给 safe 404，不泄漏 existence。

### Error handling

**Source：** `analysis/api.py:125-151`, `advanced/api.py:192-196`。

- 400/422：bounded validation；409：state changed/idempotency conflict；404：foreign/missing；503：module/service unavailable；502：外部 provider 临时故障。
- worker/model/parser exception 转成 stable code/reason，不返回 traceback、local paths 或 arbitrary exception text。

### Response safety

**Source：** `advanced/projections.py`。  
所有 API 使用 deny-by-default projection；尤其 raw trading log、account alias、checkpoint local dir、runner diagnostics 和 Parquet path 不得直出。

### Persistence split

- SQLite：batch/version/job/schedule/check/review/outcome/descriptor/provenance。
- Parquet/managed artifact：raw imported bytes、normalized/frozen panels、sampled paths、quantile series、large evaluation series。
- DuckDB/Polars：governed lake reads/transform；不新增新 market-data store。

## No Exact Analog Found

| 计划文件/能力 | 原因 | Planner 应采用的来源 |
|---|---|---|
| `forecast/calendar.py` / `GovernedTradingCalendar` | 当前仓库没有受治理 CN-A future-session dataset/service | `KlineRepository` 的 governed boundary + RESEARCH.md contract；绝不使用 `bdate_range` |
| `forecast/kronos_adapter.py` | 当前 application 无 Kronos；官方 public `predict()` 会平均 sample axis | pinned upstream commit + RESEARCH.md pre-mean tensor contract |
| `forecast/catalog.py` 的 checkpoint pairing/digest | 只有一般 optional dependency 和 host fixture 模式，没有 model catalog | lazy optional import + strict deployment manifest validation |
| `shadow/distillation.py` | Factor DSL/advanced gates 可复用，但没有 shallow-tree→JSON rules 实现 | RESEARCH.md sklearn bounded tree contract + Factor DSL allowlist pattern |
| Shadow immutable import batch | ext-data upload 是可变数据导入，不满足 D-02 | 只借 parsing/encoding seam；事实模型采用 artifact/repository immutable patterns |
| Thesis per-condition due cursor | APScheduler 存在，但没有 condition-level persisted cadence ledger | scheduler registration + guarded/monotonic SQLite cursor patterns |
| Forecast sampled-path UI | 有 ECharts 与版本表，但无多路径/quantile inspect UI | existing ECharts hook + ViewpointPanel states；结果合同以 RESEARCH.md 为准 |

## Files That Must Not Absorb Phase 05 Domain Logic

这些文件可以有**窄接线/迁移/统一入口修改**，但不得继续承载 Phase 05 领域实现：

| 文件 | 当前规模 | 允许的 Phase 05 修改 | 禁止扩展 |
|---|---:|---|---|
| `frontend/src/lib/api.ts` | 3075 行 | 最小统一 façade/共享 `request<T>` 接缝 | 不再堆三域 DTO、task parser、query logic；建议放 `phase5Api.ts` |
| `backend/app/tickflow/repository.py` | 1841 行 | 无，调用现有 `get_daily/get_daily_asset` | 不加 forecast calendar、thesis resolver、shadow feature/domain methods |
| `backend/app/services/quote_service.py` | 1490 行 | 若复用 root SSE，只加一个有界 safe channel 的最小 wiring | 不放 Forecast job state、artifact、model progress logic |
| `backend/app/jobs/daily_pipeline.py` | 1051 行 | lifespan 可调用新的 scanner register helper | 不放 per-condition due scan 或 forecast calibration 实现 |
| `backend/app/api/ext_data.py` | 889 行 | 无；只作为读取 analog | 不在这里加 Shadow routes/import semantics |
| `backend/app/backtest/strategy.py` | 838 行 | 无；通过窄 collaborator 调用 | 不加入 Shadow candidate schema、distiller 或 retention |
| `backend/app/operational/migrations.py` | 783 行 | 只追加一个/少量有内聚性的 Phase 05 migration SQL entry | 不放 repository/runtime logic；不要改旧 migration bytes |
| `backend/app/main.py` | 740 行 | 最小 `optional_modules.install(app, deps)`/router registration/scheduler lifecycle | 不直接 import torch/sklearn，不内联 catalog、calendar、scheduler、service 业务 |
| `backend/app/advanced/repository.py` | 656 行 | 无 | 不混入 shadow/theses/forecast tables 或 methods |
| `backend/app/advanced/api.py` | 583 行 | 无 | 不把 Phase 05 endpoints 加到 `/api/advanced` |
| `backend/app/analysis/repository.py` | 550 行 | 无 | Thesis 使用独立 repository/table，不与 signal lifecycle 混表 |
| `backend/app/advanced/governed_runner.py` | 490 行 | 无，复制/提取成熟的通用 process pattern到 Forecast 自有 runner | 不塞 torch/Kronos 专属配置与 artifact shape |
| `frontend/src/lib/backtestTask.ts` | 388 行 | 无 | 不复用同一个 global store 承载 Forecast；新建独立 typed task client |
| `frontend/src/pages/StockAnalysis.tsx` | 366 行 | 仅现有 `AnalysisWorkspace` 内挂载 | 不内联 Thesis/Forecast panel 逻辑 |
| `frontend/src/lib/useQuoteStream.ts` | 316 行 | 若选择 root SSE，仅新增 exact payload parser + object-local invalidation | 不存 Forecast result/path 或模块业务状态 |

## Planner Handoff: Recommended Ownership Boundaries

1. **Wave 0 共享合同：** strict DTO、SQLite migration/triggers、artifact descriptor、optional module status、governed trading calendar protocol、fixtures。
2. **Shadow slice：** upload/importer → immutable batch/artifact/repository → evidence set → distiller → governed IS/OOS collaborator → retention event → API/projection/UI。
3. **Thesis slice：** version/anchor/condition repository → governed evidence/evaluator → due scanner → pending/confirm/reject → API/projection/Analysis panel。
4. **Forecast slice：** approved catalog → governed input/calendar freezer → pre-mean Kronos adapter → bounded runner → immutable paths/quantiles → record/API/SSE/UI → maturity outcome/calibration。
5. **Shared host：** capability factory 返回各 module availability/services；`main.py` 只装配，不承载实现；所有组合保持 single-container。
6. **统一前端：** `QK` 保持对象局部 identity；API 继续统一调用体验但 Phase 05 DTO/方法应进入独立 typed module；workspace 只组合 panels。

## Metadata

- **分类文件/文件组：** 9 Shadow + 8 Thesis + 10 Forecast + 13 shared/frontend + 15 test targets。
- **精确/强 role-flow analog：** 42 个计划文件/文件组中 35 个有强 analog。
- **仅 partial 或无 exact analog：** Shadow importer/distiller、Thesis due ledger、Forecast catalog/calendar/Kronos adapter/sampled-path UI。
- **源文件精确读取：** `advanced/{schemas,repository,viewpoints,lifecycle-equivalent,governed_runner,api,projections,evolution}`、`analysis/{api,lifecycle,evidence_loader}`、`backtest/{frozen_panel,strategy}`、`tickflow/repository.py`、`operational/migrations.py`、scheduler/SSE/upload/client/query/workspace/test analogs。
- **搜索范围：** `backend/app/{shadow-analogs,analysis,advanced,backtest,research,tickflow,operational,api,services,jobs}`、`frontend/src/{lib,pages,components}`、`backend/tests`、`frontend/e2e`。
- **未执行：** formatter、linter、tests、project-wide command（遵守本次 assignment 约束）。
