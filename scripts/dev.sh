#!/usr/bin/env bash
# 本地开发（不使用 Docker）：启动后端并挂载 frontend 目录
# 用法：./scripts/dev.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "==> 创建虚拟环境"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 安装依赖"
pip install -q -r backend/requirements.txt

export DATA_DIR="${DATA_DIR:-$(pwd)/data}"
export STATIC_DIR="${STATIC_DIR:-$(pwd)/frontend}"
export COLLECT_INTERVAL_MINUTES="${COLLECT_INTERVAL_MINUTES:-60}"
export PYTHONPATH="$(pwd)/backend:${PYTHONPATH:-}"

echo "==> 打开 http://127.0.0.1:8000  (Ctrl+C 退出)"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
