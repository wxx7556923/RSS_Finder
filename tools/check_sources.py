from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import feedparser
import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "app.yml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PaperRadarSourceCheck/1.0)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}
RSS_NS = "{http://purl.org/rss/1.0/}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _clean_label(value: str) -> str:
    value = re.sub(r"\([^)]*\)", " ", value)
    value = value.replace(" - Advance Articles", " ")
    value = value.replace(" - GR-in-Advance", " ")
    value = value.replace(" Current", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalize(value: str) -> str:
    value = value.lower()
    value = value.replace("sciencedirect publication:", " ")
    value = value.replace("rss feed", " ")
    value = _clean_label(value)
    return re.sub(r"[^a-z0-9]+", "", value)


def _title_and_count(body: bytes) -> tuple[str, int]:
    parsed = feedparser.parse(body)
    if parsed.feed:
        title = str(parsed.feed.get("title") or "").strip()
        return title, len(parsed.entries)

    root = ET.fromstring(body)
    title = ""
    count = 0

    channel = root.find("channel")
    if channel is not None:
        title = (channel.findtext("title") or "").strip()
        count = len(channel.findall("item"))

    if not title:
        channel = root.find(f"{RSS_NS}channel")
        if channel is not None:
            title = (channel.findtext(f"{RSS_NS}title") or "").strip()
            count = len(root.findall(f"{RSS_NS}item"))

    if not title:
        title = (root.findtext(f"{ATOM_NS}title") or root.findtext("title") or "").strip()
        count = len(root.findall(f"{ATOM_NS}entry")) or len(root.findall("entry"))

    return title, count


def _load_feeds(config_path: Path) -> list[dict[str, Any]]:
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    feeds = []
    for item in config.get("feeds", []):
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        expected_title = str(item.get("expected_title") or "").strip()
        enabled = item.get("enabled", True)
        if name and url and enabled is not False:
            feeds.append({"name": name, "url": url, "expected_title": expected_title})
    return feeds


def _fetch(url: str, timeout: float) -> tuple[int | None, bytes]:
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.status_code, response.content[:600_000]
    except httpx.HTTPError:
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            return status, response.read(600_000)


def check_sources(config_path: Path, contains: str, timeout: float) -> int:
    pattern = contains.lower().strip()
    failures = 0
    warnings = 0
    feeds = _load_feeds(config_path)

    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        expected_title = str(feed.get("expected_title") or name)
        if pattern and pattern not in name.lower() and pattern not in url.lower():
            continue

        try:
            status, body = _fetch(url, timeout)
            title, count = _title_and_count(body)
        except (httpx.HTTPError, urllib.error.URLError, TimeoutError, ET.ParseError, ValueError) as exc:
            failures += 1
            print(f"FAIL\t{name}\t{url}\t{type(exc).__name__}: {exc}")
            continue

        expected = _normalize(expected_title)
        actual = _normalize(title)
        is_warning = bool(expected and actual and expected not in actual and actual not in expected)
        if is_warning:
            warnings += 1
        label = "WARN" if is_warning else "OK"
        print(f"{label}\t{status}\t{count}\t{name}\t=>\t{title or '(no title)'}")

    if failures:
        print(f"\n{failures} source(s) failed.", file=sys.stderr)
    if warnings:
        print(f"\n{warnings} source(s) may be mismatched.", file=sys.stderr)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Check configured RSS sources against their live feed titles.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--contains", default="", help="Only check sources whose name or URL contains this text.")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    raise SystemExit(check_sources(args.config, args.contains, args.timeout))


if __name__ == "__main__":
    main()
