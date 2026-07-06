# PulseLinkV2 前后端分离完整设计方案

## 1. 项目目标与 V1 范围

PulseLinkV2 重构为“原生微信小程序 + 独立 FastAPI 后端”的前后端分离系统。旧版微信云函数项目只作为业务流程、页面链路和评分规则参考，不逐文件迁移。

V1 先完成核心闭环：

- 微信小程序登录
- PDF 上传与文件登记
- 分析任务创建
- 高质量 PDF 解析
- 材料完整度评估
- 项目潜力评分
- 报告生成
- 任务状态查询
- 报告查看
- 历史报告列表

V1 暂不包含：

- 补充问卷
- 留资解锁
- 机构匹配
- 平台项目池
- 复杂后台管理

这些能力作为 V1.1 或 V2 继续扩展。

## 2. 总体架构

核心技术栈：

- 小程序：原生微信小程序
- API：FastAPI
- 数据库：MySQL
- 队列：Redis + RQ
- 文件存储：腾讯云 COS
- 本地开发：Docker Compose
- 生产部署：Docker 跑 API/Worker，MySQL/Redis 使用腾讯云托管服务
- AI：OpenAI-compatible 文本模型 + 视觉模型 adapter

整体链路：

```text
微信小程序
  -> FastAPI API
    -> MySQL
    -> Redis/RQ
    -> COS
    -> Text LLM
    -> Vision LLM
```

服务职责：

- `api`
  - 处理登录、上传签名、文件登记、任务创建、状态查询、报告查询。
  - 不直接执行 PDF 解析、视觉理解或 LLM 调用。

- `worker`
  - 执行异步任务。
  - 负责 PDF 解析、页面视觉理解、事实卡构建、评分、报告生成。

- `mysql`
  - 保存用户、文件、任务、解析产物、评分结果、报告、任务事件。

- `redis`
  - RQ 队列、任务调度、短期锁。

- `cos`
  - 保存 PDF 原文件、页面渲染图片、解析 artifact。

## 3. 部署方案

### 3.1 本地开发

本地使用 Docker Compose 启动完整开发依赖：

```text
api
worker
mysql
redis
minio
```

MinIO 用于模拟腾讯云 COS，方便本地完成上传、下载、页面图片存储等流程。

> **CORS 说明**：小程序生产调用 API 不需要 CORS。但在本地开发测试时，如需使用浏览器调试 API，应在 FastAPI 应用中加入 CORS 中间件。建议开发环境宽松配置、生产环境限制为小程序合法域名。

### 3.2 生产环境

生产环境建议：

```text
Docker:
  api
  worker

腾讯云托管:
  MySQL
  Redis
  COS
```

API 和 Worker 使用同一代码镜像，不同启动命令：

```text
api: uvicorn app.main:app
worker: rq worker pulselink
```

MySQL 和 Redis 不建议在生产环境放进自管 Docker 容器，原因是它们是有状态组件，需要备份、磁盘、监控、故障恢复和升级策略。生产使用腾讯云托管数据库和托管 Redis，可以降低运维风险。

API 和 Worker 适合 Docker 化，因为它们是无状态应用服务，便于依赖封装、发布、回滚和水平扩容。

### 3.3 生产启动安全阀

`APP_ENV=prod` 时，后端启动必须通过配置校验：

- `JWT_SECRET` 不能使用默认值，长度至少 32 位。
- `DATABASE_URL` 必须指向生产 MySQL，不能使用 SQLite。
- `REDIS_URL` 必须指向生产 Redis，不能使用 `localhost` 或 `127.0.0.1`。
- `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET` 必须配置。
- `COS_BUCKET` 必须配置。
- `COS_ENDPOINT` 必须配置，上传预签名接口会基于该 endpoint 返回对象上传 URL。
- `COS_SECRET_ID` 和 `COS_SECRET_KEY` 必须配置，生产上传预签名通过腾讯云 COS Python SDK 生成。

这类配置错误应在容器启动阶段直接失败，不进入半可用状态。生产环境数据库表结构通过 Alembic 迁移创建，应用启动不自动建表。

## 4. 微信小程序接入方式

小程序继续使用原生微信小程序，不重写 UI。

后续迁移重点：

- 将 `wx.cloud.callFunction` 替换为 `wx.request`。
- 将微信云存储上传替换为 COS 直传。
- 新增统一 API client：
  - 保存 JWT。
  - 自动携带 `Authorization: Bearer <jwt>`。
  - 统一处理 `401`、`403`、`409`、`500` 等错误。

核心页面迁移顺序：

1. 上传页：接入 COS 直传、文件登记、任务创建。
2. 分析中页：轮询任务状态。
3. 报告页：读取报告详情。
4. 历史页：读取历史报告列表。

## 5. 核心业务流程

1. 小程序调用 `POST /api/auth/wechat-login`。
2. 后端通过微信 `code` 获取 `openid`，创建或复用用户，返回 JWT。
3. 小程序调用 `POST /api/uploads/pdf/presign` 获取 COS 上传参数。
4. 小程序直传 PDF 到 COS。
5. 小程序调用 `POST /api/files` 登记文件。
6. 小程序调用 `POST /api/analysis-tasks` 创建分析任务，传入 `Idempotency-Key`。
7. 后端创建任务并投递 RQ pipeline。
8. Worker 执行：
   - `parse_pdf_meta`
   - `parse_text_page_batch`
   - `render_page_batch`
   - `vision_page_batch`
   - `build_fact_cards`
   - `score_dimension`
   - `aggregate_score`
   - `generate_report_section`
   - `assemble_report`
9. 小程序轮询 `GET /api/analysis-tasks/{task_id}`。
10. 完成后调用 `GET /api/reports/{task_id}` 查看报告。
11. 历史页调用 `GET /api/reports`。

## 6. API 接口协议

### 6.1 通用协议

Base URL：

```text
https://api.example.com/api
```

除 COS 上传外，业务 API 默认使用 JSON：

```http
Content-Type: application/json; charset=utf-8
Accept: application/json
```

认证请求头：

```http
Authorization: Bearer <jwt>
```

JWT 规则：

- access token 使用 `HS256` 签名。
- token payload 至少包含 `sub=user_id`、`type=access`、`iat`、`exp`。
- `JWT_SECRET` 必须在生产环境使用强随机值，并通过环境变量注入。
- 本地测试可兼容 `Bearer test:<user_id>`，生产应关闭或限制测试登录入口。

可选请求追踪头：

```http
X-Request-Id: <client-request-id>
```

创建类接口使用幂等头：

```http
Idempotency-Key: <uuid>
```

统一成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "req_20260609_xxx"
}
```

统一错误响应：

```json
{
  "code": 40001,
  "message": "文件类型不支持",
  "data": {
    "error_code": "UNSUPPORTED_FILE_TYPE",
    "details": {}
  },
  "request_id": "req_20260609_xxx"
}
```

常用 HTTP 状态：

```text
200 成功
400 参数错误
401 未登录或 token 失效
403 无权限访问
404 资源不存在
409 幂等冲突或资源状态冲突
413 文件过大
422 请求 JSON 格式正确但业务校验失败
429 请求过于频繁
500 服务端错误
503 外部服务暂不可用
```

所有时间字段使用 ISO 8601，并带时区。

### 6.2 登录

#### `POST /api/auth/wechat-login`

用途：小程序登录，换取 JWT。

认证：不需要。

Content-Type：

```http
application/json; charset=utf-8
```

入参：

```json
{
  "code": "微信 wx.login 返回的 code"
}
```

处理规则：

- 生产环境通过 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET` 配置微信小程序 client。
- 后端调用微信 `jscode2session` 换取 `openid`，再创建或复用用户。
- 微信返回无效 code 时返回 `401 AUTH_INVALID_CODE`。
- 未配置微信 client 时，非测试 code 返回 `503 WECHAT_CLIENT_NOT_CONFIGURED`。
- 本地开发可使用 `test_openid_xxx` 形式的 code 走测试登录分支。
- 生产环境必须禁用 `/api/auth/test-login` 和 `test_openid_xxx` 测试 code。
- 内部 `user_id` 由 openid 稳定哈希生成，不直接暴露 openid。

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "jwt_token",
    "token_type": "Bearer",
    "expires_in": 604800,
    "user": {
      "id": "usr_123",
      "openid_bound": true,
      "status": "active"
    }
  },
  "request_id": "req_xxx"
}
```

### 6.3 获取 PDF 上传签名

#### `POST /api/uploads/pdf/presign`

用途：获取 COS 直传参数。

认证：需要。

Content-Type：

```http
application/json; charset=utf-8
```

入参：

```json
{
  "file_name": "demo.pdf",
  "file_size": 1234567,
  "sha256": "hex_sha256",
  "content_type": "application/pdf"
}
```

校验：

```text
file_name 必须以 .pdf 结尾
content_type 必须为 application/pdf
file_size <= 50MB
sha256 必须为 64 位 hex
```

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "upload": {
      "method": "PUT",
      "url": "https://bucket.cos.region.myqcloud.com/uploads/xxx.pdf?signature=xxx",
      "headers": {
        "Content-Type": "application/pdf"
      },
      "expires_in": 900
    },
    "object": {
      "bucket": "pulselink-prod",
      "key": "uploads/usr_123/2026/06/file_xxx.pdf",
      "content_type": "application/pdf"
    },
    "limits": {
      "max_file_size": 52428800
    }
  },
  "request_id": "req_xxx"
}
```

