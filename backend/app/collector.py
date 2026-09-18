"""采集编排：Trending 周榜 + 新项目发现 + 星标快照 + 暴涨速度计算 + 数据清理。"""
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from . import translate
from .config import settings
from .db import db
from .github_client import GitHubClient, RateLimited

log = logging.getLogger("gh.collector")

# 每个速度窗口: (名称, 时间跨度, 最小有效间隔, 参考快照最大回溯)
WINDOWS = [
    ("1h", timedelta(hours=1), timedelta(minutes=40)),
    ("24h", timedelta(hours=24), timedelta(hours=12)),
    ("7d", timedelta(days=7), timedelta(days=3)),
    ("30d", timedelta(days=30), timedelta(days=10)),
]

_run_lock = threading.Lock()
# 翻译单独一把锁：采集与翻译互不阻塞，翻译慢也不会拖住采集
_translate_lock = threading.Lock()

# 翻译层：未配置 TRANSLATE_* 时为关闭状态，所有调用直接返回，不产生任何网络请求
_translator = translate.Translator()


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(text):
    if not text:
        return None
    try:
        value = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_running():
    return _run_lock.locked()


# --------------------------------------------------------------------- 写库
def upsert_repo(conn, repo, source, now_iso):
    """插入或更新仓库基础信息，保留已有的更完整字段。"""
    full_name = repo.get("full_name")
    if not full_name or "/" not in full_name:
        return
    owner, name = full_name.split("/", 1)
    topics = repo.get("topics")
    if isinstance(topics, (list, tuple)):
        topics = json.dumps(list(topics), ensure_ascii=False)
    elif not isinstance(topics, str):
        topics = "[]"

    existing = conn.execute(
        "SELECT sources, first_seen FROM repos WHERE full_name=?", (full_name,)
    ).fetchone()
    sources = set()
    first_seen = now_iso
    if existing:
        sources = {s for s in (existing["sources"] or "").split(",") if s}
        first_seen = existing["first_seen"] or now_iso
    sources.add(source)

    conn.execute(
        """
        INSERT INTO repos (
            full_name, owner, name, description, html_url, homepage, language,
            topics, license, stars, forks, open_issues, created_at, pushed_at,
            archived, sources, first_seen, last_seen
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(full_name) DO UPDATE SET
            description = CASE WHEN excluded.description != '' THEN excluded.description ELSE repos.description END,
            language    = CASE WHEN excluded.language    != '' THEN excluded.language    ELSE repos.language    END,
            homepage    = CASE WHEN excluded.homepage    != '' THEN excluded.homepage    ELSE repos.homepage    END,
            license     = CASE WHEN excluded.license     != '' THEN excluded.license     ELSE repos.license     END,
            topics      = CASE WHEN excluded.topics != '[]' THEN excluded.topics ELSE repos.topics END,
            stars       = CASE WHEN excluded.stars > 0 THEN excluded.stars ELSE repos.stars END,
            forks       = CASE WHEN excluded.forks > 0 THEN excluded.forks ELSE repos.forks END,
            open_issues = CASE WHEN excluded.open_issues > 0 THEN excluded.open_issues ELSE repos.open_issues END,
            created_at  = COALESCE(excluded.created_at, repos.created_at),
            pushed_at   = COALESCE(excluded.pushed_at, repos.pushed_at),
            archived    = excluded.archived,
            sources     = excluded.sources,
            last_seen   = excluded.last_seen
        """,
        (
            full_name,
            owner,
            name,
            repo.get("description") or "",
            repo.get("html_url") or ("https://github.com/" + full_name),
            repo.get("homepage") or "",
            repo.get("language") or "",
            topics,
            repo.get("license") or "",
            int(repo.get("stars") or 0),
            int(repo.get("forks") or 0),
            int(repo.get("open_issues") or 0),
            repo.get("created_at"),
            repo.get("pushed_at"),
            1 if repo.get("archived") else 0,
            ",".join(sorted(sources)),
            first_seen,
            now_iso,
        ),
    )


def normalize_api_repo(item):
    """把 GitHub REST 搜索结果转换成统一结构。"""
    license_info = item.get("license") or {}
    return {
        "full_name": item.get("full_name") or "",
        "description": item.get("description") or "",
        "html_url": item.get("html_url") or "",
        "homepage": item.get("homepage") or "",
        "language": item.get("language") or "",
        "topics": item.get("topics") or [],
        "license": license_info.get("spdx_id") if isinstance(license_info, dict) else "",
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "open_issues": item.get("open_issues_count") or 0,
        "created_at": item.get("created_at"),
        "pushed_at": item.get("pushed_at"),
        "archived": item.get("archived") or False,
    }


