from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "app.yml"


def valid_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("URL must start with http:// or https://")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Add one RSS feed to config/app.yml")
    parser.add_argument("--name", required=True, help="Feed display name, for example Nature")
    parser.add_argument("--url", required=True, type=valid_url, help="RSS/Atom feed URL")
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        print("config/app.yml is missing", file=sys.stderr)
        return 1

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    feeds = config.setdefault("feeds", [])
    for item in feeds:
        if str(item.get("url", "")).strip() == args.url:
            print(f"Feed already exists: {args.url}")
            return 0

    feeds.append({"name": args.name.strip(), "url": args.url.strip()})
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)

    print(f"Added feed: {args.name} -> {args.url}")
    print("Restart the web app or reload config by restarting uvicorn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
