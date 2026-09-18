"""HTTP API：榜单、搜索、详情、趋势数据。"""
import json
import math
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from . import collector, scheduler
from .config import settings
from .db import db

router = APIRouter(prefix="/api")

SORT_WHITELIST = {
    "stars": "r.stars",
    "gain_1h": "v.gain_1h",
    "gain_24h": "v.gain_24h",
    "gain_7d": "v.gain_7d",
    "gain_30d": "v.gain_30d",
    "per_day_24h": "v.per_day_24h",
    "per_day_7d": "v.per_day_7d",
    "trend_score": "v.trend_score",
    "created_at": "r.created_at",
    "pushed_at": "r.pushed_at",
    "updated_at": "r.last_seen",
}


def _row_to_repo(row):
    topics = []
    try:
        topics = json.loads(row.get("topics") or "[]")
    except (TypeError, ValueError):
        topics = []
    created = collector.parse_iso(row.get("created_at"))
    age_days = None
    if created:
        age_days = max(0, int((datetime.now(timezone.utc) - created).days))
    data = {
        "full_name": row.get("full_name"),
        "owner": row.get("owner"),
        "name": row.get("name"),
        "description": row.get("description") or "",
        "description_zh": row.get("description_zh") or "",
        "html_url": row.get("html_url") or ("https://github.com/" + (row.get("full_name") or "")),
        "homepage": row.get("homepage") or "",
        "language": row.get("language") or "",
        "topics": topics,
        "license": row.get("license") or "",
        "stars": row.get("stars") or 0,
        "forks": row.get("forks") or 0,
        "open_issues": row.get("open_issues") or 0,
        "created_at": row.get("created_at"),
        "pushed_at": row.get("pushed_at"),
        "archived": bool(row.get("archived")),
        "age_days": age_days,
        "first_seen": row.get("first_seen"),
        "last_seen": row.get("last_seen"),
    }
    for key in (
        "gain_1h",
        "gain_24h",
        "gain_7d",
        "gain_30d",
        "per_day_24h",
        "per_day_7d",
        "per_day_30d",
        "trend_score",
        "rank",
        "stars_gained",
        "collected_at",
    ):
        if key in row and row[key] is not None:
            data[key] = row[key]
    return data


def _language_filter(language):
    if not language or language.lower() in ("all", "全部"):
        return "", []
    return " AND r.language = ? ", [language]


def _trend_language_clause(language):
    """trend_entries.language 存的是「抓取该榜单时所用的语言」，通用榜单为空串，
    与仓库自身语言并不相同。按语言筛选时必须两者取或，否则通用周榜/月榜
    按任何语言过滤都会返回 0 条。"""
    lang = (language or "").strip()
    if lang and lang.lower() not in ("all", "全部"):
        return "(t.language = ? OR r.language = ?)", [lang, lang]
    return "t.language = ?", [""]


@router.get("/health")
def health():
    return {
        "status": "ok",
        "time": collector.iso(collector.utcnow()),
        "collecting": collector.is_running(),
    }


@router.get("/overview")
def overview():
    now = collector.utcnow()
    last_run = db.query_one(
        "SELECT * FROM collect_runs ORDER BY id DESC LIMIT 1"
    )
    rate_limit = db.get_meta("rate_limit")
    try:
        rate_limit = json.loads(rate_limit) if rate_limit else {}
    except (TypeError, ValueError):
        rate_limit = {}
    return {
        "repo_count": db.scalar("SELECT COUNT(*) FROM repos", default=0),
        "tracked_count": db.scalar(
            "SELECT COUNT(*) FROM velocity", default=0
        ),
        "star_total": db.scalar("SELECT COALESCE(SUM(stars),0) FROM repos", default=0),
        "new_7d": db.scalar(
            "SELECT COUNT(*) FROM repos WHERE first_seen >= ?",
            (collector.iso(now - timedelta(days=7)),),
            default=0,
        ),
        "snapshot_count": db.scalar("SELECT COUNT(*) FROM snapshots", default=0),
        "last_run": last_run,
        "next_run_at": scheduler.next_run_time(),
        "collecting": collector.is_running(),
        "rate_limit": rate_limit,
        "config": settings.as_public_dict(),
        "server_time": collector.iso(now),
    }


