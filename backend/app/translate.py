"""中文翻译层（可选，默认关闭）。

在 .env 里配置以下四项即启用（OpenAI 兼容接口，适配 DeepSeek / 通义 / 智谱 / 公司内网网关）：

    TRANSLATE_PROVIDER=openai
    TRANSLATE_BASE_URL=https://api.deepseek.com/v1
    TRANSLATE_API_KEY=sk-xxx
    TRANSLATE_MODEL=deepseek-chat

设计要点：
- 只翻一次：描述按内容哈希缓存，原文没变就不再翻；标签按 slug 全局去重，翻一次永久复用。
- 批量提交：一次请求翻一批，提示词成本摊薄到每条几个 token。
- 永不阻塞：任何异常都只记日志并跳过，采集主流程与页面展示完全不受影响。
"""
import hashlib
import json
import logging
import re
import time

import httpx

from .config import settings

log = logging.getLogger("gh.translate")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FENCE_RE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)

DESC_SYSTEM = (
    "你是技术文档翻译。用户会给出一组 GitHub 仓库的英文简介，请逐条翻译成简体中文。"
    "要求：1) 保留专有名词、产品名、库名与技术缩写（如 React、Kubernetes、LLM、MCP）；"
    "2) 不添加原文没有的信息，不解释、不加粗、不换行；"
    "3) 每条译文控制在 60 个汉字以内，通顺、口语化，面向不熟悉英文的读者；"
    "4) 严格只输出一个 JSON 字符串数组，元素个数与顺序必须和输入完全一致，"
    '例如 ["译文一","译文二"]，不要输出任何其它内容。'
)

TOPIC_SYSTEM = (
    "你是技术术语翻译。用户会给出一组 GitHub 标签（英文小写短语），"
    "请分别翻译成 2 到 6 个汉字的简体中文技术用语。"
    "保留专有名词（如 React、Kubernetes、Docker 不翻译）。"
    "严格只输出一个 JSON 字符串数组，元素个数与顺序必须和输入完全一致，不要输出任何其它内容。"
)


class BadResponse(Exception):
    """模型返回的条数或格式不对。可以像超时一样拆小重试，而不是整批丢弃。"""


def content_hash(text):
    """原文指纹，用于判断是否需要重翻。"""
    return hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()


def is_chinese(text):
    """已经是中文（或中英混排）的没必要再翻。"""
    if not text:
        return True
    cjk = len(_CJK_RE.findall(text))
    return cjk >= 4 and cjk * 3 >= len(text)