说明：

- 小程序随后直接 `PUT` 到 `upload.url`。
- COS 上传请求的 `Content-Type` 是 `application/pdf`。
- 后端不接收 PDF 二进制正文。
- 预签名 URL 应设置 `content-length-range` 条件限制，防止客户端上传超过 50MB 的文件。
  文件登记时也会二次校验 `file_size` 的准确性。

### 6.4 文件登记

#### `POST /api/files`

用途：登记已上传到 COS 的 PDF 文件。

认证：需要。

Content-Type：

```http
application/json; charset=utf-8
```

请求头：

```http
Idempotency-Key: <uuid>
```

入参：

```json
{
  "cos_bucket": "pulselink-prod",
  "cos_key": "uploads/usr_123/2026/06/file_xxx.pdf",
  "file_name": "demo.pdf",
  "file_size": 1234567,
  "sha256": "hex_sha256",
  "content_type": "application/pdf"
}
```

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "file": {
      "id": "file_123",
      "file_name": "demo.pdf",
      "file_size": 1234567,
      "sha256": "hex_sha256",
      "content_type": "application/pdf",
      "status": "uploaded",
      "created_at": "2026-06-09T10:00:00+08:00"
    },
    "deduplicated": false
  },
  "request_id": "req_xxx"
}
```

幂等规则：

```text
同一 user_id + sha256 返回同一个 file_id
重复 Idempotency-Key 返回第一次响应
```

### 6.5 创建分析任务

#### `POST /api/analysis-tasks`

用途：创建分析任务。

认证：需要。

Content-Type：

```http
application/json; charset=utf-8
```

请求头：

```http
Idempotency-Key: <uuid>
```

入参：

```json
{
  "file_id": "file_123",
  "options": {
    "language": "zh-CN",
    "enable_vision": true,
    "report_type": "financing_readiness"
  }
}
```

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task": {
      "id": "task_123",
      "file_id": "file_123",
      "status": "queued",
      "progress": 0,
      "current_step": "queued",
      "status_text": "任务已创建，等待分析",
      "created_at": "2026-06-09T10:01:00+08:00",
      "deadline_at": "2026-06-09T10:21:00+08:00"
    }
  },
  "request_id": "req_xxx"
}
```

幂等规则：

```text
同一 user_id + Idempotency-Key 返回同一个 task_id
同一个 file_id 可以创建多个任务，但必须使用不同 Idempotency-Key
```

### 6.6 查询任务状态

#### `GET /api/analysis-tasks/{task_id}`

用途：查询任务状态。

认证：需要。

Content-Type：无请求体。

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task": {
      "id": "task_123",
      "status": "vision_parsing",
      "progress": 45,
      "current_step": "vision_page_batch",
      "status_text": "正在解析图表和表格页面",
      "error_code": "",
      "error_message": "",
      "created_at": "2026-06-09T10:01:00+08:00",
      "updated_at": "2026-06-09T10:05:00+08:00",
      "completed_at": null,
      "failed_at": null
    }
  },
  "request_id": "req_xxx"
}
```

失败任务示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task": {
      "id": "task_123",
      "status": "failed",
      "progress": 35,
      "current_step": "parse_text_page_batch",
      "status_text": "PDF 解析失败",
      "error_code": "PDF_PARSE_LOW_CONFIDENCE",
      "error_message": "文件内容识别质量较低，请上传更清晰的 PDF。"
    }
  },
  "request_id": "req_xxx"
}
```

### 6.7 获取报告详情

#### `GET /api/reports/{task_id}`

用途：获取指定任务报告。

认证：需要。

Content-Type：无请求体。

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "report": {
      "task_id": "task_123",
      "title": "融资准备度诊断报告",
      "material_completeness": {
        "score": 72,
        "level": "medium",
        "missing_items": [
          "近三年财务数据",
          "股权结构说明"
        ]
      },
      "potential_score": {
        "total": 68.5,
        "confidence_level": "medium",
        "recommendation": "建议补充关键商业化和融资用途材料后再启动正式融资。"
      },
      "dimensions": [
        {
          "key": "problem_need_strength",
          "name": "问题与需求强度",
          "score": 7,
          "max_score": 10,
          "evidence_strength": "B",
          "deduction_reason": "有痛点描述，但客户调研和紧迫性证据不足。",
          "evidence_pages": [2, 3],
          "bp_supplement_suggestions": [
            "补充客户调研或访谈证据",
            "补充政策或行业变化对需求紧迫性的支撑"
          ],
          "investor_due_diligence_suggestions": [
            "访谈目标客户验证痛点强度",
            "核查政策或行业趋势的实际影响"
          ]
        }
      ],
      "sections": [
        {
          "key": "executive_summary",
          "title": "执行摘要",
          "content": "..."
        }
      ],
      "created_at": "2026-06-09T10:15:00+08:00"
    }
  },
  "request_id": "req_xxx"
}
```

错误：

```text
任务未完成：409 REPORT_NOT_READY
任务不存在：404 TASK_NOT_FOUND
非本人任务：403 FORBIDDEN
```

### 6.8 历史报告列表

#### `GET /api/reports`

用途：历史报告列表。

认证：需要。

Query 参数：

```text
page: 默认 1
page_size: 默认 20，最大 50
status: optional, queued|parsing|vision_parsing|scoring|reporting|completed|failed
```

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "task_id": "task_123",
        "file_id": "file_123",
        "file_name": "demo.pdf",
        "status": "completed",
        "progress": 100,
        "potential_score": 68.5,
        "material_completeness_score": 72,
        "confidence_level": "medium",
        "created_at": "2026-06-09T10:01:00+08:00",
        "completed_at": "2026-06-09T10:15:00+08:00"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1
    }
  },
  "request_id": "req_xxx"
}
```

### 6.9 健康检查

#### `GET /api/health`

认证：不需要。

出参：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok",
    "version": "0.1.0",
    "time": "2026-06-09T10:00:00+08:00"
  },
  "request_id": "req_xxx"
}
```

### 6.10 错误码

```text
AUTH_INVALID_CODE
AUTH_TOKEN_EXPIRED
AUTH_REQUIRED
FORBIDDEN

UNSUPPORTED_FILE_TYPE
FILE_TOO_LARGE
FILE_NOT_FOUND
FILE_UPLOAD_NOT_CONFIRMED
FILE_HASH_MISMATCH

TASK_NOT_FOUND
TASK_STATE_CONFLICT
TASK_TOTAL_TIMEOUT

PDF_DOWNLOAD_TIMEOUT
PDF_TEXT_PARSE_TIMEOUT
PDF_RENDER_TIMEOUT
PDF_PARSE_LOW_CONFIDENCE

VISION_PARSE_TIMEOUT
VISION_PARSE_LOW_CONFIDENCE

LLM_SCORING_TIMEOUT
LLM_REPORT_TIMEOUT
LLM_INVALID_JSON

REPORT_NOT_READY
REPORT_NOT_FOUND

