from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from dotenv import load_dotenv

from . import storage


APP_CONFIG_PATH = storage.BASE_DIR / "config" / "app.yml"
ENV_PATH = storage.BASE_DIR / ".env"


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "title": "前沿期刊进展",
        "default_mode": "original",
        "page_limit": 2000,
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "max_retries": 3,
        "title_timeout_seconds": 30,
        "summary_timeout_seconds": 60,
        "title_translate_concurrency": 5,
    },
    "zotero": {
        "api_key_env": "ZOTERO_API_KEY",
        "user_id_env": "ZOTERO_USER_ID",
        "group_id_env": "ZOTERO_GROUP_ID",
        "collection_key_env": "ZOTERO_COLLECTION_KEY",
        "api_key": "",
        "user_id": "",
        "group_id": "",
        "collection_key": "",
    },
    "pubmed": {
        "enabled": True,
        "api_key_env": "NCBI_API_KEY",
        "email_env": "NCBI_EMAIL",
        "api_key": "",
        "email": "",
        "tool": "rss-ai-summary",
        "timeout_seconds": 12,
    },
    "output_rss": {
        "title": "AI 中文摘要",
        "link": "http://localhost:8090/feed.xml",
        "description": "自动翻译标题并保留 RSS 摘要的 Feed",
        "original_title": "原文 RSS",
        "original_description": "不调用 DeepSeek，保留原始标题和 RSS 原始摘要的 Feed",
    },
    "feeds": [],
    "html_sources": [],
    "biorxiv_api": {"enabled": False},
    "rules": {"exclude_rules": [], "tag_rules": []},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    load_dotenv(storage.BASE_DIR / ".env")
    config = _deep_merge(DEFAULT_CONFIG, _load_yaml(APP_CONFIG_PATH))

    deepseek = config.setdefault("deepseek", {})
    api_key_env = str(deepseek.get("api_key_env") or "DEEPSEEK_API_KEY")
    env_api_key = os.getenv(api_key_env, "").strip()
    if env_api_key:
        deepseek["api_key"] = env_api_key
    zotero = config.setdefault("zotero", {})
    for key, default_env in [
        ("api_key", "ZOTERO_API_KEY"),
        ("user_id", "ZOTERO_USER_ID"),
        ("group_id", "ZOTERO_GROUP_ID"),
        ("collection_key", "ZOTERO_COLLECTION_KEY"),
    ]:
        env_name = str(zotero.get(f"{key}_env") or default_env)
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            zotero[key] = env_value
    pubmed = config.setdefault("pubmed", {})
    for key, default_env in [
        ("api_key", "NCBI_API_KEY"),
        ("email", "NCBI_EMAIL"),
    ]:
        env_name = str(pubmed.get(f"{key}_env") or default_env)
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            pubmed[key] = env_value
    return config


def reload_config() -> dict[str, Any]:
    get_config.cache_clear()
    return get_config()


def update_env_values(values: dict[str, str]) -> None:
    ENV_PATH.touch(exist_ok=True)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    next_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            value = remaining.pop(key).replace("\n", "").strip()
            next_lines.append(f"{key}={value}")
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
        else:
            next_lines.append(line)
    for key, value in remaining.items():
        clean_value = value.replace("\n", "").strip()
        next_lines.append(f"{key}={clean_value}")
        if clean_value:
            os.environ[key] = clean_value
        else:
            os.environ.pop(key, None)
    ENV_PATH.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    reload_config()


def section(name: str) -> dict[str, Any]:
    value = get_config().get(name) or {}
    return value if isinstance(value, dict) else {}


def app_title() -> str:
    return str(section("app").get("title") or DEFAULT_CONFIG["app"]["title"])


def page_limit() -> int:
    try:
        return max(1, int(section("app").get("page_limit") or 2000))
    except (TypeError, ValueError):
        return 2000


def _rss_enabled_override() -> set[str] | None:
    raw = storage.get_app_setting("rss_enabled_sources")
    if not raw:
        return None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(values, list):
        return None
    return {str(item).strip() for item in values if str(item).strip()}