@router.get("/languages")
def languages(limit: int = Query(60, ge=1, le=200)):
    rows = db.query(
        "SELECT language, COUNT(*) AS count, COALESCE(SUM(stars),0) AS stars "
        "FROM repos WHERE language != '' GROUP BY language "
        "ORDER BY count DESC LIMIT ?",
        (limit,),
    )
    return {"items": rows}


TRENDING_SORTS = {
    "rank": "t.rank ASC",
    "stars": "r.stars DESC",
    "stars_gained": "COALESCE(t.stars_gained, 0) DESC",
}


@router.get("/terms")
def terms():
    """中文术语表：前端内置词典之外，由翻译层补充的标签译文（未启用时为空）。"""
    topics = {}
    try:
        for row in db.query("SELECT slug, text FROM topic_translations WHERE text <> ''"):
            topics[row["slug"]] = row["text"]
    except Exception:  # 表缺失等异常不应影响页面
        topics = {}
    # 翻译进度：让页面能显示「已译 200 / 待译 450」
    pending = db.scalar(
        "SELECT COUNT(*) FROM repos r LEFT JOIN desc_translations t ON t.full_name = r.full_name "
        "WHERE COALESCE(r.description,'') <> '' AND t.full_name IS NULL",
        default=0,
    )
    return {
        "topics": topics,
        "translation_enabled": settings.translation_enabled,
        "translated": db.scalar("SELECT COUNT(*) FROM desc_translations", default=0),
        "pending": pending,
        "translating": collector.translation_running(),
    }


