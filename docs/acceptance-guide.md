# 验收流程

本文档已按实际代码与容器配置核对过，命令可直接复制执行。

## 0. 准备

Windows 用户请使用 Git Bash 或 WSL。若用 Git Bash，注意两个坑：

- 传给 docker 的 POSIX 路径（如 `/app`）会被 MSYS 改写成 Windows 路径，命令前加 `MSYS_NO_PATHCONV=1` 可避免；
- `curl -d` 内联中文请求体会因命令行编码非 UTF-8 而报 `400 There was an error parsing the body`，应把 JSON 写进 UTF-8 文件后用 `-d @body.json`。

## 1. 获取 DeepSeek API Key

访问 platform.deepseek.com，注册登录后创建 API Key，格式为 `sk-xxxxxx`。

## 2. 配置 .env

```bash
cp .env.example .env
```

把 `.env` 里的这几个 Key 替换为真实值（缺哪个就少哪块能力，缺失时对应工具会自动降级，不影响行程生成）：

| 变量 | 用途 | 获取入口 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 生成行程的大模型 | platform.deepseek.com |
| `TAVILY_API_KEY` | 联网搜索攻略 | app.tavily.com |
| `QWEATHER_API_HOST` / `QWEATHER_API_KEY` | 和风天气（Host 是账号专属的，形如 `xxx.re.qweatherapi.com`） | console.qweather.com |
| `AMAP_API_KEY` | 高德地图 Web 服务（POI 搜索；和前端 `VITE_AMAP_KEY` 不是同一个 Key） | console.amap.com |

Key 只在 `.env` 中维护，`docker-compose.yml` 通过 `env_file: ../.env` 注入，不要写死进 compose。`.env` 已在 `.gitignore` 中，不会被提交。

## 3. 构建并启动

```bash
cd deploy
docker compose up -d --build
```

服务清单（注意容器名是连字符，service 名是 `worker` 而不是 `celery_worker`）：

| service | 容器名 |
|---|---|
| backend | `travel-backend` |
| worker | `travel-worker` |
| mysql | `travel-mysql` |
| redis | `travel-redis` |

确认状态：

```bash
docker compose ps
curl http://localhost:8000/health
```

## 4. 初始化知识库

```bash
docker exec travel-backend python scripts/seed_knowledge.py
```

预期输出：

```
已清空知识库 collection
已入库 北京旅行攻略，共 X 个分块
已入库 北京避雷指南，共 X 个分块
```

脚本每次执行都会先清空再入库，可以反复运行。

首次运行会下载嵌入模型 `BAAI/bge-m3`（约 2.3GB，走 `HF_ENDPOINT` 指定的镜像站）。模型缓存在 `hf-cache` 卷里，backend 与 worker 共享，只需下载一次。

> 若用的是改动前构建的旧镜像（没有 `ENV PYTHONPATH=/app`），该命令会报 `ModuleNotFoundError: No module named 'app'`，此时改用 `docker exec travel-backend python -m scripts.seed_knowledge`。

## 5. 走通 API 流程

访问 http://localhost:8000/docs 打开 Swagger。

1. `POST /api/v1/auth/register` 注册用户；
2. `POST /api/v1/auth/login` 获取 `access_token`，点右上角 **Authorize**，**只填 Token 本身，不要加 `Bearer ` 前缀**（接口用 HTTPBearer，Swagger 会自动补前缀）；
3. `POST /api/v1/travel/tasks` 创建行程，`destination` 填 `北京`；
4. 记下响应里的 `task_id`（自增，不一定是 1）；
5. `POST /api/v1/travel/tasks/{task_id}/generate` 触发生成；
6. `GET /api/v1/travel/tasks/{task_id}/status` 轮询到 `completed`。

观察 Celery 日志：

```bash
docker compose logs -f worker
```

预期日志：

```
[Master Agent] 开始处理任务 {task_id}，目的地：北京
[Master Agent] 正在调用 DeepSeek 生成行程...
[Route Agent] 正在优化路线...
[Review Agent] 开始评审行程...
[Review Agent] 评审完成，评分 {score}，是否重排：False
[Graph] 评审通过或达到最大重试次数，结束流程
```

任务正常在 20 秒左右完成。状态接口返回的 `plan` 应为 DeepSeek 真实生成的行程，包含每天的景点、餐饮、住宿、交通。

## 6. 查看数据库

把 `{task_id}` 换成上一步实际返回的值：

```sql
SELECT * FROM travel_plan WHERE task_id = {task_id};
```

确认 `itinerary`、`total_cost`、`weather_summary`、`reason_score` 均已正确落库。其中 `itinerary.review` 是评审模型给出的 `score` / `summary` / `explanation` / `issues`，详情页「评分理由」展示的就是它。命令行执行：

```bash
docker exec travel-mysql mysql -uroot -p123456 --default-character-set=utf8mb4 \
  travel_planner -e "SELECT * FROM travel_plan WHERE task_id = {task_id}\G"
```

## 常见问题

| 现象 | 原因 |
|---|---|
| `ModuleNotFoundError: No module named 'langchain_chroma'` | 镜像过期。`requirements.txt` 已含该依赖，重新 `docker compose up -d --build` |
| 容器反复 `Restarting`，且存在同名 `Created` 孤儿容器 | 旧容器占用了 `container_name`，新容器建不出来。`docker rm -f travel-backend travel-worker` 后重试 |
| 任务卡在 `generating` 后变 `failed` | worker 首次要在任务内下载 2.3GB 模型，超过 `celery_app.py` 的 `task_time_limit=300` 被强杀。确认 `hf-cache` 卷已挂到两个服务 |
| 生成内容里出现 `string地标景点` | 用的是旧代码留下的历史脏数据，不是本次结果 |
