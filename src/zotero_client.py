from __future__ import annotations

import re
from typing import Any

import httpx

from . import settings, storage


def _split_authors(value: str | None) -> list[dict[str, str]]:
    authors = []
    for raw_name in re.split(r"\s*,\s*", value or ""):
        name = raw_name.strip()
        if not name:
            continue
        parts = name.split()
        if len(parts) >= 2:
            authors.append({"creatorType": "author", "firstName": " ".join(parts[:-1]), "lastName": parts[-1]})
        else:
            authors.append({"creatorType": "author", "name": name})
    return authors[:30]


def _zotero_base(config: dict[str, Any]) -> str:
    group_id = str(config.get("group_id") or "").strip()
    if group_id:
        return f"https://api.zotero.org/groups/{group_id}"
    user_id = str(config.get("user_id") or "").strip()
    if user_id:
        return f"https://api.zotero.org/users/{user_id}"
    raise ValueError("Zotero user_id or group_id is not configured")


async def save_article(article_id: int) -> dict[str, Any]:
    article = storage.get_article_detail(article_id)
    if article is None:
        raise KeyError(f"Article not found: {article_id}")
    config = settings.zotero_config()
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("Zotero API key is not configured")

    item: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": article["original_title"] or "",
        "creators": _split_authors(article["authors"]),
        "abstractNote": article["original_description"] or "",
        "url": article["link"] or "",
        "date": article["published_at"] or "",
        "DOI": article["doi"] or "",
        "publicationTitle": article["source_name"] or "",
        "tags": [{"tag": tag.strip()} for tag in (article["system_tags"] or "").split(",") if tag.strip()],
    }
    collection_key = str(config.get("collection_key") or "").strip()
    if collection_key:
        item["collections"] = [collection_key]
    if article["user_note"]:
        item["notes"] = [{"note": article["user_note"]}]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _zotero_base(config) + "/items",
            headers={"Zotero-API-Key": api_key, "Content-Type": "application/json"},
            json=[item],
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"Zotero API failed: HTTP {response.status_code} {response.text[:300]}")
    payload = response.json()
    successful = payload.get("successful") or {}
    key = ""
    if successful:
        first = next(iter(successful.values()))
        key = str((first or {}).get("key") or "")
    storage.update_article_meta(article_id, zotero_status="saved")
    return {"article_id": article_id, "zotero_status": "saved", "zotero_key": key}
