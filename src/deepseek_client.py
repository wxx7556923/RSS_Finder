from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from . import settings, storage


logger = logging.getLogger(__name__)


TITLE_SYSTEM_PROMPT = (
    "你是一个专业的 RSS 标题翻译助手。你的任务是把英文或其他语言的 RSS 文章标题翻译成自然、准确、简洁的中文标题。"
    "你必须只输出 JSON，不要输出 Markdown，不要输出解释，不要输出 JSON 以外的任何文字。"
)

SUMMARY_SYSTEM_PROMPT = (
    "你是一个专业的 RSS 文章摘要助手。你的任务是根据 RSS 标题、描述和链接信息，生成简短、实用、自然的中文三行摘要。"
    "你必须只输出 JSON，不要输出 Markdown，不要输出解释，不要输出 JSON 以外的任何文字。"
)

QUERY_SYSTEM_PROMPT = (
    "你是一个文献检索查询拆解助手。你的任务是把用户的中文或英文检索需求拆成适合本地标题、摘要、标签检索的关键词。"
    "你必须只输出 JSON，不要输出 Markdown，不要输出解释，不要输出 JSON 以外的任何文字。"
)

RELEVANCE_SYSTEM_PROMPT = (
    "你是一个文献相关性筛选助手。你的任务是根据用户研究方向判断文章是否值得优先阅读。"
    "你必须保守处理边界情况：看不准时标为 uncertain，不要轻易判为 irrelevant。"
    "你必须只输出 JSON，不要输出 Markdown，不要输出解释，不要输出 JSON 以外的任何文字。"
)


def get_env_int(name: str, default: int) -> int:
    config = settings.deepseek_config()
    mapping = {
        "MAX_RETRIES": "max_retries",
        "TITLE_TIMEOUT_SECONDS": "title_timeout_seconds",
        "SUMMARY_TIMEOUT_SECONDS": "summary_timeout_seconds",
        "TITLE_TRANSLATE_CONCURRENCY": "title_translate_concurrency",
    }
    key = mapping.get(name)
    if key and key in config:
        try:
            return int(config.get(key))
        except (TypeError, ValueError):
            return default
    try:
        return int(default)
    except ValueError:
        return default


