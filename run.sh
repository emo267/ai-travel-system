#!/usr/bin/env bash
#
# 一键启动本地开发环境（混合模式）：
#   前提：Docker Desktop 由用户手动启动，deploy 栈随 Docker 自启
#         （travel-mysql / travel-redis / travel_nginx / travel-backend / travel-worker）。
#   本脚本职责：
#     1. 等待 MySQL(3306) / Redis(6379) 就绪（不主动拉起整个 deploy）；
#     2. 停止会冲突的 travel-backend / travel-worker 容器
#        （否则 8000 端口被占、Celery 任务被容器重复消费）；
#     3. 本地启动 FastAPI(uvicorn --reload) + Celery worker + Vite 前端。
#   保留运行：travel-mysql / travel-redis / travel_nginx。
#
# 用法：./run.sh        Ctrl+C 停止全部本地服务
#       ./run.sh -h     查看帮助

set -euo pipefail

# 从 cmd 里经 run.bat 调用时，PATH 里可能没有 MSYS 工具目录
if [ -d /usr/bin ]; then
  PATH="/usr/bin:/bin:$PATH"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"
DEPLOY="$ROOT/deploy"

BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://localhost:5173"

# 随 deploy 自启、但会与本地开发冲突的容器
CONFLICT_CONTAINERS=(travel-backend travel-worker)

PIDS=()

