#!/usr/bin/env bash
# 在【无外网的内网服务器】上执行：加载离线镜像并启动服务
# 用法：./scripts/offline-load.sh [镜像tar路径]
set -euo pipefail

cd "$(dirname "$0")/.."

TAR="${1:-}"
if [ -z "${TAR}" ]; then
  TAR="$(ls -1 github-radar-*.tar ../github-radar-*.tar 2>/dev/null | head -n1 || true)"
fi
if [ -z "${TAR}" ] || [ ! -f "${TAR}" ]; then
  echo "找不到镜像 tar 包，请把 github-radar-<arch>.tar 放到当前目录，或作为参数传入。" >&2
  exit 1
fi

echo "==> 导入镜像 ${TAR}"
docker load -i "${TAR}"

if [ ! -f .env ]; then
  echo "==> 未发现 .env，从 .env.example 复制（记得填 GITHUB_TOKEN）"
  cp .env.example .env
fi

echo "==> 启动服务"
docker compose up -d --no-build

PORT="$(grep -E '^HOST_PORT=' .env | cut -d= -f2 | tr -d ' ' || true)"
PORT="${PORT:-8080}"
sleep 3
docker compose ps
echo
echo "访问地址： http://<服务器IP>:${PORT}"
