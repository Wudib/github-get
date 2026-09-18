"""FastAPI 入口：挂载 API、静态前端、启动调度器与首次采集。"""
import logging
import mimetypes
import os
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import collector, scheduler
from .api import router as api_router
from .config import settings
from .db import db

# python:3.12-slim 之类的精简镜像没有 /etc/mime.types，mimetypes 会把 .woff2
# 猜成 text/plain（本地 macOS 上则是正确的 font/woff2）。这里显式注册，
# 保证字体/视频在任何基础镜像里都以正确的 Content-Type 提供。
for _ext, _type in (
    (".woff2", "font/woff2"),
    (".woff", "font/woff"),
    (".ttf", "font/ttf"),
    (".mp4", "video/mp4"),
    (".webm", "video/webm"),
    (".js", "text/javascript"),
    (".css", "text/css"),
    (".svg", "image/svg+xml"),
):
    mimetypes.add_type(_type, _ext)

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("gh.main")

app = FastAPI(title="GitHub 热门项目雷达", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


def _bootstrap_collection():
    """首次启动且数据库为空时，后台跑一次采集，避免用户打开页面是空的。"""
    time.sleep(3)
    try:
        count = db.scalar("SELECT COUNT(*) FROM repos", default=0)
        if count and not settings.collect_on_empty_db:
            return
        if count:
            log.info("数据库已有 %s 个仓库，跳过启动采集", count)
            return
        log.info("数据库为空，启动首次采集")
        collector.run_collection(trigger="startup")
    except Exception:
        log.exception("启动采集失败")


@app.on_event("startup")
def on_startup():
    os.makedirs(settings.data_dir, exist_ok=True)
    # 容器被杀或进程崩溃时，上一轮采集会留下 status='running' 的僵尸记录，
    # 不清理的话页面会一直显示"正在采集中"的圆点。
    collector.cleanup_stale_runs()
    scheduler.start()
    if settings.run_on_startup:
        threading.Thread(target=_bootstrap_collection, daemon=True).start()


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown()


static_dir = settings.static_dir
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    log.warning("静态资源目录不存在: %s", static_dir)

    @app.get("/")
    def index_placeholder():
        return JSONResponse(
            {
                "message": "前端静态目录未找到，仅 API 可用",
                "static_dir": static_dir,
                "api": "/api/overview",
            }
        )
