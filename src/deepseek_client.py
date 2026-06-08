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


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


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