def record_snapshot(conn, full_name, stars, forks, ts):
    if stars is None:
        return False
    conn.execute(
        "INSERT INTO snapshots(full_name, ts, stars, forks) VALUES(?,?,?,?) "
        "ON CONFLICT(full_name, ts) DO UPDATE SET stars=excluded.stars, forks=excluded.forks",
        (full_name, ts, int(stars), int(forks or 0)),
    )
    return True


# ------------------------------------------------------------------- 采集步骤
def collect_trending(client, conn, now):
    """抓取 Trending 榜单（默认 weekly，可配置多周期/多语言）。"""
    total = 0
    periods = settings.trending_periods or ["weekly"]
    languages = [""] + settings.trending_languages
    for period in periods:
        for language in languages:
            try:
                repos = client.fetch_trending(period=period, language=language)
            except Exception as exc:
                log.warning("Trending 抓取失败 period=%s lang=%s: %s", period, language, exc)
                continue
            if not repos:
                continue
            conn.execute(
                "DELETE FROM trend_entries WHERE period=? AND language=?",
                (period, language),
            )
            ts = iso(now)
            for repo in repos:
                upsert_repo(conn, repo, "trending", ts)
                record_snapshot(conn, repo["full_name"], repo.get("stars"), repo.get("forks"), ts)
                conn.execute(
                    "INSERT INTO trend_entries(full_name, period, language, rank, stars_gained,"
                    " stars, collected_at) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(full_name, period, language) DO UPDATE SET "
                    "rank=excluded.rank, stars_gained=excluded.stars_gained,"
                    " stars=excluded.stars, collected_at=excluded.collected_at",
                    (
                        repo["full_name"],
                        period,
                        language,
                        repo.get("rank") or 0,
                        repo.get("stars_gained"),
                        int(repo.get("stars") or 0),
                        ts,
                    ),
                )
                total += 1
            log.info("Trending %s/%s: %d 个仓库", period, language or "all", len(repos))
    return total


def collect_discovery(client, conn, now):
    """用搜索接口发现近 N 天 star 增长最快的新项目。"""
    discovered = 0
    for window in settings.discovery_windows:
        try:
            days = int(window)
        except ValueError:
            continue
        since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        query = "created:>%s stars:>%d" % (since, settings.discovery_min_stars)
        try:
            items = client.search_repositories(
                query, sort="stars", order="desc", pages=settings.discovery_pages
            )
        except RateLimited as exc:
            log.warning("搜索接口限流，跳过 %s 天窗口: %s", window, exc)
            break
        except Exception as exc:
            log.warning("搜索 %s 天窗口失败: %s", window, exc)
            continue
        ts = iso(now)
        for item in items:
            repo = normalize_api_repo(item)
            if not repo["full_name"]:
                continue
            upsert_repo(conn, repo, "search", ts)
            record_snapshot(conn, repo["full_name"], repo.get("stars"), repo.get("forks"), ts)
            discovered += 1
        log.info("新项目发现(近 %s 天): %d 个", days, len(items))
        time.sleep(2.0)
    return discovered


def collect_enrich(client, conn, now):
    """用 REST 接口补齐 Trending 页面缺失的字段（创建时间/许可证/主页/Topics）。

    Trending 页面只有名字、描述、语言和 Star 数，缺字段会让详情页与"新建天数"显示为空。
    配置了 Token 时 GraphQL 快照会自动补齐，这里主要服务于未配置 Token 的场景。
    """
    limit = settings.enrich_limit
    if limit <= 0:
        return 0
    rows = conn.execute(
        "SELECT full_name FROM repos WHERE archived = 0 "
        "AND (created_at IS NULL OR license = '' OR homepage = '' OR topics = '[]') "
        "ORDER BY stars DESC LIMIT ?",
        (limit,),
    ).fetchall()
    ts = iso(now)
    count = 0
    for row in rows:
        full_name = row["full_name"]
        try:
            data = client.get_repo(full_name)
        except RateLimited as exc:
            log.warning("REST 配额不足，信息补全中断: %s", exc)
            break
        except Exception as exc:
            log.warning("补全 %s 失败: %s", full_name, exc)
            continue
        if not data:
            continue
        upsert_repo(conn, normalize_api_repo(data), "rest", ts)
        record_snapshot(
            conn, data.get("full_name"), data.get("stargazers_count"),
            data.get("forks_count"), ts,
        )
        count += 1
        time.sleep(0.3)
    log.info("信息补全完成: %d/%d 个仓库", count, len(rows))
    return count


