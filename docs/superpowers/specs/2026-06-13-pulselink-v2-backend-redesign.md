# PulseLinkV2 Backend Redesign Spec

## 1. Purpose

PulseLinkV2 will be redesigned around a maintainable backend architecture and a stronger PDF/model analysis pipeline. The existing architecture document is treated as business context and requirement reference. Existing code is not a structural constraint.

The redesign focuses on two priorities:

- Rebuild the backend into clear API, application, domain, infrastructure, and worker layers.
- Rebuild the PDF and large-model analysis flow around traceable evidence, high-quality parsing, idempotent tasks, and explainable scoring.

## 2. Non-Goals

This spec does not cover:

- Rebuilding the mini program UI.
- Admin dashboards.
- Investor matching.
- Payment.
- Lead unlock flows.
- Multi-user collaboration.
- Human review backend.

The data model should still leave room for future human review through evidence, judgment, and task-event traceability.

## 3. Recommended Architecture

The backend should use a layered architecture:

```text
API / Worker entrypoints
  -> application services
  -> domain modules
  -> infrastructure adapters
```

API and Worker are separate processes, but they share the same application and domain logic.

```text
Mini Program / curl
        |
        v
API process
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

Worker flow:

```text
Redis MQ
  -> Worker
  -> AnalysisOrchestrator
  -> PDF Pipeline / Model Pipeline / Scoring / Report
```

Core principles:

- API handles fast operations only: authentication, validation, task creation, status query, report query.
- Worker handles slow operations: PDF parsing, rendering, visual understanding, LLM scoring, report assembly.
- Application services orchestrate use cases and are shared by API and Worker.
- Domain modules own business rules such as task state, scoring rubric, document quality, and evidence structure.
- Infrastructure adapters own external dependencies such as MySQL, Redis, COS, MiniMax, and PDF command-line tools.

## 4. Target Directory Structure

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

Dependency rules:

```text
api -> application
workers -> application
application -> domain + repositories + infrastructure clients
domain -> no FastAPI, SQLAlchemy, Redis, COS, or vendor SDK dependency
infrastructure -> may depend on external SDKs
```

## 5. API Contract

The core API surface should remain small and stable:

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

Task creation:

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

API behavior:

1. Validate the user.
2. Verify that the file belongs to the user.
3. Enforce idempotency with `user_id + idempotency_key`.
4. Create `analysis_task` and initial `task_steps`.
5. Publish `AnalyzeDocumentRequested` to MQ.
6. Return `task_id` immediately.

## 6. MQ and Async Processing

The system uses MQ for asynchronous triggering and MySQL for authoritative task state.

```text
API creates task in MySQL
  -> API publishes MQ message
  -> Worker consumes MQ message
  -> Worker loads task from MySQL
  -> Worker executes pipeline
  -> Worker writes progress/results to MySQL
  -> API reads status/report from MySQL
```

Recommended V1 queue implementation:

```text
Redis + RQ
```

Future queue options can include Celery, Dramatiq, or cloud MQ if task routing becomes more complex.

MQ message:

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

MQ should not carry PDF content, model prompts, full options, or long-lived state. Worker must treat MySQL as the source of truth.

## 7. Task State Machine

Task states:

```text
queued
running
completed
failed
cancelled
```

Step states:

```text
pending
running
succeeded
failed
skipped
retrying
```

Pipeline steps:

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

Worker idempotency rules:

- If task is `completed`, skip the whole job.
- If a step is `succeeded`, skip the step.
- If a step is `running` and `locked_until` has not expired, do not take ownership.
- If a step is `failed` and `attempt_count < max_attempts`, move to `retrying`.
- Every step writes progress, events, and failure reason.

## 8. PDF and Model Pipeline

The analysis pipeline has 8 stages:

```text
1. load_document
   - Download/read PDF from COS or local storage.
   - Validate sha256, file size, and page count.

2. parse_text_layout
   - Extract text per page.
   - Preserve page number, block order, layout hints, headings, and paragraphs.

3. detect_tables_and_figures
   - Detect table, chart, image, and low-confidence pages.
   - Produce table candidates and vision candidates.

4. render_candidate_pages
   - Render only pages that need visual analysis.
   - Save page-image artifacts.

5. vision_understanding
   - Call visual model for candidate pages.
   - Extract chart meaning, table structure, key numbers, units, and page summary.

