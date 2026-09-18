#!/usr/bin/env bash
# 在【有外网 + 有 Docker】的机器上执行：构建镜像并导出为离线 tar 包
# 用法：./scripts/offline-save.sh [镜像标签]
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE="${1:-github-radar:1.0.0}"
ARCH="$(docker version --format '{{.Server.Arch}}' 2>/dev/null || uname -m)"
OUT_DIR="dist"
TAR="${OUT_DIR}/github-radar-${ARCH}.tar"

echo "==> 构建镜像 ${IMAGE}"
docker build -f backend/Dockerfile -t "${IMAGE}" .

mkdir -p "${OUT_DIR}"
echo "==> 导出镜像到 ${TAR}"
docker save -o "${TAR}" "${IMAGE}"

echo "==> 打包部署文件到 ${OUT_DIR}/deploy-bundle-${ARCH}.tar.gz"
BUNDLE="${OUT_DIR}/bundle"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}"
cp docker-compose.yml .env.example "${BUNDLE}/"
cp -r scripts "${BUNDLE}/"
tar -czf "${OUT_DIR}/deploy-bundle-${ARCH}.tar.gz" -C "${OUT_DIR}" bundle
rm -rf "${BUNDLE}"

echo
echo "完成！请把下面两个文件拷贝到内网服务器："
echo "  ${TAR}"
echo "  ${OUT_DIR}/deploy-bundle-${ARCH}.tar.gz"
echo
echo "内网服务器上执行："
echo "  tar -xzf deploy-bundle-${ARCH}.tar.gz && cd bundle"
echo "  docker load -i ../github-radar-${ARCH}.tar"
echo "  cp .env.example .env && vi .env    # 填 GITHUB_TOKEN"
echo "  docker compose up -d --no-build"
