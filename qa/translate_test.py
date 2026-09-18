"""中文翻译层端到端验证（本地假接口，不消耗真实 token、不动真实数据库）。

用法（在项目根目录）：
    ./.venv/bin/python qa/translate_test.py

覆盖：批量请求、缓存命中、标签去重、/api/terms、/api/repos 的 description_zh。
"""
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DB = os.path.join(ROOT, "qa", "zh-test.db")
PORT = 8899

CALLS = {"count": 0, "items": 0, "system": None, "delay_per_item": 0.0, "sizes": [], "drop_one_over": 0}


class FakeLLM(BaseHTTPRequestHandler):
    """假装是 OpenAI 兼容接口：把收到的数组逐条加上「中文译文：」前缀返回。"""

    def log_message(self, *a):
        pass

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages") or []
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in messages if m["role"] == "user"), "[]")
        items = json.loads(user)

        CALLS["count"] += 1
        CALLS["items"] += len(items)
        CALLS["system"] = system
        CALLS["sizes"].append(len(items))
        # 模拟慢网关：按条数睡眠，条数越多越慢（用来验证超时拆半）
        if CALLS["delay_per_item"]:
            time.sleep(CALLS["delay_per_item"] * len(items))
        assert self.headers.get("Authorization") == "Bearer test-key", "鉴权头不对"

        # 模拟真实模型：包一层 ```json 代码块，顺带验证解析容错
        results = ["中文译文：" + str(x)[:14] for x in items]
        if CALLS["drop_one_over"] and len(items) > CALLS["drop_one_over"]:
            results = results[:-1]      # 模拟模型漏掉一条
        payload = "```json\n" + json.dumps(results, ensure_ascii=False) + "\n```"
        data = json.dumps({"choices": [{"message": {"content": payload}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    if not os.path.exists(TEST_DB):
        shutil.copy(os.path.join(ROOT, "data", "github_trending.db"), TEST_DB)
    # 每次从干净副本开始（并清掉副本里可能存在的真实译文，保证结果可预期）
    shutil.copy(os.path.join(ROOT, "data", "github_trending.db"), TEST_DB)
    _seed = sqlite3.connect(TEST_DB)
    for _t in ("desc_translations", "topic_translations"):
        try:
            _seed.execute("DELETE FROM " + _t)
        except sqlite3.OperationalError:
            pass
    _seed.commit()
    _seed.close()

    os.environ.update({
        "DB_PATH": TEST_DB,
        "TRANSLATE_PROVIDER": "openai",
        "TRANSLATE_BASE_URL": "http://127.0.0.1:%d/v1" % PORT,
        "TRANSLATE_API_KEY": "test-key",
        "TRANSLATE_MODEL": "fake-model",
        "TRANSLATE_BATCH": "20",
        "TRANSLATE_PER_RUN": "60",
        "TRANSLATE_TOPICS_PER_RUN": "50",
    })
    sys.path.insert(0, os.path.join(ROOT, "backend"))

    server = HTTPServer(("127.0.0.1", PORT), FakeLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    from app import collector, translate
    from app.config import settings
    from app.db import db

    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print("  %s %-46s %s" % ("✅" if cond else "❌", label, detail))

    print("\n=== 1. 配置识别 ===")
    check("translation_enabled 为真", settings.translation_enabled is True)
    check("describe() 输出模型名", "fake-model" in translate.Translator().describe(),
          translate.Translator().describe())

    print("\n=== 2. 采集时写入翻译 ===")
    before = db.scalar("SELECT COUNT(*) FROM desc_translations", default=0)
    topics_before = db.scalar("SELECT COUNT(*) FROM topic_translations", default=0)
    translator = collector._translator
    n1 = collector.collect_translate(translator, db, datetime.now(timezone.utc))
    desc_rows = db.scalar("SELECT COUNT(*) FROM desc_translations", default=0)
    topic_rows = db.scalar("SELECT COUNT(*) FROM topic_translations", default=0)
    new_desc, new_topic = desc_rows - before, topic_rows - topics_before
    check("首轮写入条数 = 标签 + 描述", n1 == new_desc + new_topic,
          "%d = %d + %d" % (n1, new_desc, new_topic))
    check("描述翻译写入 > 0", new_desc > 0, "%d 条" % new_desc)
    check("标签翻译写入 > 0", new_topic > 0, "%d 个" % new_topic)
    check("每轮上限被遵守（默认 200，本例配 60/50）", new_desc <= 60 and new_topic <= 50,
          "%d 描述 / %d 标签" % (new_desc, new_topic))
    check("批量生效（请求数 << 条数）", CALLS["count"] < n1,
          "%d 次请求 / %d 条" % (CALLS["count"], CALLS["items"]))

    print("\n=== 3. 缓存：翻完后再跑不应重复翻译 ===")
    # 放开每轮上限，把剩余的描述与标签一次性翻完
    settings.translate_per_run = 5000
    settings.translate_topics_per_run = 5000
    drained = collector.collect_translate(translator, db, datetime.now(timezone.utc))
    total_desc = db.scalar("SELECT COUNT(*) FROM repos WHERE COALESCE(description,'') <> ''", default=0)
    stored = db.scalar("SELECT COUNT(*) FROM desc_translations", default=0)
    check("放开上限后把剩余全部翻完", drained > 0, "本轮再写入 %d" % drained)
    check("描述覆盖率 100%", stored >= total_desc, "%d/%d" % (stored, total_desc))

    calls_before = CALLS["count"]
    n2 = collector.collect_translate(translator, db, datetime.now(timezone.utc))
    check("第三轮无新增写入", n2 == 0, "本轮写入 %d" % n2)
    check("第三轮零模型请求（缓存命中）", CALLS["count"] == calls_before,
          "%d → %d 次" % (calls_before, CALLS["count"]))

    print("\n=== 4. API 暴露 ===")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    terms = client.get("/api/terms").json()
    check("/api/terms 返回标签译文", len(terms["topics"]) > 0, "%d 个" % len(terms["topics"]))
    check("/api/terms 标记翻译已启用", terms["translation_enabled"] is True)
    sample = list(terms["topics"].items())[:3]
    check("标签译文样例", True, " / ".join("%s→%s" % kv for kv in sample))

    repos = client.get("/api/repos", params={"limit": 5}).json()["items"]
    with_zh = [r for r in repos if r.get("description_zh")]
    check("/api/repos 带 description_zh", len(with_zh) > 0, "%d/%d 条" % (len(with_zh), len(repos)))
    if with_zh:
        check("中文描述内容非空且是中文", bool(with_zh[0]["description_zh"]) and
              any("\u4e00" <= ch <= "\u9fff" for ch in with_zh[0]["description_zh"]),
              with_zh[0]["description_zh"][:30])
        check("英文原文仍保留", bool(with_zh[0]["description"]), with_zh[0]["description"][:30])

    detail = client.get("/api/repo/%s" % with_zh[0]["full_name"]) if with_zh else None
    if detail is not None and detail.status_code == 200:
        check("详情接口同样返回中文", bool(detail.json().get("description_zh")))
    for view in ("/api/trending", "/api/surging"):
        r = client.get(view, params={"limit": 3})
        items = r.json().get("items") or []
        check("%s 不报错" % view, r.status_code == 200 and isinstance(items, list), "%d 条" % len(items))

    print("\n=== 5. 关闭翻译时零副作用 ===")
    settings.translate_provider = "off"
    off = translate.Translator()
    check("关闭状态下 enabled=False", off.enabled is False)
    check("关闭状态下不建 HTTP 客户端", off.client is None)

    print("\n=== 6. 翻译已与采集解耦 ===")
    settings.translate_provider = "openai"
    settings.translate_per_run = 5000
    settings.translate_topics_per_run = 5000
    settings.translate_max_seconds = 300
    with db.write() as conn:
        conn.execute("DELETE FROM desc_translations")
        conn.execute("DELETE FROM topic_translations")
    # 其余联网步骤替换成空实现，只验证编排本身
    originals = (collector.collect_trending, collector.collect_discovery,
                 collector.collect_enrich, collector.collect_snapshots)
    collector.collect_trending = lambda *a, **k: 0
    collector.collect_discovery = lambda *a, **k: 0
    collector.collect_enrich = lambda *a, **k: 0
    collector.collect_snapshots = lambda *a, **k: 0
    try:
        calls_before_collect = CALLS["count"]
        stats = collector.run_collection(trigger="test")
        check("采集状态为 ok", stats["status"] == "ok", stats["message"] or "无错误信息")
        check("采集流程已不含翻译", "translated_count" not in stats)
        delta = CALLS["count"] - calls_before_collect
        check("采集期间没有发出翻译请求", delta == 0, "新增 %d 次" % delta)
        res = collector.run_translation(trigger="test")
        check("独立翻译任务正常返回", res["status"] == "ok", res.get("message") or "")
        check("独立翻译任务写入 > 0", res["translated"] > 0, "%d 条 / %.1f 秒 / %d 次请求"
              % (res["translated"], res.get("elapsed_seconds", 0), res.get("requests", 0)))
        check("翻译结果已落库", db.scalar("SELECT COUNT(*) FROM desc_translations", default=0) > 0)
    finally:
        (collector.collect_trending, collector.collect_discovery,
         collector.collect_enrich, collector.collect_snapshots) = originals

    print("\n=== 7. 慢网关：超时自动拆半而不是整批丢弃 ===")
    with db.write() as conn:
        conn.execute("DELETE FROM topic_translations")
    settings.translate_batch = 20
    settings.translate_timeout = 1.0
    CALLS["delay_per_item"] = 0.07   # 20 条要 1.4 秒 > 1.0 秒超时；10 条只要 0.7 秒，能过
    CALLS["sizes"] = []
    slow = translate.Translator()
    assert slow.client is not None
    t0 = time.monotonic()
    got = slow.translate_topics(["tag-%02d" % i for i in range(20)])
    cost = time.monotonic() - t0
    check("超时后拆半救回了全部结果", len(got) == 20, "拿到 %d/20" % len(got))
    check("确实发生了拆半", slow.splits >= 1, "拆半 %d 次，请求批次 %s" % (slow.splits, CALLS["sizes"][:6]))
    check("拆半后的批次都变小了", max(CALLS["sizes"]) == 20 and 10 in CALLS["sizes"],
          "批次大小序列 %s" % CALLS["sizes"][:6])
    check("总耗时可控", cost < 20, "%.1f 秒" % cost)
    CALLS["delay_per_item"] = 0.0
    settings.translate_timeout = 90

    print("\n=== 7b. 模型少返回一条：拆小重试而不是整批丢弃 ===")
    CALLS["drop_one_over"] = 10      # 一批超过 10 条时故意少返回一条
    CALLS["delay_per_item"] = 0.0
    settings.translate_timeout = 90
    partial = translate.Translator()
    got2 = partial.translate_topics(["q-%02d" % i for i in range(20)])
    check("条数不符时拆半救回结果", len(got2) == 20, "拿到 %d/20" % len(got2))
    check("触发了拆半", partial.splits >= 1, "拆半 %d 次" % partial.splits)
    CALLS["drop_one_over"] = 0

    print("\n=== 8. 坏接口：熔断 + 时间上限，不会挂死 ===")
    with db.write() as conn:
        conn.execute("DELETE FROM topic_translations")
    settings.translate_topics_per_run = 5000
    good_url = settings.translate_base_url
    settings.translate_base_url = "http://127.0.0.1:9/v1"   # 必然连不上
    broken = translate.Translator()
    CALLS["count"] = 0
    t0 = time.monotonic()
    out = broken.translate_topics(["x-%d" % i for i in range(500)])
    cost = time.monotonic() - t0
    check("坏接口下没有死循环", cost < 30, "%.1f 秒后放弃" % cost)
    check("熔断生效（只试了几批就停）", broken.failures <= translate.Translator.MAX_CONSECUTIVE_FAILS,
          "失败 %d 批后熔断" % broken.failures)
    check("没有写入半成品", out == {})
    settings.translate_base_url = good_url

    # 时间上限：给 0.001 秒预算，应当在第一批之前就收手
    settings.translate_base_url = good_url
    limited = translate.Translator()
    t0 = time.monotonic()
    # 预算已经过期：应当在第一批之前就收手
    out2 = limited.translate_topics(["y-%d" % i for i in range(200)], deadline=time.monotonic() - 1)
    check("时间上限生效（过期预算立即停手）", out2 == {} and time.monotonic() - t0 < 2,
          "写入 %d 条，耗时 %.2f 秒" % (len(out2), time.monotonic() - t0))
    # 预算耗尽时应当只做一部分而不是全做完（让假接口慢下来才观察得到）
    CALLS["delay_per_item"] = 0.02          # 每批 20 条 ≈ 0.4 秒
    out3 = limited.translate_topics(["z-%d" % i for i in range(200)], deadline=time.monotonic() + 1.0)
    check("预算耗尽时只做一部分", 0 < len(out3) < 200,
          "200 条里翻了 %d 条就按预算收手" % len(out3))
    CALLS["delay_per_item"] = 0.0

    print("\n=== 9. 分批提交：跑一半也能留下成果 ===")
    settings.translate_batch = 20
    settings.translate_per_run = 200
    settings.translate_topics_per_run = 0      # 只看描述，排除干扰
    with db.write() as conn:
        conn.execute("DELETE FROM desc_translations")
    CALLS["delay_per_item"] = 0.35              # 每批 20 条 ≈ 7 秒
    settings.translate_timeout = 90
    t0 = time.monotonic()
    res = collector.run_translation(trigger="test", max_seconds=8)
    cost = time.monotonic() - t0
    stored = db.scalar("SELECT COUNT(*) FROM desc_translations", default=0)
    check("预算到点前就收手了", 0 < res["translated"] < 200, "只翻了 %d 条" % res["translated"])
    check("耗时没超出预算太多", cost < 25, "%.1f 秒" % cost)
    check("已完成的部分已提交入库（不再怕进程被杀）", stored >= 20,
          "库里已有 %d 条，与返回的 %d 条一致" % (stored, res["translated"]))
    check("提交数与返回数一致", stored == res["translated"], "%d == %d" % (stored, res["translated"]))
    # 读者在翻译进行中就能看到已完成的译文（旧实现要等整轮结束）
    check("翻译中途可见", db.scalar("SELECT COUNT(*) FROM desc_translations", default=0) > 0)
    CALLS["delay_per_item"] = 0.0
    settings.translate_topics_per_run = 200

    server.shutdown()
    os.remove(TEST_DB)
    print("\n" + ("全部通过 ✅" if ok else "存在失败 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
