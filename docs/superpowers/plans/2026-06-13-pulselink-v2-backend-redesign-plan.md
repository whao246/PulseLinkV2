# PulseLinkV2 后端重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按中文 spec 重建 PulseLinkV2 后端，让 API/Worker 分层清晰、任务异步可靠、PDF 分析以 EvidenceUnit 为中心、评分报告可追溯。

**Architecture:** 采用 `api -> application -> domain -> infrastructure` 分层。API 和 Worker 只作为入口；业务编排在 application；任务状态机、证据、评分规则在 domain；MySQL、Redis、COS、MiniMax、PDF 工具在 infrastructure。分析任务由 API 落库并发布 MQ 消息，Worker 消费消息后执行 Pipeline，并以 MySQL 状态机为事实来源。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Redis/RQ, MySQL, Tencent COS, MiniMax OpenAI-compatible API, pytest, Docker Compose.

---

## Scope Check

该 spec 覆盖后端重构、PDF/模型 Pipeline、MQ、数据模型、API、Worker 和测试验收。它们共同组成一个后端核心系统，不能完全独立交付，但可以按任务阶段增量实现。每个任务都应保持测试可运行，并在任务结束提交一次。

## Target File Map

### Create

- `backend/app/api/routes/auth.py`：微信登录和本地测试登录 route。
- `backend/app/api/routes/files.py`：上传预签名和文件登记 route。
- `backend/app/api/routes/tasks.py`：创建任务和查询任务 route。
- `backend/app/api/routes/reports.py`：报告详情和报告列表 route。
- `backend/app/api/routes/health.py`：健康检查 route。
- `backend/app/api/schemas/common.py`：统一响应、错误响应、分页 schema。
- `backend/app/api/schemas/auth.py`：登录请求/响应 schema。
- `backend/app/api/schemas/files.py`：上传签名、文件登记 schema。
- `backend/app/api/schemas/tasks.py`：任务创建、任务状态 schema。
- `backend/app/api/schemas/reports.py`：报告 schema。
- `backend/app/application/auth_service.py`：登录用例。
- `backend/app/application/file_service.py`：文件上传签名和登记用例。
- `backend/app/application/task_service.py`：创建任务、查询任务、幂等用例。
- `backend/app/application/analysis_orchestrator.py`：Worker 调用的分析编排器。
- `backend/app/application/report_service.py`：报告查询用例。
- `backend/app/domain/tasks/state_machine.py`：任务和 step 状态机。
- `backend/app/domain/tasks/events.py`：任务事件名和事件构造。
- `backend/app/domain/analysis/evidence.py`：EvidenceUnit、EvidenceCategory、EvidenceSourceType。
- `backend/app/domain/analysis/pipeline.py`：Pipeline step 名称、step 输入输出协议。
- `backend/app/domain/documents/entities.py`：DocumentPage、PageBlock、PageTable、PageArtifact domain entity。
- `backend/app/domain/documents/quality.py`：PDF 页面质量评估规则。
- `backend/app/domain/scoring/dimensions.py`：八个评分维度。
- `backend/app/domain/scoring/rubric.py`：评分基线规则。
- `backend/app/domain/scoring/judge.py`：JudgmentCard domain entity 和评分输入输出。
- `backend/app/domain/reports/assembler.py`：报告组装 domain 服务。
- `backend/app/infrastructure/config.py`：新配置入口。
- `backend/app/infrastructure/logging.py`：结构化日志字段工具。
- `backend/app/infrastructure/db/models/*.py`：拆分后的 SQLAlchemy models。
- `backend/app/infrastructure/db/repositories/*.py`：拆分后的 repositories。
- `backend/app/infrastructure/queue/messages.py`：MQ 消息 schema。
- `backend/app/infrastructure/queue/publisher.py`：发布 `AnalyzeDocumentRequested`。
- `backend/app/infrastructure/queue/consumer.py`：Worker 消费工具。
- `backend/app/infrastructure/storage/object_storage.py`：对象存储接口。
- `backend/app/infrastructure/storage/local_storage.py`：本地对象存储实现。
- `backend/app/infrastructure/storage/cos_storage.py`：COS 实现。
- `backend/app/infrastructure/model_clients/model_gateway.py`：统一模型网关协议。
- `backend/app/infrastructure/model_clients/openai_compatible_client.py`：OpenAI-compatible JSON client。
- `backend/app/infrastructure/model_clients/minimax_client.py`：MiniMax adapter。
- `backend/app/infrastructure/model_clients/local_fallback_client.py`：无模型 fallback。
- `backend/app/infrastructure/pdf_tools/reader.py`：PDF 文本读取。
- `backend/app/infrastructure/pdf_tools/renderer.py`：候选页渲染。
- `backend/app/infrastructure/pdf_tools/table_detector.py`：表格/图表候选检测。
- `backend/app/workers/main.py`：Worker 入口。
- `backend/app/workers/jobs/analyze_document.py`：分析任务 job。

### Modify

- `backend/app/main.py`：改为 app factory + 注册拆分 route。
- `backend/app/api/deps.py`：保留鉴权依赖，接入新 service/repository。
- `backend/migrations/versions/0001_initial_schema.py`：替换/新增符合新模型的显式 migration。
- `backend/Dockerfile`：确认 worker/api 入口可用。
- `docker-compose.yml`：确认 api/worker 命令、env、healthcheck 与新入口一致。
- `.env.example`：补充 Pipeline 配置项。
- `.vscode/launch.json`：提供本机 Python API/Worker 单步调试配置。

