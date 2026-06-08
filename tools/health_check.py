from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def main() -> int:
    try:
        from src import settings, storage
    except Exception as exc:
        fail(f"Cannot import app modules: {exc}")
        fail("Run: python -m pip install -r requirements.txt")
        return 1

    config_path = ROOT / "config" / "app.yml"
    if config_path.exists():
        ok("config/app.yml exists")
    else:
        fail("config/app.yml is missing")
        return 1

    env_path = ROOT / ".env"
    if env_path.exists():
        ok(".env exists")
    else:
        warn(".env is missing. Copy .env.example to .env before using AI features.")

    deepseek = settings.deepseek_config()
    key_env = str(deepseek.get("api_key_env") or "DEEPSEEK_API_KEY")
    if os.getenv(key_env) or str(deepseek.get("api_key") or "").strip():
        ok(f"{key_env} is configured")
    else:
        warn(f"{key_env} is not configured. Fetching RSS works, AI translation/summaries will fail.")

    zotero = settings.zotero_config()
    zotero_key_env = str(zotero.get("api_key_env") or "ZOTERO_API_KEY")
    if os.getenv(zotero_key_env) or str(zotero.get("api_key") or "").strip():
        ok(f"{zotero_key_env} is configured")
    else:
        warn(f"{zotero_key_env} is not configured. Zotero saving will use local status only.")

    feeds = settings.feeds()
    if feeds:
        ok(f"{len(feeds)} RSS feed(s) configured")
    else:
        warn("No RSS feeds configured. Add feeds in config/app.yml or use tools/add_feed.py.")

    try:
        storage.ensure_dirs()
        test_db = storage.DATA_DIR / ".healthcheck.sqlite"
        with sqlite3.connect(test_db) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS healthcheck (id INTEGER PRIMARY KEY)")
            conn.commit()
        test_db.unlink(missing_ok=True)
        ok("data/ is writable")
    except Exception as exc:
        fail(f"data/ is not writable: {exc}")
        return 1

    ok("health check complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