RATE_LIMITED
INTERNAL_ERROR
```

## 7. MySQL 数据模型

所有表 ID 采用 `nanoid` 生成，带前缀标识业务类型：

```text
users:               usr_xxx
files:               file_xxx
analysis_tasks:      task_xxx
task_steps:          step_xxx
document_pages:      page_xxx
page_blocks:         blk_xxx
page_tables:         tbl_xxx
parse_artifacts:     art_xxx
bp_fact_cards:       card_xxx
judgment_cards:      jdg_xxx
score_results:       scr_xxx
reports:             rpt_xxx
task_events:         evt_xxx
```

### 7.1 `users`

保存微信用户。

字段：

```text
id
openid
nickname
avatar_url
role                              -- user | admin，预留权限扩展
status                            -- active | disabled
created_at
updated_at
```

索引：

```text
unique(openid)
```

### 7.2 `files`

保存上传文件元数据。

字段：

```text
id
user_id
cos_bucket
cos_key
file_name
file_size
sha256
page_count
parse_status
created_at
updated_at
```

索引：

```text
unique(user_id, sha256)
index(user_id, created_at)
```

### 7.3 `analysis_tasks`

保存一次分析任务。

字段：

```text
id
user_id
file_id
idempotency_key
status
progress
current_step
status_text
error_code
error_message
deadline_at
started_at
completed_at
failed_at
created_at
updated_at
```

状态：

```text
queued                              -- 已创建，待消费
parsing                             -- 解析中（含文本解析 + 表格结构化 + 视觉解析）
scoring                             -- 评分中（事实卡抽取 + 维度评分 + 聚合）
reporting                           -- 报告生成中
completed
failed
```

> 状态粒度为用户对外感知。内部通过 `current_step` 追踪精确的 pipeline 步骤（如 `parse_text_page_batch`、`vision_page_batch`）。

索引：

```text
unique(user_id, idempotency_key)
index(user_id, created_at)
index(status, deadline_at)
```

### 7.4 `task_steps`

保存 pipeline 阶段状态。

字段：

```text
id
task_id
step_name
status
attempt_count
max_attempts
timeout_seconds
locked_until
last_heartbeat_at
next_retry_at
last_error_code
last_error_message
started_at
finished_at
created_at
updated_at
```

索引：

```text
unique(task_id, step_name)
index(status, next_retry_at)
index(locked_until)
```

### 7.5 `document_pages`

保存页级解析结果。

字段：

```text
id
task_id
file_id
page_number
raw_text
clean_text
final_content_json
parse_quality
needs_vision
confidence_score
created_at
updated_at
```

索引：

```text
unique(task_id, page_number)
index(file_id, page_number)
```

### 7.6 `page_blocks`

保存页面结构化块。

字段：

```text
id
task_id
page_id
block_type
block_order
content_text
content_json
confidence_score
created_at
```

`block_type`：

```text
heading
paragraph
list
table
chart
image_summary
metric
unknown
```

### 7.7 `page_tables`

保存结构化表格。

字段：

```text
id
task_id
page_id
table_type
columns_json
rows_json
semantic_summary
confidence_score
source
created_at
```

`table_type` 示例：

```text
financial_forecast
competitor_comparison
financing_history
equity_structure
customer_orders
milestones
other
```

`source`：

```text
text
vision
hybrid
unknown
```

### 7.8 `parse_artifacts`

保存解析中间产物。

字段：

```text
id
task_id
page_id
artifact_type
cos_key
model_name
request_json
response_json
created_at
```

用途：

- 页面渲染图
- 视觉模型输入输出
- 解析调试数据

### 7.9 `bp_fact_cards`

保存融资诊断事实卡。

字段：

```text
id
task_id
dimension_key
fact_summary
evidence_json
confidence_score
created_at
```

索引：

```text
unique(task_id, dimension_key)
```

### 7.10 `judgment_cards`

保存维度判断。

字段：

```text
id
task_id
dimension_key
dimension_name
score
max_score
evidence_strength
deduction_reason
judgment_json
bp_supplement_suggestions_json
investor_due_diligence_suggestions_json
evidence_pages_json
created_at
```

索引：

```text
unique(task_id, dimension_key)
```

### 7.11 `score_results`

保存评分汇总。

字段：

```text
id
task_id
material_completeness_score
potential_score
confidence_level
recommendation
dimension_scores_json
completeness_items_json
overall_bp_supplement_suggestions_json
overall_investor_due_diligence_suggestions_json
raw_result_json
version
created_at
```

索引：

```text
unique(task_id)
```

### 7.12 `reports`

保存最终报告。

字段：

```text
id
task_id
title
summary_json
sections_json
raw_model_output_json
version
created_at
updated_at
```

索引：

```text
unique(task_id)
```

### 7.13 `task_events`

保存任务事件和审计日志。

字段：

```text
id
task_id
event_type
message
payload_json
created_at
```

索引：

```text
index(task_id, created_at)
```

## 8. PDF 高质量解析方案

PDF 解析目标不是“抽一段文本”，而是生成可被评分引擎消费的结构化页面内容。

### 8.1 文本解析

每页提取：

- 原始文本
- 清洗文本
- 标题
- 段落
- 列表
- 数字密集区
- 可能的表格区域

清理规则：

- 去水印
- 去重复页眉页脚
- 合并异常换行
- 清理重复空格
- 标记乱码比例

### 8.2 表格结构化

表格不能只转成普通文本。系统需要保留行列关系和语义。

重点识别：

- 财务预测表
- 竞品对比表
- 融资历史表
- 股权结构表
- 客户订单表
- 里程碑表

处理策略：

- 如果文本层能稳定还原行列，直接生成 `page_tables`。
- 如果行列关系不稳定，渲染页面图片后交给视觉模型。
- 视觉模型必须输出结构化 JSON：`columns`、`rows`、`semantic_summary`、`confidence_score`。
- 表格结论必须保留页码证据。

### 8.3 视觉解析

进入视觉解析的页面：

- 扫描页
- 图片重页
- 图表页
- 复杂表格页
- 文本质量低但包含关键融资信息的页面

视觉模型输出：

```text
page_summary
key_facts
tables
charts
metrics
confidence_score
```

V1 不单独接传统 OCR。视觉模型承担 OCR + 图文理解。

### 8.4 质量控制

每页生成：

```text
parse_quality: high | medium | low
confidence_score
needs_vision
source_types
```

失败规则：

- 整份 PDF 可用内容不足：`PDF_PARSE_LOW_CONFIDENCE`
- 关键表格无法解析：降低对应维度证据强度
- 单页视觉失败：记录失败，可继续
- 关键页大量失败：`VISION_PARSE_LOW_CONFIDENCE`

## 9. 评分规则与报告输出

报告展示顺序：

1. 材料完整度
2. 项目潜力评分

项目潜力总分：100 分。

### 9.1 八个评分维度

#### 问题与需求强度：10 分

- 有问题/痛点描述是及格线。
- 有政策、客户调研、行业证据、紧迫性证明则加分。
- 没有痛点描述则不及格。
- 建议补充围绕痛点真实性、紧迫程度和客观证据。

#### 市场空间与赛道吸引力：10 分

- 必须有市场规模数据。
- 加分看细分领域相关性、增速、渗透率、国产化率、权威来源。
- 客户订单不放在此项。
- 建议补充第三方市场数据、权威行业报告、细分市场规模和增速。

#### 产品与解决方案：12.5 分

- 必须讲清产品或解决方案是什么。
- 加分看是否回应痛点、核心竞争力、成熟度、稳定供应、业务数据、竞品对比。

#### 商业模式与单位经济：12.5 分

- 必须讲清怎么创收、客户是谁。
- 加分看商业闭环、利润来源、毛利、成本、客单价、回收周期等。

#### 团队匹配度：15 分

- 先校验团队事实抽取准确性。
- 看研发、市场、产业资源是否支撑项目。
- 强创始人或均衡豪华团队加分。

#### 商业化进展：15 分

- 看研发进展、客户验证、产能布局、订单数据、过往三年财务、未来三年预测、行业认证和里程碑。
- 原旧版“进展与验证数据”统一改为“商业化进展”。

#### 竞争格局与壁垒：15 分

- 看核心壁垒、行业地位、竞对、对标上市公司、优劣势分析。
- 壁垒不要求面面俱到，但定位要清楚。

#### 融资逻辑与资金用途：10 分

- 看融资原因、金额、用途。
- 判断融资阶段、资金用途、估值是否匹配项目阶段。
- 后续融资和上市退出路径可加分。

### 9.2 评分流程

```text
结构化 PDF 内容
  -> 事实卡抽取
  -> 维度证据匹配
  -> 规则层硬性判断
  -> LLM 维度评分解释
  -> 汇总总分
  -> 生成报告
