"""SQLite 存储层：建表、连接管理、通用查询辅助。"""
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager

from .config import settings

log = logging.getLogger("gh.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    full_name       TEXT PRIMARY KEY,
    owner           TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    html_url        TEXT NOT NULL DEFAULT '',
    homepage        TEXT NOT NULL DEFAULT '',
    language        TEXT NOT NULL DEFAULT '',
    topics          TEXT NOT NULL DEFAULT '[]',
    license         TEXT NOT NULL DEFAULT '',
    stars           INTEGER NOT NULL DEFAULT 0,
    forks           INTEGER NOT NULL DEFAULT 0,
    open_issues     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT,
    pushed_at       TEXT,
    archived        INTEGER NOT NULL DEFAULT 0,
    sources         TEXT NOT NULL DEFAULT '',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repos_stars       ON repos(stars DESC);
CREATE INDEX IF NOT EXISTS idx_repos_language    ON repos(language);
CREATE INDEX IF NOT EXISTS idx_repos_last_seen   ON repos(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_repos_created_at  ON repos(created_at DESC);

CREATE TABLE IF NOT EXISTS snapshots (
    full_name   TEXT NOT NULL,
    ts          TEXT NOT NULL,
    stars       INTEGER NOT NULL,
    forks       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (full_name, ts)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);

CREATE TABLE IF NOT EXISTS velocity (
    full_name       TEXT PRIMARY KEY,
    stars           INTEGER NOT NULL DEFAULT 0,
    gain_1h         INTEGER,
    gain_24h        INTEGER,
    gain_7d         INTEGER,
    gain_30d        INTEGER,
    hours_1h        REAL,
    hours_24h       REAL,
    hours_7d        REAL,
    hours_30d       REAL,
    per_day_24h     REAL NOT NULL DEFAULT 0,
    per_day_7d      REAL NOT NULL DEFAULT 0,
    per_day_30d     REAL NOT NULL DEFAULT 0,
    trend_score     REAL NOT NULL DEFAULT 0,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_velocity_gain24 ON velocity(gain_24h DESC);
CREATE INDEX IF NOT EXISTS idx_velocity_gain7  ON velocity(gain_7d DESC);
CREATE INDEX IF NOT EXISTS idx_velocity_score  ON velocity(trend_score DESC);

CREATE TABLE IF NOT EXISTS trend_entries (
    full_name       TEXT NOT NULL,
    period          TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT '',
    rank            INTEGER NOT NULL DEFAULT 0,
    stars_gained    INTEGER,
    stars           INTEGER NOT NULL DEFAULT 0,
    collected_at    TEXT NOT NULL,
    PRIMARY KEY (full_name, period, language)
);
CREATE INDEX IF NOT EXISTS idx_trend_lookup ON trend_entries(period, language, rank);

CREATE TABLE IF NOT EXISTS collect_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger          TEXT NOT NULL DEFAULT 'manual',
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    status           TEXT NOT NULL DEFAULT 'running',
    message          TEXT NOT NULL DEFAULT '',
    trending_count   INTEGER NOT NULL DEFAULT 0,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    snapshot_count   INTEGER NOT NULL DEFAULT 0,
    duration_ms      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL DEFAULT ''
);

-- 中文翻译缓存：同一段原文只翻一次；描述变了（src_hash 不同）才重翻
CREATE TABLE IF NOT EXISTS desc_translations (
    full_name   TEXT PRIMARY KEY,
    src_hash    TEXT NOT NULL,
    text        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 标签（Topics）翻译缓存：按 slug 去重，全站标签总数有限，翻一次永久复用
CREATE TABLE IF NOT EXISTS topic_translations (
    slug        TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class Database:
    """线程安全的 SQLite 包装（每次调用取一条连接，写操作串行化）。"""

    def __init__(self, path=None):
        self.path = path or settings.db_path
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_schema()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        conn = self.connect()
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()
        log.info("sqlite ready at %s", self.path)

    @contextmanager
    def read(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write(self):
        """写事务：全局串行，避免 SQLite 锁冲突。"""
        with self._write_lock:
            conn = self.connect()
            try:
                conn.execute("BEGIN")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            finally:
                conn.close()

    # --- 便捷方法 ---
    def query(self, sql, params=()):
        with self.read() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def query_one(self, sql, params=()):
        with self.read() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def scalar(self, sql, params=(), default=None):
        with self.read() as conn:
            row = conn.execute(sql, params).fetchone()
            if row is None or row[0] is None:
                return default
            return row[0]

    def execute(self, sql, params=()):
        with self.write() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def set_meta(self, key, value):
        self.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def get_meta(self, key, default=None):
        row = self.query_one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default


db = Database()
