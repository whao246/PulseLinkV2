# PulseLinkV2 腾讯云部署说明

## 1. 生产组件

- API / Worker：同一个 Docker 镜像，不同启动命令。
- MySQL：腾讯云 MySQL。
- Redis：腾讯云 Redis。
- Storage：腾讯云 COS。
- 入口：HTTPS 域名 + Nginx 或腾讯云负载均衡。

## 2. 必需环境变量

- `APP_ENV=prod`
- `DATABASE_URL=mysql+pymysql://<user>:<password>@<tencent-mysql-host>:3306/pulselink`
- `REDIS_URL=redis://:<password>@<tencent-redis-host>:6379/0`
- `QUEUE_NAME=pulselink`
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
- `VISION_API_BASE=https://api.minimax.chat/v1`
- `VISION_API_KEY=<MiniMax API Key>`
- `VISION_MODEL=MiniMax-M3`

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