```

原则：

- 每个维度独立评分。
- 每个维度只消费相关事实卡。
- 分数不能超过维度上限。
- 证据不足不能脑补。
- 每个维度都输出：
  - 分数
  - 扣分原因
  - 证据页码
  - BP 补充建议
  - 投资方尽调建议

### 9.3 报告输出结构

报告应包含：

- 材料完整度评分
- 缺失材料列表
- 项目潜力总分
- 置信度
- 融资推进建议
- 八个维度评分明细
- 各维度证据页码
- 各维度扣分原因
- 项目方 BP 补充建议
- 投资方尽调建议
- 执行摘要
- 结构化章节内容

## 10. 超时、重试与任务状态

所有耗时操作异步执行。API 不等待 PDF 解析或 LLM。

### 10.1 三层超时

用户请求超时：

- 登录、文件登记、创建任务 3 秒内返回。
- 小程序上传走 COS 直传。
- 小程序通过轮询查询状态。

Worker job 超时：

- 每个 job 有 `timeout_seconds`。
- 执行时写 `locked_until` 和 `last_heartbeat_at`。
- 超时后可重试或永久失败。

任务总超时：

- 单个分析任务 SLA 默认 20 分钟。
- 超过总时长进入 `failed`。
- 错误码：`TASK_TOTAL_TIMEOUT`。

### 10.2 Job 超时默认值

```text
parse_pdf_meta: 30s
parse_text_page_batch: 60s
render_page_batch: 90s
vision_page_batch: 90s
build_fact_cards: 90s
score_dimension: 60s
aggregate_score: 30s
generate_report_section: 60s
assemble_report: 30s
```

### 10.3 重试规则

- PDF 下载、页面渲染、视觉模型、LLM 调用最多重试 2-3 次。
- 指数退避：
  - 第一次失败：30 秒后重试
  - 第二次失败：2 分钟后重试
  - 第三次失败：永久失败

### 10.4 用户侧错误文案

```text
PDF_DOWNLOAD_TIMEOUT: 文件读取超时，请稍后重试或重新上传。
PDF_TEXT_PARSE_TIMEOUT: 文件内容较复杂，解析超时，请尝试上传更清晰的 PDF。
VISION_PARSE_LOW_CONFIDENCE: 部分图表页解析失败，请尝试上传更清晰版本。
LLM_SCORING_TIMEOUT: 评分服务暂时繁忙，请稍后重试。
LLM_REPORT_TIMEOUT: 报告生成服务暂时繁忙，请稍后重试。
TASK_TOTAL_TIMEOUT: 分析时间过长，请稍后重试或重新上传文件。
```

## 11. 幂等与可靠性

### 11.1 API 幂等

- `files`: `user_id + sha256` 唯一。
- `analysis_tasks`: `user_id + idempotency_key` 唯一。
- 重复请求返回已有资源。
- 创建类接口使用 `Idempotency-Key`。

### 11.2 Worker 幂等

- 每个 step 执行前检查 `task_steps`。
- 已完成 step 直接跳过。
- 页面、事实卡、评分、报告使用唯一索引 + upsert。
- RQ job 重复投递不会产生重复结果。

### 11.3 可靠性原则

- 不允许任务永久停留在处理中。
- 不输出半成品总分。
- 报告结论必须能追溯到页码或结构化证据。
- 低质量解析降低置信度或失败，不强行生成确定结论。

## 12. 域名、HTTPS 与备案

生产环境需要域名，原因是微信小程序调用独立后端 API 有要求：

- API 必须使用 HTTPS。
- 域名要配置到微信小程序后台的 request 合法域名。
- 生产环境不能直接使用普通 IP 地址。
- 如果后端部署在中国大陆腾讯云，域名通常需要 ICP 备案。

建议准备：

```text
api.yourdomain.com  -> FastAPI 后端
cos.yourdomain.com  -> 可选，COS 自定义域名/CDN
```

微信小程序后台配置：

```text
request 合法域名: https://api.yourdomain.com
uploadFile/downloadFile 合法域名: COS 官方域名或自定义域名
```

推荐在腾讯云购买域名并完成备案，原因是后端、备案、证书、DNS、COS 都计划使用腾讯云，流程最顺。

备案基本步骤：

1. 购买域名。
2. 完成域名实名认证。
3. 准备腾讯云中国大陆资源。
4. 在腾讯云 ICP 备案系统提交备案。
5. 填写主体信息和网站信息。
6. 上传资料并完成人脸核验。
7. 腾讯云初审。
8. 管局审核。
9. 备案通过后配置 DNS、HTTPS 证书和小程序合法域名。

如果 PulseLink 作为商业项目上线，建议使用企业主体备案。

## 13. 后端目录结构

后端建议采用单仓库内的 FastAPI + RQ Worker 结构。API 和 Worker 共用 domain、service、repository、schema、client 等模块，避免同一套业务逻辑在两个入口重复实现。

### 13.1 当前 V1 MVP 落地目录

当前本地后端先采用“少文件、边界清晰”的 MVP 结构，优先把 API、数据库、PDF 解析、评分、报告和 Worker 主链路跑通。等功能稳定后，再把大文件拆到 `routes/`、`models/`、`repositories/`、`schemas/` 等更细目录。

```text
backend/
  app/
    __init__.py
    main.py                         -- FastAPI 应用入口；注册 API、数据库会话和健康检查

    api/
      __init__.py
      deps.py                       -- 鉴权、当前用户、请求依赖

    clients/
      __init__.py
      llm_client.py                 -- OpenAI-compatible LLM JSON client 和本地 fallback
      wechat_client.py              -- 微信小程序 jscode2session client

    core/
      __init__.py
      config.py                     -- 环境变量集中配置；数据库、Redis、队列、artifact、模型配置
      responses.py                  -- 统一响应结构、错误响应
      security.py                   -- JWT access token 签发和校验

    db/
      __init__.py
      base.py                       -- SQLAlchemy ORM 模型；V1 先集中定义
      repositories.py               -- 用户、文件、任务、报告等 Repository；V1 先集中定义
      session.py                    -- SessionLocal、engine、DB 初始化

    parsing/
      __init__.py
      models.py                     -- PDF 页面、块、表格、解析结果模型
      pdf_reader.py                 -- pdfinfo / pdftotext 读取 PDF 元信息和 layout 文本
      pipeline.py                   -- PDF 解析主流程
      quality.py                    -- 水印清理、表格页/视觉页判断、解析质量评分
      page_renderer.py              -- pdftoppm 页面渲染，供视觉解析使用
      vision_parser.py              -- 视觉解析 adapter；本地 heuristic fallback

    pipeline/
      __init__.py
      offline.py                    -- 本地离线分析 pipeline，便于 fixture 验证
      persistence.py                -- 将解析、事实卡、评分、报告写入数据库

    reporting/
      __init__.py
      assembler.py                  -- 报告 JSON 组装

    scoring/
      __init__.py
      dimensions.py                 -- 八维评分定义与权重
      engine.py                     -- 材料完整度、维度评分、总分聚合
      fact_builder.py               -- 从解析内容构建事实卡
      models.py                     -- 事实卡、判断卡、评分结果模型

    services/
      __init__.py
      memory_store.py               -- 早期内存存储兼容层，后续由 DB service 替代

    storage/
      __init__.py
      file_resolver.py              -- 文件源解析；支持本地路径和对象存储下载到 worker 临时目录
      object_clients.py             -- 对象存储 client adapter；本地 file-backed，后续扩展 COS/MinIO
      resolver_factory.py           -- 根据 settings 构建文件 resolver

    workers/
      __init__.py
      enqueue.py                    -- RQ enqueue adapter；把 API 创建的任务投递到队列
      pipeline.py                   -- RQ 可调用的分析任务入口
      rq_app.py                     -- Worker 队列配置入口；从 settings 创建 RQ Queue
      jobs/
        __init__.py
        config.py                   -- pipeline 步骤、超时、重试配置

  migrations/
    env.py                          -- Alembic 迁移环境
    script.py.mako                  -- Alembic revision 模板
    versions/
      0001_initial_schema.py        -- 初始数据库 schema

  scripts/
    verify_pdfs.py                  -- 使用本地两个 PDF fixture 跑完整解析和评分验证

  tests/
    test_app_factory.py
    test_api_contract.py
    test_api_database_integration.py
    test_db_models.py
    test_file_resolver.py
    test_file_resolver_factory.py
    test_llm_client.py
    test_migrations.py
    test_offline_pipeline.py
    test_page_renderer.py
    test_pdf_parser.py
    test_persistence_pipeline.py
    test_repositories.py
    test_rq_app.py
    test_scoring.py
    test_security.py
    test_settings.py
    test_storage_clients.py
    test_vision_parser.py
    test_worker_config.py
    test_worker_enqueue.py
    test_worker_jobs.py

  Dockerfile
  alembic.ini
  requirements.txt

docker-compose.yml
pyproject.toml
docs/
  architecture/
    pulselink-v2-design.md
