from __future__ import annotations

import asyncio
import email.utils
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import httpx

from . import settings, storage


logger = logging.getLogger(__name__)
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSSAISummary/0.1; +http://localhost:8090)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}
PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_doi(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", value)
    return match.group(0).rstrip(".,;)") if match else ""


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _science_direct_pii(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"/pii/(S[0-9A-Z]+)", value)
    return match.group(1) if match else ""


def _short_source_label(source_name: str) -> str:
    return source_name.replace(" (ScienceDirect Feed)", "").strip()


def _needs_pubmed_backfill(source_name: str, description: str | None) -> bool:
    description = (description or "").strip()
    if "ScienceDirect" not in source_name:
        return False
    if len(description) >= 650:
        return False
    metadata_markers = ["Publication date:", "Source:", "Author(s):"]
    return any(marker in description for marker in metadata_markers)


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return _clean_text(" ".join(element.itertext()))


def _pubmed_abstract_from_xml(xml_text: str, expected_title: str) -> tuple[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return "", ""

    expected_norm = _normalize_title(expected_title)
    fallback: tuple[str, str] | None = None
    for article in root.findall(".//PubmedArticle"):
        pmid = _xml_text(article.find(".//PMID"))
        title = _xml_text(article.find(".//ArticleTitle"))
        title_norm = _normalize_title(title)
        abstract_parts = []
        for item in article.findall(".//Abstract/AbstractText"):
            label = str(item.get("Label") or "").strip()
            text = _xml_text(item)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(abstract_parts).strip()
        if not abstract:
            continue
        if fallback is None:
            fallback = (pmid, abstract)
        if expected_norm and title_norm and (expected_norm == title_norm or expected_norm in title_norm or title_norm in expected_norm):
            return pmid, abstract
    return fallback or ("", "")


def _pubmed_description(existing: str, abstract: str, pmid: str) -> str:
    parts = [existing.strip()] if existing.strip() else []
    label = f"PubMed abstract (PMID: {pmid})" if pmid else "PubMed abstract"
    parts.append(f"{label}:\n{abstract.strip()}")
    return "\n\n".join(parts)


def _entry_authors(entry: Any) -> str:
    authors = entry.get("authors")
    values = []
    if isinstance(authors, list):
        values = [_clean_text(str(item.get("name") or item.get("email") or "")) for item in authors]
    if not values:
        raw = entry.get("author") or entry.get("creator") or entry.get("dc_creator")
        if isinstance(raw, list):
            values = [_clean_text(str(item)) for item in raw]
        elif raw:
            values = [_clean_text(str(raw))]
    return ", ".join([value for value in values if value])


def _entry_doi(entry: Any) -> str:
    values = [
        str(entry.get("prism_doi") or ""),
        str(entry.get("doi") or ""),
        str(entry.get("dc_identifier") or ""),
        str(entry.get("id") or ""),
        str(entry.get("guid") or ""),
        str(entry.get("link") or ""),
        str(entry.get("summary") or ""),
    ]
    return _clean_doi("\n".join(values))


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
    content_values = []
    if content and isinstance(content, list):
        content_values = [str(item.get("value") or "") for item in content if item.get("value")]
    candidates = [
        *(content_values or []),
        str(entry.get("summary") or ""),
        str(entry.get("description") or ""),
        str(entry.get("subtitle") or ""),
    ]
    cleaned = [_clean_text(value) for value in candidates]
    cleaned = [value for value in cleaned if value]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


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


def load_html_sources(path: Path | None = None) -> list[dict[str, Any]]:
    if path is not None:
        import yaml

        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        result = []
        for item in config.get("html_sources", []):
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            parser = str(item.get("parser", "")).strip()
            enabled = item.get("enabled", True)
            try:
                pages = max(1, int(item.get("pages") or 1))
            except (TypeError, ValueError):
                pages = 1
            if name and url and parser and enabled is not False:
                result.append({"name": name, "url": url, "parser": parser, "pages": pages})
        return result
    return settings.html_sources()


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
        "authors": authors,
        "doi": doi,
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


async def _pubmed_search_ids(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    pubmed_config: dict[str, Any],
    term: str,
) -> list[str]:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": "5",
        "term": term,
        "tool": str(pubmed_config.get("tool") or "rss-ai-summary"),
    }
    api_key = str(pubmed_config.get("api_key") or "").strip()
    email_value = str(pubmed_config.get("email") or "").strip()
    if api_key:
        params["api_key"] = api_key
    if email_value:
        params["email"] = email_value
    response = await _get_with_fallback(
        client,
        direct_client,
        f"{PUBMED_EUTILS_BASE}/esearch.fcgi",
        params=params,
    )
    response.raise_for_status()
    data = response.json()
    return [str(value) for value in data.get("esearchresult", {}).get("idlist", []) if value]


async def _pubmed_fetch_abstract(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    pubmed_config: dict[str, Any],
    pmids: list[str],
    expected_title: str,
) -> tuple[str, str]:
    if not pmids:
        return "", ""
    params = {
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(pmids[:5]),
        "tool": str(pubmed_config.get("tool") or "rss-ai-summary"),
    }
    api_key = str(pubmed_config.get("api_key") or "").strip()
    email_value = str(pubmed_config.get("email") or "").strip()
    if api_key:
        params["api_key"] = api_key
    if email_value:
        params["email"] = email_value
    response = await _get_with_fallback(
        client,
        direct_client,
        f"{PUBMED_EUTILS_BASE}/efetch.fcgi",
        params=params,
    )
    response.raise_for_status()
    return _pubmed_abstract_from_xml(response.text, expected_title)


async def _backfill_pubmed_abstract(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    pubmed_config: dict[str, Any],
    article: dict[str, Any],
) -> bool:
    if not pubmed_config:
        return False
    source_name = str(article.get("source_name") or "")
    description = str(article.get("original_description") or "")
    title = str(article.get("original_title") or "").strip()
    if not title or not _needs_pubmed_backfill(source_name, description):
        return False

    doi = str(article.get("doi") or "").strip()
    pii = _science_direct_pii(str(article.get("link") or ""))
    journal = _short_source_label(source_name)
    terms = []
    if doi:
        terms.append(f"{doi}[AID]")
    if pii:
        terms.append(f"{pii}[AID]")
    terms.append(f'"{title}"[Title] AND "{journal}"[Journal]')
    terms.append(f'"{title}"[Title]')

    seen_terms: set[str] = set()
    try:
        for term in terms:
            if term in seen_terms:
                continue
            seen_terms.add(term)
            pmids = await _pubmed_search_ids(client, direct_client, pubmed_config, term)
            pmid, abstract = await _pubmed_fetch_abstract(client, direct_client, pubmed_config, pmids, title)
            if len(abstract) < 120:
                continue
            article["original_description"] = _pubmed_description(description, abstract, pmid)
            return True
    except Exception as exc:
        logger.warning("PubMed backfill failed for %r: %s", title, exc)
    return False


async def backfill_existing_pubmed_abstracts(limit: int = 100) -> dict[str, int]:
    storage.init_db()
    settings.reload_config()
    pubmed_config = settings.pubmed_config()
    if not pubmed_config:
        return {"candidates": 0, "checked": 0, "backfilled": 0, "skipped": 0, "errors": 0}

    candidates = []
    for row in storage.iter_article_details():
        description = str(row["original_description"] or "")
        if "PubMed abstract" in description:
            continue
        if _needs_pubmed_backfill(str(row["source_name"] or ""), description):
            candidates.append(row)
        if len(candidates) >= max(1, limit):
            break

    checked = 0
    backfilled = 0
    skipped = 0
    errors = 0
    timeout_seconds = float(pubmed_config.get("timeout_seconds") or 12)
    timeout = httpx.Timeout(timeout_seconds, connect=min(8.0, timeout_seconds))
    async with (
        httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=timeout, follow_redirects=True) as client,
        httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=timeout, follow_redirects=True, trust_env=False) as direct_client,
    ):
        for row in candidates:
            checked += 1
            article = {key: row[key] for key in row.keys()}
            try:
                if not await _backfill_pubmed_abstract(client, direct_client, pubmed_config, article):
                    skipped += 1
                    continue
                if storage.update_article_description(int(row["article_id"]), str(article["original_description"] or "")):
                    backfilled += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors += 1
                logger.warning("Existing PubMed backfill failed for article_id=%s: %s", row["article_id"], exc)

    logger.info(
        "Existing PubMed backfill complete: candidates=%s checked=%s backfilled=%s skipped=%s errors=%s",
        len(candidates),
        checked,
        backfilled,
        skipped,
        errors,
    )
    return {
        "candidates": len(candidates),
        "checked": checked,
        "backfilled": backfilled,
        "skipped": skipped,
        "errors": errors,
    }


