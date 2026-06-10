from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import deepseek_client, rss_parser, rss_writer, settings, storage


storage.setup_logging()
storage.init_db()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_title())
app.mount("/static", StaticFiles(directory=storage.BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=storage.BASE_DIR / "templates")
templates.env.filters["urlquote"] = lambda value: quote(str(value), safe="")


def _fallback_terms(query: str) -> list[str]:
    parts = re.split(r"[\s,，;；、]+", query.strip())
    return [part for part in parts if len(part) >= 2][:12]


def _source_label(source_name: str) -> str:
    label = source_name.strip()
    for suffix in [
        " (ScienceDirect Feed)",
        " (Oxford Academic)",
        " (CSHL Press)",
        " (Wiley)",
        " (Springer)",
        " - Advance Articles",
        " - GR-in-Advance",
        " Current",
    ]:
        label = label.replace(suffix, "")
    return label.strip() or source_name


def _source_options() -> list[dict[str, str]]:
    return [{"name": name, "label": _source_label(name)} for name in storage.list_source_names()]


READING_LEVELS = {
    "none": "未分类",
    "skim": "摘要够了",
    "readable": "可读",
    "deep_read": "精读",
}


READ_STATUS_LABELS = {
    "unread": "未读",
    "opened": "已打开",
    "read": "已读",
    "to_read": "待读",
    "filtered": "已过滤",
}


@app.get("/")
async def index(
    request: Request,
    mode: str | None = Query(default=None),
    q: str = Query(default=""),
    smart_q: str = Query(default=""),
    source: str = Query(default=""),
    read_status: str = Query(default=""),
    reading_level: str = Query(default=""),
    favorite: bool = Query(default=False),
    author: str = Query(default=""),
    doi: str = Query(default=""),
    tag: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    mode_value = mode or str(settings.section("app").get("default_mode") or "original")
    view_mode = "original" if mode_value == "original" else "ds"
    effective_read_status = read_status.strip()
    if not effective_read_status:
        effective_read_status = None
    effective_reading_level = reading_level.strip()
    if not effective_reading_level:
        effective_reading_level = None
    smart_terms: list[str] = []
    smart_reason = ""
    smart_error = ""
    if smart_q.strip():
        try:
            expanded = await deepseek_client.expand_search_query(smart_q)
            smart_terms = expanded["terms"]
            smart_reason = expanded.get("reason", "")
        except Exception as exc:
            logger.exception("Smart search expansion failed: %s", exc)
            smart_terms = _fallback_terms(smart_q)
            smart_error = "智能拆解失败，已使用本地关键词切分。"
    articles = storage.list_articles(
        limit=settings.page_limit(),
        query=q.strip() or None,
        smart_terms=smart_terms,
        source=source.strip() or None,
        read_status=effective_read_status,
        reading_level=effective_reading_level,
        favorite=True if favorite else None,
        author=author.strip() or None,
        doi=doi.strip() or None,
        tag=tag.strip() or None,
        date_from=date_from.strip() or None,
        date_to=date_to.strip() or None,
    )
    if not read_status.strip():
        articles = [article for article in articles if article["read_status"] not in {"filtered", "read"}]
    stats = storage.get_stats()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "articles": articles,
            "articles_count": len(articles),
            "stats": stats,
            "app_title": settings.app_title(),
            "mode": view_mode,
            "query": q,
            "smart_q": smart_q,
            "smart_terms": smart_terms,
            "smart_reason": smart_reason,
            "smart_error": smart_error,
            "source": source,
            "read_status": read_status,
            "reading_level": reading_level,
            "favorite": favorite,
            "author": author,
            "doi": doi,
            "tag": tag,
            "date_from": date_from,
            "date_to": date_to,
            "sources": _source_options(),
            "tag_suggestions": storage.list_tags(limit=80),
            "reading_levels": READING_LEVELS,
            "read_status_labels": READ_STATUS_LABELS,
            "feed_url": "/feed-original.xml" if view_mode == "original" else "/feed.xml",
        },
    )