def collect_snapshots(client, conn, now):
    """通过 GraphQL 批量刷新已跟踪仓库的实时 star 数。"""
    if not settings.token_configured:
        log.info("未配置 GITHUB_TOKEN，跳过批量快照（仅依赖榜单/搜索数据）")
        return 0
    cutoff = iso(now - timedelta(days=settings.retention_days))
    rows = conn.execute(
        "SELECT full_name FROM repos WHERE last_seen >= ? AND archived = 0 "
        "ORDER BY last_seen DESC LIMIT ?",
        (cutoff, settings.max_tracked_repos),
    ).fetchall()
    names = [row["full_name"] for row in rows]
    if not names:
        return 0
    ts = iso(now)
    count = 0
    try:
        data = client.graphql_star_batch(names)
    except RateLimited as exc:
        log.warning("GraphQL 限流，快照中断: %s", exc)
        return 0
    for name, repo in data.items():
        upsert_repo(conn, repo, "snapshot", ts)
        if record_snapshot(conn, name, repo.get("stars"), repo.get("forks"), ts):
            count += 1
    log.info("批量快照完成: %d/%d 个仓库", count, len(names))
    return count


def compute_velocity(conn, now):
    """基于历史快照计算各时间窗的 star 增速。"""
    select_parts = ["r.full_name", "r.stars AS repo_stars"]
    for name, _, _ in WINDOWS:
        select_parts.append(
            "(SELECT s.stars FROM snapshots s WHERE s.full_name=r.full_name "
            "AND s.ts <= ? ORDER BY s.ts DESC LIMIT 1) AS s_%s" % name
        )
        select_parts.append(
            "(SELECT s.ts FROM snapshots s WHERE s.full_name=r.full_name "
            "AND s.ts <= ? ORDER BY s.ts DESC LIMIT 1) AS t_%s" % name
        )
    params = []
    for name, delta, _ in WINDOWS:
        params.append(iso(now - delta))
        params.append(iso(now - delta))

    sql = (
        "SELECT %s FROM repos r WHERE r.archived = 0 AND r.last_seen >= ? "
        "AND EXISTS (SELECT 1 FROM snapshots s WHERE s.full_name = r.full_name)"
        % ", ".join(select_parts)
    )
    params.append(iso(now - timedelta(days=settings.retention_days)))
    rows = conn.execute(sql, params).fetchall()

    updated = 0
    for row in rows:
        current = row["repo_stars"]
        values = {}
        per_day = {}
        for name, delta, min_span in WINDOWS:
            ref_stars = row["s_%s" % name]
            ref_ts = parse_iso(row["t_%s" % name])
            if ref_stars is None or ref_ts is None:
                values[name] = (None, None)
                continue
            span = now - ref_ts
            if span < min_span:
                values[name] = (None, None)
                continue
            gain = max(0, int(current) - int(ref_stars))
            hours = span.total_seconds() / 3600.0
            values[name] = (gain, hours)
            if name == "1h":
                continue
            per_day[name] = gain / (hours / 24.0) if hours > 0 else 0.0

        pd24 = per_day.get("24h", 0.0) or 0.0
        pd7 = per_day.get("7d", 0.0) or 0.0
        pd30 = per_day.get("30d", 0.0) or 0.0
        has_any = any(v[0] is not None for v in values.values())
        score = 0.0
        if has_any:
            weights = []
            if values["24h"][0] is not None:
                weights.append((pd24, 0.5))
            if values["7d"][0] is not None:
                weights.append((pd7, 0.3))
            if values["30d"][0] is not None:
                weights.append((pd30, 0.2))
            total_weight = sum(w for _, w in weights) or 1.0
            score = sum(v * w for v, w in weights) / total_weight

        conn.execute(
            """
            INSERT INTO velocity (
                full_name, stars, gain_1h, gain_24h, gain_7d, gain_30d,
                hours_1h, hours_24h, hours_7d, hours_30d,
                per_day_24h, per_day_7d, per_day_30d, trend_score, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(full_name) DO UPDATE SET
                stars=excluded.stars, gain_1h=excluded.gain_1h, gain_24h=excluded.gain_24h,
                gain_7d=excluded.gain_7d, gain_30d=excluded.gain_30d,
                hours_1h=excluded.hours_1h, hours_24h=excluded.hours_24h,
                hours_7d=excluded.hours_7d, hours_30d=excluded.hours_30d,
                per_day_24h=excluded.per_day_24h, per_day_7d=excluded.per_day_7d,
                per_day_30d=excluded.per_day_30d, trend_score=excluded.trend_score,
                updated_at=excluded.updated_at
            """,
            (
                row["full_name"],
                int(current or 0),
                values["1h"][0],
                values["24h"][0],
                values["7d"][0],
                values["30d"][0],
                values["1h"][1],
                values["24h"][1],
                values["7d"][1],
                values["30d"][1],
                round(pd24, 3),
                round(pd7, 3),
                round(pd30, 3),
                round(score, 3),
                iso(now),
            ),
        )
        updated += 1
    log.info("增速计算完成: %d 个仓库", updated)
    return updated


