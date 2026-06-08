from __future__ import annotations

from typing import Any

from . import settings, storage


def _load_rules() -> dict[str, Any]:
    data = settings.rules_config()
    return {
        "exclude_rules": data.get("exclude_rules") or [],
        "tag_rules": data.get("tag_rules") or [],
    }


def _text_for_article(article: Any) -> str:
    return "\n".join(
        [
            str(article["source_name"] or ""),
            str(article["original_title"] or ""),
            str(article["original_description"] or ""),
        ]
    ).lower()


def _split_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _matches_source(article: Any, source_contains: str | None) -> bool:
    needle = (source_contains or "").strip().lower()
    if not needle:
        return True
    return needle in str(article["source_name"] or "").lower()


def _has_keyword(text: str, keywords: list[Any]) -> bool:
    return any(str(keyword).strip().lower() in text for keyword in keywords if str(keyword).strip())


def classify_article(article: Any, rules: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    rules = rules or _load_rules()
    text = _text_for_article(article)
    filtered = False
    for rule in rules.get("exclude_rules", []):
        if _matches_source(article, rule.get("source_contains")) and _has_keyword(text, rule.get("keywords") or []):
            filtered = True
            break

    tags = []
    for rule in rules.get("tag_rules", []):
        tag = str(rule.get("tag") or "").strip()
        if tag and _has_keyword(text, rule.get("keywords") or []):
            tags.append(tag)
    return filtered, tags


def apply_rules_to_all() -> dict[str, int]:
    storage.init_db()
    rules = _load_rules()
    tagged = 0
    filtered = 0
    unchanged = 0

    for article in storage.iter_article_details():
        should_filter, rule_tags = classify_article(article, rules)
        existing_tags = _split_tags(article["system_tags"])
        merged_tags = sorted(set(existing_tags + rule_tags))
        read_status = article["read_status"]
        next_status = "filtered" if should_filter and read_status == "unread" else None
        next_tags = ", ".join(merged_tags)

        changed = False
        if next_status is not None:
            changed = True
            filtered += 1
        if next_tags != (article["system_tags"] or ""):
            changed = True
            if rule_tags:
                tagged += 1
        if changed:
            storage.update_article_meta(
                int(article["article_id"]),
                read_status=next_status,
                system_tags=next_tags,
            )
        else:
            unchanged += 1

    return {"tagged": tagged, "filtered": filtered, "unchanged": unchanged}