```

MVP 目录原则：

- 先保证业务链路完整：上传登记 -> 创建任务 -> PDF 解析 -> 事实卡 -> 评分 -> 报告。
- `main.py` 暂时承载 API route，后续接口增多后拆到 `app/api/routes/`。
- `db/base.py` 暂时集中 ORM，后续模型稳定后拆到 `app/db/models/`。
- `db/repositories.py` 暂时集中 Repository，后续按 users/files/tasks/reports 拆分。
- `migrations/` 使用 Alembic 管理 schema；生产发版前执行 `alembic upgrade head`，不要依赖应用启动自动建表。
- `pipeline/offline.py` 用于本地和测试验证；生产 Worker 入口走 `workers/pipeline.py`，API 通过 `workers/enqueue.py` 投递 RQ。
- `storage/file_resolver.py` 是 Worker 读取 PDF 的统一入口；本地开发可直接解析路径，生产可通过对象存储 client 下载 COS 文件到临时目录后再进入解析。
- `parsing`、`scoring`、`reporting` 不依赖 FastAPI，保证 Worker、测试、命令行验证都能复用。
- 所有 LLM、视觉模型、COS、微信调用都应通过 `clients/` 封装；当前本地 heuristic 只是无外部依赖的 fallback。

### 13.2 完整生产推荐目录

生产版本推荐演进为下面的更细目录：

```text
backend/
  app/
    __init__.py
    main.py
    api/
      __init__.py
      deps.py
      routes/
        __init__.py
        auth.py
        uploads.py
        files.py
        analysis_tasks.py
        reports.py
        health.py
    core/
      __init__.py
      config.py
      logging.py
      security.py
      errors.py
      idempotency.py
      timeouts.py
    db/
      __init__.py
      session.py
      base.py
      models/
        __init__.py
        user.py
        file.py
        analysis_task.py
        task_step.py
        document_page.py
        page_block.py
        page_table.py
        parse_artifact.py
        bp_fact_card.py
        judgment_card.py
        score_result.py
        report.py
        task_event.py
      repositories/
        __init__.py
        users.py
        files.py
        tasks.py
        parsing.py
        scoring.py
        reports.py
    schemas/
      __init__.py
      common.py
      auth.py
      upload.py
      file.py
      analysis_task.py
      report.py
    services/
      __init__.py
      auth_service.py
      upload_service.py
      file_service.py
      task_service.py
      report_service.py
      scoring_service.py
      material_completeness_service.py
    clients/
      __init__.py
      wechat_client.py
      cos_client.py
      llm_client.py
      vision_client.py
    workers/
      __init__.py
      rq_app.py
      pipeline.py
      jobs/
        __init__.py
        parse_pdf_meta.py
        parse_text_page_batch.py
        render_page_batch.py
        vision_page_batch.py
        build_fact_cards.py
        score_dimension.py
        aggregate_score.py
        generate_report_section.py
        assemble_report.py
    parsing/
      __init__.py
      pdf_reader.py
      text_cleaner.py
      layout_detector.py
      table_extractor.py
      page_renderer.py
      vision_parser.py
      quality.py
      prompts/
        vision_page.md
        table_structure.md
    scoring/
      __init__.py
      dimensions.py
      rules.py
      fact_builder.py
      dimension_scorer.py
      aggregator.py
      prompts/
        build_fact_cards.md
        score_dimension.md
        generate_report_section.md
    reporting/
      __init__.py
      section_builder.py
      report_assembler.py
      templates/
        report_sections.md
    migrations/
      versions/
    tests/
      api/
      services/
      workers/
      parsing/
      scoring/
      fixtures/
  Dockerfile
  pyproject.toml
  alembic.ini
docker-compose.yml
docs/
  architecture/
    pulselink-v2-design.md
```

### 13.3 目录职责

- `app/main.py`
  - FastAPI 应用入口。
  - 注册路由、中间件、异常处理和健康检查。

- `app/api/routes`
  - 只放 HTTP 层逻辑：参数接收、鉴权依赖、调用 service、返回 schema。
  - 不直接写数据库、不直接调用 LLM、不执行 PDF 解析。

- `app/core`
  - 全局配置、日志、错误码、JWT、安全、幂等、超时常量。
  - `config.py` 读取环境变量，区分 local/test/prod。

- `app/db/models`
  - SQLAlchemy ORM 模型。
  - 与 MySQL 数据模型一一对应。

- `app/db/repositories`
  - 数据访问层。
  - 封装查询、upsert、状态更新、唯一约束冲突处理。
  - service 不直接拼复杂 SQL。

- `app/schemas`
  - Pydantic 请求/响应模型。
  - API 协议中的入参、出参、错误结构都在这里定义。

- `app/services`
  - 业务编排层。
  - 处理登录、文件登记、任务创建、报告读取、材料完整度、评分汇总等用例。

- `app/clients`
  - 外部服务 client。
  - 微信、COS、文本 LLM、视觉模型都通过 client 封装。
  - 业务代码不直接依赖具体供应商 SDK。

- `app/workers`
  - RQ worker 入口和任务 pipeline。
  - `jobs` 下每个文件对应一个可重试、可幂等、可超时的 job。
  - Worker 只调用 service/parsing/scoring/reporting 模块，不把业务逻辑塞进任务入口。

- `app/parsing`
  - PDF 文本、版面、表格、页面渲染、视觉理解、质量评估。
  - prompt 放在 `parsing/prompts`，避免散落在代码里。

- `app/scoring`
  - 八维评分规则、事实卡构建、维度评分、总分聚合。
  - 评分规则和 prompt 独立管理，便于以后校准。

- `app/reporting`
  - 报告章节生成和最终组装。
  - 报告结构与评分逻辑分离。

- `app/migrations`
  - Alembic 数据库迁移。
  - 所有表结构、索引、唯一约束都通过 migration 管理。

- `app/tests`
  - API、service、worker、PDF 解析、评分规则测试。
  - `fixtures` 存放测试 PDF、模型 mock 响应和样例报告 JSON。

### 13.4 分层规则

- route 可以依赖 service 和 schema。
- service 可以依赖 repository、client、domain parser/scorer。
- repository 只负责数据库。
- worker job 只负责任务入口、状态推进和调用 service。
- parsing/scoring/reporting 不依赖 FastAPI route。
- client 不写业务规则，只封装外部服务调用、超时、重试和响应规范化。

启动入口：

```text
API: backend/app/main.py
Worker: backend/app/workers/rq_app.py
```

生产镜像可以共用一个 `Dockerfile`，通过不同命令启动 API 或 Worker。

## 14. 测试计划

### 14.1 API 测试

- 未登录访问返回 `401`。
- 访问非本人任务返回 `403`。
- 重复文件登记返回同一个 `file_id`。
- 重复创建任务返回同一个 `task_id`。
- 非 PDF 或超过 50MB 返回 `400`。
- 报告未完成时读取报告返回 `409 REPORT_NOT_READY`。

### 14.2 数据测试

- MySQL 唯一索引生效。
- upsert 不产生重复页面、重复表格、重复报告。
- 已完成 task step 不被重试覆盖。
- `user_id + sha256` 去重正确。
- `user_id + idempotency_key` 去重正确。

### 14.3 PDF 测试

- 文本 PDF 能输出页面 blocks。
- 表格 PDF 能输出 `page_tables`。
- 图表页进入视觉解析。
- 扫描页通过视觉模型生成结构化内容。
- 低质量 PDF 返回 `PDF_PARSE_LOW_CONFIDENCE`。

### 14.4 Worker 测试

- 完整 fixture PDF 跑通 parse -> fact cards -> score -> report。
- LLM 非法 JSON 触发重试。
- LLM 超时触发重试。
- 重复投递 job 不产生重复数据。
- 总任务超时后进入 `failed`。

### 14.5 评分测试

- 八个维度权重相加为 100。
- 无痛点描述时“问题与需求强度”不及格。
- 无市场规模数据时“市场空间与赛道吸引力”不及格。
- 每个维度都生成 BP 补充建议和投资方尽调建议。
- 材料完整度先于项目潜力展示。

### 14.6 线下测试操作

线下测试分三层：纯本地单元测试、两份样例 PDF 回归测试、Docker Compose 端到端测试。建议按顺序执行，先保证代码逻辑正确，再验证容器和依赖服务。

#### 14.6.1 纯本地测试

适合开发阶段快速验证，不依赖 MySQL、Redis、COS 或真实大模型。

执行：

```bash
cd /Users/whao/Documents/PulseLinkV2
.venv/bin/pytest
```

预期：

- 所有测试通过。
- API、数据库 repository、PDF 解析、评分、报告、Worker 任务入口、迁移脚本都能被覆盖。
- 本地测试可使用 SQLite 和 mock/fallback，不需要真实云资源。

#### 14.6.2 两份样例 PDF 回归测试

用于验证 PDF 解析、表格识别、视觉候选页、评分和报告结构是否稳定。

执行：

```bash
cd /Users/whao/Documents/PulseLinkV2
.venv/bin/python backend/scripts/verify_pdfs.py
```

当前样例文件：

```text
多线程DSP智能终端芯片_202603_副本.pdf
追光科技A+轮融资商业计划书260226_副本.pdf
```

重点检查：

- `page_count` 是否正确。
- `block_count` 是否明显异常。
- `table_count` 是否能识别表格。
- `parse_quality` 不应大面积变为 `low`。
- `vision_candidate_count` 是否能覆盖图表页、表格页、图片页。
- `potential_score.total` 是否稳定在合理范围。
- 输出报告是否包含材料完整度、项目潜力、八个维度评分、证据页和建议补充内容。

#### 14.6.3 Docker Compose 线下端到端测试

用于模拟生产依赖，但仍在本机完成。

执行配置检查：

```bash
cd /Users/whao/Documents/PulseLinkV2
docker compose config
```

启动本地依赖和服务：

```bash
docker compose up --build
```

本地服务：

```text
API: http://localhost:8000
MinIO: http://localhost:9001
MySQL: localhost:3307
Redis: localhost:6379
```

本地 Compose 已给 MySQL 和 Redis 配置 healthcheck，API/Worker 会等待依赖健康后再启动。如果仍看到 `Can't connect to MySQL server on 'mysql'`，通常是 MySQL 首次初始化较慢或旧容器状态异常，先看：