def prune(conn, now):
    """降采样 + 清理过期数据，控制 SQLite 体积。"""
    hourly_cutoff = iso(now - timedelta(days=settings.hourly_keep_days))
    retention_cutoff = iso(now - timedelta(days=settings.retention_days))
    # 超过 hourly_keep_days 的快照，每个仓库每天只保留最早一条
    conn.execute(
        "DELETE FROM snapshots WHERE ts < ? AND ts >= ? AND ts NOT IN ("
        "  SELECT MIN(ts) FROM snapshots WHERE ts < ? AND ts >= ? "
        "  GROUP BY full_name, substr(ts, 1, 10)"
        ")",
        (hourly_cutoff, retention_cutoff, hourly_cutoff, retention_cutoff),
    )
    conn.execute("DELETE FROM snapshots WHERE ts < ?", (retention_cutoff,))
    conn.execute(
        "DELETE FROM velocity WHERE full_name IN ("
        "  SELECT full_name FROM repos WHERE last_seen < ?"
        ")",
        (iso(now - timedelta(days=settings.stale_repo_days)),),
    )
    conn.execute(
        "DELETE FROM repos WHERE last_seen < ? AND full_name NOT IN ("
        "  SELECT full_name FROM trend_entries"
        ")",
        (iso(now - timedelta(days=settings.stale_repo_days)),),
    )


# ------------------------------------------------------------------- 主入口
def _parse_topics(raw):
    """topics 列存的是 JSON 数组文本，兼容历史数据里的逗号分隔格式。"""
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except (TypeError, ValueError):
        arr = re.split(r"[,\s]+", str(raw))
    return [str(x).strip().lower() for x in arr if str(x).strip()]


def _pending_topic_slugs(conn, limit):
    """挑出还没翻译过的标签：按 slug 全局去重，翻过就不再翻。"""
    if limit <= 0:
        return []
    known = {row["slug"] for row in conn.execute("SELECT slug FROM topic_translations").fetchall()}
    picked = []
    for row in conn.execute(
        "SELECT topics FROM repos WHERE COALESCE(topics,'') <> '' ORDER BY stars DESC"
    ).fetchall():
        for slug in _parse_topics(row["topics"]):
            if slug and slug not in known and slug not in picked:
                picked.append(slug)
                if len(picked) >= limit:
                    return picked
    return picked


def _pending_descriptions(conn, limit):
    """挑出需要翻译的描述：没翻过的优先，其次是原文变过的。"""
    if limit <= 0:
        return []
    rows = conn.execute(
        "SELECT r.full_name, r.description, t.src_hash FROM repos r "
        "LEFT JOIN desc_translations t ON t.full_name = r.full_name "
        "WHERE COALESCE(r.description,'') <> '' "
        "ORDER BY (t.src_hash IS NULL) DESC, r.stars DESC LIMIT ?",
        (max(limit * 3, limit),),
    ).fetchall()
    out = []
    for row in rows:
        if translate.content_hash(row["description"]) != (row["src_hash"] or ""):
            out.append(row)
            if len(out) >= limit:
                break
    return out