### Optional Create

- `docker-compose.debug.yml`：提供容器内 debugpy attach 调试配置。
- `docs/deployment/tencent-cloud.md`：腾讯云部署操作说明。

### Test

- `backend/tests/domain/test_task_state_machine.py`
- `backend/tests/domain/test_evidence.py`
- `backend/tests/domain/test_scoring_rubric.py`
- `backend/tests/domain/test_document_quality.py`
- `backend/tests/infrastructure/test_queue_messages.py`
- `backend/tests/infrastructure/test_model_gateway.py`
- `backend/tests/infrastructure/test_storage.py`
- `backend/tests/application/test_task_service.py`
- `backend/tests/application/test_analysis_orchestrator.py`
- `backend/tests/api/test_auth_routes.py`
- `backend/tests/api/test_file_routes.py`
- `backend/tests/api/test_task_routes.py`
- `backend/tests/api/test_report_routes.py`
- `backend/tests/e2e/test_analysis_flow.py`
- `backend/tests/e2e/test_sample_pdf_regression.py`

---

## Task 1: 建立新分层骨架和 App Factory

**Files:**
- Create: package `__init__.py` files under `backend/app/api/routes`, `backend/app/api/schemas`, `backend/app/application`, `backend/app/domain/*`, `backend/app/infrastructure/*`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_app_factory.py`

- [ ] **Step 1: Write the failing app factory test**

Add to `backend/tests/test_app_factory.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_registers_health_route():
    app = create_app(database_url="sqlite:///:memory:", run_analysis_inline=True)
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
.venv/bin/pytest backend/tests/test_app_factory.py::test_create_app_registers_health_route -q
```

Expected: PASS before refactor or FAIL after route extraction starts. If it passes, keep it as a regression guard.

- [ ] **Step 3: Create route module skeleton**

Create `backend/app/api/routes/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.responses import ok


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    return ok({"status": "ok", "version": "0.1.0"}, request)
```

Create empty `__init__.py` files for new packages.

- [ ] **Step 4: Modify app factory to include health router**

In `backend/app/main.py`, import and register:

```python
from app.api.routes import health

app.include_router(health.router)
```

Keep old route behavior until all route modules are migrated.

- [ ] **Step 5: Run test**

Run:

```bash
.venv/bin/pytest backend/tests/test_app_factory.py::test_create_app_registers_health_route -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_app_factory.py
git commit -m "refactor: introduce layered app route skeleton"
```

---

## Task 2: 实现任务状态机 Domain

**Files:**
- Create: `backend/app/domain/tasks/state_machine.py`
- Create: `backend/tests/domain/test_task_state_machine.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from app.domain.tasks.state_machine import (
    StepStatus,
    TaskStatus,
    can_retry_step,
    can_start_step,
    transition_task,
)


def test_task_can_move_from_queued_to_running():
    assert transition_task(TaskStatus.QUEUED, TaskStatus.RUNNING) == TaskStatus.RUNNING