say() { printf '[run] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*"; }
die() {
  printf '[error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
用法：./run.sh

前提：先手动启动 Docker Desktop，deploy 栈（mysql/redis/nginx）会随之自启。
脚本会停掉冲突的 travel-backend / travel-worker 容器，然后在本地启动：
  FastAPI 后端   uvicorn --reload   http://127.0.0.1:8000
  Celery worker  Windows 下使用 solo 池
  Vite 前端      npm run dev        http://localhost:5173
日志写入 logs/ 目录，Ctrl+C 停止全部本地进程。
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      printf '\n未知参数：%s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) IS_WIN=1 ;;
  *) IS_WIN=0 ;;
esac

if [ "$IS_WIN" = 1 ]; then
  VENV_BIN="$BACKEND/.venv/Scripts"
  PY_BIN="$VENV_BIN/python.exe"
  CELERY_BIN="$VENV_BIN/celery.exe"
else
  VENV_BIN="$BACKEND/.venv/bin"
  PY_BIN="$VENV_BIN/python"
  CELERY_BIN="$VENV_BIN/celery"
fi

port_open() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

preflight() {
  if [ ! -f "$BACKEND/.env" ]; then
    die "缺少 backend/.env，请先执行 cp backend/.env.example backend/.env 并填入 DEEPSEEK_API_KEY"
  fi
  if [ ! -x "$PY_BIN" ]; then
    die "未找到虚拟环境 $VENV_BIN，请先执行：cd backend && uv sync"
  fi
  if [ ! -d "$FRONTEND/node_modules" ]; then
    die "缺少前端依赖，请先执行：cd frontend && npm install"
  fi
  mkdir -p "$LOGS"
}

ensure_docker() {
  command -v docker >/dev/null 2>&1 || die "未安装 docker，请先安装并启动 Docker Desktop"
  docker info >/dev/null 2>&1 || die "docker 未运行：请先手动启动 Docker Desktop，待 deploy 容器自启后重试"
}

# deploy 栈随 Docker 自启，这里只等待基础设施就绪；
# 仅当 docker 在跑但 mysql/redis 缺失时才兜底拉起这两个容器
wait_deps() {
  local waited=0
  while [ "$waited" -lt 90 ]; do
    if port_open 3306 && port_open 6379; then
      say "MySQL(3306) / Redis(6379) 已就绪"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done

  warn "MySQL/Redis 90s 未就绪，尝试仅拉起基础设施容器 ..."
  (cd "$DEPLOY" && docker compose up -d mysql redis) || true
  waited=0
  while [ "$waited" -lt 60 ]; do
    if port_open 3306 && port_open 6379; then
      say "MySQL(3306) / Redis(6379) 已就绪"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

# 无条件停止冲突容器；带重试以覆盖"容器比 mysql 晚几秒才自启"的竞态
stop_conflicts() {
  local attempt name running=()
  for attempt in 1 2 3; do
    running=()
    for name in "${CONFLICT_CONTAINERS[@]}"; do
      if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
        running+=("$name")
      fi
    done
    [ "${#running[@]}" -eq 0 ] && break
    say "停止冲突容器：${running[*]} ..."
    docker stop "${running[@]}" >/dev/null 2>&1 || true
    sleep 2
  done

  for name in "${CONFLICT_CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
      die "容器 $name 仍在运行，请手动执行：docker stop $name"
    fi
  done
  say "冲突容器已停止（travel-mysql / travel-redis / travel_nginx 保留运行）"
}

check_local_ports() {
  if port_open 8000; then
    die "8000 端口仍被占用，请释放后重试：netstat -ano | findstr :8000 查 PID，再 taskkill /PID <pid> /F"
  fi
  if port_open 5173; then
    FRONTEND_PORT_BUSY=1
    warn "5173 已被占用，Vite 会自动换端口；届时需同步修改 backend/.env 的 CORS_ORIGINS"
  else
    FRONTEND_PORT_BUSY=0
  fi
}

# taskkill 认的是 Windows PID，而 $! 给的是 MSYS 的虚拟 PID，必须经 /proc 转换
win_pid() {
  cat "/proc/$1/winpid" 2>/dev/null | tr -d '[:space:]'
}

kill_tree() {
  local pid="${1:-}" wpid
  [ -n "$pid" ] || return 0
  if [ "$IS_WIN" = 1 ]; then
    wpid="$(win_pid "$pid")"
    if [ -n "$wpid" ]; then
      taskkill //PID "$wpid" //T //F >/dev/null 2>&1 || true
    fi
    kill -KILL "$pid" >/dev/null 2>&1 || true
  else
    pkill -TERM -P "$pid" >/dev/null 2>&1 || true
    kill -TERM "$pid" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  printf '\n'
  say "正在停止本地服务 ..."
  local pid
  for pid in "${PIDS[@]:-}"; do
    kill_tree "$pid"
  done
  sleep 1
  say "已停止（docker 容器不受影响）"
}

start_backend() {
  say "启动后端 uvicorn（热重载，监听 $BACKEND_URL）..."
  (
    cd "$BACKEND"
    exec "$PY_BIN" -m uvicorn app.main:app \
      --host 127.0.0.1 --port 8000 \
      --reload --reload-dir app
  ) >>"$LOGS/backend.log" 2>&1 &
  BACKEND_PID=$!
  PIDS+=("$BACKEND_PID")
}

start_worker() {
  say "启动 Celery worker ..."
  local pool_args=()
  if [ "$IS_WIN" = 1 ]; then
    pool_args=(--pool=solo)
  fi
  (
    cd "$BACKEND"
    exec "$CELERY_BIN" -A app.tasks.celery_app:celery_app worker \
      --loglevel=info "${pool_args[@]}"
  ) >>"$LOGS/worker.log" 2>&1 &
  PIDS+=("$!")
}

start_frontend() {
  say "启动前端 Vite ..."
  (
    cd "$FRONTEND"
    exec npm run dev
  ) >>"$LOGS/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  PIDS+=("$FRONTEND_PID")
}

wait_http() {
  local url="$1" timeout="$2" pid="$3" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    if curl -fsS -o /dev/null --max-time 2 "$url" 2>/dev/null; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

# 单个 tail 进程跟三个文件：管道形式在 MSYS 下无法整棵杀掉，会留下孤儿 tail
stream_logs() {
  cd "$ROOT"
  tail -n 0 -f logs/backend.log logs/worker.log logs/frontend.log &
  PIDS+=("$!")
}

print_banner() {
  printf '\n'
  say "全部就绪："
  printf '      前端    %s\n' "$FRONTEND_URL"
  printf '      后端    %s   （接口文档 %s/docs）\n' "$BACKEND_URL" "$BACKEND_URL"
  printf '      日志    logs/backend.log  logs/worker.log  logs/frontend.log\n'
  printf '\n'
  warn "端口 80 的 nginx 仍是 docker 里的旧构建，开发请走 %s" "$FRONTEND_URL"
  warn "首次提问会下载 bge-m3 向量模型（约 2GB，已指向 hf-mirror.com），耗时较长属正常"
  say "初始化知识库（可选）：cd $BACKEND && \"$PY_BIN\" scripts/seed_knowledge.py"
  printf '\n'
  say "按 Ctrl+C 停止本地服务（不会动 docker 容器）"
  printf '\n'
}

preflight
ensure_docker
wait_deps || die "等待 MySQL/Redis 超时，请查看：cd deploy && docker compose logs mysql"
stop_conflicts
check_local_ports

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

trap cleanup EXIT INT TERM

: >"$LOGS/backend.log"
: >"$LOGS/worker.log"
: >"$LOGS/frontend.log"

start_backend
start_worker
start_frontend

if ! wait_http "$BACKEND_URL/health" 60 "$BACKEND_PID"; then
  warn "后端 60s 内未就绪，最近日志："
  tail -n 30 "$LOGS/backend.log" || true
  exit 1
fi

if [ "$FRONTEND_PORT_BUSY" = 0 ]; then
  if ! wait_http "$FRONTEND_URL/" 60 "$FRONTEND_PID"; then
    warn "前端 60s 内未就绪，最近日志："
    tail -n 30 "$LOGS/frontend.log" || true
  fi
fi

print_banner
stream_logs

wait