```bash
docker compose ps
docker compose logs mysql
```

测试顺序：

1. 调用 `GET /api/health`，确认 API 存活。
2. 调用 `POST /api/auth/test-login` 获取本地 JWT。
3. 调用 `POST /api/uploads/pdf/presign` 获取本地上传 URL。
4. 上传 PDF 到 MinIO 或使用本地绑定文件路径登记。
5. 调用 `POST /api/files` 登记文件。
6. 调用 `POST /api/analysis-tasks` 创建任务。
7. 确认 Worker 从 Redis 消费任务。
8. 轮询 `GET /api/analysis-tasks/{task_id}`。
9. 任务完成后调用 `GET /api/reports/{task_id}`。
10. 重复提交同一个 `Idempotency-Key`，确认返回同一个任务。

#### 14.6.4 线下测试通过标准

- `.venv/bin/pytest` 全部通过。
- `docker compose config` 通过。
- 两份样例 PDF 都能生成结果。
- 文件去重和任务幂等可复现。
- API 不在请求中同步等待长耗时解析。
- Worker 失败时任务状态能进入失败或可重试状态。
- 解析结果至少包含文本 blocks、表格 tables、视觉候选页和评分维度。

### 14.7 curl 接口验证

curl 验证用于在不接小程序 UI 的情况下，直接检查 API 协议、登录、鉴权、上传登记、任务创建、幂等和报告读取。线下建议先用 Docker Compose 启动 API、Worker、MySQL、Redis 和 MinIO。

#### 14.7.1 准备本地环境

启动服务：

```bash
cd /Users/whao/Documents/PulseLinkV2
docker compose up --build
```

另开一个终端设置 API 地址：

```bash
export API_BASE=http://localhost:8000/api
```

检查健康状态：

```bash
curl -s "$API_BASE/health"
```

预期返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok"
  }
}
```

#### 14.7.2 本地测试登录

本地环境使用测试登录接口：

```bash
curl -s -X POST "$API_BASE/auth/test-login" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"usr_curl"}'
```

从响应中取出：

```text
data.access_token
```

后续请求统一带：

```bash
export TOKEN=<上一步返回的access_token>
```

鉴权请求头：

```bash
-H "Authorization: Bearer $TOKEN"
```

生产环境不能使用 `/api/auth/test-login`，生产应使用 `/api/auth/wechat-login`。

#### 14.7.3 获取 PDF 上传预签名

先计算 PDF sha256：

```bash
export PDF_FILE="/Users/whao/Documents/PulseLinkV2/追光科技A+轮融资商业计划书260226_副本.pdf"
export PDF_NAME="追光科技A+轮融资商业计划书260226_副本.pdf"
export PDF_SIZE=$(wc -c < "$PDF_FILE" | tr -d ' ')
export PDF_SHA256=$(shasum -a 256 "$PDF_FILE" | awk '{print $1}')
```

请求预签名：

```bash
curl -s -X POST "$API_BASE/uploads/pdf/presign" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"file_name\":\"$PDF_NAME\",
    \"file_size\":$PDF_SIZE,
    \"sha256\":\"$PDF_SHA256\",
    \"content_type\":\"application/pdf\"
  }"
```

重点检查：

- `data.upload.method` 是 `PUT`。
- `data.upload.url` 存在。
- `data.upload.headers.Content-Type` 是 `application/pdf`。
- `data.object.bucket` 存在。
- `data.object.key` 以 `.pdf` 结尾。

本地当前预签名主要用于验证协议结构。线下 Docker 端到端测试可以直接登记 compose 中绑定到 `/app` 的 PDF 文件路径；生产环境必须使用真实 COS presigned URL 上传。

#### 14.7.4 登记文件

本地 Docker Compose 已把两份样例 PDF 挂载到 API/Worker 容器的 `/app` 下。为了验证完整分析链路，可以直接把 `cos_key` 写成容器内可解析的文件名：

```bash
curl -s -X POST "$API_BASE/files" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: file-curl-001" \
  -H "Content-Type: application/json" \
  -d "{
    \"cos_bucket\":\"local\",
    \"cos_key\":\"追光科技A+轮融资商业计划书260226_副本.pdf\",
    \"file_name\":\"$PDF_NAME\",
    \"file_size\":$PDF_SIZE,
    \"sha256\":\"$PDF_SHA256\",
    \"content_type\":\"application/pdf\"
  }"
```

从响应中取出：

```text
data.file.id
```

设置：

```bash
export FILE_ID=<上一步返回的file.id>
```

重复执行同一个 sha256 的文件登记，预期：

- HTTP `200`。
- 返回同一个 `file.id`。
- `data.deduplicated` 为 `true`。

#### 14.7.5 创建分析任务

创建任务：

```bash
curl -s -X POST "$API_BASE/analysis-tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: task-curl-001" \
  -H "Content-Type: application/json" \
  -d "{
    \"file_id\":\"$FILE_ID\",
    \"options\": {
      \"enable_vision\": true
    }
  }"
```

从响应中取出：

```text
data.task.id
```

设置：

```bash
export TASK_ID=<上一步返回的task.id>
```

重复使用同一个 `Idempotency-Key` 创建任务，预期：

- HTTP `200`。
- 返回同一个 `task.id`。
- 不重复创建任务。

#### 14.7.6 查询任务状态

轮询任务：

```bash
curl -s "$API_BASE/analysis-tasks/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN"
```

重点检查：

- `data.task.status`
- `data.task.progress`
- `data.task.current_step`
- `data.task.error_code`
- `data.task.error_message`

常见状态：

```text
queued
running
completed
failed
```

如果长时间停在 `queued`，优先检查 Worker 是否启动、Redis 是否可连接、队列名是否为 `pulselink`。

#### 14.7.7 查询报告

任务完成后查询报告：

```bash
curl -s "$API_BASE/reports/$TASK_ID" \
  -H "Authorization: Bearer $TOKEN"
```

预期：

- 任务未完成时返回 `409 REPORT_NOT_READY`。
- 任务完成后返回 `data.report`。
- 报告包含材料完整度、项目潜力评分、八个维度评分、证据页和建议。

查询历史报告：

```bash
curl -s "$API_BASE/reports?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"
```

#### 14.7.8 生产微信登录验证

生产不能使用测试登录。生产验证微信登录时，小程序端先调用 `wx.login` 获取临时 code，然后用 curl 验证：

```bash
export API_BASE=https://api.example.com/api
export WX_CODE=<小程序wx.login返回的code>

curl -s -X POST "$API_BASE/auth/wechat-login" \
  -H "Content-Type: application/json" \
  -d "{
    \"code\":\"$WX_CODE\"
  }"
```

预期：

- 返回 `access_token`。
- `token_type` 是 `Bearer`。
- `user.openid_bound` 是 `true`。

如果返回 `WECHAT_CLIENT_NOT_CONFIGURED`，检查：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- `APP_ENV`
- 后端是否使用了正确生产环境变量启动。

如果返回 `AUTH_INVALID_CODE`，检查：

- code 是否过期。
- code 是否已被使用。
- 小程序 AppID 是否和后端配置一致。

#### 14.7.9 生产 COS 直传验证

生产流程必须真的把 PDF 上传到 COS：

1. 调用 `/api/uploads/pdf/presign` 获取 `data.upload.url`。
2. 使用 `PUT` 上传 PDF：

```bash
curl -X PUT "<data.upload.url>" \
  -H "Content-Type: application/pdf" \
  --data-binary "@$PDF_FILE"
