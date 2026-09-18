"""定时任务：按固定间隔执行采集（APScheduler 后台线程）。"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import collector
from .config import settings

log = logging.getLogger("gh.scheduler")

JOB_ID = "github-collect"

_scheduler = None


def _job():
    log.info("定时采集开始")
    result = collector.run_collection(trigger="schedule")
    log.info("定时采集结束: %s", result.get("status"))
    # 翻译单独跑：采集不被它拖慢，翻不完的下一轮继续
    if settings.translation_enabled:
        tr = collector.run_translation(trigger="schedule")
        log.info("定时翻译结束: %s 写入 %s 条", tr.get("status"), tr.get("translated"))


def start():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(
        _job,
        trigger=IntervalTrigger(minutes=max(5, settings.collect_interval_minutes)),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("调度器已启动，间隔 %s 分钟", settings.collect_interval_minutes)
    return scheduler


def shutdown():
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover
            pass
        _scheduler = None


def next_run_time():
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    if not job or not job.next_run_time:
        return None
    return job.next_run_time.replace(microsecond=0).isoformat()