@app.post("/api/fetch")
async def api_fetch(limit: int | None = Query(default=None, ge=1, le=1000)):
    try:
        result = await rss_parser.fetch_and_store(limit=limit)
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("Fetch API failed: %s", exc)
        raise HTTPException(status_code=500, detail="抓取 RSS 失败，请查看 logs/app.log")


@app.post("/api/sync")
async def api_sync(limit: int | None = Query(default=None, ge=1, le=1000)):
    try:
        fetch_result = await rss_parser.fetch_and_store(limit=limit)

        from . import rules

        rules_result = rules.apply_rules_to_all()
        translate_result: dict[str, object]
        deepseek_config = settings.deepseek_config()
        if str(deepseek_config.get("api_key") or "").strip():
            default_concurrency = deepseek_client.get_env_int("TITLE_TRANSLATE_CONCURRENCY", 3)
            translate_result = await deepseek_client.translate_pending_titles(
                concurrency=default_concurrency,
                limit=limit,
            )
        else:
            translate_result = {
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "message": "DeepSeek API Key 未配置，未进行标题翻译。",
            }
        feed_result = rss_writer.build_feed()
        original_feed_result = rss_writer.build_original_feed()
        return JSONResponse(
            {
                "fetch": fetch_result,
                "rules": rules_result,
                "translate": translate_result,
                "feed": feed_result,
                "original_feed": original_feed_result,
            }
        )
    except Exception as exc:
        logger.exception("Sync API failed: %s", exc)
        raise HTTPException(status_code=500, detail="一键同步失败，请查看 logs/app.log")


@app.post("/api/translate-titles")
async def api_translate_titles(
    concurrency: int | None = Query(default=None, ge=1, le=20),
    limit: int | None = Query(default=None, ge=1, le=1000),
):
    try:
        default_concurrency = deepseek_client.get_env_int("TITLE_TRANSLATE_CONCURRENCY", 5)
        result = await deepseek_client.translate_pending_titles(
            concurrency=concurrency or default_concurrency,
            limit=limit,
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("Title translation API failed: %s", exc)
        raise HTTPException(status_code=500, detail="批量翻译标题失败，请查看 logs/app.log")


@app.post("/api/articles/{article_id}/summarize")
async def api_summarize(article_id: int, force: bool = Query(default=False)):
    try:
        result = await deepseek_client.summarize_article(article_id, force=force)
        rss_writer.build_feed()
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail="文章不存在")
    except Exception as exc:
        logger.exception("Summarize API failed for article_id=%s: %s", article_id, exc)
        raise HTTPException(status_code=500, detail="生成摘要失败，请查看 logs/app.log")


@app.post("/api/articles/{article_id}/meta")
async def api_article_meta(article_id: int, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    allowed_statuses = {"unread", "opened", "read", "to_read", "filtered"}
    allowed_reading_levels = set(READING_LEVELS)
    allowed_zotero_statuses = {"not_saved", "saved"}
    read_status = payload.get("read_status")
    if read_status is not None and read_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="无效阅读状态")
    reading_level = payload.get("reading_level")
    if reading_level is not None and reading_level not in allowed_reading_levels:
        raise HTTPException(status_code=400, detail="无效可读性等级")
    zotero_status = payload.get("zotero_status")
    if zotero_status is not None and zotero_status not in allowed_zotero_statuses:
        raise HTTPException(status_code=400, detail="无效 Zotero 状态")
    try:
        row = storage.update_article_meta(
            article_id,
            read_status=read_status,
            reading_level=reading_level,
            favorite=payload.get("favorite") if "favorite" in payload else None,
            user_note=payload.get("user_note") if "user_note" in payload else None,
            tags=payload.get("tags") if "tags" in payload else None,
            zotero_status=zotero_status,
        )
        return JSONResponse(
            {
                "article_id": article_id,
                "read_status": row["read_status"],
                "reading_level": row["reading_level"],
                "favorite": bool(row["favorite"]),
                "user_note": row["user_note"],
                "tags": row["tags"],
                "zotero_status": row["zotero_status"],
            }
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="文章不存在")