```

3. 使用 `data.object.bucket` 和 `data.object.key` 调用 `/api/files` 登记文件。
4. 创建分析任务。
5. 确认 Worker 能从 COS 下载 PDF 并完成解析。

生产 COS 直传失败时重点检查：

- `COS_BUCKET`
- `COS_ENDPOINT`
- `COS_REGION`
- `COS_SECRET_ID`
- `COS_SECRET_KEY`
- bucket CORS 设置
- 预签名 URL 是否过期
- 上传时 `Content-Type` 是否与预签名一致

#### 14.7.10 curl 验证通过标准

- `/api/health` 成功。
- 本地测试登录或生产微信登录成功。
- 未带 token 的受保护接口返回 `401`。
- 预签名接口返回 PUT 上传协议。
- 文件登记成功并支持去重。
- 任务创建成功并支持幂等。
- Worker 能消费任务。
- 任务最终进入 `completed`。
- 报告可以读取。
- 历史报告列表可以读取。
- 生产环境 COS 直传能真实上传 PDF。

### 14.8 大模型配置

系统把文本大模型和视觉模型分开配置，二者都按 OpenAI-compatible API 适配。这样可以使用 OpenAI、Azure OpenAI、兼容 OpenAI 协议的国内模型服务，或自建模型网关。

#### 14.8.1 文本模型配置

文本模型用于：

- 事实卡抽取。
- 八个评分维度判断。
- 扣分原因生成。
- BP 补充建议生成。
- 投资方尽调建议生成。
- 报告章节生成。

环境变量：

```bash
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=<文本模型API Key>
LLM_MODEL=<文本模型名称>
```

MiniMax 示例：

```bash
LLM_API_BASE=https://api.minimax.chat/v1
LLM_API_KEY=<MiniMax API Key>
LLM_MODEL=MiniMax-Text-01
```

OpenAI-compatible 请求形态：

```text
POST {LLM_API_BASE}/chat/completions
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json
```

要求：

- 模型必须稳定输出 JSON。
- prompt 中必须明确要求只返回 JSON。
- 后端需要校验 JSON schema，不合格则重试或降级。
- 文本模型超时不能阻塞 API，只能影响 Worker 当前任务。

#### 14.8.2 视觉模型配置

视觉模型用于处理文本解析无法完整表达结构含义的页面，例如：

- 表格页。
- 图表页。
- 扫描页。
- 信息图页。
- 图片中包含关键业务信息的页面。

环境变量：

```bash
VISION_API_BASE=https://api.openai.com/v1
VISION_API_KEY=<视觉模型API Key>
VISION_MODEL=<视觉模型名称>
```

MiniMax 示例：

```bash
VISION_API_BASE=https://api.minimax.chat/v1
VISION_API_KEY=<MiniMax API Key>
VISION_MODEL=MiniMax-VL-01
```

视觉模型输入：

- PDF 页面先渲染为图片。
- 只对低置信度页面、表格页、图表页、图片页调用视觉模型。
- 不对所有页面无差别调用视觉模型，避免成本和超时失控。

视觉模型输出要求：

- 页面摘要。
- 页面中可结构化的表格。
- 图表表达的关键结论。
- 关键数据和单位。
- 对评分维度有用的证据。
- 置信度。

#### 14.8.3 线下无模型模式

线下可以不配置 `LLM_API_KEY` 和 `VISION_API_KEY`。此时系统使用本地 heuristic/fallback 跑通主链路，适合验证：

- PDF 是否能读取。
- 页面是否能切分。
- 表格是否能初步抽取。
- 评分结构是否能生成。
- 报告 JSON 是否能组装。

无模型模式不能作为最终质量验收，因为它无法真正理解复杂图表、扫描页和高语义表格。

#### 14.8.4 线下接真实模型

如果要在线下接真实大模型，需要在本地 `.env` 或启动环境中配置：

```bash
LLM_API_BASE=<文本模型Base URL>
LLM_API_KEY=<文本模型Key>
LLM_MODEL=<文本模型名称>

VISION_API_BASE=<视觉模型Base URL>
VISION_API_KEY=<视觉模型Key>
VISION_MODEL=<视觉模型名称>
```

本地推荐用 `.env` 管理测试配置：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```bash
LLM_API_BASE=https://api.minimax.chat/v1
LLM_API_KEY=<你的MiniMax API Key>
LLM_MODEL=MiniMax-Text-01

VISION_API_BASE=https://api.minimax.chat/v1
VISION_API_KEY=<你的MiniMax API Key>
VISION_MODEL=MiniMax-VL-01
```

如果你的 MiniMax 控制台显示的可用模型名不同，以控制台模型名为准替换 `LLM_MODEL` 和 `VISION_MODEL`。

`docker-compose.yml` 会把 `.env` 注入到 API 和 Worker。改完 `.env` 后重启：

```bash
docker compose down
docker compose up --build
```

确认容器内变量：

```bash
docker compose exec api env | grep -E 'LLM|VISION'
docker compose exec worker env | grep -E 'LLM|VISION'
```

安全规则：

- `.env.example` 可以提交，只放占位符。
- `.env` 不提交，里面可以放本地测试 key。
- 生产不要直接复用本地 `.env`，应使用云平台环境变量或密钥管理服务。

然后执行：

```bash
.venv/bin/python backend/scripts/verify_pdfs.py
```

重点观察：

- LLM 是否返回合法 JSON。
- 视觉模型是否能识别表格结构和图表含义。
- 是否出现 `LLM_INVALID_JSON`。
- 是否出现 `LLM_SCORING_TIMEOUT`。
- 是否出现 `VISION_PARSE_TIMEOUT`。
- 单份 PDF 总耗时是否可接受。
- 生成内容是否严格引用证据页，不凭空补充。

#### 14.8.5 推荐配置策略

本地开发：

```text
LLM_API_KEY 可不配
VISION_API_KEY 可不配
使用 heuristic/fallback 保证主链路跑通
```

线下质量测试：

```text
配置真实文本模型
配置真实视觉模型
使用两份样例 PDF 跑回归
人工抽查表格页、图表页、评分证据页
```

生产：

```text
文本模型和视觉模型都必须配置
API key 通过环境变量或密钥管理服务注入
设置调用超时、重试、失败告警
按页面质量选择性调用视觉模型
记录模型名称、请求摘要、响应摘要和 artifact，便于追溯
```

模型选择原则：

- 文本模型优先选择 JSON 稳定性强、长上下文能力好、中文商业材料理解能力好的模型。
- 视觉模型优先选择表格、图表、截图理解能力强的模型。
- 不建议为了节省成本把所有页面都交给低能力模型，否则评分解释和证据抽取会不稳定。
- 可采用“两级模型”策略：普通文本页用低成本模型，低置信度页和评分生成用高能力模型。

## 15. 后续阶段规划

V1.1 可扩展：

- 补充问卷
- 留资解锁
- 报告完整版/免费版区分
- 服务线索表
- 报告导出 PDF

V2 可扩展：

- 平台项目池
- 顾问复核后台
- 机构匹配
- 相似案例库
- 投资方尽调工作台
- 多模型评估和人工校准

## 16. 关键决策汇总

- V1 使用 MySQL，不使用 MongoDB。
- V1 保留原生微信小程序。
- V1 后端先行，小程序接入随后做。
- PDF 解析采用“文本 + 表格结构化 + 视觉理解”。
- 不单独接传统 OCR。
- LLM 和视觉模型都通过 OpenAI-compatible adapter 接入。
- 本地基础设施用 Docker Compose。
- 生产 MySQL/Redis 使用云托管，API/Worker 使用 Docker。
- 生产小程序调用独立后端需要 HTTPS 域名，并在微信后台配置合法域名。
- 如果部署在中国大陆腾讯云，域名通常需要 ICP 备案。

## 17. 生产部署操作手册

本节用于把 PulseLinkV2 从本地开发环境部署到生产环境。生产部署前必须先完成域名、备案、云资源、环境变量、数据库迁移、镜像发布、小程序配置和端到端验证。

### 17.1 部署前置条件

必须先准备：

- 域名，例如 `api.example.com`。
- ICP 备案，适用于中国大陆云服务器或大陆访问链路。
- HTTPS 证书。
- 微信小程序 AppID 和 AppSecret。
- 腾讯云 COS bucket。
- 腾讯云 MySQL 实例。
- 腾讯云 Redis 实例。
- 运行 API 和 Worker 的服务器或容器平台。
- 文本 LLM 和视觉模型的 API key。

推荐生产资源：

```text
API / Worker:
  Docker 容器部署

有状态服务:
  腾讯云 MySQL
  腾讯云 Redis
  腾讯云 COS

入口:
  Nginx / 负载均衡
  HTTPS
  api.example.com
