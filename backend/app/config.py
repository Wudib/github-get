"""运行期配置：全部来自环境变量，方便在内网部署时按需覆盖。"""
import os


def _env(name, default=""):
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name, default):
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default):
    return _env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


def _env_list(name, default=""):
    return [x.strip() for x in _env(name, default).split(",") if x.strip()]


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Settings:
    def __init__(self):
        # ---- GitHub ----
        self.github_token = _env("GITHUB_TOKEN")
        self.github_api_base = _env("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
        self.github_graphql_url = _env(
            "GITHUB_GRAPHQL_URL", self.github_api_base + "/graphql"
        )
        self.trending_base = _env(
            "GITHUB_TRENDING_BASE", "https://github.com/trending"
        ).rstrip("/")
        self.user_agent = _env("GITHUB_USER_AGENT", DEFAULT_UA)
        self.request_timeout = _env_float("GITHUB_TIMEOUT_SECONDS", 30)

        # ---- 采集策略 ----
        # 周热门榜周期，可写 weekly / daily / monthly
        self.trending_periods = _env_list("TRENDING_PERIODS", "weekly")
        # 额外抓取的语言榜单（用 GitHub trending 的语言 slug，如 python,go,javascript）
        self.trending_languages = _env_list("TRENDING_LANGUAGES", "")
        # 新项目发现窗口（天）与最低 star 门槛
        self.discovery_windows = _env_list("DISCOVERY_WINDOWS", "7,30,90")
        self.discovery_min_stars = _env_int("DISCOVERY_MIN_STARS", 100)
        self.discovery_pages = _env_int("DISCOVERY_PAGES", 2)
        # 每轮用 REST 补齐信息（创建时间/许可证/主页等）的仓库数量上限
        # Trending 页面本身不提供这些字段，需要单独补全；配了 Token 时 GraphQL 会自动补齐，可设为 0
        self.enrich_limit = _env_int("ENRICH_LIMIT", 25)
        # 每小时快照追踪的仓库上限（越大越耗 API 配额）
        self.max_tracked_repos = _env_int("MAX_TRACKED_REPOS", 3000)
        # 快照保留天数 / 超过多少天后降采样为每天一条
        self.retention_days = _env_int("RETENTION_DAYS", 90)
        self.hourly_keep_days = _env_int("HOURLY_KEEP_DAYS", 14)
        # 长时间未出现的仓库清理天数
        self.stale_repo_days = _env_int("STALE_REPO_DAYS", 180)

        # ---- 调度 ----
        self.collect_interval_minutes = _env_int("COLLECT_INTERVAL_MINUTES", 60)
        self.run_on_startup = _env_bool("RUN_ON_STARTUP", True)
        self.collect_on_empty_db = _env_bool("COLLECT_ON_EMPTY_DB", True)

        # ---- 存储 / 服务 ----
        self.data_dir = _env("DATA_DIR", "/data")
        self.db_path = _env("DB_PATH", os.path.join(self.data_dir, "github_trending.db"))
        self.host = _env("HOST", "0.0.0.0")
        self.port = _env_int("PORT", 8000)
        self.log_level = _env("LOG_LEVEL", "INFO").upper()
        # 前端静态资源目录
        self.static_dir = _env("STATIC_DIR", "/app/static")

        # ---- 中文翻译（可选，默认关闭）----
        # provider 为 off 时完全不发外部请求，页面显示英文原文
        self.translate_provider = _env("TRANSLATE_PROVIDER", "off").strip().lower()
        self.translate_base_url = _env("TRANSLATE_BASE_URL", "").strip().rstrip("/")
        self.translate_api_key = _env("TRANSLATE_API_KEY", "").strip()
        self.translate_model = _env("TRANSLATE_MODEL", "").strip()
        self.translate_batch = _env_int("TRANSLATE_BATCH", 20)
        self.translate_per_run = _env_int("TRANSLATE_PER_RUN", 200)
        self.translate_topics_per_run = _env_int("TRANSLATE_TOPICS_PER_RUN", 200)
        self.translate_max_chars = _env_int("TRANSLATE_MAX_CHARS", 300)
        self.translate_timeout = float(_env("TRANSLATE_TIMEOUT", "90"))
        # 单轮翻译的时间上限（秒）：到点就停，剩余留到下一轮，避免慢接口把任务挂死
        self.translate_max_seconds = _env_int("TRANSLATE_MAX_SECONDS", 300)

    @property
    def translation_enabled(self):
        """三个必要参数齐全才启用；缺任意一个就安静地退回英文原文，不影响采集。"""
        return (
            self.translate_provider not in ("", "off", "none", "false", "0")
            and bool(self.translate_base_url)
            and bool(self.translate_api_key)
            and bool(self.translate_model)
        )

    @property
    def token_configured(self):
        return bool(self.github_token)

    def as_public_dict(self):
        """可以在页面上展示的配置快照（不含 token）。"""
        return {
            "collect_interval_minutes": self.collect_interval_minutes,
            "retention_days": self.retention_days,
            "hourly_keep_days": self.hourly_keep_days,
            "trending_periods": self.trending_periods,
            "trending_languages": self.trending_languages,
            "discovery_windows": self.discovery_windows,
            "discovery_min_stars": self.discovery_min_stars,
            "enrich_limit": self.enrich_limit,
            "max_tracked_repos": self.max_tracked_repos,
            "token_configured": self.token_configured,
            "github_api_base": self.github_api_base,
            "translation_enabled": self.translation_enabled,
            "translate_provider": self.translate_provider if self.translation_enabled else "off",
            "translate_model": self.translate_model if self.translation_enabled else "",
        }


settings = Settings()
