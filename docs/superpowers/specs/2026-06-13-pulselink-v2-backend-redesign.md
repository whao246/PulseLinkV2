# PulseLinkV2 后端重构设计 Spec

## 1. 目标

PulseLinkV2 将围绕“可维护的后端架构”和“更扎实的 PDF/大模型分析 Pipeline”重新设计。现有架构文档只作为业务背景和需求参考，现有代码不作为目录结构、类设计或模块边界的约束。

本次重构聚焦两个优先级：

- 将后端重建为清晰的 API、application、domain、infrastructure、worker 分层结构。
- 将 PDF 和大模型分析链路重建为可追溯证据、高质量解析、任务幂等和可解释评分的核心 Pipeline。

## 2. 非目标

本 spec 不覆盖：

- 小程序 UI 重做。
- 后台管理系统。
- 投资机构匹配。
- 支付。
- 留资解锁。
- 多人协作。
- 人工复核后台。

但数据模型需要为未来人工复核预留基础：证据、判断卡和任务事件都必须可追溯。

## 3. 推荐架构

后端采用分层架构：

```text
API / Worker 入口
  -> application services
  -> domain modules
  -> infrastructure adapters
```

API 和 Worker 是两个独立进程，但共享同一套 application 和 domain 逻辑。

```text
小程序 / curl
        |
        v
API 进程
  - auth routes
  - file routes
  - task routes
  - report routes
        |
        v
Application Services
  - AuthService
  - FileService
  - TaskService
  - AnalysisOrchestrator
  - ReportService
        |
        v
Domain Modules
  - users
  - files
  - tasks
  - documents
  - analysis
  - scoring
  - reports
        |
        v
Infrastructure
  - MySQL repositories
  - Redis queue
  - COS storage
  - MiniMax/OpenAI-compatible clients
  - PDF tools
```

Worker 流程：

```text
Redis MQ
  -> Worker
  -> AnalysisOrchestrator
  -> PDF Pipeline / Model Pipeline / Scoring / Report
```

核心原则：

- API 只处理快操作：认证、参数校验、任务创建、状态查询、报告查询。
- Worker 处理慢操作：PDF 解析、页面渲染、视觉理解、LLM 评分、报告组装。
- Application services 编排业务用例，并被 API 和 Worker 复用。
- Domain modules 承载业务规则，例如任务状态机、评分规则、文档质量评估、证据结构。
- Infrastructure adapters 封装外部依赖，例如 MySQL、Redis、COS、MiniMax 和 PDF 命令行工具。

## 4. 目标目录结构

```text
backend/app/
  main.py

  api/
    deps.py
    errors.py
    routes/
      auth.py
      files.py
      tasks.py
      reports.py
      health.py
    schemas/
      auth.py
      files.py
      tasks.py
      reports.py
      common.py

  application/
    auth_service.py
    file_service.py
    task_service.py
    analysis_orchestrator.py
    report_service.py

  domain/
    users/
      entities.py
      errors.py
    files/
      entities.py
      policies.py
    tasks/
      entities.py
      state_machine.py
      events.py
    documents/
      entities.py
      quality.py
    analysis/
      evidence.py
      pipeline.py
      prompts/
    scoring/
      dimensions.py
      rubric.py
      judge.py
    reports/
      assembler.py

  infrastructure/
    config.py
    logging.py
    db/
      base.py
      session.py
      models/
        users.py
        files.py
        tasks.py
        documents.py
        analysis.py
        reports.py
      repositories/
        users.py
        files.py
        tasks.py
        documents.py
        evidence.py
        reports.py
    queue/
      publisher.py
      consumer.py
      messages.py
    storage/
      object_storage.py
      cos_storage.py
      local_storage.py
    model_clients/
      model_gateway.py
      openai_compatible_client.py
      minimax_client.py
      local_fallback_client.py
    pdf_tools/
      reader.py
      renderer.py
      table_detector.py

  workers/
    main.py
    jobs/
      analyze_document.py

  tests/
```

依赖规则：

```text
api -> application
workers -> application
application -> domain + repositories + infrastructure clients
domain -> 不依赖 FastAPI、SQLAlchemy、Redis、COS 或供应商 SDK
infrastructure -> 可以依赖外部 SDK
```

## 5. API 协议

核心 API 保持小而稳定：

```text
POST /api/auth/wechat-login
POST /api/uploads/pdf/presign
POST /api/files
POST /api/analysis-tasks
GET  /api/analysis-tasks/{task_id}
GET  /api/reports/{task_id}
GET  /api/reports
GET  /api/health
```

创建任务：

```http
POST /api/analysis-tasks
Authorization: Bearer <jwt>
Idempotency-Key: <uuid>
Content-Type: application/json
```

```json
{
  "file_id": "file_20260613_001",
  "options": {
    "enable_vision": true,
    "model_profile": "default"
  }
}
```

API 行为：

1. 校验用户身份。
2. 校验文件属于当前用户。
3. 使用 `user_id + idempotency_key` 做幂等控制。
4. 创建 `analysis_task` 和初始 `task_steps`。
5. 向 MQ 发布 `AnalyzeDocumentRequested` 消息。
6. 立即返回 `task_id`，不等待 PDF 或大模型处理完成。