def _clean_json_text(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text


def parse_json_content(content: str) -> dict[str, Any]:
    if not content or not content.strip():
        raise ValueError("DeepSeek returned empty content")
    return json.loads(_clean_json_text(content))


class DeepSeekClient:
    def __init__(self) -> None:
        config = settings.deepseek_config()
        self.api_key = str(config.get("api_key") or "").strip()
        self.base_url = str(config.get("base_url") or "https://api.deepseek.com").rstrip("/")
        self.model = str(config.get("model") or "deepseek-chat")
        self.max_retries = max(1, get_env_int("MAX_RETRIES", 3))

    def _headers(self) -> dict[str, str]:
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _chat_json(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=timeout_seconds,
                )
                if response.status_code == 429:
                    raise httpx.HTTPStatusError("HTTP 429 Too Many Requests", request=response.request, response=response)
                response.raise_for_status()
                try:
                    body = response.json()
                except json.JSONDecodeError as exc:
                    raise ValueError("DeepSeek returned non-JSON HTTP response") from exc
                content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                return parse_json_content(content)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                wait_seconds = min(30.0, (2 ** (attempt - 1)) + random.uniform(0, 0.5))
                logger.warning("DeepSeek request failed on attempt %s/%s: %s", attempt, self.max_retries, exc)
                await asyncio.sleep(wait_seconds)
        raise RuntimeError(f"DeepSeek request failed after {self.max_retries} attempts: {last_error}")

    async def translate_title(self, client: httpx.AsyncClient, article: dict[str, Any]) -> str:
        prompt = f"""请翻译下面这篇 RSS 文章的标题，输出严格 JSON：

{{
"translated_title": "中文标题"
}}

要求：
* translated_title 必须是自然中文标题
* 保留必要的产品名、公司名、人名、模型名
* 不要添加原文没有的信息
* 不要夸张
* 不要营销腔
* 不要输出 Markdown
* 不要输出 JSON 以外的任何文字

文章信息：
来源：{article.get("source_name", "")}
原文标题：{article.get("original_title", "")}
原文摘要或描述：{article.get("original_description", "")}
链接：{article.get("link", "")}
"""
        result = await self._chat_json(
            client,
            [
                {"role": "system", "content": TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("TITLE_TIMEOUT_SECONDS", 30),
        )
        translated_title = str(result.get("translated_title", "")).strip()
        if not translated_title:
            raise ValueError("DeepSeek returned empty translated_title")
        return translated_title

    async def summarize(self, client: httpx.AsyncClient, article: dict[str, Any]) -> list[str]:
        prompt = f"""请为下面这篇 RSS 文章生成中文三行摘要，输出严格 JSON：

{{
"summary": ["第一行摘要", "第二行摘要", "第三行摘要"]
}}

要求：
* summary 必须正好三行
* 每行简短实用
* 不要夸张
* 不要营销腔
* 不要做推荐判断
* 不要判断和我的相关度
* 不要输出 Markdown
* 不要输出 JSON 以外的任何文字
* 如果 RSS 没有正文或 description，就只基于标题生成摘要
* 摘要只描述文章本身，不要加入外部猜测

文章信息：
来源：{article.get("source_name", "")}
原文标题：{article.get("original_title", "")}
中文标题：{article.get("translated_title") or article.get("original_title", "")}
原文摘要或描述：{article.get("original_description", "")}
链接：{article.get("link", "")}
"""
        result = await self._chat_json(
            client,
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("SUMMARY_TIMEOUT_SECONDS", 60),
        )
        summary = result.get("summary")
        if not isinstance(summary, list) or len(summary) != 3:
            raise ValueError("DeepSeek summary must contain exactly three lines")
        lines = [str(line).strip() for line in summary]
        if any(not line for line in lines):
            raise ValueError("DeepSeek returned empty summary line")
        return lines

    async def classify_relevance_batch(
        self,
        client: httpx.AsyncClient,
        profile: str,
        articles: list[dict[str, Any]],
        use_abstract: bool = False,
    ) -> list[dict[str, Any]]:
        payload_articles = []
        for article in articles:
            item = {
                "article_id": int(article.get("article_id")),
                "source_name": str(article.get("source_name") or ""),
                "title": str(article.get("original_title") or ""),
                "translated_title": str(article.get("translated_title") or ""),
                "system_tags": str(article.get("system_tags") or ""),
                "user_tags": str(article.get("tags") or ""),
            }
            if use_abstract:
                item["abstract"] = str(article.get("original_description") or "")[:1200]
            payload_articles.append(item)

        evidence = "标题、来源、标签和 RSS 摘要" if use_abstract else "标题、来源和标签"
        prompt = f"""请根据用户研究方向，对下面文章做相关性筛选，输出严格 JSON：

{{
  "items": [
    {{
      "article_id": 123,
      "relevance": "strong",
      "score": 90,
      "reason": "一句话理由"
    }}
  ]
}}

用户研究方向和筛选偏好：
{profile}

判断依据：{evidence}

分类标准：
* strong：高度符合用户方向，应该优先阅读。
* weak：有一定参考价值，但不是首要方向，保留并靠后。
* uncertain：信息不足或边界情况，保守保留。
* irrelevant：明显无关，可以过滤隐藏。

重要规则：
* 如果标题看不准，不要判为 irrelevant，判为 uncertain。
* 方法学、工具、数据库、算法、LLM、知识抽取、AI for biology、通用生物信息学方法，即使研究对象是人类/动物/材料，也通常不要判为 irrelevant，除非明显与用户方向无关。
* 纯材料、催化、电池、纳米材料、纯临床癌症机制等，如果不涉及用户声明的例外方法方向，通常判为 irrelevant。
* score 是 0 到 100 的整数。
* 每篇文章必须返回一个结果。
* 不要输出 JSON 以外的任何文字。

文章列表：
{json.dumps(payload_articles, ensure_ascii=False)}
"""
        result = await self._chat_json(
            client,
            [
                {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("SUMMARY_TIMEOUT_SECONDS", 60),
        )
        items = result.get("items")
        if not isinstance(items, list):
            raise ValueError("DeepSeek relevance response must contain items list")
        return items

    async def analyze_profile(self, client: httpx.AsyncClient, profile: str) -> dict[str, Any]:
        prompt = f"""请把下面用户研究方向转换成稳定的结构化偏好，输出严格 JSON：

{{
  "priority_terms": ["优先关注词"],
  "priority_domains": ["plant", "crop", "genomics"],
  "methods_keep": ["bioinformatics", "single-cell", "LLM"],
  "exception_terms": ["即使非本领域也保留的内容"],
  "exclude_terms": ["排除方向"],
  "weak_terms": ["弱相关但可保留方向"],
  "summary": "一句话概括"
}}

要求：
* 同时保留中文和英文关键词或常用缩写。
* methods_keep 用于表示方法学、工具、数据库、算法、AI/LLM 等应保留的例外。
* exclude_terms 只放用户明确不关注或明显应该过滤的方向。
* 不要输出 JSON 以外的任何文字。

用户描述：
{profile}
"""
        result = await self._chat_json(
            client,
            [
                {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("TITLE_TIMEOUT_SECONDS", 30),
        )
        return _clean_profile_semantics(result, profile)

    async def analyze_articles_batch(
        self,
        client: httpx.AsyncClient,
        articles: list[dict[str, Any]],
        use_abstract: bool = False,
    ) -> list[dict[str, Any]]:
        payload_articles = []
        for article in articles:
            item = {
                "article_id": int(article.get("article_id")),
                "source_name": str(article.get("source_name") or ""),
                "title": str(article.get("original_title") or ""),
                "translated_title": str(article.get("translated_title") or ""),
                "system_tags": str(article.get("system_tags") or ""),
                "user_tags": str(article.get("tags") or ""),
            }
            if use_abstract:
                item["abstract"] = str(article.get("original_description") or "")[:1200]
            payload_articles.append(item)

        evidence = "标题、来源、标签和摘要" if use_abstract else "标题、来源和标签"
        prompt = f"""请只理解文章本身，不要判断和任何用户是否相关。输出严格 JSON：

{{
  "items": [
    {{
      "article_id": 123,
      "domains": ["plant", "human", "material"],
      "organisms": ["Brassica napus"],
      "topics": ["genomics", "cancer", "breeding"],
      "methods": ["GWAS", "single-cell", "LLM"],
      "content_type": "research|review|method|tool|database|clinical|material|other",
      "is_method_tool": true,
      "exclusion_flags": ["pure_material", "clinical_cancer"],
      "summary": "一句话描述文章语义",
      "confidence": 80
    }}
  ]
}}

判断依据：{evidence}

要求：
* domains/topics/methods 使用简短中文或英文术语均可，优先保留英文领域词和缩写。
* is_method_tool 为 true 表示这是方法、工具、数据库、算法、benchmark、LLM/AI、生物信息学流程等文章。
* exclusion_flags 可包含 pure_material、clinical_cancer、editorial_news、none 等。
* confidence 是 0 到 100 的整数。
* 每篇文章必须返回一条。
* 不要输出 JSON 以外的任何文字。

文章列表：
{json.dumps(payload_articles, ensure_ascii=False)}
"""
        result = await self._chat_json(
            client,
            [
                {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("SUMMARY_TIMEOUT_SECONDS", 60),
        )
        items = result.get("items")
        if not isinstance(items, list):
            raise ValueError("DeepSeek semantic response must contain items list")
        return items


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value:
        raw_items = [value]
    else:
        raw_items = []
    result = []
    seen = set()
    for item in raw_items:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text[:80])
    return result[:30]


def _clean_profile_semantics(value: dict[str, Any], profile: str) -> dict[str, Any]:
    return {
        "priority_terms": _as_list(value.get("priority_terms")),
        "priority_domains": _as_list(value.get("priority_domains")),
        "methods_keep": _as_list(value.get("methods_keep")),
        "exception_terms": _as_list(value.get("exception_terms")),
        "exclude_terms": _as_list(value.get("exclude_terms")),
        "weak_terms": _as_list(value.get("weak_terms")),
        "summary": str(value.get("summary") or profile[:180]).strip()[:240],
    }


def _fallback_profile_semantics(profile: str) -> dict[str, Any]:
    lowered = profile.casefold()
    priority_terms = []
    methods_keep = []
    exclude_terms = []
    weak_terms = []
    for term in [
        "plant", "植物", "crop", "作物", "brassica", "油菜", "rapeseed", "canola",
        "genomics", "基因组", "breeding", "育种", "single-cell", "single cell", "单细胞",
        "gwas", "qtl", "pangenome", "泛基因组",
    ]:
        if term.casefold() in lowered:
            priority_terms.append(term)
    for term in [
        "method", "方法", "tool", "工具", "database", "数据库", "algorithm", "算法",
        "bioinformatics", "生物信息", "llm", "large language model", "AI", "benchmark",
    ]:
        if term.casefold() in lowered:
            methods_keep.append(term)
    for term in ["material", "材料", "clinical cancer", "临床癌症", "cancer", "癌症"]:
        if term.casefold() in lowered and ("不" in lowered or "无意义" in lowered or "过滤" in lowered):
            exclude_terms.append(term)
    for term in ["human", "人类", "animal", "动物"]:
        if term.casefold() in lowered:
            weak_terms.append(term)
    synonym_map = {
        "植物": ["plant"],
        "plant": ["植物"],
        "作物": ["crop"],
        "crop": ["作物"],
        "油菜": ["Brassica", "rapeseed", "canola"],
        "基因组": ["genomics", "genome"],
        "育种": ["breeding"],
        "单细胞": ["single-cell", "single cell"],
        "方法": ["method"],
        "工具": ["tool"],
        "数据库": ["database"],
        "算法": ["algorithm"],
        "生物信息": ["bioinformatics"],
        "材料": ["material"],
        "癌症": ["cancer"],
    }
    for bucket in [priority_terms, methods_keep, exclude_terms, weak_terms]:
        additions = []
        for item in bucket:
            additions.extend(synonym_map.get(item.casefold(), synonym_map.get(item, [])))
        bucket.extend(additions)
    return _clean_profile_semantics(
        {
            "priority_terms": priority_terms,
            "priority_domains": priority_terms,
            "methods_keep": methods_keep,
            "exception_terms": methods_keep,
            "exclude_terms": exclude_terms,
            "weak_terms": weak_terms,
            "summary": profile[:180],
        },
        profile,
    )


def _clean_article_semantics(value: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    try:
        confidence = int(value.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    return {
        "domains": _as_list(value.get("domains")),
        "organisms": _as_list(value.get("organisms")),
        "topics": _as_list(value.get("topics")),
        "methods": _as_list(value.get("methods")),
        "content_type": str(value.get("content_type") or "other").strip()[:40],
        "is_method_tool": bool(value.get("is_method_tool")),
        "exclusion_flags": _as_list(value.get("exclusion_flags")),
        "summary": str(value.get("summary") or article.get("original_title") or "").strip()[:240],
        "confidence": max(0, min(confidence, 100)),
    }


def _load_semantics(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _semantic_text(article: dict[str, Any], semantics: dict[str, Any]) -> str:
    parts = [
        article.get("source_name", ""),
        article.get("original_title", ""),
        article.get("translated_title", ""),
        article.get("system_tags", ""),
        article.get("tags", ""),
        semantics.get("content_type", ""),
        semantics.get("summary", ""),
        " ".join(_as_list(semantics.get("domains"))),
        " ".join(_as_list(semantics.get("organisms"))),
        " ".join(_as_list(semantics.get("topics"))),
        " ".join(_as_list(semantics.get("methods"))),
        " ".join(_as_list(semantics.get("exclusion_flags"))),
    ]
    return " ".join(str(part or "") for part in parts).casefold()


def _term_hits(terms: list[str], text: str) -> int:
    hits = 0
    for term in terms:
        clean = term.casefold().strip()
        if clean and clean in text:
            hits += 1
    return hits


def _local_relevance(
    article: dict[str, Any],
    profile_semantics: dict[str, Any],
    profile_hash: str,
    source: str,
) -> dict[str, Any] | None:
    semantics = _load_semantics(article.get("article_semantics"))
    if not semantics:
        return None

    text = _semantic_text(article, semantics)
    priority_terms = _as_list(profile_semantics.get("priority_terms")) + _as_list(profile_semantics.get("priority_domains"))
    methods_keep = _as_list(profile_semantics.get("methods_keep")) + _as_list(profile_semantics.get("exception_terms"))
    exclude_terms = _as_list(profile_semantics.get("exclude_terms"))
    weak_terms = _as_list(profile_semantics.get("weak_terms"))

    priority_hits = _term_hits(priority_terms, text)
    method_hits = _term_hits(methods_keep, text)
    exclude_hits = _term_hits(exclude_terms, text)
    weak_hits = _term_hits(weak_terms, text)
    flags = {item.casefold() for item in _as_list(semantics.get("exclusion_flags"))}
    is_method_tool = bool(semantics.get("is_method_tool"))

    score = 42
    reasons = []
    if priority_hits:
        score += min(priority_hits * 14, 36)
        reasons.append("匹配研究方向关键词")
    if method_hits or (is_method_tool and methods_keep):
        score += 18
        reasons.append("符合保留的方法/工具类例外")
    if weak_hits:
        score += 8
        reasons.append("命中弱相关保留方向")
    if exclude_hits:
        score -= 30
        reasons.append("命中排除方向")
    if ("pure_material" in flags or "clinical_cancer" in flags) and not method_hits:
        score -= 34
        reasons.append("语义标记为应过滤方向")
    if is_method_tool and not priority_hits and not method_hits:
        score += 8
        reasons.append("方法工具类文章保守保留")

    score = max(0, min(score, 100))
    if score >= 78 and (priority_hits or method_hits):
        label = "strong"
        confidence = 88
    elif 50 <= score < 78 and (priority_hits or method_hits or weak_hits or is_method_tool):
        label = "weak"
        confidence = 76
    elif score <= 18 and (exclude_hits or "pure_material" in flags or "clinical_cancer" in flags):
        label = "irrelevant"
        confidence = 86
    else:
        return None

    reason = "；".join(reasons[:3]) or "基于缓存语义本地判断"
    return {
        "article_id": int(article["article_id"]),
        "relevance": label,
        "score": score,
        "reason": f"{reason}（语义缓存）",
        "profile_hash": profile_hash,
        "source": f"semantic_{source}",
        "confidence": confidence,
    }


async def translate_pending_titles(concurrency: int = 5, limit: int | None = None) -> dict[str, int]:
    storage.init_db()
    articles = storage.get_articles_for_title_translation(limit)
    if not articles:
        return {"success": 0, "failed": 0, "skipped": 0}

    concurrency = max(1, min(int(concurrency or 1), 20))
    deepseek = DeepSeekClient()
    if not deepseek.api_key or deepseek.api_key == "your_deepseek_api_key_here":
        for article in articles:
            storage.update_title_status(article["article_id"], "failed")
        logger.error("DEEPSEEK_API_KEY is not configured; title translation skipped")
        return {"success": 0, "failed": len(articles), "skipped": 0}

    success = 0
    failed = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def translate_one(article: Any, client: httpx.AsyncClient) -> bool:
        async with semaphore:
            article_id = int(article["article_id"])
            try:
                translated = await deepseek.translate_title(client, row_to_dict(article))
                storage.update_title_status(article_id, "translated", translated)
                return True
            except Exception as exc:
                logger.exception("Failed to translate title for article_id=%s: %s", article_id, exc)
                storage.update_title_status(article_id, "failed")
                return False

    async with httpx.AsyncClient() as http_client:
        if concurrency == 1:
            results = []
            for article in articles:
                results.append(await translate_one(article, http_client))
        else:
            results = await asyncio.gather(*(translate_one(article, http_client) for article in articles))

    success = sum(1 for item in results if item)
    failed = len(results) - success
    logger.info("Title translation complete: success=%s failed=%s", success, failed)
    return {"success": success, "failed": failed, "skipped": 0}


async def summarize_article(article_id: int, force: bool = False) -> dict[str, Any]:
    storage.init_db()
    article = storage.get_article(article_id)
    if article is None:
        raise KeyError(f"Article not found: {article_id}")

    if article["summary_status"] == "summarized" and not force:
        return {
            "article_id": article_id,
            "summary": [article["summary_line_1"], article["summary_line_2"], article["summary_line_3"]],
            "cached": True,
        }

    deepseek = DeepSeekClient()
    if not deepseek.api_key or deepseek.api_key == "your_deepseek_api_key_here":
        storage.update_summary(article_id, "failed")
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    async with httpx.AsyncClient() as http_client:
        try:
            lines = await deepseek.summarize(http_client, row_to_dict(article))
            storage.update_summary(article_id, "summarized", lines[0], lines[1], lines[2])
            logger.info("Summary generated for article_id=%s", article_id)
            return {"article_id": article_id, "summary": lines, "cached": False}
        except Exception as exc:
            logger.exception("Failed to summarize article_id=%s: %s", article_id, exc)
            storage.update_summary(article_id, "failed")
            raise


async def expand_search_query(query: str) -> dict[str, Any]:
    text = query.strip()
    if not text:
        return {"terms": [], "reason": ""}

    prompt = f"""请把下面的文献检索需求拆成适合本地数据库模糊检索的关键词，输出严格 JSON：

{{
  "terms": ["关键词1", "keyword 2"],
  "reason": "一句话说明拆解思路"
}}

要求：
* terms 数量 4 到 12 个
* 同时给中文和英文关键词
* 包含常见缩写、同义词和领域术语
* 不要给太泛的词，例如 study、research、paper、article
* 不要输出 JSON 以外的任何文字

用户检索需求：
{text}
"""
    deepseek = DeepSeekClient()
    if not deepseek.api_key or deepseek.api_key == "your_deepseek_api_key_here":
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    async with httpx.AsyncClient() as http_client:
        result = await deepseek._chat_json(
            http_client,
            [
                {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            get_env_int("TITLE_TIMEOUT_SECONDS", 30),
        )
    terms = result.get("terms") or []
    if not isinstance(terms, list):
        raise ValueError("DeepSeek query expansion must return terms list")
    clean_terms = []
    seen = set()
    for term in terms:
        value = str(term).strip()
        key = value.lower()
        if value and key not in seen:
            clean_terms.append(value)
            seen.add(key)
    return {"terms": clean_terms[:12], "reason": str(result.get("reason", "")).strip()}


async def classify_pending_relevance(
    profile: str,
    use_abstract: bool = False,
    limit: int | None = 100,
    batch_size: int = 12,
    scope: str | None = None,
) -> dict[str, Any]:
    storage.init_db()
    clean_profile = profile.strip()
    if not clean_profile:
        raise ValueError("研究方向不能为空")
    profile_hash = storage.relevance_profile_hash(clean_profile)
    storage.set_app_setting("relevance_profile", clean_profile)
    clean_scope = scope or storage.get_app_setting("relevance_scope", "unread_pending")
    if clean_scope not in {"new_only", "unread_pending"}:
        clean_scope = "unread_pending"

    articles = storage.get_articles_for_relevance(profile_hash, limit=limit, scope=clean_scope)
    source = "title_abstract" if use_abstract else "title"
    if not articles:
        return {
            "checked": 0,
            "strong": 0,
            "weak": 0,
            "uncertain": 0,
            "irrelevant": 0,
            "failed": 0,
            "local_checked": 0,
            "deepseek_checked": 0,
            "semantic_cached": 0,
            "source": source,
            "scope": clean_scope,
        }

    deepseek = DeepSeekClient()
    if not deepseek.api_key or deepseek.api_key == "your_deepseek_api_key_here":
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    batch_size = max(1, min(int(batch_size or 12), 30))
    counts: dict[str, int] = {
        "checked": 0,
        "strong": 0,
        "weak": 0,
        "uncertain": 0,
        "irrelevant": 0,
        "failed": 0,
        "local_checked": 0,
        "deepseek_checked": 0,
        "semantic_cached": 0,
    }

    async with httpx.AsyncClient() as http_client:
        profile_setting_key = f"profile_semantics:{profile_hash}"
        profile_semantics = _load_semantics(storage.get_app_setting(profile_setting_key))
        if not profile_semantics:
            try:
                profile_semantics = await deepseek.analyze_profile(http_client, clean_profile)
            except Exception as exc:
                logger.exception("Profile semantic analysis failed, using local fallback: %s", exc)
                profile_semantics = _fallback_profile_semantics(clean_profile)
            storage.set_app_setting(profile_setting_key, json.dumps(profile_semantics, ensure_ascii=False, sort_keys=True))

        article_dicts = [row_to_dict(row) for row in articles]
        missing_semantics = [article for article in article_dicts if not _load_semantics(article.get("article_semantics"))]
        for start in range(0, len(missing_semantics), batch_size):
            batch = missing_semantics[start : start + batch_size]
            try:
                semantic_items = await deepseek.analyze_articles_batch(http_client, batch, use_abstract=use_abstract)
            except Exception as exc:
                logger.exception("Article semantic analysis batch failed: %s", exc)
                continue
            semantic_by_id = {}
            for item in semantic_items:
                try:
                    semantic_by_id[int(item.get("article_id"))] = item
                except (TypeError, ValueError):
                    continue
            for article in batch:
                article_id = int(article["article_id"])
                item = semantic_by_id.get(article_id)
                if not item:
                    continue
                cleaned_semantics = _clean_article_semantics(item, article)
                storage.update_article_semantics(article_id, cleaned_semantics, source)
                article["article_semantics"] = json.dumps(cleaned_semantics, ensure_ascii=False, sort_keys=True)
                counts["semantic_cached"] += 1

        remaining_for_deepseek = []
        for article in article_dicts:
            local = _local_relevance(article, profile_semantics, profile_hash, source)
            if local is None:
                remaining_for_deepseek.append(article)
                continue
            label = str(local["relevance"])
            storage.update_article_relevance(
                int(local["article_id"]),
                label,
                int(local["score"]),
                str(local["reason"]),
                profile_hash,
                str(local["source"]),
            )
            counts["checked"] += 1
            counts["local_checked"] += 1
            counts[label] += 1

        for start in range(0, len(remaining_for_deepseek), batch_size):
            batch = remaining_for_deepseek[start : start + batch_size]
            try:
                results = await deepseek.classify_relevance_batch(http_client, clean_profile, batch, use_abstract=use_abstract)
            except Exception as exc:
                counts["failed"] += len(batch)
                logger.exception("Relevance classification batch failed: %s", exc)
                continue

            result_by_id = {}
            for item in results:
                try:
                    result_by_id[int(item.get("article_id"))] = item
                except (TypeError, ValueError):
                    continue

            for article in batch:
                article_id = int(article["article_id"])
                item = result_by_id.get(article_id)
                if not item:
                    counts["failed"] += 1
                    continue
                label = str(item.get("relevance") or "uncertain").strip()
                if label not in {"strong", "weak", "uncertain", "irrelevant"}:
                    label = "uncertain"
                try:
                    score = int(item.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0
                reason = str(item.get("reason") or "").strip()
                storage.update_article_relevance(
                    article_id,
                    label,
                    score,
                    reason,
                    profile_hash,
                    source,
                )
                counts["checked"] += 1
                counts["deepseek_checked"] += 1
                counts[label] += 1

    logger.info("Relevance classification complete: %s source=%s", counts, source)
    return {**counts, "source": source, "scope": clean_scope}