@router.get("/trending")
def trending(
    period: str = Query("weekly", pattern="^(daily|weekly|monthly)$"),
    language: str = Query(""),
    sort: str = Query("stars_gained", pattern="^(rank|stars|stars_gained)$"),
    min_stars: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where = ["t.period = ?"]
    params = [period]
    trend_lang_sql, trend_lang_params = _trend_language_clause(language)
    where.append(trend_lang_sql)
    params.extend(trend_lang_params)
    if min_stars:
        where.append("r.stars >= ?")
        params.append(min_stars)
    order = TRENDING_SORTS.get(sort, "t.rank ASC")
    sql = (
        "SELECT r.*, dt.text AS description_zh, t.rank AS rank, t.stars_gained AS stars_gained,"
        " t.collected_at AS collected_at, t.language AS trend_language,"
        " v.gain_24h, v.gain_7d, v.per_day_24h, v.trend_score "
        "FROM trend_entries t JOIN repos r ON r.full_name = t.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
        "LEFT JOIN velocity v ON v.full_name = r.full_name "
        "WHERE %s "
        "ORDER BY %s, t.rank ASC LIMIT ? OFFSET ?"
    ) % (" AND ".join(where), order)
    rows = db.query(sql, params + [limit, offset])
    collected_at = rows[0].get("collected_at") if rows else None
    return {
        "items": [_row_to_repo(row) for row in rows],
        "period": period,
        "language": language or "",
        "sort": sort,
        "collected_at": collected_at,
        "has_more": len(rows) == limit,
    }


@router.get("/surging")
def surging(
    window: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    mode: str = Query("velocity", pattern="^(velocity|new)$"),
    language: str = Query(""),
    min_stars: int = Query(0, ge=0),
    min_gain: int = Query(1, ge=0),
    max_age_days: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where = ["r.archived = 0"]
    params = []
    lang_sql, lang_params = _language_filter(language)
    where.append("1=1" + lang_sql)
    params.extend(lang_params)
    if min_stars:
        where.append("r.stars >= ?")
        params.append(min_stars)
    if max_age_days:
        where.append("r.created_at >= ?")
        params.append(collector.iso(collector.utcnow() - timedelta(days=max_age_days)))

    if mode == "new":
        where.append("v.full_name IS NOT NULL")
        order = "r.stars DESC"
        if window in ("1h", "24h", "7d", "30d"):
            order = "COALESCE(v.per_day_%s, v.trend_score, 0) DESC" % (
                window if window in ("24h", "7d") else "24h"
            )
        sql = (
            "SELECT r.*, dt.text AS description_zh, v.gain_1h, v.gain_24h, v.gain_7d, v.gain_30d,"
            " v.per_day_24h, v.per_day_7d, v.trend_score "
            "FROM repos r JOIN velocity v ON v.full_name = r.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
            "WHERE %s ORDER BY %s, r.stars DESC LIMIT ? OFFSET ?"
        ) % (" AND ".join(where), order)
        rows = db.query(sql, params + [limit, offset])
        return {"items": [_row_to_repo(r) for r in rows], "window": window, "mode": mode}

    gain_col = "v.gain_%s" % window
    where.append("%s IS NOT NULL AND %s >= ?" % (gain_col, gain_col))
    params.append(min_gain)
    order = "%s DESC, r.stars DESC" % gain_col
    sql = (
        "SELECT r.*, dt.text AS description_zh, v.gain_1h, v.gain_24h, v.gain_7d, v.gain_30d,"
        " v.per_day_24h, v.per_day_7d, v.per_day_30d, v.trend_score "
        "FROM repos r JOIN velocity v ON v.full_name = r.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
        "WHERE %s ORDER BY %s LIMIT ? OFFSET ?"
    ) % (" AND ".join(where), order)
    rows = db.query(sql, params + [limit, offset])

    # 冷启动兜底：快照还没攒够时，用 GitHub Trending 官方周期增量（真实数据，非估算）
    fallback = None
    if not rows and offset == 0 and window in ("7d", "30d"):
        period = "weekly" if window == "7d" else "monthly"
        fb_lang_sql, fb_lang_params = _trend_language_clause(language)
        rows = db.query(
            "SELECT r.*, dt.text AS description_zh, t.rank AS rank, t.stars_gained AS stars_gained,"
            " t.collected_at AS collected_at, v.gain_1h, v.gain_24h, v.gain_7d, v.gain_30d,"
            " v.per_day_24h, v.per_day_7d, v.trend_score "
            "FROM trend_entries t JOIN repos r ON r.full_name = t.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
            "LEFT JOIN velocity v ON v.full_name = r.full_name "
            "WHERE t.period = ? AND %s AND t.stars_gained IS NOT NULL "
            "ORDER BY t.stars_gained DESC LIMIT ?" % fb_lang_sql,
            [period] + fb_lang_params + [limit],
        )
        if rows:
            fallback = "github-%s" % period

    return {
        "items": [_row_to_repo(r) for r in rows],
        "window": window,
        "mode": mode,
        "fallback": fallback,
        "has_more": fallback is None and len(rows) == limit,
    }


@router.get("/repos")
def list_repos(
    q: str = Query("", max_length=120),
    language: str = Query(""),
    sort: str = Query("stars"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    min_stars: int = Query(0, ge=0),
    max_age_days: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    order_col = SORT_WHITELIST.get(sort, "r.stars")
    where = ["r.archived = 0"]
    params = []
    if q:
        where.append("(r.full_name LIKE ? OR r.description LIKE ? OR r.topics LIKE ?)")
        like = "%" + q + "%"
        params.extend([like, like, like])
    lang_sql, lang_params = _language_filter(language)
    where.append("1=1" + lang_sql)
    params.extend(lang_params)
    if min_stars:
        where.append("r.stars >= ?")
        params.append(min_stars)
    if max_age_days:
        where.append("r.created_at >= ?")
        params.append(collector.iso(collector.utcnow() - timedelta(days=max_age_days)))

    total = db.scalar(
        "SELECT COUNT(*) FROM repos r WHERE %s" % " AND ".join(where), params, default=0
    )
    sql = (
        "SELECT r.*, dt.text AS description_zh, v.gain_1h, v.gain_24h, v.gain_7d, v.gain_30d,"
        " v.per_day_24h, v.per_day_7d, v.trend_score "
        "FROM repos r LEFT JOIN velocity v ON v.full_name = r.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
        "WHERE %s ORDER BY %s %s, r.stars DESC LIMIT ? OFFSET ?"
    ) % (" AND ".join(where), order_col, order.upper())
    rows = db.query(sql, params + [limit, offset])
    return {
        "items": [_row_to_repo(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }


@router.get("/repos/{owner}/{name}")
def repo_detail(owner: str, name: str, days: int = Query(0, ge=0, le=365)):
    full_name = "%s/%s" % (owner, name)
    row = db.query_one(
        "SELECT r.*, dt.text AS description_zh, v.gain_1h, v.gain_24h, v.gain_7d, v.gain_30d, v.per_day_24h,"
        " v.per_day_7d, v.per_day_30d, v.trend_score "
        "FROM repos r LEFT JOIN velocity v ON v.full_name = r.full_name LEFT JOIN desc_translations dt ON dt.full_name = r.full_name "
        "WHERE r.full_name = ?",
        (full_name,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="未收录该仓库，请先执行一次采集")
    repo = _row_to_repo(row)
    where = "full_name = ?"
    params = [full_name]
    if days:
        where += " AND ts >= ?"
        params.append(collector.iso(collector.utcnow() - timedelta(days=days)))
    series = db.query(
        "SELECT ts, stars, forks FROM snapshots WHERE %s ORDER BY ts ASC" % where, params
    )
    repo["series"] = _downsample(series, 400)
    repo["point_count"] = len(series)
    repo["trend_history"] = db.query(
        "SELECT period, language, rank, stars_gained, collected_at FROM trend_entries "
        "WHERE full_name = ? ORDER BY collected_at DESC",
        (full_name,),
    )
    return repo


def _downsample(rows, max_points):
    if len(rows) <= max_points:
        return [[r["ts"], r["stars"]] for r in rows]
    step = int(math.ceil(len(rows) / float(max_points)))
    sampled = rows[::step]
    if sampled[-1] != rows[-1]:
        sampled.append(rows[-1])
    return [[r["ts"], r["stars"]] for r in sampled]


@router.get("/runs")
def runs(limit: int = Query(20, ge=1, le=100)):
    return {"items": db.query("SELECT * FROM collect_runs ORDER BY id DESC LIMIT ?", (limit,))}


def _collect_then_translate():
    collector.run_collection(trigger="manual")
    if settings.translation_enabled:
        collector.run_translation(trigger="manual")


@router.post("/collect", status_code=202)
def trigger_collect(background: BackgroundTasks):
    if collector.is_running():
        return {"status": "running", "message": "已有采集任务在运行，请稍候"}
    background.add_task(_collect_then_translate)
    return {"status": "accepted", "message": "采集任务已提交，稍后刷新页面查看"}


@router.post("/translate", status_code=202)
def trigger_translate(background: BackgroundTasks):
    """只跑翻译，不重新采集。适合刚配好翻译、想把存量描述补齐的场景。"""
    if not settings.translation_enabled:
        return {"status": "disabled", "message": "未启用翻译：请在 .env 配置 TRANSLATE_PROVIDER 等四项后重建容器"}
    if collector.translation_running():
        return {"status": "running", "message": "已有翻译任务在运行，请稍候"}
    background.add_task(collector.run_translation, "manual")
    return {"status": "accepted", "message": "翻译任务已提交，稍后刷新页面查看"}