class Translator:
    """把英文描述与标签翻成中文。

    对慢网关友好：整批超时会自动拆成两半重试，而不是整批丢弃；
    连续多批失败会提前结束本轮，避免在坏接口上空转几十分钟。
    """

    MAX_CONSECUTIVE_FAILS = 3   # 连续失败多少批就放弃本轮
    MAX_SPLIT_DEPTH = 2         # 超时拆半的最大层数
    SLOW_SECONDS_PER_ITEM = 3.0  # 单条超过这个耗时就在日志里提示调小批量

    def __init__(self, cfg=None):
        self.cfg = cfg or settings
        self.client = httpx.Client(timeout=self.cfg.translate_timeout) if self.enabled else None
        self.requests = 0    # 本轮实际发出的请求数
        self.failures = 0    # 本轮失败批次数
        self.splits = 0      # 本轮因超时拆半的次数

    @property
    def enabled(self):
        return bool(self.cfg.translation_enabled)

    def describe(self):
        if not self.enabled:
            return "未启用（页面显示英文原文）"
        return "%s / %s" % (self.cfg.translate_provider, self.cfg.translate_model)

    # ------------------------------------------------------------------ HTTP
    def _endpoint(self):
        url = (self.cfg.translate_base_url or "").rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        return url + "/chat/completions"

    def _reset_stats(self):
        self.requests = 0
        self.failures = 0
        self.splits = 0

    def _chat(self, system, texts):
        self.requests += 1
        started = time.monotonic()
        payload = {
            "model": self.cfg.translate_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
            ],
        }
        resp = self.client.post(
            self._endpoint(),
            json=payload,
            headers={
                "Authorization": "Bearer " + self.cfg.translate_api_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if texts:
            per_item = (time.monotonic() - started) / len(texts)
            if per_item > self.SLOW_SECONDS_PER_ITEM:
                log.warning(
                    "翻译网关较慢：%d 条用了 %.0f 秒（约 %.1f 秒/条）。"
                    "建议把 TRANSLATE_BATCH 调小到 %d，或把 TRANSLATE_TIMEOUT 调到 %d",
                    len(texts), time.monotonic() - started, per_item,
                    max(1, int(30 / per_item)), int(per_item * 12) + 30,
                )
        return self._parse_array(content, len(texts))

    def _chat_safe(self, system, items, depth=0):
        """自适应请求：超时或返回条数不对时拆半重试，最大限度保住这一批。"""
        if not items:
            return []
        try:
            return self._chat(system, items)
        except (httpx.TimeoutException, BadResponse) as exc:
            if depth >= self.MAX_SPLIT_DEPTH or len(items) <= 1:
                self.failures += 1
                log.warning("翻译批次放弃（%d 条，已拆到最小）：%s", len(items), exc)
                return None
            self.splits += 1
            mid = len(items) // 2
            log.info("翻译批次需要重试（%d 条）：%s → 拆成 %d + %d", len(items), exc, mid, len(items) - mid)
            left = self._chat_safe(system, items[:mid], depth + 1)
            right = self._chat_safe(system, items[mid:], depth + 1)
            if left is None and right is None:
                return None
            return (left if left is not None else [""] * mid) + \
                   (right if right is not None else [""] * (len(items) - mid))
        except Exception as exc:  # 网络/鉴权/配额问题：整批跳过，下轮再试
            self.failures += 1
            log.warning("翻译请求失败，本批跳过：%s", exc)
            return None

    @staticmethod
    def _parse_array(content, expect):
        """宽容解析：容忍 ```json 包裹、前后多余文字；条数不符就整批丢弃。"""
        text = _FENCE_RE.sub("", (content or "").strip()).strip()
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            arr = json.loads(text)
        except ValueError:
            log.warning("翻译返回不是合法 JSON，本批跳过：%s", (content or "")[:120])
            return None
        if not isinstance(arr, list) or len(arr) != expect:
            got = len(arr) if isinstance(arr, list) else "非数组"
            raise BadResponse("返回条数不符：期望 %s，实际 %s" % (expect, got))
        return [str(x).strip() for x in arr]

    # ------------------------------------------------------------- 对外接口
    def translate_descriptions(self, pairs, deadline=None):
        """pairs: [(full_name, description)] -> {full_name: 中文}

        deadline 为 time.monotonic() 时间戳；到点就停下，剩下的留到下一轮。
        """
        out = {}
        todo = []
        for key, text in pairs:
            clean = (text or "").strip()
            if not clean or is_chinese(clean):
                continue
            if len(clean) > self.cfg.translate_max_chars:
                clean = clean[:self.cfg.translate_max_chars].rstrip()
            todo.append((key, clean))

        size = max(1, self.cfg.translate_batch)
        fails = 0
        for i in range(0, len(todo), size):
            if deadline and time.monotonic() > deadline:
                log.warning("已达本轮翻译时间上限，剩余 %d 条描述留到下一轮", len(todo) - i)
                break
            chunk = todo[i:i + size]
            arr = self._chat_safe(DESC_SYSTEM, [t for _, t in chunk])
            if arr is None:
                fails += 1
                if fails >= self.MAX_CONSECUTIVE_FAILS:
                    log.warning("连续 %d 批失败，本轮描述翻译提前结束（检查 TRANSLATE_BASE_URL / 模型名 / 网络）", fails)
                    break
                continue
            fails = 0
            for (key, _), zh in zip(chunk, arr):
                if zh:
                    out[key] = zh
        return out

    def translate_topics(self, slugs, deadline=None):
        """slugs: [slug] -> {slug: 中文}（标签很短，但慢网关上同样要限流）"""
        out = {}
        size = max(1, self.cfg.translate_batch)
        fails = 0
        for i in range(0, len(slugs), size):
            if deadline and time.monotonic() > deadline:
                log.warning("已达本轮翻译时间上限，剩余 %d 个标签留到下一轮", len(slugs) - i)
                break
            chunk = slugs[i:i + size]
            arr = self._chat_safe(TOPIC_SYSTEM, chunk)
            if arr is None:
                fails += 1
                if fails >= self.MAX_CONSECUTIVE_FAILS:
                    log.warning("连续 %d 批失败，本轮标签翻译提前结束", fails)
                    break
                continue
            fails = 0
            for slug, zh in zip(chunk, arr):
                if zh:
                    out[slug] = zh
        return out