def collect_translate(translator, writer, now, max_seconds=None):
    """把英文描述与标签翻成中文（可选步骤，未启用时直接返回 0）。

    writer 是能提供 write() 事务上下文的对象（即 db）。**每批一个独立短事务**：
    整轮翻译可能要跑几分钟，若包成一个大事务，期间既看不到任何译文，
    又会长时间占住 SQLite 写锁，还会在进程退出时丢掉全部成果。
    max_seconds 为本轮时间上限，到点就停，剩余留到下一轮。
    """
    if not translator.enabled:
        return 0
    budget = settings.translate_max_seconds if max_seconds is None else max_seconds
    deadline = (time.monotonic() + budget) if budget and budget > 0 else None
    ts = iso(now)
    translator._reset_stats()
    done = _translate_topics(translator, writer, ts, deadline)
    done += _translate_descriptions(translator, writer, ts, deadline)
    return done


def _translate_topics(translator, writer, ts, deadline):
    limit = max(0, translator.cfg.translate_topics_per_run)
    batch = max(1, translator.cfg.translate_batch)
    done = 0
    while done < limit:
        if deadline and time.monotonic() > deadline:
            log.warning("已达本轮翻译时间上限，标签剩余部分留到下一轮")
            break
        take = min(batch, limit - done)
        with writer.write() as conn:
            slugs = _pending_topic_slugs(conn, take)
        if not slugs:
            break
        mapping = translator.translate_topics(slugs, deadline=deadline)
        if not mapping:
            break  # 失败或预算耗尽，下轮再试
        with writer.write() as conn:
            for slug, zh in mapping.items():
                conn.execute(
                    "INSERT INTO topic_translations(slug, text, updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(slug) DO UPDATE SET text=excluded.text, updated_at=excluded.updated_at",
                    (slug, zh, ts),
                )
        done += len(mapping)
        if len(slugs) < take:
            break  # 已经取完
    if done:
        log.info("标签翻译：本轮新增 %d 个", done)
    return done


def _translate_descriptions(translator, writer, ts, deadline):
    limit = max(0, translator.cfg.translate_per_run)
    batch = max(1, translator.cfg.translate_batch)
    done = 0
    while done < limit:
        if deadline and time.monotonic() > deadline:
            log.warning("已达本轮翻译时间上限，描述剩余部分留到下一轮")
            break
        take = min(batch, limit - done)
        with writer.write() as conn:
            rows = _pending_descriptions(conn, take)
        if not rows:
            break
        mapping = translator.translate_descriptions(
            [(row["full_name"], row["description"]) for row in rows], deadline=deadline
        )
        saved = 0
        with writer.write() as conn:
            for row in rows:
                name = row["full_name"]
                src = (row["description"] or "").strip()
                if name in mapping:
                    zh = mapping[name]
                elif translate.is_chinese(src):
                    zh = ""  # 原文本来就是中文：写空串占位，避免每轮重复挑出来
                else:
                    continue  # 本批失败，下一轮再试
                conn.execute(
                    "INSERT INTO desc_translations(full_name, src_hash, text, updated_at) "
                    "VALUES(?,?,?,?) ON CONFLICT(full_name) DO UPDATE SET "
                    "src_hash=excluded.src_hash, text=excluded.text, updated_at=excluded.updated_at",
                    (name, translate.content_hash(src), zh, ts),
                )
                saved += 1
        done += saved
        if saved == 0 or len(rows) < take:
            break
    if done:
        log.info("描述翻译：本轮完成 %d 条", done)
    return done


def translation_running():
    return _translate_lock.locked()


def run_translation(trigger="manual", max_seconds=None):
    """独立的翻译任务：与采集分开跑，互不阻塞。

    采集只负责把数据抓回来（约 2 分钟），翻译在它结束后另起一轮，
    这样可以慢慢翻、翻多少算多少，页面也能立刻看到已有译文。
    """
    if not _translator.enabled:
        return {"status": "disabled", "message": "未配置翻译（TRANSLATE_PROVIDER=off）", "translated": 0}
    if not _translate_lock.acquire(blocking=False):
        return {"status": "skipped", "message": "已有翻译任务在运行", "translated": 0}
    started = time.monotonic()
    try:
        n = collect_translate(_translator, db, utcnow(), max_seconds=max_seconds)
        elapsed = time.monotonic() - started
        log.info(
            "翻译任务结束（%s）：写入 %d 条，用时 %.0f 秒，请求 %d 次，失败 %d 批，拆半 %d 次",
            trigger, n, elapsed, _translator.requests, _translator.failures, _translator.splits,
        )
        return {"status": "ok", "translated": n, "elapsed_seconds": round(elapsed, 1),
                "requests": _translator.requests, "failures": _translator.failures}
    except Exception as exc:
        log.exception("翻译任务异常")
        return {"status": "error", "message": str(exc)[:300], "translated": 0}
    finally:
        _translate_lock.release()


