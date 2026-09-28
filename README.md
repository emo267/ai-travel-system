# 旅行计划智能助手

基于大模型多 Agent 协作的旅行行程生成与问答系统。用户输入目的地、日期、预算和偏好，系统调用 DeepSeek 生成逐日行程，经路线优化与评审打分后落库；另提供带工具调用的流式对话助手。

## 核心能力

- **行程生成**：按天数产出景点、餐饮、住宿、交通与预算明细，结果以 JSON 落库。
- **多 Agent 协作与评审闭环**：LangGraph 编排 `Master（生成）→ Route（优化路线）→ Review（评审打分）`，评审不通过自动回到 Master 重生成，最多 3 次。
- **知识库增强检索（RAG）**：攻略与避雷文档经 `bge-m3` 向量化后存入 Chroma，生成时检索注入，减少模型编造。
- **对话助手**：SSE 流式输出，支持 Tavily 联网搜索、和风天气、高德 POI 等工具调用，会话历史与用户偏好持久化。
- **用户体系**：JWT 注册 / 登录 / 刷新，接口按用户隔离数据。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI、SQLAlchemy 2.0、Pydantic v2、Pydantic Settings |
| Agent | LangGraph、LangChain、DeepSeek（`deepseek-chat` 结构化输出 + `deepseek-flash` 对话/工具） |
| RAG | sentence-transformers（`BAAI/bge-m3`）、Chroma、langchain-text-splitters |
| 异步 | Celery + Redis |
| 存储 | MySQL 8（业务数据）、Chroma（向量，本地持久化） |
| 前端 | Vue 3、Vite、Element Plus、Pinia、高德地图 JS API |
| 部署 | Docker Compose、Nginx |

## 架构

```
                       ┌───────────────┐
   浏览器 ──:5173(dev)─▶│  Vue 3 前端    │
            :80(prod)  └───────┬───────┘
                             │ /api/v1/*
                             ▼
                       ┌───────────────┐      ┌──────────┐
                       │    FastAPI    │─────▶│ MySQL 8  │
                       │    :8000      │      └──────────┘
                       └───────┬───────┘
                               │ 投递任务
                               ▼
                       ┌───────────────┐      ┌──────────┐
                       │ Celery worker │─────▶│  Redis   │
                       └───────┬───────┘      └──────────┘
                               │ LangGraph
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        Master Agent ──▶ Route Agent ──▶ Review Agent
              ▲                                 │
              └───── 评审不通过，重试（≤3 次）─────┘
                               │
                    ┌──────────┴───────────┐
                    ▼                      ▼
              Chroma（bge-m3）        外部工具
               攻略/避雷向量库   DeepSeek·Tavily·和风天气·高德
```

行程生成是异步任务：创建任务只落 `pending` 记录，触发后由 Celery 消费，前端轮询状态接口获取结果。

## 目录结构

```
travel_system/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # 路由：auth / travel / chat
│   │   ├── agents/          # LangGraph 图、三个 Agent 及提示词
│   │   ├── rag/             # 嵌入、检索、向量库、知识加载
│   │   ├── llm/             # DeepSeek 客户端与提示词
│   │   ├── db/              # 模型、会话、缺列补偿
│   │   ├── tasks/           # Celery app 与任务
│   │   ├── core/            # 配置、日志、异常、JWT/密码
│   │   └── main.py          # 应用入口
│   ├── scripts/             # seed_knowledge.py 知识库入库
│   ├── tests/               # unit / integration / functional
│   └── pyproject.toml       # 依赖（uv 管理）
├── frontend/                # Vue 3 + Vite 前端
│   └── src/{api,views,components,store,router}
├── deploy/                  # docker-compose、nginx、环境变量
├── docs/                    # 验收流程等文档
└── run.sh                   # 本地混合模式一键启动
```

## 快速开始

### 方式一：Docker Compose（完整栈）

**前置：** Docker Desktop。首次启动会下载嵌入模型 `BAAI/bge-m3`（约 2.3GB），耗时较长属正常。

1. 创建环境变量文件（`deploy/env/*.env` 不入版本库，需自行创建）：

   ```bash
   # deploy/env/mysql.env
   MYSQL_ROOT_PASSWORD=123456
   MYSQL_DATABASE=travel_planner
   ```

   ```bash
   # deploy/env/backend.env —— 变量清单见下方「环境变量」
   DATABASE_URL=mysql+pymysql://root:123456@mysql:3306/travel_planner?charset=utf8mb4
   REDIS_URL=redis://redis:6379/0
   JWT_SECRET_KEY=<一段足够长的随机字符串>
   # ... 其余见下表
   ```