```

### 17.2 域名与备案操作

操作顺序：

1. 在腾讯云、阿里云、华为云或 Cloudflare 等平台购买域名。
2. 如果服务器部署在中国大陆，提交 ICP 备案。
3. 备案主体要与实际运营主体一致。
4. 备案通过后，将 `api.example.com` 解析到生产入口 IP 或负载均衡 CNAME。
5. 申请 HTTPS 证书。
6. 在 Nginx 或负载均衡上绑定证书。
7. 在微信小程序后台配置 request 合法域名：

```text
https://api.example.com
```

如果后续小程序直接使用 `uploadFile`、`downloadFile` 或访问独立 H5 页面，还需要同步配置 uploadFile 合法域名、downloadFile 合法域名、业务域名。

### 17.3 腾讯云资源准备

MySQL：

- 版本建议 MySQL 8.x。
- 创建独立数据库，例如 `pulselink`。
- 创建业务账号，不使用 root。
- 开启自动备份。
- 配置白名单，只允许 API / Worker 所在内网或固定出口访问。

Redis：

- 用作 RQ 队列。
- 配置访问密码。
- 配置白名单。
- 生产不要使用本地容器 Redis 保存正式任务队列。

COS：

- 创建 bucket，例如 `pulselink-prod`。
- 设置合适地域，例如 `ap-guangzhou`。
- 原文件建议路径：

```text
uploads/{user_id}/{sha256_prefix}/{file_name}
```

- 解析 artifact 建议路径：

```text
artifacts/{task_id}/...
```

- COS 密钥只保存在后端环境变量中，小程序不直接持有永久密钥。

### 17.4 生产环境变量

API 和 Worker 使用同一套镜像，环境变量保持一致。生产环境必须配置：

```bash
APP_ENV=prod
DATABASE_URL=mysql+pymysql://<user>:<password>@<mysql-host>:3306/pulselink
REDIS_URL=redis://:<password>@<redis-host>:6379/0
QUEUE_NAME=pulselink
RUN_ANALYSIS_INLINE=false

JWT_SECRET=<至少32位强随机字符串>

WECHAT_APP_ID=<微信小程序AppID>
WECHAT_APP_SECRET=<微信小程序AppSecret>

COS_REGION=ap-guangzhou
COS_BUCKET=pulselink-prod
COS_ENDPOINT=https://pulselink-prod.cos.ap-guangzhou.myqcloud.com
COS_SECRET_ID=<腾讯云SecretId>
COS_SECRET_KEY=<腾讯云SecretKey>

LLM_API_BASE=<文本模型API地址>
LLM_API_KEY=<文本模型API Key>
LLM_MODEL=<文本模型名称>

VISION_API_BASE=<视觉模型API地址>
VISION_API_KEY=<视觉模型API Key>
VISION_MODEL=<视觉模型名称>
```

生产启动安全阀：

- `APP_ENV=prod` 时不能使用默认 `JWT_SECRET`。
- 生产不能使用 SQLite。
- 生产 Redis 不能指向 `localhost` 或 `127.0.0.1`。
- 微信、COS bucket、COS endpoint、COS 密钥必须配置。
- 数据库表结构必须通过 Alembic 创建，应用启动不自动建表。

### 17.5 数据库迁移

首次部署前执行：

```bash
cd backend
alembic upgrade head
```

迁移要求：

- 生产发布前先在测试库执行一遍。
- 确认所有表、索引、唯一约束创建成功。
- 禁止在生产依赖应用启动自动 `create_all`。
- 每次修改表结构都要新增 migration，不直接改历史 migration。

### 17.6 镜像构建与发布

API 和 Worker 使用同一个 Dockerfile，构建一次镜像：

```bash
docker build -f backend/Dockerfile -t pulselink-api:<version> .
```

API 启动命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker 启动命令：

```bash
rq worker pulselink --url "$REDIS_URL"
```

部署原则：

- API 至少 1 个实例，后续可水平扩容。
- Worker 至少 1 个实例，PDF 量增大后横向扩容。
- API 和 Worker 使用同一版本镜像。
- 发布时先部署 Worker，再部署 API，避免新 API 投递旧 Worker 不认识的任务。

### 17.7 Nginx 与 HTTPS

推荐由 Nginx 或云负载均衡终止 HTTPS：

```text
client -> https://api.example.com -> Nginx/LB -> api:8000
```

Nginx 需要注意：

- 上传相关请求体大小至少大于 50MB。
- API 超时时间不能太短。
- `/api/analysis-tasks/{task_id}` 是轮询接口，应保持轻量。
- PDF 文件不经过 API 中转上传，使用 COS 直传，避免 API 被大文件上传拖垮。

### 17.8 小程序生产配置

小程序侧需要操作：

1. 将后端地址改为生产 API：

```text
https://api.example.com/api
```

2. 登录流程调用：

```text
POST /api/auth/wechat-login
```

3. 上传流程调用：

```text
POST /api/uploads/pdf/presign
PUT COS presigned URL
POST /api/files
POST /api/analysis-tasks
```

4. 分析中页面轮询：

```text
GET /api/analysis-tasks/{task_id}
```

5. 报告页面调用：

```text
GET /api/reports/{task_id}
```

6. 历史页面调用：

```text
GET /api/reports
```

7. 微信小程序后台配置 request 合法域名。

### 17.9 生产联调清单

上线前按顺序验证：

1. `GET /api/health` 返回成功。
2. 真实微信 `code` 可以换取 JWT。
3. 非法或过期 JWT 返回 `401`。
4. 获取 PDF 上传预签名成功。
5. 使用预签名 URL 可以把 PDF 上传到 COS。
6. 调用 `/api/files` 可以登记文件。
7. 重复登记同一用户同一 sha256 文件不会产生重复记录。
8. 调用 `/api/analysis-tasks` 可以创建任务。
9. 相同 `Idempotency-Key` 重复创建任务返回同一个任务。
10. Worker 能从 Redis 取到任务。
11. Worker 能从 COS 下载 PDF。
12. PDF 文本、表格、页面图片 artifact 能正常生成。
13. 文本 LLM 和视觉模型调用成功。
14. 任务最终进入 `completed`。
15. 报告详情可以读取。
16. 历史报告列表可以读取。
17. 表格型 PDF、图片页 PDF、长 PDF 都能跑通。
18. Worker 重启后不会造成重复报告或重复评分数据。

### 17.10 上线验收标准

最小上线标准：

- 全量自动化测试通过。
- Docker 镜像构建成功。
- Alembic 迁移在生产库执行成功。
- API 和 Worker 容器启动成功。
- 微信登录生产联调通过。
- COS 直传生产联调通过。
- 两份样例 PDF 能完整生成报告。
- 任务幂等、文件去重、报告读取全部验证通过。
- 微信小程序后台合法域名配置完成。
- HTTPS 证书有效。
- API 错误日志和 Worker 失败日志可查看。

### 17.11 监控与告警

上线后至少监控：

- API 5xx 错误率。
- API P95 响应时间。
- Worker 任务成功率。
- Worker 任务平均耗时。
- Worker 失败任务数量。
- Redis 队列积压数量。
- LLM 调用失败率。
- LLM 调用超时率。
- COS 上传失败率。
- MySQL 连接数和慢查询。
- Redis 内存和连接数。

关键告警：

- 连续 5 分钟 API 5xx 超过阈值。
- Worker 队列积压持续增加。
- 单个任务超过最大允许处理时间。
- LLM 或视觉模型调用连续失败。
- MySQL 或 Redis 连接失败。

### 17.12 回滚方案

代码回滚：

- API 和 Worker 回滚到上一版镜像。
- 回滚时 API 和 Worker 版本必须一致。
- 回滚后观察任务创建、任务消费、报告读取是否恢复。

数据库回滚：

- 能不回滚数据库就不回滚数据库。
- 生产 migration 发布前必须先备份。
- 如果 migration 只新增表或新增 nullable 字段，通常优先代码回滚。
- 如果 migration 删除字段或改字段类型，必须提前设计向前兼容方案。

任务回滚：

- 已进入 Redis 的任务不直接删除。
- 如果旧 Worker 无法处理新任务，先暂停 API 创建任务，再处理队列。
- 失败任务保留错误信息，后续通过后台或脚本重试。

### 17.13 上线当天操作顺序

推荐顺序：

1. 冻结发布版本。
2. 确认测试环境全量验证通过。
3. 备份生产 MySQL。
4. 构建并推送 Docker 镜像。
5. 执行 `alembic upgrade head`。
6. 启动或更新 Worker。
7. 启动或更新 API。
8. 检查 `/api/health`。
9. 用真实微信登录验证 JWT。
10. 用小 PDF 验证 COS 直传和任务创建。
11. 用两份样例 PDF 验证完整分析报告。
12. 配置或确认微信小程序合法域名。
13. 发布小程序体验版或灰度版本。
14. 观察日志、队列、任务耗时和错误率。
15. 确认无异常后扩大使用范围。