def _infer_rss_group(name: str, url: str) -> str:
    lower_name = name.casefold()
    host = urlsplit(url).netloc.casefold()
    if "nature.com" in host or lower_name.startswith("nature"):
        return "Nature Portfolio"
    if "science.org" in host:
        return "Science / AAAS"
    if "sciencedirect.com" in host or "sciencedirect" in lower_name:
        return "ScienceDirect / Cell Press"
    if "academic.oup.com" in host or "oxford" in lower_name:
        return "Oxford Academic"
    if "wiley.com" in host or "wiley" in lower_name:
        return "Wiley"
    if "annualreviews.org" in host:
        return "Annual Reviews"
    if "springer.com" in host or "springer" in lower_name:
        return "Springer Nature"
    if "cshlp.org" in host or "cshl" in lower_name:
        return "CSHL Press"
    if "arxiv.org" in host:
        return "arXiv"
    if "pnas.org" in host:
        return "PNAS"
    return "其他"


def _infer_rss_tags(name: str, explicit_tags: list[str]) -> list[str]:
    tags = list(explicit_tags)
    lower_name = name.casefold()
    tag_rules = [
        ("plant", ["plant", "phytologist", "horticulture", "crop", "food"]),
        ("genetics", ["genetic", "genomics", "genome", "gpb"]),
        ("bioinformatics", ["bioinformatics", "computational", "cs.", "q-bio"]),
        ("methods", ["methods", "biotechnology", "machine intelligence"]),
        ("review", ["reviews", "annual review", "briefings"]),
        ("general", ["nature", "science", "pnas", "communications"]),
    ]
    for tag, needles in tag_rules:
        if any(needle in lower_name for needle in needles) and tag not in tags:
            tags.append(tag)
    return tags


def all_rss_sources() -> list[dict[str, Any]]:
    enabled_override = _rss_enabled_override()
    result: list[dict[str, Any]] = []
    for item in get_config().get("feeds") or []:
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        enabled = item.get("enabled", True)
        if not name or not url:
            continue
        tags = item.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        configured_enabled = enabled is not False
        result.append(
            {
                "name": name,
                "url": url,
                "group": str(item.get("group") or _infer_rss_group(name, url)).strip() or "其他",
                "tags": _infer_rss_tags(name, clean_tags),
                "host": urlsplit(url).netloc,
                "enabled": configured_enabled if enabled_override is None else name in enabled_override,
                "configured_enabled": configured_enabled,
            }
        )
    return result


def rss_source_groups() -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for source in all_rss_sources():
        groups.setdefault(str(source["group"]), []).append(source)
    result = []
    for name, sources in groups.items():
        result.append(
            {
                "name": name,
                "sources": sources,
                "total": len(sources),
                "enabled_count": sum(1 for source in sources if source["enabled"]),
            }
        )
    return result


def feeds() -> list[dict[str, str]]:
    result = []
    for item in all_rss_sources():
        if item["enabled"]:
            result.append({"name": str(item["name"]), "url": str(item["url"])})
    return result


def html_sources() -> list[dict[str, Any]]:
    result = []
    for item in get_config().get("html_sources") or []:
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


def biorxiv_config() -> dict[str, Any]:
    config = dict(section("biorxiv_api"))
    enabled_setting = storage.get_app_setting("biorxiv_enabled")
    if enabled_setting in {"0", "1"}:
        config["enabled"] = enabled_setting == "1"
    if not config.get("enabled"):
        return {}
    return config


def pubmed_config() -> dict[str, Any]:
    config = section("pubmed")
    if config.get("enabled") is False:
        return {}
    return config


def rules_config() -> dict[str, Any]:
    return section("rules")


def deepseek_config() -> dict[str, Any]:
    return section("deepseek")


def zotero_config() -> dict[str, Any]:
    return section("zotero")


def output_rss_config() -> dict[str, Any]:
    return section("output_rss")
