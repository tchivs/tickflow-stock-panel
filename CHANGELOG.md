# Changelog

All notable user-facing changes are recorded here. This project follows semantic versioning for AthenaQuant releases.

## Phase 55: WebSocket 全量迁移

- 从 SSE 单向轮询升级为 WebSocket 双向通信; 新增 /ws/stream 端点 + ConnectionManager + 频道订阅 + seq 环形缓冲恢复 + 应用层心跳 + 指数退避重连
- 前端全局单连接 (useWsStream) 替代 7 处 EventSource + 5 处 ndjson + 1 处 fetch SSE
- 删除 sse-starlette 依赖 + 全部 SSE/ndjson 端点 (D-03 无回退路径)
- 连接状态三态 UI (connected/reconnecting/disconnected)
- 连接生命周期审计 (scope=ws)
- 任务启动改为 POST /strategy/start、/optimize/start、/walkforward/start (返回 job_key, 进度走 WS)

## 1.0.0 - 2026-07-27

- Established AthenaQuant as the self-hosted quantitative research project identity.
- Added governed portfolio operations, decision playbooks, factor and strategy research, evidence-first analysis, and advanced research workflows.
- Added optional Shadow Account, versioned theses, and local-only Kronos forecast support.
- Added reproducibility and safety controls for research artifacts, optional model provisioning, recovery, and bounded worker execution.
- Preserved upstream attribution and a documented synchronization path to `tickflow-stock-panel`.
