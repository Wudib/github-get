"""GitHub 数据源封装：REST 搜索、GraphQL 批量取星、Trending 页面解析。"""
import logging
import re
import time

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("gh.client")

STARS_GAINED_RE = re.compile(
    r"([\d,]+)\s+stars?\s+(today|this week|this month)", re.IGNORECASE
)
TRENDING_PERIOD_MAP = {
    "daily": "today",
    "weekly": "this week",
    "monthly": "this month",
}


class RateLimited(Exception):
    """GitHub 主/次限流，调用方应稍后重试。"""


def _to_int(text):
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def parse_trending_html(html, period="weekly"):
    """解析 github.com/trending 页面，返回仓库字典列表。"""
    soup = BeautifulSoup(html, "html.parser")
    expected = TRENDING_PERIOD_MAP.get(period, "this week")
    results = []
    for rank, article in enumerate(soup.select("article.Box-row"), start=1):
        title_link = article.select_one("h2 a")
        if not title_link or not title_link.get("href"):
            continue
        full_name = "/".join(title_link["href"].strip("/").split("/")[:2])
        if "/" not in full_name:
            continue

        desc_el = article.select_one("p")
        lang_el = article.select_one('[itemprop="programmingLanguage"]')
        star_link = article.select_one('a[href$="/stargazers"]')
        fork_link = article.select_one('a[href$="/forks"]')

        stars_gained = None
        gained_el = article.select_one("span.float-sm-right")
        if gained_el:
            match = STARS_GAINED_RE.search(gained_el.get_text(" ", strip=True))
            if match and match.group(2).lower() == expected:
                stars_gained = _to_int(match.group(1))
            elif match:
                stars_gained = _to_int(match.group(1))

        owner, name = full_name.split("/", 1)
        results.append(
            {
                "full_name": full_name,
                "owner": owner,
                "name": name,
                "description": (desc_el.get_text(" ", strip=True) if desc_el else "")[:600],
                "language": lang_el.get_text(strip=True) if lang_el else "",
                "stars": _to_int(star_link.get_text(strip=True)) if star_link else 0,
                "forks": _to_int(fork_link.get_text(strip=True)) if fork_link else 0,
                "stars_gained": stars_gained,
                "rank": rank,
                "html_url": "https://github.com/" + full_name,
            }
        )
    return results