6. build_evidence_units
   - Normalize text blocks, tables, and vision outputs into evidence units.
   - Every evidence unit must have page number, source type, source ref, and confidence.

7. score_and_judge
   - Score all 8 dimensions.
   - Produce facts, evidence references, deduction reasons, BP supplement suggestions, and investor due-diligence suggestions.

8. assemble_report
   - Assemble final report JSON.
   - Persist report and mark task completed.
```

The central pipeline concept is `EvidenceUnit`. Scoring must consume evidence units instead of raw PDF text.

Benefits:

- PDF parsing and scoring are decoupled.
- Every score can be traced back to page-level evidence.
- Human review and evidence highlighting can be added later.
- Model replacement becomes easier because scoring consumes a stable evidence contract.

## 9. Data Model

Main tables:

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

Important unique constraints:

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

Key models:

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

## 10. Scoring and Report Rules

The 8 scoring dimensions remain:

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

Scoring requirements:

- Each dimension must cite evidence units.
- Missing problem/pain description makes `problem_need_strength` fail its baseline.
- Missing market-size data makes `market_attractiveness` fail its baseline.
- Team facts must be parsed carefully because entity extraction errors directly affect scoring.
- Material completeness must appear before project potential in the report.
- Suggestions must be split into BP supplement suggestions and investor due-diligence suggestions.

Report requirements:

- Include material completeness.
- Include project potential score.
- Include 8 dimension cards.
- Include evidence pages.
- Include confidence level.
- Clearly mark low-confidence sections.

## 11. Model Integration

Use a model gateway abstraction:

```text
ModelGateway
  complete_json()
  understand_image_json()
```

Concrete adapters:

```text
MiniMaxClient
OpenAICompatibleClient
LocalFallbackClient
```

Local MiniMax configuration:

```text
LLM_API_BASE=https://api.minimax.chat/v1
LLM_MODEL=MiniMax-M3
VISION_API_BASE=https://api.minimax.chat/v1
VISION_MODEL=MiniMax-M3
```

Model rules:

- Model output must be JSON.
- JSON must pass schema validation before persistence.
- Invalid JSON triggers retry or fallback.
- All model calls must record artifact metadata.
- API keys must come from `.env` locally and secret management in production.

Model error categories:

```text
timeout
invalid_json
rate_limited
provider_error
low_confidence
```

Artifact metadata:

```text
model_name
prompt_version
request_summary
response_summary
latency_ms
error_code
```

## 12. Configuration

Configuration groups:

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

Production startup must fail fast if required settings are missing or unsafe.

## 13. Error Handling and Observability

User-facing errors:

```text
PDF_PARSE_FAILED
PDF_PARSE_LOW_CONFIDENCE
VISION_TIMEOUT
LLM_TIMEOUT
REPORT_NOT_READY
```

Log fields:

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

Task events:

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

Internal logs can include detailed stack traces. User responses must not expose stack traces.

## 14. Testing and Acceptance

Testing layers:

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

Sample PDF regression files:

```text
多线程DSP智能终端芯片_202603_副本.pdf
追光科技A+轮融资商业计划书260226_副本.pdf
```

Acceptance criteria:

- API can create and query tasks.
- API does not synchronously wait for PDF/model processing.
- MQ triggers Worker.
- Worker can resume or skip already completed work.
- PDF page count is correct for both sample PDFs.
- Text blocks and table structures are extracted.
- Vision candidates cover table/chart/image/low-confidence pages.
- Evidence units cover all 8 scoring dimensions where source material exists.
- Judgment cards reference evidence unit IDs.
- Reports include completeness, potential score, dimension scores, evidence pages, supplement suggestions, and due-diligence suggestions.
- Low-confidence sections are visibly marked.

## 15. Redesign Boundary

This is a large redesign. The implementation should not continue piling features into the current MVP shape.

Implementation guidance:

- Use current documentation as requirement source.
- Use current code only as behavior reference.
- Use existing API behavior and PDF regression outputs as acceptance references.
- Rebuild target modules according to the new architecture.
- Remove or archive old MVP code after the new flow passes acceptance.

Final target:

```text
clear API
reliable async task execution
high-quality PDF evidence
controlled model calls
explainable scoring report
production-ready deployment foundation
```