2. 构建并启动：

   ```bash
   cd deploy
   docker compose up -d --build
   ```

3. 确认服务：

   ```bash
   docker compose ps
   curl http://localhost:8000/health
   ```

4. 初始化知识库（每次执行先清空再入库，可反复运行）：

   ```bash
   docker exec travel-backend python scripts/seed_knowledge.py
   ```

5. 打开 <http://localhost:8000/docs> 走通接口；前端经 Nginx 在 <http://localhost>。

   容器名：`travel-backend`、`travel-worker`、`travel-mysql`、`travel-redis`、`travel_nginx`。

### 方式二：本地混合开发（run.sh）

前提是 Docker Desktop 已启动（deploy 栈随 Docker 自启）。脚本会等待 MySQL/Redis 就绪、停掉冲突的 `travel-backend` / `travel-worker` 容器，然后在本地以热重载方式启动后端、Worker 与前端。

```bash
cd backend && uv sync          # 首次
cd ../frontend && npm install  # 首次
cp backend/.env.example backend/.env   # 填入 DEEPSEEK_API_KEY 等
cd .. && ./run.sh
```

| 服务 | 地址 |
|---|---|
| 前端（Vite） | <http://localhost:5173> |
| 后端（uvicorn --reload） | <http://127.0.0.1:8000>，文档 `/docs` |

日志写入 `logs/`，`Ctrl+C` 停止本地进程（不影响 Docker 容器）。

> Windows 用户请用 Git Bash 或 WSL。Git Bash 下有两个常见坑：传给 docker 的 `/app` 之类路径会被 MSYS 改写（加 `MSYS_NO_PATHCONV=1`）；`curl -d` 内联中文请求体会因命令行编码报 `400`，应把 JSON 写进 UTF-8 文件后用 `-d @body.json`。

## 环境变量

| 变量 | 必填 | 用途 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 是 | 生成行程与对话的大模型 |
| `DATABASE_URL` | 是 | MySQL 连接串 |
| `REDIS_URL` | 是 | Celery broker / 结果后端 |
| `JWT_SECRET_KEY` | 是 | 签发 token |
| `TAVILY_API_KEY` | 否 | 联网搜索攻略 |
| `QWEATHER_API_HOST` / `QWEATHER_API_KEY` | 否 | 和风天气（Host 为账号专属，形如 `xxx.re.qweatherapi.com`） |
| `AMAP_API_KEY` | 否 | 高德 Web 服务，POI 搜索 |
| `VITE_AMAP_KEY` / `VITE_AMAP_SECURITY_CODE` | 否 | 前端高德 JS API（与 `AMAP_API_KEY` 不是同一个 Key） |
| `HF_ENDPOINT` | 否 | 嵌入模型下载镜像，默认 `https://hf-mirror.com` |

非必填项缺失时对应工具自动降级，不影响基础行程生成。模板见 `.env.example`、`backend/.env.example`、`frontend/.env.example`。真实 `.env` 已被 `.gitignore` 排除。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录，返回 access / refresh token |
| POST | `/api/v1/auth/refresh` | 刷新 token |
| GET | `/api/v1/auth/me` | 当前用户 |
| POST | `/api/v1/travel/tasks` | 创建行程任务 |
| GET | `/api/v1/travel/tasks` | 任务列表 |
| GET | `/api/v1/travel/tasks/{id}` | 任务详情 |
| PUT | `/api/v1/travel/tasks/{id}` | 修改任务 |
| DELETE | `/api/v1/travel/tasks/{id}` | 删除任务 |
| POST | `/api/v1/travel/tasks/{id}/generate` | 触发异步生成 |
| GET | `/api/v1/travel/tasks/{id}/status` | 轮询生成状态与结果 |
| POST | `/api/v1/chat/stream` | 对话（SSE 流式） |
| GET | `/api/v1/chat/conversations` | 会话列表 |
| GET | `/api/v1/chat/conversations/{id}/messages` | 会话消息 |
| PUT / DELETE | `/api/v1/chat/conversations/{id}` | 重命名 / 删除会话 |
| GET / PUT | `/api/v1/chat/preferences` | 用户偏好 |

## 相关文档

- [验收流程](docs/acceptance-guide.md)：按代码与容器配置核对过的端到端验收步骤与常见问题。

## 测试

```bash
cd backend && uv run pytest
```