## 6. MQ 与异步处理

系统使用 MQ 做异步触发，使用 MySQL 作为任务状态的事实来源。

```text
API 在 MySQL 创建任务
  -> API 发布 MQ 消息
  -> Worker 消费 MQ 消息
  -> Worker 从 MySQL 加载任务
  -> Worker 执行 Pipeline
  -> Worker 将进度和结果写回 MySQL
  -> API 从 MySQL 读取状态和报告
```

V1 推荐队列实现：

```text
Redis + RQ
```

如果后续任务路由、优先级、定时调度变复杂，可以再演进到 Celery、Dramatiq 或云消息队列。

MQ 消息：

```json
{
  "event_type": "AnalyzeDocumentRequested",
  "event_id": "evt_20260613_001",
  "task_id": "task_20260613_001",
  "file_id": "file_20260613_001",
  "user_id": "usr_20260613_001",
  "requested_at": "2026-06-13T10:00:00Z",
  "schema_version": 1
}
```

MQ 不承载 PDF 内容、模型 prompt、完整 options 或长期状态。Worker 必须以 MySQL 中的任务状态为准。

## 7. 任务状态机

任务主状态：

```text
queued
running
completed
failed
cancelled
```

步骤状态：

```text
pending
running
succeeded
failed
skipped
retrying
```

Pipeline 步骤：

```text
load_document
parse_text_layout
detect_tables_and_figures
render_candidate_pages
vision_understanding
build_evidence_units
score_and_judge
assemble_report
```

Worker 幂等规则：

- 如果任务已经是 `completed`，跳过整个 job。
- 如果某个 step 已经是 `succeeded`，跳过该 step。
- 如果某个 step 是 `running` 且 `locked_until` 未过期，不抢占执行权。
- 如果某个 step 是 `failed` 且 `attempt_count < max_attempts`，进入 `retrying`。
- 每个 step 都要写入进度、事件和失败原因。

## 8. PDF 与模型 Pipeline

分析 Pipeline 分为 8 个阶段：

```text
1. load_document
   - 从 COS 或本地存储下载/读取 PDF。
   - 校验 sha256、文件大小和页数。

2. parse_text_layout
   - 按页提取文本。
   - 保留页码、块顺序、版面提示、标题和段落结构。

3. detect_tables_and_figures
   - 检测表格、图表、图片页和低置信度页面。
   - 生成 table candidates 和 vision candidates。

4. render_candidate_pages
   - 只渲染需要视觉分析的页面。
   - 保存页面图片 artifact。

5. vision_understanding
   - 对候选页调用视觉模型。
   - 提取图表含义、表格结构、关键数字、单位和页面摘要。

6. build_evidence_units
   - 将文本块、表格和视觉结果统一归一化为 evidence units。
   - 每条 evidence unit 必须包含页码、来源类型、来源引用和置信度。

7. score_and_judge
   - 对 8 个维度评分。
   - 输出事实、证据引用、扣分原因、BP 补充建议和投资方尽调建议。

8. assemble_report
   - 组装最终报告 JSON。
   - 持久化报告，并将任务标记为 completed。
```

Pipeline 的中心概念是 `EvidenceUnit`。评分模块必须消费 evidence units，不能直接消费 PDF 原始文本。

好处：

- PDF 解析和评分解耦。
- 每个分数都能追溯到页级证据。
- 后续可以加入人工复核和证据高亮。
- 更换模型时，只要 evidence contract 稳定，评分层不需要大改。

## 9. 数据模型

主表：

```text
users
files
analysis_tasks
task_steps
task_events

document_pages
page_blocks
page_tables
page_artifacts

evidence_units
fact_cards
judgment_cards
score_results
reports
```

重要唯一约束：

```text
files: unique(user_id, sha256)
analysis_tasks: unique(user_id, idempotency_key)
task_steps: unique(task_id, step_name)
document_pages: unique(task_id, page_number)
evidence_units: unique(task_id, source_type, source_ref)
fact_cards: unique(task_id, dimension_key)
judgment_cards: unique(task_id, dimension_key)
score_results: unique(task_id)
reports: unique(task_id)
```

关键模型：

```text
DocumentPage
  page_number
  raw_text
  clean_text
  parse_quality
  needs_vision
  confidence_score

EvidenceUnit
  task_id
  page_number
  source_type: text/table/vision
  source_ref
  category
  content
  structured_data_json
  confidence_score

JudgmentCard
  task_id
  dimension_key
  dimension_name
  score
  max_score
  evidence_unit_ids
  deduction_reason
  bp_supplement_suggestions_json
  investor_due_diligence_suggestions_json
```

## 10. 评分与报告规则

8 个评分维度保持不变：

```text
problem_need_strength: 10
market_attractiveness: 10
product_solution: 12.5
business_model_unit_economics: 12.5
team_fit: 15
commercialization_progress: 15
competition_barriers: 15
financing_logic_use_of_funds: 10
```

评分要求：

