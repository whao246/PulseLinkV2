# PulseLinkV2 腾讯云部署说明

## 1. 当前上线结论

当前代码适合先部署到腾讯云 `staging` 或小范围内测环境。正式生产对外前必须确认：

- 生产环境 `APP_ENV=prod`，`/api/auth/test-login` 已禁用。
- API、Worker 使用 `docker-compose.prod.yml`，不能使用本地开发的 `docker-compose.yml`。
- 业务接口使用 `Authorization: Bearer <token>` 识别用户，不再使用硬编码用户。
- COS 上传使用带时效的 PUT 预签名 Authorization。
- MiniMax key、COS key、JWT secret 均已重新生成，不能使用调试时暴露过的 key。

## 2. 生产组件

- API / Worker：同一个 Docker 镜像，不同启动命令。
- MySQL：腾讯云 MySQL。
- Redis：腾讯云 Redis。
- Storage：腾讯云 COS。
- 入口：HTTPS 域名 + Nginx 或腾讯云负载均衡。

## 3. 必需环境变量

生产推荐使用 `.env.prod` 或云平台密钥管理，不要把真实密钥提交到 Git。

- `APP_ENV=prod`
- `DATABASE_URL=mysql+pymysql://<user>:<password>@<tencent-mysql-host>:3306/pulselink`
- `REDIS_URL=redis://:<password>@<tencent-redis-host>:6379/0`
- `QUEUE_NAME=pulselink`
- `RQ_JOB_TIMEOUT_SECONDS=1800`
- `JWT_SECRET=<至少32位强随机字符串>`
- `WECHAT_APP_ID=<微信小程序AppID>`
- `WECHAT_APP_SECRET=<微信小程序AppSecret>`
- `COS_REGION=<腾讯云COS地域>`
- `COS_BUCKET=<腾讯云COS bucket>`
- `COS_ENDPOINT=https://<bucket>.cos.<region>.myqcloud.com`
- `COS_SECRET_ID=<腾讯云SecretId>`
- `COS_SECRET_KEY=<腾讯云SecretKey>`
- `LLM_API_BASE=https://api.minimax.chat/v1`
- `LLM_API_KEY=<MiniMax API Key>`
- `LLM_MODEL=MiniMax-M3`
- `LLM_TIMEOUT_SECONDS=360`
- `LLM_REASONING_SPLIT=true`
- `VISION_API_BASE=https://api.minimax.chat/v1`
- `VISION_API_KEY=<MiniMax API Key>`
- `VISION_MODEL=MiniMax-M3`

## 4. 发布顺序

1. 创建腾讯云 MySQL、Redis、COS bucket。
2. 配置 MySQL/Redis 安全组或白名单，只允许 API/Worker 所在机器访问。
3. 配置 COS CORS，允许小程序或前端域名发起 `PUT` 上传。
4. 在服务器写入 `.env.prod`，填入上面的生产环境变量。
5. 构建镜像：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml build
```

6. 执行数据库迁移：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api alembic -c alembic.ini upgrade head
```

7. 启动 API 和 Worker：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d api worker
```

8. 检查容器状态和日志：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f api
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f worker
```

9. 检查健康接口：

```bash
curl -i https://<api-domain>/api/health
```

10. 验证业务链路：微信登录获取 token、PDF 预签名、上传 COS、登记文件、创建分析任务、Worker 消费、查看任务和报告。

## 5. 生产启动文件

生产只能使用：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d api worker
```

不要用本地开发的 `docker-compose.yml` 部署生产，因为它包含：

- `uvicorn --reload`
- 本地源码 volume 挂载
- 本地 MySQL/Redis/MinIO 依赖
- 本地样例 PDF 挂载

## 6. 验证 curl

健康检查：

```bash
curl -i https://<api-domain>/api/health
```

微信登录：

```bash
curl -s -X POST https://<api-domain>/api/auth/wechat-login \
  -H "Content-Type: application/json" \
  -d '{
    "code": "<wx.login 返回的 code>"
  }' | jq
```

获取 PDF 上传预签名：

```bash
curl -s -X POST https://<api-domain>/api/uploads/pdf/presign \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access-token>" \
  -d '{
    "file_name": "sample.pdf",
    "file_size": 1024,
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "content_type": "application/pdf"
  }' | jq
```

登记文件：

```bash
curl -s -X POST https://<api-domain>/api/files \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access-token>" \
  -H "Idempotency-Key: file-prod-001" \
  -d '{
    "filename": "sample.pdf",
    "content_type": "application/pdf",
    "size_bytes": 1024,
    "storage_uri": "cos://<bucket>/uploads/<user>/<yyyy>/<mm>/sample.pdf",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }' | jq
```

创建任务：

```bash
curl -s -X POST https://<api-domain>/api/analysis-tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access-token>" \
  -H "Idempotency-Key: task-prod-001" \
  -d '{
    "file_id": "<file_id>",
    "options": {
      "enable_vision": true
    }
  }' | jq
```

查看任务：

```bash
curl -s https://<api-domain>/api/analysis-tasks/<task_id> \
  -H "Authorization: Bearer <access-token>" | jq
```

## 7. 腾讯云检查项

- MySQL 白名单允许 API/Worker 访问。
- Redis 白名单允许 API/Worker 访问。
- COS bucket CORS 允许小程序上传所需方法和请求头。
- HTTPS 域名已备案并配置到微信小程序 request 合法域名。
- 生产环境不使用仓库里的 `.env` 文件保存密钥。
- 旧 MiniMax key 已作废，线上使用新 key。
- `JWT_SECRET` 至少 32 位，并且不同环境使用不同值。