@app.post("/api/articles/{article_id}/zotero")
async def api_article_zotero(article_id: int):
    try:
        from . import zotero_client

        return JSONResponse(await zotero_client.save_article(article_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="文章不存在")
    except ValueError as exc:
        storage.update_article_meta(article_id, zotero_status="saved")
        return JSONResponse({"article_id": article_id, "zotero_status": "saved", "message": str(exc), "local_only": True})
    except Exception as exc:
        logger.exception("Zotero save failed for article_id=%s: %s", article_id, exc)
        raise HTTPException(status_code=500, detail=f"Zotero 保存失败：{exc}")


@app.post("/api/articles/batch")
async def api_articles_batch(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    ids = [int(value) for value in payload.get("article_ids") or []]
    action = str(payload.get("action") or "").strip()
    if not ids:
        raise HTTPException(status_code=400, detail="未选择文章")
    if action in {"read", "to_read", "unread", "filtered"}:
        count = storage.batch_update_status(ids, action)
        return JSONResponse({"action": action, "count": count})
    if action == "reading_level":
        reading_level = str(payload.get("reading_level") or "").strip()
        if reading_level not in READING_LEVELS:
            raise HTTPException(status_code=400, detail="无效可读性等级")
        count = storage.batch_update_reading_level(ids, reading_level)
        return JSONResponse({"action": action, "reading_level": reading_level, "count": count})
    if action == "delete":
        count = storage.batch_delete_articles(ids)
        rss_writer.build_feed()
        rss_writer.build_original_feed()
        return JSONResponse({"action": action, "count": count})
    raise HTTPException(status_code=400, detail="无效批量操作")


@app.post("/api/articles/{article_id}/delete")
async def api_delete_article(article_id: int):
    if not storage.delete_article(article_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    rss_writer.build_feed()
    rss_writer.build_original_feed()
    return JSONResponse({"article_id": article_id, "deleted": True})


@app.get("/api/articles/{article_id}/open")
async def api_article_open(article_id: int):
    article = storage.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    link = article["link"]
    if not link:
        raise HTTPException(status_code=404, detail="原文链接不存在")
    storage.mark_article_opened(article_id)
    return RedirectResponse(link)


def _ris_escape(value: str | None) -> str:
    return (value or "").replace("\r", " ").replace("\n", " ").strip()


@app.get("/api/articles/{article_id}/ris")
async def api_article_ris(article_id: int):
    article = storage.get_article_detail(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    lines = [
        "TY  - JOUR",
        f"TI  - {_ris_escape(article['original_title'])}",
        f"AB  - {_ris_escape(article['original_description'])}",
        f"UR  - {_ris_escape(article['link'])}",
    ]
    if article["authors"]:
        for author in str(article["authors"]).split(","):
            author = author.strip()
            if author:
                lines.append(f"AU  - {_ris_escape(author)}")
    if article["doi"]:
        lines.append(f"DO  - {_ris_escape(article['doi'])}")
    if article["published_at"]:
        lines.append(f"PY  - {_ris_escape(article['published_at'][:4])}")
    note = article["user_note"]
    if note:
        lines.append(f"N1  - {_ris_escape(note)}")
    lines.append("ER  -")
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="application/x-research-info-systems; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="article-{article_id}.ris"'},
    )


@app.post("/api/build-feed")
async def api_build_feed(mode: str = Query(default="ds")):
    try:
        if mode == "original":
            return JSONResponse(rss_writer.build_original_feed())
        return JSONResponse(rss_writer.build_feed())
    except Exception as exc:
        logger.exception("Build feed API failed: %s", exc)
        raise HTTPException(status_code=500, detail="重新生成 RSS 失败，请查看 logs/app.log")


@app.post("/api/apply-rules")
async def api_apply_rules():
    try:
        from . import rules

        return JSONResponse(rules.apply_rules_to_all())
    except Exception as exc:
        logger.exception("Apply rules API failed: %s", exc)
        raise HTTPException(status_code=500, detail="应用规则失败，请查看 logs/app.log")


@app.post("/api/expand-query")
async def api_expand_query(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="检索需求不能为空")
    try:
        return JSONResponse(await deepseek_client.expand_search_query(query))
    except Exception as exc:
        logger.exception("Expand query API failed: %s", exc)
        return JSONResponse(
            {
                "terms": _fallback_terms(query),
                "reason": "智能拆解失败，已使用本地关键词切分。",
                "error": str(exc),
            }
        )


@app.get("/sources")
async def sources(request: Request):
    return templates.TemplateResponse(
        "sources.html",
        {
            "request": request,
            "sources": storage.list_source_health(),
        },
    )


@app.get("/database")
async def database(request: Request, show_ai: bool = Query(default=False)):
    return templates.TemplateResponse(
        "database.html",
        {
            "request": request,
            "overview": storage.get_database_overview(),
            "app_title": settings.app_title(),
            "show_ai": show_ai,
            "reading_levels": READING_LEVELS,
            "read_status_labels": READ_STATUS_LABELS,
        },
    )


@app.get("/tags")
async def tags(request: Request):
    return templates.TemplateResponse(
        "tags.html",
        {
            "request": request,
            "tags": storage.list_tags(),
            "app_title": settings.app_title(),
            "reading_levels": READING_LEVELS,
            "read_status_labels": READ_STATUS_LABELS,
        },
    )


@app.get("/tags/{tag:path}")
async def tag_detail(request: Request, tag: str):
    clean_tag = tag.strip()
    summary = storage.get_tag_summary(clean_tag)
    if summary is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    articles = storage.list_articles_by_tag(clean_tag)
    return templates.TemplateResponse(
        "tag_detail.html",
        {
            "request": request,
            "tag": clean_tag,
            "tag_url": quote(clean_tag, safe=""),
            "summary": summary,
            "articles": articles,
            "app_title": settings.app_title(),
            "reading_levels": READING_LEVELS,
            "read_status_labels": READ_STATUS_LABELS,
        },
    )


@app.get("/api/tags")
async def api_tags():
    return JSONResponse({"tags": storage.list_tags()})


@app.get("/digest")
async def digest(request: Request, days: int = Query(default=7, ge=1, le=90)):
    articles = storage.recent_digest(days=days, limit=300)
    return templates.TemplateResponse(
        "digest.html",
        {
            "request": request,
            "articles": articles,
            "days": days,
            "app_title": settings.app_title(),
            "reading_levels": READING_LEVELS,
            "read_status_labels": READ_STATUS_LABELS,
        },
    )


@app.get("/api/backup/db")
async def api_backup_db():
    storage.init_db()
    return FileResponse(
        storage.DB_PATH,
        media_type="application/vnd.sqlite3",
        filename="rss_ai.db",
    )


@app.get("/api/export/articles.json")
async def api_export_articles_json():
    return PlainTextResponse(
        storage.export_articles_json(),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rss-finder-articles.json"'},
    )


@app.get("/feed.xml")
async def feed_xml():
    path = rss_writer.ensure_feed_exists()
    return FileResponse(
        path,
        media_type="application/rss+xml; charset=utf-8",
        filename="feed.xml",
    )


@app.get("/feed-original.xml")
async def feed_original_xml():
    path = rss_writer.ensure_original_feed_exists()
    return FileResponse(
        path,
        media_type="application/rss+xml; charset=utf-8",
        filename="feed-original.xml",
    )
