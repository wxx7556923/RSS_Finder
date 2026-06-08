from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from . import storage


APP_CONFIG_PATH = storage.BASE_DIR / "config" / "app.yml"


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
    "output_rss": {
        "title": "AI 中文摘要",
        "link": "http://localhost:8090/feed.xml",
        "description": "自动翻译标题并按需生成摘要后的 RSS Feed",
        "original_title": "原文 RSS",
        "original_description": "不调用 DeepSeek，保留原始标题和 RSS 原始摘要的 Feed",
    },
    "feeds": [],
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
    return config


def reload_config() -> dict[str, Any]:
    get_config.cache_clear()
    return get_config()


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


def feeds() -> list[dict[str, str]]:
    result = []
    for item in get_config().get("feeds") or []:
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        enabled = item.get("enabled", True)
        if name and url and enabled is not False:
            result.append({"name": name, "url": url})
    return result


def biorxiv_config() -> dict[str, Any]:
    config = section("biorxiv_api")
    if not config.get("enabled"):
        return {}
    return config


def rules_config() -> dict[str, Any]:
    return section("rules")


def deepseek_config() -> dict[str, Any]:
    return section("deepseek")


def output_rss_config() -> dict[str, Any]:
    return section("output_rss")
