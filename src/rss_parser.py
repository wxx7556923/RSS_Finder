from __future__ import annotations

import asyncio
import email.utils
import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import httpx

from . import settings, storage


logger = logging.getLogger(__name__)
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSSAISummary/0.1; +http://localhost:8090)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_time_to_iso(entry: Any, fallback: str) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(time.mktime(parsed), timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            logger.warning("Failed to parse entry time; using fetched time")

    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = email.utils.parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            logger.warning("Failed to parse raw date %r; using fetched time", raw)
    return fallback


def _entry_description(entry: Any) -> str:
    content = entry.get("content")
    if content and isinstance(content, list) and content:
        content_value = content[0].get("value", "")
    else:
        content_value = ""
    return _clean_text(
        entry.get("summary")
        or entry.get("description")
        or entry.get("subtitle")
        or content_value
        or ""
    )


def load_feeds(path: Path | None = None) -> list[dict[str, str]]:
    if path is not None:
        import yaml

        if not path.exists():
            raise FileNotFoundError(f"Feeds config not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        return [
            {"name": str(item.get("name", "")).strip(), "url": str(item.get("url", "")).strip()}
            for item in config.get("feeds", [])
            if str(item.get("name", "")).strip() and str(item.get("url", "")).strip()
        ]
    return settings.feeds()


def load_biorxiv_config(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        import yaml

        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        biorxiv_config = config.get("biorxiv_api") or {}
        if not isinstance(biorxiv_config, dict) or not biorxiv_config.get("enabled"):
            return {}
        return biorxiv_config
    return settings.biorxiv_config()


def _date_range(days_back: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, days_back))
    return start.isoformat(), end.isoformat()


def _biorxiv_article(record: dict[str, Any], category: str, fetched_at: str) -> dict[str, str]:
    doi = str(record.get("doi") or "").strip()
    version = str(record.get("version") or "").strip()
    link = str(record.get("jatsxml") or "").strip()
    if doi:
        suffix = f"v{version}" if version else ""
        link = f"https://www.biorxiv.org/content/{doi}{suffix}"
    published_at = str(record.get("date") or record.get("posted") or "").strip() or fetched_at
    authors = _clean_text(str(record.get("authors") or ""))
    abstract = _clean_text(str(record.get("abstract") or ""))
    description_parts = []
    if authors:
        description_parts.append(f"Authors: {authors}")
    if category:
        description_parts.append(f"Category: {category}")
    if abstract:
        description_parts.append(abstract)
    return {
        "source_name": f"bioRxiv {category}",
        "guid": doi or link,
        "link": link,
        "original_title": _clean_text(str(record.get("title") or "")) or "(no title)",
        "original_description": "\n\n".join(description_parts),
        "published_at": published_at,
        "fetched_at": fetched_at,
    }


async def _fetch_biorxiv_api(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    config: dict[str, Any],
    limit: int | None,
    seen: int,
    fetched_at: str,
) -> tuple[int, int, int]:
    base_url = str(config.get("base_url") or "https://api.biorxiv.org").rstrip("/")
    server = str(config.get("server") or "biorxiv").strip() or "biorxiv"
    categories = [str(item).strip() for item in config.get("categories", []) if str(item).strip()]
    days_back = int(config.get("days_back") or 2)
    max_pages = max(1, int(config.get("max_pages_per_category") or 1))
    request_interval = max(0.0, float(config.get("request_interval_seconds") or 0))
    start_date, end_date = _date_range(days_back)

    added = 0
    errors = 0
    total_seen = seen
    for category in categories:
        if limit is not None and total_seen >= limit:
            break
        cursor = 0
        for page_index in range(max_pages):
            if limit is not None and total_seen >= limit:
                break
            url = f"{base_url}/details/{server}/{start_date}/{end_date}/{cursor}/json"
            try:
                response = await _get_with_fallback(client, direct_client, url, params={"category": category})
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                errors += 1
                http_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                storage.update_source_health_failure(
                    f"bioRxiv {category}",
                    url,
                    "biorxiv_api",
                    str(exc),
                    http_status,
                )
                logger.exception("Failed to fetch bioRxiv category %s: %s", category, exc)
                break

            records = body.get("collection") or []
            storage.update_source_health_success(
                f"bioRxiv {category}",
                url,
                "biorxiv_api",
                len(records),
                response.status_code,
            )
            if not records:
                break
            for record in records:
                if limit is not None and total_seen >= limit:
                    break
                total_seen += 1
                if storage.insert_article(_biorxiv_article(record, category, fetched_at)):
                    added += 1

            cursor += len(records)
            if len(records) < 100 or page_index + 1 >= max_pages:
                break
            if request_interval:
                await asyncio.sleep(request_interval)
    return added, total_seen, errors