class GitHubClient:
    def __init__(self, cfg):
        self.cfg = cfg
        headers = {
            "User-Agent": cfg.user_agent,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if cfg.github_token:
            headers["Authorization"] = "Bearer " + cfg.github_token
        self.http = httpx.Client(
            headers=headers, timeout=cfg.request_timeout, follow_redirects=True
        )
        self.web = httpx.Client(
            headers={
                "User-Agent": cfg.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=cfg.request_timeout,
            follow_redirects=True,
        )
        self.rate_limit = {"remaining": None, "limit": None, "reset": None}

    def close(self):
        for client in (self.http, self.web):
            try:
                client.close()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ REST
    def _capture_rate_limit(self, resp):
        remaining = resp.headers.get("X-RateLimit-Remaining")
        limit = resp.headers.get("X-RateLimit-Limit")
        reset = resp.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self.rate_limit["remaining"] = _to_int(remaining)
            self.rate_limit["limit"] = _to_int(limit)
            self.rate_limit["reset"] = _to_int(reset)

    def _rest_get(self, path, params=None, retries=3):
        url = path if path.startswith("http") else self.cfg.github_api_base + path
        last_error = None
        for attempt in range(retries):
            try:
                resp = self.http.get(url, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
                continue

            self._capture_rate_limit(resp)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                if self._is_primary_rate_limit(resp):
                    raise RateLimited(
                        "GitHub REST 配额耗尽，剩余=%s" % self.rate_limit.get("remaining")
                    )
                wait = min(60, 5 * (attempt + 1))
                log.warning("GitHub 限流(%s)，%ss 后重试", resp.status_code, wait)
                time.sleep(wait)
                last_error = RateLimited("HTTP %s" % resp.status_code)
                continue
            last_error = RuntimeError("GitHub REST %s: %s" % (resp.status_code, resp.text[:200]))
            time.sleep(1.5 * (attempt + 1))
        if isinstance(last_error, RateLimited):
            raise last_error
        raise RuntimeError("GitHub REST 请求失败: %s" % last_error)

    @staticmethod
    def _is_primary_rate_limit(resp):
        return resp.headers.get("X-RateLimit-Remaining") == "0"

    def search_repositories(self, query, sort="stars", order="desc", per_page=100, pages=1):
        """调用 /search/repositories，返回标准化后的仓库列表。"""
        items = []
        for page in range(1, pages + 1):
            payload = self._rest_get(
                "/search/repositories",
                {
                    "q": query,
                    "sort": sort,
                    "order": order,
                    "per_page": min(per_page, 100),
                    "page": page,
                },
            )
            if not payload:
                break
            batch = payload.get("items") or []
            items.extend(batch)
            if len(batch) < min(per_page, 100):
                break
            # 搜索接口有独立的 30 次/分钟限制，稍微放缓
            time.sleep(2.0)
        return items

    def get_repo(self, full_name):
        return self._rest_get("/repos/" + full_name)

    # --------------------------------------------------------------- GraphQL
    def graphql_star_batch(self, full_names):
        """一次批量拉取最多 100 个仓库的实时 star/fork 等字段。"""
        if not self.cfg.github_token:
            return {}
        chunks = [full_names[i : i + 100] for i in range(0, len(full_names), 100)]
        out = {}
        for chunk in chunks:
            query = self._build_graphql_query(chunk)
            try:
                resp = self.http.post(self.cfg.github_graphql_url, json={"query": query})
            except httpx.HTTPError as exc:
                log.warning("GraphQL 请求异常: %s", exc)
                continue
            if resp.status_code != 200:
                log.warning("GraphQL HTTP %s: %s", resp.status_code, resp.text[:200])
                if resp.status_code in (401, 403):
                    raise RateLimited("GraphQL 鉴权/限流失败: HTTP %s" % resp.status_code)
                continue
            payload = resp.json()
            data = payload.get("data") or {}
            rate = data.get("rateLimit") or {}
            if rate.get("remaining") is not None:
                self.rate_limit["remaining"] = rate.get("remaining")
                self.rate_limit["limit"] = rate.get("limit")
            for alias, item in data.items():
                if alias == "rateLimit" or not item:
                    continue
                name = item.get("nameWithOwner")
                if not name:
                    continue
                topics = [
                    node["topic"]["name"]
                    for node in ((item.get("repositoryTopics") or {}).get("nodes") or [])
                    if node and node.get("topic")
                ]
                out[name] = {
                    "full_name": name,
                    "description": item.get("description") or "",
                    "stars": item.get("stargazerCount") or 0,
                    "forks": item.get("forkCount") or 0,
                    "open_issues": ((item.get("issues") or {}).get("totalCount")) or 0,
                    "pushed_at": item.get("pushedAt"),
                    "created_at": item.get("createdAt"),
                    "archived": bool(item.get("isArchived")),
                    "language": ((item.get("primaryLanguage") or {}) or {}).get("name") or "",
                    "topics": topics,
                    "homepage": item.get("homepageUrl") or "",
                    "license": ((item.get("licenseInfo") or {}) or {}).get("spdxId") or "",
                    "html_url": item.get("url") or ("https://github.com/" + name),
                }
            time.sleep(0.8)
        return out

    @staticmethod
    def _build_graphql_query(full_names):
        parts = [
            "query {",
            "  rateLimit { remaining limit resetAt }",
        ]
        for idx, full_name in enumerate(full_names):
            if "/" not in full_name:
                continue
            owner, name = full_name.split("/", 1)
            parts.append(
                '  r%d: repository(owner: "%s", name: "%s") {'
                " databaseId nameWithOwner url description stargazerCount forkCount"
                " pushedAt createdAt isArchived homepageUrl"
                " primaryLanguage { name }"
                " licenseInfo { spdxId }"
                " issues(states: OPEN) { totalCount }"
                " repositoryTopics(first: 20) { nodes { topic { name } } }"
                " }" % (idx, owner.replace('"', ""), name.replace('"', ""))
            )
        parts.append("}")
        return "\n".join(parts)

    # -------------------------------------------------------------- Trending
    def fetch_trending(self, period="weekly", language=""):
        """抓取 GitHub Trending 页面并解析，返回仓库列表。"""
        url = self.cfg.trending_base
        if language:
            url = "%s/%s" % (url, language.strip().lower())
        params = {"since": period}
        resp = self.web.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError("Trending 页面返回 %s (%s)" % (resp.status_code, resp.url))
        return parse_trending_html(resp.text, period=period)
