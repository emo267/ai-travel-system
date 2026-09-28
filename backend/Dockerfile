FROM python:3.12-slim

WORKDIR /app

# 让 scripts/ 下的脚本可以直接 python scripts/xxx.py 运行并 import app
ENV PYTHONPATH=/app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .

# 使用清华镜像加速（与 pyproject.toml 保持一致）；torch +cpu 轮仅存在于阿里云 CPU 目录，用 find-links 补充
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/

# 复制应用代码（.dockerignore 会排除 venv、.env 等）
COPY . .

EXPOSE 8000

# 默认启动 API 服务；worker 服务在 docker-compose 里覆盖 command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