def test_task_cannot_move_from_completed_to_running():
    with pytest.raises(ValueError, match="invalid task transition"):
        transition_task(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_step_can_start_when_pending():
    assert can_start_step(StepStatus.PENDING, locked_until_expired=True)


def test_step_cannot_start_when_running_lock_not_expired():
    assert not can_start_step(StepStatus.RUNNING, locked_until_expired=False)


def test_failed_step_can_retry_when_attempts_remain():
    assert can_retry_step(StepStatus.FAILED, attempt_count=1, max_attempts=3)
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/domain/test_task_state_machine.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement state machine**

```python
from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


ALLOWED_TASK_TRANSITIONS = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def transition_task(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    if target not in ALLOWED_TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current} -> {target}")
    return target


def can_start_step(status: StepStatus, *, locked_until_expired: bool) -> bool:
    if status in {StepStatus.PENDING, StepStatus.RETRYING}:
        return True
    if status == StepStatus.RUNNING:
        return locked_until_expired
    return False


def can_retry_step(status: StepStatus, *, attempt_count: int, max_attempts: int) -> bool:
    return status == StepStatus.FAILED and attempt_count < max_attempts
```

- [ ] **Step 4: Run test**

```bash
.venv/bin/pytest backend/tests/domain/test_task_state_machine.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/tasks/state_machine.py backend/tests/domain/test_task_state_machine.py
git commit -m "feat: add task state machine domain"
```

---

## Task 3: 实现 EvidenceUnit Domain

**Files:**
- Create: `backend/app/domain/analysis/evidence.py`
- Create: `backend/tests/domain/test_evidence.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from app.domain.analysis.evidence import EvidenceSourceType, EvidenceUnit


def test_evidence_unit_requires_page_number():
    unit = EvidenceUnit(
        id="ev_1",
        task_id="task_1",
        page_number=3,
        source_type=EvidenceSourceType.TEXT,
        source_ref="page_3:block_1",
        category="market",
        content="市场规模达到 100 亿元",
        structured_data={},
        confidence_score=0.8,
    )

    assert unit.page_number == 3
    assert unit.source_type == EvidenceSourceType.TEXT


def test_evidence_unit_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence_score"):
        EvidenceUnit(
            id="ev_1",
            task_id="task_1",
            page_number=1,
            source_type=EvidenceSourceType.VISION,
            source_ref="page_1:vision",
            category="team",
            content="团队介绍",
            structured_data={},
            confidence_score=1.5,
        )
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/domain/test_evidence.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement evidence domain**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EvidenceSourceType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    VISION = "vision"


@dataclass(frozen=True)
class EvidenceUnit:
    id: str
    task_id: str
    page_number: int
    source_type: EvidenceSourceType
    source_ref: str
    category: str
    content: str
    structured_data: dict[str, Any]
    confidence_score: float

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be >= 1")
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("confidence_score must be between 0 and 1")
        if not self.content.strip():
            raise ValueError("content is required")
```

- [ ] **Step 4: Run test**

```bash
.venv/bin/pytest backend/tests/domain/test_evidence.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/analysis/evidence.py backend/tests/domain/test_evidence.py
git commit -m "feat: add evidence unit domain"
```

---

## Task 4: 实现评分维度和 Rubric 基线规则

**Files:**
- Create: `backend/app/domain/scoring/dimensions.py`
- Create: `backend/app/domain/scoring/rubric.py`
- Test: `backend/tests/domain/test_scoring_rubric.py`

- [ ] **Step 1: Write failing tests**

```python
from app.domain.scoring.dimensions import SCORING_DIMENSIONS
from app.domain.scoring.rubric import baseline_score_allowed


def test_scoring_dimensions_sum_to_100():
    assert sum(d.max_score for d in SCORING_DIMENSIONS) == 100


def test_problem_dimension_fails_baseline_without_problem_evidence():
    allowed = baseline_score_allowed(
        dimension_key="problem_need_strength",
        evidence_categories={"market", "team"},
    )

    assert allowed is False


def test_market_dimension_fails_baseline_without_market_evidence():
    allowed = baseline_score_allowed(
        dimension_key="market_attractiveness",
        evidence_categories={"problem", "team"},
    )

    assert allowed is False
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/domain/test_scoring_rubric.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement dimensions**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringDimension:
    key: str
    name: str
    max_score: float
    required_category: str | None = None


SCORING_DIMENSIONS = [
    ScoringDimension("problem_need_strength", "问题与需求强度", 10, "problem"),
    ScoringDimension("market_attractiveness", "市场空间与赛道吸引力", 10, "market"),
    ScoringDimension("product_solution", "产品与解决方案", 12.5, "product"),
    ScoringDimension("business_model_unit_economics", "商业模式与单位经济", 12.5, "business_model"),
    ScoringDimension("team_fit", "团队匹配度", 15, "team"),
    ScoringDimension("commercialization_progress", "商业化进展", 15, "commercialization"),
    ScoringDimension("competition_barriers", "竞争格局与壁垒", 15, "competition"),
    ScoringDimension("financing_logic_use_of_funds", "融资逻辑与资金用途", 10, "funding"),
]
```

- [ ] **Step 4: Implement rubric**

```python
from __future__ import annotations

from app.domain.scoring.dimensions import SCORING_DIMENSIONS


DIMENSION_BY_KEY = {dimension.key: dimension for dimension in SCORING_DIMENSIONS}


def baseline_score_allowed(*, dimension_key: str, evidence_categories: set[str]) -> bool:
    dimension = DIMENSION_BY_KEY[dimension_key]
    if dimension.required_category is None:
        return True
    return dimension.required_category in evidence_categories
```

- [ ] **Step 5: Run test**

```bash
.venv/bin/pytest backend/tests/domain/test_scoring_rubric.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/scoring backend/tests/domain/test_scoring_rubric.py
git commit -m "feat: add scoring rubric domain"
```

---

## Task 5: 实现 MQ 消息协议和发布器

**Files:**
- Create: `backend/app/infrastructure/queue/messages.py`
- Create: `backend/app/infrastructure/queue/publisher.py`
- Test: `backend/tests/infrastructure/test_queue_messages.py`

- [ ] **Step 1: Write failing tests**

```python
from app.infrastructure.queue.messages import AnalyzeDocumentRequested
from app.infrastructure.queue.publisher import QueuePublisher


def test_analyze_document_message_serializes_schema_version():
    message = AnalyzeDocumentRequested(
        event_id="evt_1",
        task_id="task_1",
        file_id="file_1",
        user_id="usr_1",
        requested_at="2026-06-13T10:00:00Z",
    )

    payload = message.to_dict()

    assert payload["event_type"] == "AnalyzeDocumentRequested"
    assert payload["schema_version"] == 1


def test_queue_publisher_enqueues_task_id():
    captured = {}

    class FakeQueue:
        def enqueue(self, func_path, **kwargs):
            captured["func_path"] = func_path
            captured["kwargs"] = kwargs

    publisher = QueuePublisher(queue=FakeQueue())
    publisher.publish_analyze_document(task_id="task_1")

    assert captured["kwargs"]["task_id"] == "task_1"
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/infrastructure/test_queue_messages.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement messages**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AnalyzeDocumentRequested:
    event_id: str
    task_id: str
    file_id: str
    user_id: str
    requested_at: str
    event_type: str = "AnalyzeDocumentRequested"
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

- [ ] **Step 4: Implement publisher**

```python
from __future__ import annotations


class QueuePublisher:
    def __init__(self, *, queue):
        self.queue = queue

    def publish_analyze_document(self, *, task_id: str) -> None:
        self.queue.enqueue(
            "app.workers.jobs.analyze_document.run",
            task_id=task_id,
        )
```

- [ ] **Step 5: Run test**

```bash
.venv/bin/pytest backend/tests/infrastructure/test_queue_messages.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/queue backend/tests/infrastructure/test_queue_messages.py
git commit -m "feat: add queue message protocol"
```

---

## Task 6: 实现模型网关和 MiniMax/OpenAI-compatible Client

**Files:**
- Create: `backend/app/infrastructure/model_clients/model_gateway.py`
- Create: `backend/app/infrastructure/model_clients/openai_compatible_client.py`
- Create: `backend/app/infrastructure/model_clients/minimax_client.py`
- Create: `backend/app/infrastructure/model_clients/local_fallback_client.py`
- Test: `backend/tests/infrastructure/test_model_gateway.py`

- [ ] **Step 1: Write failing tests**

```python
import httpx
import pytest

from app.infrastructure.model_clients.local_fallback_client import LocalFallbackClient
from app.infrastructure.model_clients.openai_compatible_client import OpenAICompatibleClient


def test_local_fallback_returns_json_object():
    client = LocalFallbackClient()

    result = client.complete_json(messages=[{"role": "user", "content": "hi"}])

    assert result["fallback"] is True


def test_openai_compatible_client_parses_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.complete_json(messages=[{"role": "user", "content": "hi"}]) == {"ok": True}


def test_openai_compatible_client_rejects_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://models.example.com/v1",
        api_key="key",
        model="MiniMax-M3",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ValueError, match="invalid model JSON"):
        client.complete_json(messages=[{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/infrastructure/test_model_gateway.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement model gateway protocol**

```python
from __future__ import annotations

from typing import Any, Protocol


class ModelGateway(Protocol):
    def complete_json(self, *, messages: list[dict[str, str]], temperature: float = 0) -> dict[str, Any]:
        raise NotImplementedError

    def understand_image_json(self, *, prompt: str, image_bytes: bytes) -> dict[str, Any]:
        raise NotImplementedError
```

- [ ] **Step 4: Implement OpenAI-compatible client**

```python
from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds

    def complete_json(self, *, messages: list[dict[str, str]], temperature: float = 0) -> dict[str, Any]:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid model JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("invalid model JSON")
        return parsed

    def understand_image_json(self, *, prompt: str, image_bytes: bytes) -> dict[str, Any]:
        raise NotImplementedError("vision request body will be implemented in the pipeline task")
```

- [ ] **Step 5: Implement MiniMax and fallback clients**

```python
from __future__ import annotations

from app.infrastructure.model_clients.openai_compatible_client import OpenAICompatibleClient


class MiniMaxClient(OpenAICompatibleClient):
    pass
```

```python
from __future__ import annotations

from typing import Any


class LocalFallbackClient:
    def complete_json(self, *, messages: list[dict[str, str]], temperature: float = 0) -> dict[str, Any]:
        return {"fallback": True, "message_count": len(messages)}

    def understand_image_json(self, *, prompt: str, image_bytes: bytes) -> dict[str, Any]:
        return {"fallback": True, "prompt": prompt, "image_size": len(image_bytes)}
```

- [ ] **Step 6: Run test**

```bash
.venv/bin/pytest backend/tests/infrastructure/test_model_gateway.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/model_clients backend/tests/infrastructure/test_model_gateway.py
git commit -m "feat: add model gateway clients"
```

---

## Task 7: 重建 SQLAlchemy Models 和 Alembic Migration

**Files:**
- Create/Modify: `backend/app/infrastructure/db/models/*.py`
- Modify: `backend/app/infrastructure/db/base.py`
- Modify: `backend/migrations/versions/0001_initial_schema.py`
- Test: `backend/tests/test_migrations.py`, `backend/tests/test_db_models.py`

- [ ] **Step 1: Write failing schema tests**

Add assertions to `backend/tests/test_db_models.py`:

```python
from app.infrastructure.db.base import Base


def test_new_schema_contains_evidence_units():
    assert "evidence_units" in Base.metadata.tables


def test_new_schema_contains_page_artifacts():
    assert "page_artifacts" in Base.metadata.tables


def test_evidence_units_have_source_ref_column():
    table = Base.metadata.tables["evidence_units"]

    assert "source_ref" in table.columns
```

- [ ] **Step 2: Run tests to verify failure**

```bash
.venv/bin/pytest backend/tests/test_db_models.py -q
```

Expected: FAIL until new models are wired to `Base`.

- [ ] **Step 3: Implement model modules**

Create models with these table names and constraints:

```python
UniqueConstraint("user_id", "sha256", name="uq_files_user_sha256")
UniqueConstraint("user_id", "idempotency_key", name="uq_tasks_user_idempotency")
UniqueConstraint("task_id", "step_name", name="uq_task_steps_task_step")
UniqueConstraint("task_id", "page_number", name="uq_document_pages_task_page")
UniqueConstraint("task_id", "source_type", "source_ref", name="uq_evidence_units_source")
UniqueConstraint("task_id", "dimension_key", name="uq_fact_cards_task_dimension")
UniqueConstraint("task_id", "dimension_key", name="uq_judgment_cards_task_dimension")
UniqueConstraint("task_id", name="uq_score_results_task")
UniqueConstraint("task_id", name="uq_reports_task")
```

Use SQLAlchemy types:

```python
String
Text
Integer
Float
Boolean
DateTime
JSON
ForeignKey
```

- [ ] **Step 4: Update Alembic migration explicitly**

Update `backend/migrations/versions/0001_initial_schema.py` with explicit Alembic `op.create_table` calls for all new tables. Do not import `Base.metadata` in migration.

- [ ] **Step 5: Run migration and model tests**

```bash
.venv/bin/pytest backend/tests/test_db_models.py backend/tests/test_migrations.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/infrastructure/db backend/migrations/versions/0001_initial_schema.py backend/tests/test_db_models.py backend/tests/test_migrations.py
git commit -m "feat: add redesigned database schema"
```

---

## Task 8: 实现 Repositories 和 TaskService 幂等

**Files:**
- Create: `backend/app/infrastructure/db/repositories/files.py`
- Create: `backend/app/infrastructure/db/repositories/tasks.py`
- Create: `backend/app/application/task_service.py`
- Test: `backend/tests/application/test_task_service.py`

- [ ] **Step 1: Write failing tests**

```python
from app.application.task_service import TaskService


def test_task_service_returns_same_task_for_same_idempotency_key(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)
    user_id = "usr_1"
    file_id = "file_1"

    first = service.create_task(user_id=user_id, file_id=file_id, idempotency_key="idem_1", options={})
    second = service.create_task(user_id=user_id, file_id=file_id, idempotency_key="idem_1", options={})

    assert first.id == second.id


def test_task_service_initializes_pipeline_steps(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)

    task = service.create_task(user_id="usr_1", file_id="file_1", idempotency_key="idem_2", options={})
    steps = service.list_steps(task.id)

    assert [step.step_name for step in steps] == [
        "load_document",
        "parse_text_layout",
        "detect_tables_and_figures",
        "render_candidate_pages",
        "vision_understanding",
        "build_evidence_units",
        "score_and_judge",
        "assemble_report",
    ]
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/application/test_task_service.py -q
```

Expected: FAIL until service exists.

- [ ] **Step 3: Implement TaskService**

Implement methods:

```python
from __future__ import annotations

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.domain.tasks.state_machine import StepStatus, TaskStatus
from app.infrastructure.db.repositories.tasks import TaskRepository


class TaskService:
    def __init__(self, *, db_session, queue_publisher):
        self.db_session = db_session
        self.queue_publisher = queue_publisher
        self.task_repository = TaskRepository(db_session)

    def create_task(self, *, user_id: str, file_id: str, idempotency_key: str, options: dict):
        existing = self.task_repository.get_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if existing:
            return existing

        task = self.task_repository.create_task(
            user_id=user_id,
            file_id=file_id,
            idempotency_key=idempotency_key,
            status=TaskStatus.QUEUED.value,
            model_profile=options.get("model_profile", "default"),
        )
        for step_name in PIPELINE_STEP_NAMES:
            self.task_repository.create_step(
                task_id=task.id,
                step_name=step_name,
                status=StepStatus.PENDING.value,
            )
        self.db_session.commit()

        if self.queue_publisher:
            self.queue_publisher.publish_analyze_document(task_id=task.id)
        return task

    def list_steps(self, task_id: str):
        return self.task_repository.list_steps(task_id)
```

Behavior:

- If `(user_id, idempotency_key)` exists, return existing task.
- Else create task with status `queued`.
- Create all 8 task steps.
- Publish queue message if `queue_publisher` is present.

- [ ] **Step 4: Run test**

```bash
.venv/bin/pytest backend/tests/application/test_task_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/task_service.py backend/app/infrastructure/db/repositories backend/tests/application/test_task_service.py
git commit -m "feat: add idempotent task service"
```

---

## Task 9: 实现 AnalysisOrchestrator Pipeline 骨架

**Files:**
- Create: `backend/app/application/analysis_orchestrator.py`
- Create: `backend/app/domain/analysis/pipeline.py`
- Test: `backend/tests/application/test_analysis_orchestrator.py`

- [ ] **Step 1: Write failing tests**

```python
from app.application.analysis_orchestrator import AnalysisOrchestrator


def test_orchestrator_skips_completed_task(fake_task_repository):
    fake_task_repository.status = "completed"
    orchestrator = AnalysisOrchestrator(task_repository=fake_task_repository, steps=[])

    result = orchestrator.run(task_id="task_1")

    assert result.skipped is True


def test_orchestrator_runs_steps_in_order(fake_task_repository):
    calls = []

    class Step:
        name = "load_document"

        def run(self, context):
            calls.append(self.name)
            return context

    fake_task_repository.status = "queued"
    orchestrator = AnalysisOrchestrator(task_repository=fake_task_repository, steps=[Step()])

    result = orchestrator.run(task_id="task_1")

    assert result.skipped is False
    assert calls == ["load_document"]
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/application/test_analysis_orchestrator.py -q
```

Expected: FAIL until orchestrator exists.

- [ ] **Step 3: Implement orchestrator interfaces**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class AnalysisContext:
    task_id: str


@dataclass
class AnalysisResult:
    task_id: str
    skipped: bool


class PipelineStep(Protocol):
    name: str

    def run(self, context: AnalysisContext) -> AnalysisContext:
        raise NotImplementedError


class AnalysisOrchestrator:
    def __init__(self, *, task_repository, steps: list[PipelineStep]):
        self.task_repository = task_repository
        self.steps = steps

    def run(self, *, task_id: str) -> AnalysisResult:
        task = self.task_repository.get(task_id)
        if task.status == "completed":
            return AnalysisResult(task_id=task_id, skipped=True)
        context = AnalysisContext(task_id=task_id)
        for step in self.steps:
            context = step.run(context)
        return AnalysisResult(task_id=task_id, skipped=False)
```

- [ ] **Step 4: Add fake repository fixtures**

In test file, define:

```python
import pytest


class FakeTask:
    def __init__(self, status):
        self.status = status


class FakeTaskRepository:
    status = "queued"

    def get(self, task_id):
        return FakeTask(self.status)


@pytest.fixture
def fake_task_repository():
    return FakeTaskRepository()
```

- [ ] **Step 5: Run test**

```bash
.venv/bin/pytest backend/tests/application/test_analysis_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/application/analysis_orchestrator.py backend/tests/application/test_analysis_orchestrator.py
git commit -m "feat: add analysis orchestrator skeleton"
```

---

## Task 10: 实现 API Routes 迁移

**Files:**
- Create/Modify: `backend/app/api/routes/auth.py`, `files.py`, `tasks.py`, `reports.py`
- Create/Modify: `backend/app/api/schemas/*.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_*_routes.py`

- [ ] **Step 1: Write route tests for auth**

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_test_login_returns_token_in_local():
    response = TestClient(create_app(database_url="sqlite:///:memory:")).post(
        "/api/auth/test-login",
        json={"user_id": "usr_route"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
```

- [ ] **Step 2: Write route tests for task creation**

```python
def test_create_task_requires_idempotency_key(authenticated_client):
    response = authenticated_client.post(
        "/api/analysis-tasks",
        json={"file_id": "file_1", "options": {}},
    )

    assert response.status_code == 400
    assert response.json()["data"]["error_code"] == "IDEMPOTENCY_KEY_REQUIRED"
```

- [ ] **Step 3: Run route tests**

```bash
.venv/bin/pytest backend/tests/api -q
```

Expected: FAIL until routes are migrated.

- [ ] **Step 4: Move route handlers from `main.py` into route modules**

Create routers with these prefixes:

```python
router = APIRouter(prefix="/api/auth", tags=["auth"])
router = APIRouter(prefix="/api/uploads", tags=["uploads"])
router = APIRouter(prefix="/api/files", tags=["files"])
router = APIRouter(prefix="/api/analysis-tasks", tags=["tasks"])
router = APIRouter(prefix="/api/reports", tags=["reports"])
```

Use application services rather than repository calls directly in route handlers.

- [ ] **Step 5: Register routers in app factory**

In `backend/app/main.py`:

```python
for router in [
    health.router,
    auth.router,
    files.router,
    tasks.router,
    reports.router,
]:
    app.include_router(router)
```

- [ ] **Step 6: Run API tests**

```bash
.venv/bin/pytest backend/tests/api -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/api
git commit -m "refactor: split API routes into modules"
```

---

## Task 11: 实现 Worker Job 入口

**Files:**
- Create: `backend/app/workers/main.py`
- Create: `backend/app/workers/jobs/analyze_document.py`
- Test: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing worker test**

```python
from app.workers.jobs.analyze_document import run


def test_analyze_document_job_invokes_orchestrator(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def run(self, *, task_id):
            captured["task_id"] = task_id

    monkeypatch.setattr(
        "app.workers.jobs.analyze_document.build_orchestrator",
        lambda: FakeOrchestrator(),
    )

    run(task_id="task_1")

    assert captured["task_id"] == "task_1"
```

- [ ] **Step 2: Run test to verify failure**

```bash
.venv/bin/pytest backend/tests/test_worker_jobs.py::test_analyze_document_job_invokes_orchestrator -q
```

Expected: FAIL until new worker job exists.

- [ ] **Step 3: Implement job**

```python
from __future__ import annotations


def build_orchestrator():
    raise RuntimeError("orchestrator wiring is configured in the worker composition root")


def run(*, task_id: str) -> None:
    orchestrator = build_orchestrator()
    orchestrator.run(task_id=task_id)
```

- [ ] **Step 4: Implement worker main placeholder**

```python
from __future__ import annotations

from app.workers.jobs.analyze_document import run as analyze_document


__all__ = ["analyze_document"]
```

- [ ] **Step 5: Run test**

```bash
.venv/bin/pytest backend/tests/test_worker_jobs.py::test_analyze_document_job_invokes_orchestrator -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers backend/tests/test_worker_jobs.py
git commit -m "feat: add redesigned worker job entrypoint"
```

---

## Task 12: 实现端到端回归和样例 PDF 验收

**Files:**
- Create: `backend/tests/e2e/test_analysis_flow.py`
- Create: `backend/tests/e2e/test_sample_pdf_regression.py`
- Modify: `backend/scripts/verify_pdfs.py`

- [ ] **Step 1: Write E2E test for API flow**

```python
def test_api_to_report_flow(test_client, sample_pdf_file):
    token = test_client.post("/api/auth/test-login", json={"user_id": "usr_e2e"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    file_response = test_client.post(
        "/api/files",
        headers={**headers, "Idempotency-Key": "file-e2e-1"},
        json=sample_pdf_file.registration_payload,
    )
    file_id = file_response.json()["data"]["file"]["id"]

    task_response = test_client.post(
        "/api/analysis-tasks",
        headers={**headers, "Idempotency-Key": "task-e2e-1"},
        json={"file_id": file_id, "options": {"enable_vision": True}},
    )

    assert task_response.status_code == 200
    assert task_response.json()["data"]["task"]["id"]
```

- [ ] **Step 2: Write sample PDF regression test**

```python
from pathlib import Path

from app.pipeline.offline import analyze_pdf_offline


ROOT = Path(__file__).resolve().parents[3]


def test_sample_pdfs_produce_pages_tables_and_scores(tmp_path):
    pdfs = [
        ROOT / "多线程DSP智能终端芯片_202603_副本.pdf",
        ROOT / "追光科技A+轮融资商业计划书260226_副本.pdf",
    ]

    for pdf in pdfs:
        result = analyze_pdf_offline(pdf, artifact_dir=tmp_path)
        assert result.parse_summary.page_count > 0
        assert result.parse_summary.block_count > 0
        assert result.score_result.potential_score > 0
```

- [ ] **Step 3: Run E2E tests**

```bash
.venv/bin/pytest backend/tests/e2e -q
```

Expected: FAIL until all application wiring and pipeline implementation are complete.

- [ ] **Step 4: Wire pipeline stages into orchestrator**

Register concrete step classes:

```python
steps = [
    LoadDocumentStep(storage=storage, file_repository=file_repository),
    ParseTextLayoutStep(pdf_reader=pdf_reader, document_repository=document_repository),
    DetectTablesAndFiguresStep(table_detector=table_detector, document_repository=document_repository),
    RenderCandidatePagesStep(renderer=renderer, artifact_repository=artifact_repository),
    VisionUnderstandingStep(model_gateway=model_gateway, artifact_repository=artifact_repository),
    BuildEvidenceUnitsStep(document_repository=document_repository, evidence_repository=evidence_repository),
    ScoreAndJudgeStep(model_gateway=model_gateway, scoring_repository=scoring_repository),
    AssembleReportStep(report_assembler=report_assembler, report_repository=report_repository),
]
```

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest
```

Expected: PASS.

- [ ] **Step 6: Run sample PDF verification**

```bash
.venv/bin/python backend/scripts/verify_pdfs.py
```

Expected:

- Both sample PDFs complete.
- Page counts are non-zero and match known fixtures.
- Tables are detected.
- Evidence units are generated.
- Reports include completeness and potential score.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests/e2e backend/scripts/verify_pdfs.py
git commit -m "test: add redesigned end-to-end analysis regression"
```

---

## Task 13: Docker Compose and Local Debug Finalization

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/Dockerfile`
- Create: `.vscode/launch.json`
- Create: `docker-compose.debug.yml`
- Test: Docker Compose config and health curl.

- [ ] **Step 1: Add pipeline env variables to `.env.example`**

```dotenv
PDF_MAX_PAGES=120
PDF_MAX_SIZE_MB=50
STEP_TIMEOUT_SECONDS=300
MAX_RETRY_ATTEMPTS=3
ENABLE_VISION=true
```

- [ ] **Step 2: Ensure compose injects pipeline variables into api and worker**

Add to both services:

```yaml
PDF_MAX_PAGES: ${PDF_MAX_PAGES:-120}
PDF_MAX_SIZE_MB: ${PDF_MAX_SIZE_MB:-50}
STEP_TIMEOUT_SECONDS: ${STEP_TIMEOUT_SECONDS:-300}
MAX_RETRY_ATTEMPTS: ${MAX_RETRY_ATTEMPTS:-3}
ENABLE_VISION: ${ENABLE_VISION:-true}
```

- [ ] **Step 3: Verify compose config**

```bash
docker compose config
```

Expected: command exits 0 and shows variables under both `api.environment` and `worker.environment`.

- [ ] **Step 4: Verify health endpoint**

```bash
docker compose up --build
curl --noproxy '*' http://localhost:8000/api/health
```

Expected:

```json
{"code":0,"message":"ok","data":{"status":"ok","version":"0.1.0"}}
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example backend/Dockerfile
git commit -m "chore: finalize local compose configuration"
```

---

## Task 14: VSCode 单步调试与腾讯云部署文档

**Files:**
- Create: `.vscode/launch.json`
- Create: `docker-compose.debug.yml`
- Create: `docs/deployment/tencent-cloud.md`
- Modify: `.env.example`
- Test: VSCode config is valid JSON, Docker debug compose config passes.

- [ ] **Step 1: Add local debug env comments to `.env.example`**

Add these local host values as comments below the Docker defaults:

```dotenv
# VSCode local-process debug values:
# DATABASE_URL=mysql+pymysql://pulselink:pulselink@127.0.0.1:3307/pulselink
# REDIS_URL=redis://127.0.0.1:6379/0
# LOCAL_FILE_ROOT=/Users/whao/Documents/PulseLinkV2
# COS_ENDPOINT=http://localhost:9000
```

- [ ] **Step 2: Create VSCode launch config**

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "PulseLink API (local Python)",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
      ],
      "cwd": "${workspaceFolder}/backend",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/backend",
        "APP_ENV": "local",
        "DATABASE_URL": "mysql+pymysql://pulselink:pulselink@127.0.0.1:3307/pulselink",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "QUEUE_NAME": "pulselink",
        "RUN_ANALYSIS_INLINE": "false",
        "LOCAL_FILE_ROOT": "${workspaceFolder}",
        "COS_ENDPOINT": "http://localhost:9000",
        "COS_BUCKET": "pulselink-local"
      },
      "justMyCode": false
    },
    {
      "name": "PulseLink Worker Job (local Python)",
      "type": "python",
      "request": "launch",
      "module": "app.workers.main",
      "cwd": "${workspaceFolder}/backend",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/backend",
        "APP_ENV": "local",
        "DATABASE_URL": "mysql+pymysql://pulselink:pulselink@127.0.0.1:3307/pulselink",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "QUEUE_NAME": "pulselink",
        "RUN_ANALYSIS_INLINE": "false",
        "LOCAL_FILE_ROOT": "${workspaceFolder}",
        "COS_ENDPOINT": "http://localhost:9000",
        "COS_BUCKET": "pulselink-local"
      },
      "justMyCode": false
    },
    {
      "name": "Attach API in Docker (debugpy)",
      "type": "python",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}/backend",
          "remoteRoot": "/app/backend"
        }
      ],
      "justMyCode": false
    }
  ]
}
```

- [ ] **Step 3: Create debug compose override**

Create `docker-compose.debug.yml`:

```yaml
services:
  api:
    command: python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
      - "5678:5678"
```

- [ ] **Step 4: Ensure debugpy dependency exists**

Add to `backend/requirements.txt`:

```text
debugpy==1.8.11
```

- [ ] **Step 5: Validate VSCode config JSON**

Run:

```bash
python -m json.tool .vscode/launch.json >/tmp/pulselink-launch-check.json
```

Expected: command exits 0.

- [ ] **Step 6: Validate debug compose**

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml config
```

Expected: command exits 0 and api exposes `5678`.

- [ ] **Step 7: Create Tencent Cloud deployment doc**

Create `docs/deployment/tencent-cloud.md`:

```markdown
# PulseLinkV2 腾讯云部署说明

## 1. 生产组件

- API / Worker：同一个 Docker 镜像，不同启动命令。
- MySQL：腾讯云 MySQL。
- Redis：腾讯云 Redis。
- Storage：腾讯云 COS。
- 入口：HTTPS 域名 + Nginx 或腾讯云负载均衡。

## 2. 必需环境变量

- APP_ENV=prod
- DATABASE_URL=mysql+pymysql://<user>:<password>@<tencent-mysql-host>:3306/pulselink
- REDIS_URL=redis://:<password>@<tencent-redis-host>:6379/0
- QUEUE_NAME=pulselink
- JWT_SECRET=<至少32位强随机字符串>
- WECHAT_APP_ID=<微信小程序AppID>
- WECHAT_APP_SECRET=<微信小程序AppSecret>
- COS_REGION=<腾讯云COS地域>
- COS_BUCKET=<腾讯云COS bucket>
- COS_ENDPOINT=https://<bucket>.cos.<region>.myqcloud.com
- COS_SECRET_ID=<腾讯云SecretId>
- COS_SECRET_KEY=<腾讯云SecretKey>
- LLM_API_BASE=https://api.minimax.chat/v1
- LLM_API_KEY=<MiniMax API Key>
- LLM_MODEL=MiniMax-M3
- VISION_API_BASE=https://api.minimax.chat/v1
- VISION_API_KEY=<MiniMax API Key>
- VISION_MODEL=MiniMax-M3

## 3. 发布顺序

1. 构建并推送 Docker 镜像。
2. 执行 Alembic migration。
3. 启动或更新 Worker。
4. 启动或更新 API。
5. 检查 `/api/health`。
6. 验证微信登录、COS 直传、任务创建、Worker 消费、报告读取。

## 4. 腾讯云检查项

- MySQL 白名单允许 API/Worker 访问。
- Redis 白名单允许 API/Worker 访问。
- COS bucket CORS 允许小程序上传所需方法和请求头。
- HTTPS 域名已备案并配置到微信小程序 request 合法域名。
- 生产环境不使用 `.env` 文件保存密钥。
```

- [ ] **Step 8: Commit**

```bash
git add .vscode/launch.json docker-compose.debug.yml .env.example backend/requirements.txt docs/deployment/tencent-cloud.md
git commit -m "chore: add local debug and Tencent Cloud deployment docs"
```

---

## Final Verification

- [ ] Run full unit/integration/e2e suite:

```bash
.venv/bin/pytest
```

- [ ] Validate Docker Compose:

```bash
docker compose config
```

- [ ] Run sample PDF regression:

```bash
.venv/bin/python backend/scripts/verify_pdfs.py
```

- [ ] Confirm no secrets are staged:

```bash
git status --short
git diff --cached -- . ':!.env'
```

Expected final state:

- Tests pass.
- Compose config passes.
- Both sample PDFs produce report output.
- `.env` remains untracked and ignored.
- API and Worker use the redesigned application/domain/infrastructure layers.