def _iso_date(value: str, fallback: str) -> str:
    value = value.strip()
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    for date_format in ("%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return fallback


def _page_url(url: str, page: int) -> str:
    if page <= 1:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _parse_nature_articles_html(source: dict[str, Any], body: str, fetched_at: str) -> list[dict[str, str]]:
    articles = []
    blocks = re.findall(r"<article\b[^>]*ScholarlyArticle[^>]*>.*?</article>", body, re.S)
    for block in blocks:
        link_match = re.search(
            r'<a href="([^"]+)"[^>]*data-track-label="link"[^>]*>(.*?)</a>',
            block,
            re.S,
        )
        if not link_match:
            continue
        date_match = re.search(r'<time[^>]+datetime="([^"]+)"', block, re.S)
        description_match = re.search(r'data-test="article-description"[^>]*>.*?<p>(.*?)</p>', block, re.S)
        authors = [_clean_text(value) for value in re.findall(r'itemprop="name">(.*?)</span>', block, re.S)]
        authors = [value for value in authors if value]

        link = urljoin(str(source["url"]), html.unescape(link_match.group(1)))
        title = _clean_text(link_match.group(2)) or "(no title)"
        description_parts = []
        if authors:
            description_parts.append("Authors: " + ", ".join(authors))
        description = _clean_text(description_match.group(1)) if description_match else ""
        if description:
            description_parts.append(description)
        published_at = _iso_date(date_match.group(1), fetched_at) if date_match else fetched_at
        articles.append(
            {
                "source_name": str(source["name"]),
                "guid": link,
                "link": link,
                "original_title": title,
                "original_description": "\n\n".join(description_parts),
                "authors": ", ".join(authors),
                "doi": _clean_doi(link),
                "published_at": published_at,
                "fetched_at": fetched_at,
            }
        )
    return articles


def _parse_springer_articles_html(source: dict[str, Any], body: str, fetched_at: str) -> list[dict[str, str]]:
    articles = []
    blocks = re.findall(r'<article class="app-card-open">.*?</article>', body, re.S)
    for block in blocks:
        link_match = re.search(r'<h2 class="app-card-open__heading">.*?<a href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link_match:
            continue
        authors = [_clean_text(value) for value in re.findall(r'<li class="app-author-list__item">(.*?)</li>', block, re.S)]
        authors = [value for value in authors if value]
        meta_items = [_clean_text(value) for value in re.findall(r'<span class="c-meta__item[^"]*">(.*?)</span>', block, re.S)]
        date_text = next((value for value in reversed(meta_items) if re.search(r"\d{4}", value)), "")
        article_type = next((value for value in meta_items if value and value.lower() != "open access"), "")

        link = urljoin(str(source["url"]), html.unescape(link_match.group(1)))
        title = _clean_text(link_match.group(2)) or "(no title)"
        description_parts = []
        if authors:
            description_parts.append("Authors: " + ", ".join(authors))
        if article_type:
            description_parts.append("Article type: " + article_type)
        articles.append(
            {
                "source_name": str(source["name"]),
                "guid": link,
                "link": link,
                "original_title": title,
                "original_description": "\n\n".join(description_parts),
                "authors": ", ".join(authors),
                "doi": _clean_doi(link),
                "published_at": _iso_date(date_text, fetched_at),
                "fetched_at": fetched_at,
            }
        )
    return articles


def _parse_cshl_early_articles_html(source: dict[str, Any], body: str, fetched_at: str) -> list[dict[str, str]]:
    articles = []
    blocks = re.findall(r'<article class="article-section">.*?</article>', body, re.S)
    for block in blocks:
        link_match = re.search(r'<h5 class="title">.*?<a\s+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link_match:
            continue
        authors_block = re.search(r'<div class="article__authorname">(.*?)</div>', block, re.S)
        authors = []
        if authors_block:
            authors = [_clean_text(value) for value in re.findall(r"<li[^>]*>(.*?)</li>", authors_block.group(1), re.S)]
            authors = [value for value in authors if value and not value.startswith("...") and "[+" not in value]
        date_match = re.search(r'<span class="card-citation-value">(.*?)</span>', block, re.S)
        date_text = _clean_text(date_match.group(1)) if date_match else ""

        link = urljoin(str(source["url"]), html.unescape(link_match.group(1)))
        title = _clean_text(link_match.group(2)) or "(no title)"
        description = "Authors: " + ", ".join(authors) if authors else ""
        articles.append(
            {
                "source_name": str(source["name"]),
                "guid": link,
                "link": link,
                "original_title": title,
                "original_description": description,
                "authors": ", ".join(authors),
                "doi": _clean_doi(link),
                "published_at": _iso_date(date_text, fetched_at),
                "fetched_at": fetched_at,
            }
        )
    return articles


def _parse_html_articles(source: dict[str, Any], body: str, fetched_at: str) -> list[dict[str, str]]:
    parser = str(source.get("parser") or "").strip()
    if parser == "nature_articles":
        return _parse_nature_articles_html(source, body, fetched_at)
    if parser == "springer_articles":
        return _parse_springer_articles_html(source, body, fetched_at)
    if parser == "cshl_early_articles":
        return _parse_cshl_early_articles_html(source, body, fetched_at)
    raise ValueError(f"Unsupported HTML source parser: {parser}")


async def _fetch_html_sources(
    client: httpx.AsyncClient,
    direct_client: httpx.AsyncClient,
    html_sources: list[dict[str, Any]],
    limit: int | None,
    seen: int,
    fetched_at: str,
) -> tuple[int, int, int]:
    added = 0
    errors = 0
    total_seen = seen
    for source in html_sources:
        pages = int(source.get("pages") or 1)
        health_name = f"{source['name']} (Article page)"
        for page in range(1, pages + 1):
            if limit is not None and total_seen >= limit:
                break
            url = _page_url(str(source["url"]), page)
            try:
                response = await _get_with_fallback(client, direct_client, url)
                response.raise_for_status()
                articles = _parse_html_articles(source, response.text, fetched_at)
            except (httpx.HTTPError, ValueError) as exc:
                errors += 1
                http_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                storage.update_source_health_failure(
                    health_name,
                    url,
                    "html_articles",
                    str(exc),
                    http_status,
                )
                logger.exception("Failed to fetch HTML source %s: %s", source["name"], exc)
                break

            storage.update_source_health_success(
                health_name,
                url,
                "html_articles",
                len(articles),
                response.status_code,
            )
            if not articles:
                break
            for article in articles:
                if limit is not None and total_seen >= limit:
                    break
                total_seen += 1
                if storage.insert_article(article):
                    added += 1
    return added, total_seen, errors


async def fetch_and_store(limit: int | None = None) -> dict[str, int]:
    storage.init_db()
    settings.reload_config()
    feeds = load_feeds()
    html_sources = load_html_sources()
    biorxiv_config = load_biorxiv_config()
    pubmed_config = settings.pubmed_config()
    added = 0
    seen = 0
    errors = 0
    pubmed_backfilled = 0
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
                authors = _entry_authors(entry)
                doi = _entry_doi(entry)
                description_parts = []
                if authors and "Authors:" not in description:
                    description_parts.append("Authors: " + authors)
                if description:
                    description_parts.append(description)
                article = {
                    "source_name": feed["name"],
                    "guid": guid,
                    "link": link,
                    "original_title": title,
                    "original_description": "\n\n".join(description_parts),
                    "authors": authors,
                    "doi": doi,
                    "published_at": _entry_time_to_iso(entry, fetched_at),
                    "fetched_at": fetched_at,
                }
                seen += 1
                if storage.insert_article(article):
                    added += 1
                    if await _backfill_pubmed_abstract(client, direct_client, pubmed_config, article):
                        storage.insert_article(article)
                        pubmed_backfilled += 1

        if html_sources and (limit is None or seen < limit):
            html_added, seen, html_errors = await _fetch_html_sources(
                client,
                direct_client,
                html_sources,
                limit,
                seen,
                fetched_at,
            )
            added += html_added
            errors += html_errors

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
    logger.info(
        "Fetch complete: added=%s seen=%s total=%s errors=%s pubmed_backfilled=%s",
        added,
        seen,
        total,
        errors,
        pubmed_backfilled,
    )
    return {
        "added": added,
        "seen": seen,
        "total": total,
        "errors": errors,
        "pubmed_backfilled": pubmed_backfilled,
    }