def cleanup_stale_runs():
    """启动时清理僵尸采集记录。

    容器被 kill / 进程崩溃时，正在跑的那轮采集来不及写 finished_at，
    数据库里会永久留下 status='running' 的记录，页面据此显示"正在采集中"。
    这里统一标记为 interrupted，并返回清理条数。
    """
    try:
        with db.write() as conn:
            cur = conn.execute(
                "UPDATE collect_runs SET status='interrupted', finished_at=?, message=? "
                "WHERE status='running'",
                (iso(utcnow()), "采集被中断（容器重启或进程退出）"),
            )
            n = cur.rowcount or 0
        if n:
            log.warning("清理了 %d 条未正常结束的采集记录", n)
        return n
    except Exception:
        log.exception("清理僵尸采集记录失败")
        return 0


def run_collection(trigger="manual"):
    """执行一轮完整采集。返回统计信息字典。"""
    if not _run_lock.acquire(blocking=False):
        return {"status": "skipped", "message": "已有采集任务在运行"}

    started = utcnow()
    started_iso = iso(started)
    stats = {
        "status": "ok",
        "trigger": trigger,
        "started_at": started_iso,
        "trending_count": 0,
        "discovered_count": 0,
        "enriched_count": 0,
        "snapshot_count": 0,
        "velocity_count": 0,
        "message": "",
    }
    client = GitHubClient(settings)
    try:
        with db.write() as conn:
            run_id = conn.execute(
                "INSERT INTO collect_runs(trigger, started_at, status, message) "
                "VALUES(?,?, 'running', '')",
                (trigger, started_iso),
            ).lastrowid
        errors = []
        for label, func in (
            ("trending", collect_trending),
            ("discovery", collect_discovery),
            ("enrich", collect_enrich),
            ("snapshots", collect_snapshots),
        ):
            try:
                with db.write() as conn:
                    if label == "trending":
                        stats["trending_count"] = func(client, conn, started)
                    elif label == "discovery":
                        stats["discovered_count"] = func(client, conn, started)
                    elif label == "enrich":
                        stats["enriched_count"] = func(client, conn, started)
                    else:
                        stats["snapshot_count"] = func(client, conn, started)
            except RateLimited as exc:
                errors.append("%s: %s" % (label, exc))
                log.warning("%s 被限流: %s", label, exc)
            except Exception as exc:  # 单个步骤失败不影响其它步骤
                errors.append("%s: %s" % (label, exc))
                log.exception("%s 采集失败", label)

        with db.write() as conn:
            stats["velocity_count"] = compute_velocity(conn, utcnow())
            prune(conn, utcnow())

        if errors:
            stats["status"] = "partial"
            stats["message"] = " | ".join(errors)[:500]

        finished = utcnow()
        with db.write() as conn:
            conn.execute(
                "UPDATE collect_runs SET finished_at=?, status=?, message=?, trending_count=?,"
                " discovered_count=?, snapshot_count=?, duration_ms=? WHERE id=?",
                (
                    iso(finished),
                    stats["status"],
                    stats["message"],
                    stats["trending_count"],
                    stats["discovered_count"],
                    stats["snapshot_count"],
                    int((finished - started).total_seconds() * 1000),
                    run_id,
                ),
            )
        db.set_meta("last_success_at", iso(finished))
        db.set_meta("last_run_status", stats["status"])
        db.set_meta("rate_limit", json.dumps(client.rate_limit))
    except Exception as exc:
        log.exception("采集任务异常")
        stats["status"] = "error"
        stats["message"] = str(exc)[:500]
        with db.write() as conn:
            conn.execute(
                "UPDATE collect_runs SET finished_at=?, status='error', message=? "
                "WHERE started_at=?",
                (iso(utcnow()), stats["message"], started_iso),
            )
    finally:
        client.close()
        _run_lock.release()
    return stats
