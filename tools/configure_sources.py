from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "app.yml"


def _parse_numbers(value: str, max_value: int) -> set[int]:
    result: set[int] = set()
    for part in re.split(r"[\s,，;；]+", value.strip()):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if start_text.isdigit() and end_text.isdigit():
                start = max(1, int(start_text))
                end = min(max_value, int(end_text))
                result.update(range(start, end + 1))
            continue
        if part.isdigit():
            number = int(part)
            if 1 <= number <= max_value:
                result.add(number)
    return result


def _yes_no(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"config file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _save_config(config: dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False, width=120)


def main() -> None:
    config = _load_config()
    feeds = list(config.get("feeds") or [])
    print()
    print("订阅源选择")
    print("默认全部启用。输入不需要的编号即可关闭；直接回车保留全部。")
    print("示例：关闭 arXiv 和部分综合期刊，可以输入 2, 5, 28-31")
    print()
    for index, feed in enumerate(feeds, start=1):
        name = str(feed.get("name") or "").strip()
        enabled = feed.get("enabled", True) is not False
        marker = "ON " if enabled else "OFF"
        print(f"{index:2d}. [{marker}] {name}")

    disabled = _parse_numbers(input("\n关闭哪些订阅源编号？").strip(), len(feeds))
    for index, feed in enumerate(feeds, start=1):
        if index in disabled:
            feed["enabled"] = False
        elif "enabled" in feed and feed.get("enabled") is False:
            feed["enabled"] = True

    biorxiv = config.get("biorxiv_api") or {}
    if biorxiv:
        biorxiv["enabled"] = _yes_no("是否启用 bioRxiv 分类抓取？", bool(biorxiv.get("enabled", False)))
        config["biorxiv_api"] = biorxiv

    config["feeds"] = feeds
    _save_config(config)
    print()
    print("订阅源配置已保存。以后需要修改，可以重新运行 windows\\configure-sources.bat。")


if __name__ == "__main__":
    main()
