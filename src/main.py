from __future__ import annotations

import argparse
import asyncio
import sys

from . import deepseek_client, storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local RSS AI translation and summary tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch RSS articles")
    fetch_parser.add_argument("--limit", type=int, default=None)

    translate_parser = subparsers.add_parser("translate-titles", help="Translate pending article titles")
    translate_parser.add_argument("--concurrency", type=int, default=None)
    translate_parser.add_argument("--limit", type=int, default=None)

    summarize_parser = subparsers.add_parser("summarize", help="Generate a three-line summary for one article")
    summarize_parser.add_argument("--article-id", type=int, required=True)
    summarize_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("build-feed", help="Build output RSS feed")
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    storage.setup_logging()
    storage.init_db()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "fetch":
        from . import rss_parser

        result = await rss_parser.fetch_and_store(limit=args.limit)
        print(result)
        return 0

    if args.command == "translate-titles":
        from . import deepseek_client

        result = await deepseek_client.translate_pending_titles(
            concurrency=args.concurrency or deepseek_client.get_env_int("TITLE_TRANSLATE_CONCURRENCY", 5),
            limit=args.limit,
        )
        print(result)
        return 0

    if args.command == "summarize":
        from . import deepseek_client, rss_writer

        try:
            result = await deepseek_client.summarize_article(args.article_id, force=args.force)
            rss_writer.build_feed()
            print(result)
            return 0
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"Failed to summarize article: {exc}", file=sys.stderr)
            return 1

    if args.command == "build-feed":
        from . import rss_writer

        result = rss_writer.build_feed()
        print(result)
        return 0

    parser.print_help()
    return 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