- 每个维度必须引用 evidence units。
- 缺少问题/痛点描述时，`problem_need_strength` 不能达到及格基线。
- 缺少市场规模数据时，`market_attractiveness` 不能达到及格基线。
- 团队事实必须谨慎解析，因为实体抽取错误会直接影响评分。
- 材料完整度必须在项目潜力之前呈现。
- 建议必须拆成 BP 补充建议和投资方尽调建议两类。

报告要求：

- 包含材料完整度。
- 包含项目潜力评分。
- 包含 8 个维度卡片。
- 包含证据页。
- 包含置信度等级。
- 对低置信度部分做明确标记。

## 11. 模型接入

使用统一模型网关抽象：

```text
ModelGateway
  complete_json()
  understand_image_json()
```

具体 adapter：

```text
MiniMaxClient
OpenAICompatibleClient
LocalFallbackClient
```

本地 MiniMax 配置：

```text
LLM_API_BASE=https://api.minimax.chat/v1
LLM_MODEL=MiniMax-M3
VISION_API_BASE=https://api.minimax.chat/v1
VISION_MODEL=MiniMax-M3
```

模型规则：

- 模型输出必须是 JSON。
- JSON 必须通过 schema 校验后才能持久化。
- 非法 JSON 触发重试或 fallback。
- 所有模型调用都必须记录 artifact 元数据。
- 本地 API key 来自 `.env`，生产 API key 来自密钥管理或云平台环境变量。

模型错误分类：

```text
timeout
invalid_json
rate_limited
provider_error
low_confidence
```

Artifact 元数据：

```text
model_name
prompt_version
request_summary
response_summary
latency_ms
error_code
```

## 12. 配置

配置分组：

```text
App:
  APP_ENV
  JWT_SECRET

Database:
  DATABASE_URL

Queue:
  REDIS_URL
  QUEUE_NAME

Storage:
  COS_REGION
  COS_BUCKET
  COS_ENDPOINT
  COS_SECRET_ID
  COS_SECRET_KEY

Models:
  LLM_API_BASE
  LLM_API_KEY
  LLM_MODEL
  VISION_API_BASE
  VISION_API_KEY
  VISION_MODEL

Pipeline:
  PDF_MAX_PAGES
  PDF_MAX_SIZE_MB
  STEP_TIMEOUT_SECONDS
  MAX_RETRY_ATTEMPTS
  ENABLE_VISION
```

生产启动时必须做配置校验。如果关键配置缺失或存在不安全默认值，服务应该启动失败，而不是进入半可用状态。

## 13. 错误处理与可观测性

用户可见错误：

```text
PDF_PARSE_FAILED
PDF_PARSE_LOW_CONFIDENCE
VISION_TIMEOUT
LLM_TIMEOUT
REPORT_NOT_READY
```

日志字段：

```text
request_id
task_id
file_id
user_id
step_name
event_type
duration_ms
model_name
error_code
```

任务事件：

```text
task_created
pdf_loaded
text_parsing_started
vision_understanding_started
scoring_started
report_assembling_started
task_completed
task_failed
```

内部日志可以包含详细堆栈。用户响应不能暴露堆栈信息。

## 14. 测试与验收

测试分层：

```text
1. Unit tests
   - task state machine
   - scoring rubric
   - evidence builder
   - model response parser
   - PDF quality rules

2. Integration tests
   - repositories
   - file registration idempotency
   - task creation idempotency
   - queue publish/consume
   - storage resolver

3. Pipeline tests
   - no-model fallback
   - model mock JSON
   - invalid JSON retry
   - timeout retry
   - duplicate task skip

4. End-to-end tests
   - API login -> file -> task -> worker -> report
   - two sample PDFs regression
```

样例 PDF 回归文件：

```text
多线程DSP智能终端芯片_202603_副本.pdf
追光科技A+轮融资商业计划书260226_副本.pdf
```

验收标准：

- API 可以创建任务和查询任务。
- API 不同步等待 PDF/模型处理完成。
- MQ 可以触发 Worker。
- Worker 可以恢复或跳过已经完成的工作。
- 两份样例 PDF 的页数正确。
- 文本 blocks 和表格结构可以被抽取。
- Vision candidates 覆盖表格、图表、图片和低置信度页面。
- 在源材料存在的前提下，evidence units 可以覆盖全部 8 个评分维度。
- Judgment cards 引用 evidence unit IDs。
- 报告包含材料完整度、项目潜力评分、维度评分、证据页、补充建议和尽调建议。
- 低置信度部分有明确标记。

## 15. 重构边界

这是一次大重构。实现时不应继续在当前 MVP 形态上堆功能。

实施指导：

- 使用当前文档作为需求来源。
- 使用当前代码作为行为参考，而不是结构约束。
- 使用现有 API 行为和 PDF 回归输出作为验收参考。
- 按新架构重建目标模块。
- 新流程通过验收后，旧 MVP 代码可以删除或归档。

最终目标：

```text
清晰 API
可靠异步任务执行
高质量 PDF evidence
可控模型调用
可解释评分报告
生产可部署基础
```
