from __future__ import annotations

import email.utils
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from . import settings, storage


OUTPUT_XML = storage.OUTPUT_DIR / "output.xml"
OUTPUT_ORIGINAL_XML = storage.OUTPUT_DIR / "original.xml"


def _parse_datetime(value: str | None) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _pub_date(value: str | None) -> str:
    return email.utils.format_datetime(_parse_datetime(value), usegmt=True)


def _description(article: Any) -> str:
    if article["summary_status"] == "summarized":
        summary_text = "\n".join(
            [
                "中文摘要：",
                "",
                f"1. {article['summary_line_1'] or ''}",
                f"2. {article['summary_line_2'] or ''}",
                f"3. {article['summary_line_3'] or ''}",
            ]
        )
    else:
        summary_text = "RSS 摘要：\n" + (article["original_description"] or "RSS 未提供摘要。")

    return "\n\n".join(
        [
            summary_text,
            f"原文标题：\n{article['original_title'] or ''}",
            f"作者：\n{article['authors'] or ''}",
            f"DOI：\n{article['doi'] or ''}",
            f"来源：\n{article['source_name'] or ''}",
            f"原文链接：\n{article['link'] or ''}",
        ]
    )


def _original_description(article: Any) -> str:
    source_text = article["original_description"] or "RSS 未提供摘要。"
    return "\n\n".join(
        [
            f"原始摘要：\n{source_text}",
            f"作者：\n{article['authors'] or ''}",
            f"DOI：\n{article['doi'] or ''}",
            f"来源：\n{article['source_name'] or ''}",
            f"原文链接：\n{article['link'] or ''}",
        ]
    )


def build_feed(path: Path = OUTPUT_XML) -> dict[str, Any]:
    storage.init_db()
    storage.ensure_dirs()

    config = settings.output_rss_config()
    channel_title = str(config.get("title") or "Paper Radar Feed")
    channel_link = str(config.get("link") or "http://localhost:8090/feed.xml")
    channel_description = str(config.get("description") or "自动翻译标题并保留 RSS 摘要的 Feed")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = channel_description
    ET.SubElement(channel, "language").text = "zh-CN"
    ET.SubElement(channel, "lastBuildDate").text = _pub_date(storage.now_iso())

    articles = storage.get_translated_articles()
    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["translated_title"] or article["original_title"] or ""
        ET.SubElement(item, "link").text = article["link"] or ""
        guid = ET.SubElement(item, "guid")
        guid.text = article["link"] or article["guid"] or article["dedupe_key"] or str(article["article_id"])
        guid.set("isPermaLink", "false")
        ET.SubElement(item, "pubDate").text = _pub_date(article["published_at"] or article["fetched_at"])
        ET.SubElement(item, "description").text = _description(article)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return {"path": str(path), "items": len(articles)}


def build_original_feed(path: Path = OUTPUT_ORIGINAL_XML) -> dict[str, Any]:
    storage.init_db()
    storage.ensure_dirs()

    config = settings.output_rss_config()
    channel_title = str(config.get("original_title") or "Paper Radar Original Feed")
    channel_link = str(config.get("link") or "http://localhost:8090/feed.xml").replace("feed.xml", "feed-original.xml")
    channel_description = str(config.get("original_description") or "不调用 DeepSeek，保留原始标题和 RSS 原始摘要的 Feed")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_link
    ET.SubElement(channel, "description").text = channel_description
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "lastBuildDate").text = _pub_date(storage.now_iso())

    articles = storage.get_original_feed_articles()
    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["original_title"] or ""
        ET.SubElement(item, "link").text = article["link"] or ""
        guid = ET.SubElement(item, "guid")
        guid.text = article["link"] or article["guid"] or article["dedupe_key"] or str(article["article_id"])
        guid.set("isPermaLink", "false")
        ET.SubElement(item, "pubDate").text = _pub_date(article["published_at"] or article["fetched_at"])
        ET.SubElement(item, "description").text = _original_description(article)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return {"path": str(path), "items": len(articles)}


def ensure_feed_exists() -> Path:
    if not OUTPUT_XML.exists():
        build_feed(OUTPUT_XML)
    return OUTPUT_XML


def ensure_original_feed_exists() -> Path:
    if not OUTPUT_ORIGINAL_XML.exists():
        build_original_feed(OUTPUT_ORIGINAL_XML)
    return OUTPUT_ORIGINAL_XML
