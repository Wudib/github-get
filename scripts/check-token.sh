#!/usr/bin/env bash
# 校验 GITHUB_TOKEN 是否有效，并显示剩余配额
# 用法：
#   ./scripts/check-token.sh              # 读取 .env 里的 GITHUB_TOKEN
#   ./scripts/check-token.sh ghp_xxxxx    # 直接指定 token
set -uo pipefail

cd "$(dirname "$0")/.."

TOKEN="${1:-}"
if [ -z "$TOKEN" ] && [ -f .env ]; then
  TOKEN="$(grep -E '^GITHUB_TOKEN=' .env | head -n1 | cut -d= -f2- | tr -d ' \r\n')"
fi

if [ -z "$TOKEN" ]; then
  echo "❌ .env 里还没有填 GITHUB_TOKEN。"
  echo "   1) 打开 https://github.com/settings/tokens 生成（见 README 第 4 节）"
  echo "   2) 写入 .env：GITHUB_TOKEN=ghp_xxxxxxxx"
  echo "   3) 重新执行：docker compose up -d"
  exit 1
fi

echo "==> 1. 校验身份 (/user)"
USER_JSON="$(curl -s -m 20 -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" https://api.github.com/user)"
LOGIN="$(printf '%s' "$USER_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('login',''))" 2>/dev/null)"
if [ -z "$LOGIN" ]; then
  echo "❌ Token 无效或已过期。GitHub 返回："
  printf '%s\n' "$USER_JSON" | head -c 300; echo
  exit 1
fi
echo "✅ 认证成功，账号：${LOGIN}"

echo "==> 2. 剩余配额 (/rate_limit)"
curl -s -m 20 -H "Authorization: Bearer ${TOKEN}" https://api.github.com/rate_limit \
  | python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)['resources']
for key, label in (('core', 'REST 核心'), ('search', '搜索(每分钟)'), ('graphql', 'GraphQL'), ('code_search', '代码搜索')):
    r = d.get(key)
    if not r:
        continue
    reset = datetime.datetime.fromtimestamp(r['reset']).strftime('%H:%M:%S')
    print('   %-12s %s/%s，重置于 %s' % (label, r['remaining'], r['limit'], reset))
" 2>/dev/null || echo "   (无法解析配额信息)"

echo "==> 3. 探测 GraphQL（本项目用它批量刷新 Star 数）"
GQL="$(curl -s -m 20 -X POST https://api.github.com/graphql \
  -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"query":"{ rateLimit { remaining limit } repository(owner:\"github\",name:\"docs\"){ stargazerCount } }"}')"
if printf '%s' "$GQL" | grep -q '"stargazerCount"'; then
  echo "✅ GraphQL 可用，批量快照功能将正常工作"
else
  echo "⚠️  GraphQL 探测失败（经典 Token 通常没问题；细粒度 Token 需勾选 Public Repositories 只读权限）："
  printf '%s\n' "$GQL" | head -c 300; echo
fi

echo
echo "全部通过后执行：docker compose up -d   # 重建容器让 .env 生效"