async def _get_with_fallback(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    try:
        response = await client.get(url, **kwargs)
        if response.status_code not in {403, 407}:
            return response
        logger.warning("Request returned HTTP %s via environment proxy; retrying direct: %s", response.status_code, url)
    except httpx.HTTPError as exc:
        logger.warning("Request failed via environment proxy; retrying direct: %s: %s", url, exc)
    return await direct_client.get(url, **kwargs)


async def fetch_and_store(limit: int | None = None) -> dict[str, int]:
    storage.init_db()
    settings.reload_config()
    feeds = load_feeds()
    biorxiv_config = load_biorxiv_config()
    added = 0
    seen = 0
    errors = 0
    fetched_at = storage.now_iso()

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with (
        httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=timeout, follow_redirects=True) as client,
        httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=timeout, follow_redirects=True, trust_env=False) as direct_client,
    ):
        for feed in feeds:
            if limit is not None and seen >= limit:
                break
            try:
                response = await _get_with_fallback(client, direct_client, feed["url"])
                response.raise_for_status()
            except httpx.HTTPError as exc:
                errors += 1
                http_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                storage.update_source_health_failure(
                    feed["name"],
                    feed["url"],
                    "rss",
                    str(exc),
                    http_status,
                )
                logger.exception("Failed to fetch RSS source %s: %s", feed["name"], exc)
                continue

            parsed = feedparser.parse(response.content)
            if parsed.bozo:
                logger.warning("RSS source parsed with warning: %s", feed["name"])
            storage.update_source_health_success(
                feed["name"],
                feed["url"],
                "rss",
                len(parsed.entries),
                response.status_code,
            )

            for entry in parsed.entries:
                if limit is not None and seen >= limit:
                    break
                title = _clean_text(entry.get("title")) or "(no title)"
                link = str(entry.get("link") or "").strip()
                guid = str(entry.get("id") or entry.get("guid") or link or "").strip()
                description = _entry_description(entry)
                article = {
                    "source_name": feed["name"],
                    "guid": guid,
                    "link": link,
                    "original_title": title,
                    "original_description": description,
                    "published_at": _entry_time_to_iso(entry, fetched_at),
                    "fetched_at": fetched_at,
                }
                seen += 1
                if storage.insert_article(article):
                    added += 1

        if biorxiv_config and (limit is None or seen < limit):
            biorxiv_added, seen, biorxiv_errors = await _fetch_biorxiv_api(
                client,
                direct_client,
                biorxiv_config,
                limit,
                seen,
                fetched_at,
            )
            added += biorxiv_added
            errors += biorxiv_errors

    total = storage.get_stats()["total"]
    try:
        from . import rules

        rule_result = rules.apply_rules_to_all()
        logger.info("Rules applied after fetch: %s", rule_result)
    except Exception as exc:
        logger.exception("Failed to apply rules after fetch: %s", exc)
    logger.info("Fetch complete: added=%s seen=%s total=%s errors=%s", added, seen, total, errors)
    return {"added": added, "seen": seen, "total": total, "errors": errors}
