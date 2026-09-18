# 构建上下文 = 项目根目录（见 docker-compose.yml 的 build.context）
# 刻意不使用 `# syntax=docker/dockerfile:1` 指令：内网离线环境下 BuildKit
# 无法从 Docker Hub 拉取该前端镜像，去掉后使用内置前端，构建不依赖外网。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖单独一层，便于缓存
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY frontend /app/static

ENV DATA_DIR=/data \
    STATIC_DIR=/app/static \
    PORT=8000 \
    COLLECT_INTERVAL_MINUTES=60 \
    RETENTION_DAYS=90 \
    HOURLY_KEEP_DAYS=14 \
    TRENDING_PERIODS=weekly \
    DISCOVERY_WINDOWS=7,30,90 \
    DISCOVERY_MIN_STARS=100 \
    DISCOVERY_PAGES=2 \
    ENRICH_LIMIT=25 \
    MAX_TRACKED_REPOS=3000 \
    RUN_ON_STARTUP=true

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status==200 else 1)"

# 单 worker：内置调度器只能在一个进程里运行
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
