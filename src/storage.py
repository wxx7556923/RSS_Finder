from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "rss_ai.db"
LOG_PATH = LOGS_DIR / "app.log"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_dedupe_key(source_name: str, guid: str | None, link: str | None, title: str | None) -> str:
    if link:
        return "link:" + link.strip()
    if guid:
        return "guid:" + guid.strip()
    raw = f"{source_name}\n{title or ''}".strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "hash:" + digest


def _update_description_if_better(
    conn: sqlite3.Connection,
    dedupe_key: str,
    link: str | None,
    description: str | None,
    timestamp: str,
) -> None:
    clean_description = (description or "").strip()
    if len(clean_description) < 80:
        return
    row = conn.execute(
        """
        SELECT article_id, COALESCE(original_description, '') AS original_description
        FROM articles
        WHERE dedupe_key = ? OR (? IS NOT NULL AND link = ?)
        LIMIT 1
        """,
        (dedupe_key, link, link),
    ).fetchone()
    if row is None:
        return
    existing = str(row["original_description"] or "")
    if len(clean_description) > len(existing) + 80:
        conn.execute(
            """
            UPDATE articles
            SET original_description = ?, updated_at = ?
            WHERE article_id = ?
            """,
            (clean_description, timestamp, row["article_id"]),
        )
        conn.commit()


def _clean_doi(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", value)
    if not match:
        return ""
    return match.group(0).rstrip(".,;)")


def _authors_from_description(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"(?:^|\n)Authors:\s*([^\n]+)", value)
    return match.group(1).strip() if match else ""


def _backfill_article_metadata(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT article_id, link, guid, original_description, authors, doi
        FROM articles
        WHERE COALESCE(authors, '') = '' OR COALESCE(doi, '') = ''
        """
    ).fetchall()
    for row in rows:
        authors = row["authors"] or _authors_from_description(row["original_description"])
        doi = row["doi"] or _clean_doi("\n".join([str(row["guid"] or ""), str(row["link"] or ""), str(row["original_description"] or "")]))
        if authors or doi:
            conn.execute(
                """
                UPDATE articles
                SET authors = COALESCE(NULLIF(?, ''), authors),
                    doi = COALESCE(NULLIF(?, ''), doi)
                WHERE article_id = ?
                """,
                (authors, doi, row["article_id"]),
            )


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _split_tag_values(*values: str | None) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in (value or "").split(","):
            tag = item.strip()
            key = tag.casefold()
            if tag and key not in seen:
                seen.add(key)
                tags.append(tag)
    return tags


def _row_has_tag(row: sqlite3.Row, tag: str) -> bool:
    needle = tag.strip().casefold()
    return needle in {item.casefold() for item in _split_tag_values(row["tags"], row["system_tags"])}


def init_db() -> None:
    setup_logging()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                article_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT,
                guid TEXT,
                link TEXT UNIQUE,
                dedupe_key TEXT UNIQUE,
                original_title TEXT,
                translated_title TEXT,
                original_description TEXT,
                authors TEXT,
                doi TEXT,
                published_at TEXT,
                fetched_at TEXT,
                summary_line_1 TEXT,
                summary_line_2 TEXT,
                summary_line_3 TEXT,
                title_status TEXT,
                summary_status TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        _ensure_column(conn, "articles", "authors", "TEXT")
        _ensure_column(conn, "articles", "doi", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_title_status ON articles(title_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_summary_status ON articles(summary_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_doi ON articles(doi)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS article_meta (
                article_id INTEGER PRIMARY KEY,
                read_status TEXT DEFAULT 'unread',
                reading_level TEXT DEFAULT 'none',
                favorite INTEGER DEFAULT 0,
                user_note TEXT,
                tags TEXT,
                system_tags TEXT,
                pdf_url TEXT,
                doi TEXT,
                zotero_status TEXT DEFAULT 'not_saved',
                opened_at TEXT,
                noted_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(article_id) REFERENCES articles(article_id)
            )
            """
        )
        _ensure_column(conn, "article_meta", "system_tags", "TEXT")
        _ensure_column(conn, "article_meta", "reading_level", "TEXT DEFAULT 'none'")
        _ensure_column(conn, "article_meta", "zotero_status", "TEXT DEFAULT 'not_saved'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_article_meta_read_status ON article_meta(read_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_article_meta_reading_level ON article_meta(reading_level)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_article_meta_favorite ON article_meta(favorite)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_article_meta_zotero_status ON article_meta(zotero_status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health (
                source_name TEXT PRIMARY KEY,
                url TEXT,
                source_type TEXT,
                enabled INTEGER DEFAULT 1,
                last_success_at TEXT,
                last_failure_at TEXT,
                last_http_status INTEGER,
                last_error TEXT,
                last_item_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_articles (
                dedupe_key TEXT PRIMARY KEY,
                link TEXT,
                guid TEXT,
                source_name TEXT,
                original_title TEXT,
                deleted_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_deleted_articles_link ON deleted_articles(link)")
        _backfill_article_metadata(conn)
        conn.commit()


def insert_article(article: dict[str, Any]) -> bool:
    init_db()
    timestamp = now_iso()
    dedupe_key = make_dedupe_key(
        article.get("source_name", ""),
        article.get("guid"),
        article.get("link"),
        article.get("original_title"),
    )
    link = article.get("link") or None
    with get_connection() as conn:
        deleted = conn.execute(
            """
            SELECT 1 FROM deleted_articles
            WHERE dedupe_key = ? OR (? IS NOT NULL AND link = ?)
            LIMIT 1
            """,
            (dedupe_key, link, link),
        ).fetchone()
        if deleted is not None:
            return False
        try:
            conn.execute(
                """
                INSERT INTO articles (
                    source_name, guid, link, dedupe_key, original_title, translated_title,
                    original_description, authors, doi, published_at, fetched_at, summary_line_1,
                    summary_line_2, summary_line_3, title_status, summary_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.get("source_name", ""),
                    article.get("guid"),
                    link,
                    dedupe_key,
                    article.get("original_title", ""),
                    None,
                    article.get("original_description", ""),
                    article.get("authors", ""),
                    _clean_doi(article.get("doi") or article.get("guid") or article.get("link")),
                    article.get("published_at") or timestamp,
                    article.get("fetched_at") or timestamp,
                    None,
                    None,
                    None,
                    "pending",
                    "none",
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            _update_description_if_better(
                conn,
                dedupe_key,
                link,
                article.get("original_description"),
                timestamp,
            )
            return False


def get_article(article_id: int) -> sqlite3.Row | None:
    init_db()
    with get_connection() as conn:
        return conn.execute("SELECT * FROM articles WHERE article_id = ?", (article_id,)).fetchone()


def list_articles(
    limit: int = 200,
    query: str | None = None,
    smart_terms: list[str] | None = None,
    source: str | None = None,
    read_status: str | None = None,
    reading_level: str | None = None,
    favorite: bool | None = None,
    author: str | None = None,
    doi: str | None = None,
    tag: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    init_db()
    where = []
    params: list[Any] = []
    if query:
        like = f"%{query.strip()}%"
        where.append(
            """
            (
                a.original_title LIKE ?
                OR a.translated_title LIKE ?
                OR a.original_description LIKE ?
                OR a.authors LIKE ?
                OR a.doi LIKE ?
                OR m.user_note LIKE ?
                OR m.tags LIKE ?
                OR m.system_tags LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like, like, like])
    clean_terms = [term.strip() for term in smart_terms or [] if term.strip()]
    if clean_terms:
        term_clauses = []
        for term in clean_terms:
            like = f"%{term}%"
            term_clauses.append(
                """
                (
                    a.original_title LIKE ?
                    OR a.translated_title LIKE ?
                    OR a.original_description LIKE ?
                    OR a.authors LIKE ?
                    OR a.doi LIKE ?
                    OR m.user_note LIKE ?
                    OR m.tags LIKE ?
                    OR m.system_tags LIKE ?
                )
                """
            )
            params.extend([like, like, like, like, like, like, like, like])
        where.append("(" + " OR ".join(term_clauses) + ")")
    if source:
        where.append("a.source_name = ?")
        params.append(source)
    if read_status:
        where.append("COALESCE(m.read_status, 'unread') = ?")
        params.append(read_status)
    if reading_level:
        where.append("COALESCE(m.reading_level, 'none') = ?")
        params.append(reading_level)
    if favorite is not None:
        where.append("COALESCE(m.favorite, 0) = ?")
        params.append(1 if favorite else 0)
    if author:
        where.append("a.authors LIKE ?")
        params.append(f"%{author.strip()}%")
    if doi:
        where.append("a.doi LIKE ?")
        params.append(f"%{doi.strip()}%")
    if tag:
        where.append("(m.tags LIKE ? OR m.system_tags LIKE ?)")
        like = f"%{tag.strip()}%"
        params.extend([like, like])
    if date_from:
        where.append("date(COALESCE(a.published_at, a.fetched_at, a.created_at)) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(COALESCE(a.published_at, a.fetched_at, a.created_at)) <= date(?)")
        params.append(date_to)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT
                a.*,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level,
                COALESCE(m.favorite, 0) AS favorite,
                COALESCE(m.user_note, '') AS user_note,
                COALESCE(m.tags, '') AS tags,
                COALESCE(m.system_tags, '') AS system_tags,
                COALESCE(m.pdf_url, '') AS pdf_url,
                COALESCE(NULLIF(a.doi, ''), m.doi, '') AS doi,
                COALESCE(m.zotero_status, 'not_saved') AS zotero_status,
                m.opened_at,
                m.noted_at
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            {where_sql}
            ORDER BY datetime(COALESCE(a.published_at, a.fetched_at, a.created_at)) DESC, a.article_id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()


def list_source_names() -> list[str]:
    init_db()
    with get_connection() as conn:
        return [
            str(row["source_name"])
            for row in conn.execute(
                "SELECT DISTINCT source_name FROM articles ORDER BY source_name"
            ).fetchall()
        ]


def get_article_detail(article_id: int) -> sqlite3.Row | None:
    init_db()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.*,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level,
                COALESCE(m.favorite, 0) AS favorite,
                COALESCE(m.user_note, '') AS user_note,
                COALESCE(m.tags, '') AS tags,
                COALESCE(m.system_tags, '') AS system_tags,
                COALESCE(m.pdf_url, '') AS pdf_url,
                COALESCE(NULLIF(a.doi, ''), m.doi, '') AS doi,
                COALESCE(m.zotero_status, 'not_saved') AS zotero_status,
                m.opened_at,
                m.noted_at
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            WHERE a.article_id = ?
            """,
            (article_id,),
        ).fetchone()


def iter_article_details() -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.*,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level,
                COALESCE(m.favorite, 0) AS favorite,
                COALESCE(m.user_note, '') AS user_note,
                COALESCE(m.tags, '') AS tags,
                COALESCE(m.system_tags, '') AS system_tags,
                COALESCE(m.pdf_url, '') AS pdf_url,
                COALESCE(NULLIF(a.doi, ''), m.doi, '') AS doi,
                COALESCE(m.zotero_status, 'not_saved') AS zotero_status,
                m.opened_at,
                m.noted_at
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            ORDER BY a.article_id
            """
        ).fetchall()


def delete_article(article_id: int) -> bool:
    init_db()
    with get_connection() as conn:
        article = conn.execute("SELECT * FROM articles WHERE article_id = ?", (article_id,)).fetchone()
        if article is None:
            return False
        conn.execute(
            """
            INSERT INTO deleted_articles (
                dedupe_key, link, guid, source_name, original_title, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                link = excluded.link,
                guid = excluded.guid,
                source_name = excluded.source_name,
                original_title = excluded.original_title,
                deleted_at = excluded.deleted_at
            """,
            (
                article["dedupe_key"],
                article["link"],
                article["guid"],
                article["source_name"],
                article["original_title"],
                now_iso(),
            ),
        )
        conn.execute("DELETE FROM article_meta WHERE article_id = ?", (article_id,))
        cursor = conn.execute("DELETE FROM articles WHERE article_id = ?", (article_id,))
        conn.commit()
        return cursor.rowcount > 0


def batch_update_status(article_ids: list[int], read_status: str) -> int:
    init_db()
    ids = [int(article_id) for article_id in article_ids if int(article_id) > 0]
    if not ids:
        return 0
    timestamp = now_iso()
    with get_connection() as conn:
        for article_id in ids:
            conn.execute(
                """
                INSERT INTO article_meta (article_id, read_status, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    read_status = excluded.read_status,
                    updated_at = excluded.updated_at
                """,
                (article_id, read_status, timestamp, timestamp),
            )
        conn.commit()
    return len(ids)


def batch_update_reading_level(article_ids: list[int], reading_level: str) -> int:
    init_db()
    ids = [int(article_id) for article_id in article_ids if int(article_id) > 0]
    if not ids:
        return 0
    timestamp = now_iso()
    with get_connection() as conn:
        for article_id in ids:
            conn.execute(
                """
                INSERT INTO article_meta (article_id, reading_level, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    reading_level = excluded.reading_level,
                    updated_at = excluded.updated_at
                """,
                (article_id, reading_level, timestamp, timestamp),
            )
        conn.commit()
    return len(ids)


def batch_delete_articles(article_ids: list[int]) -> int:
    count = 0
    for article_id in article_ids:
        if delete_article(int(article_id)):
            count += 1
    return count


def export_articles_json() -> str:
    rows = iter_article_details()
    payload = []
    for row in rows:
        payload.append({key: row[key] for key in row.keys()})
    return json.dumps(payload, ensure_ascii=False, indent=2)


def recent_digest(days: int = 7, limit: int = 200) -> list[sqlite3.Row]:
    init_db()
    start = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).date().isoformat()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                a.*,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level,
                COALESCE(m.favorite, 0) AS favorite,
                COALESCE(m.user_note, '') AS user_note,
                COALESCE(m.tags, '') AS tags,
                COALESCE(m.system_tags, '') AS system_tags,
                COALESCE(NULLIF(a.doi, ''), m.doi, '') AS doi,
                COALESCE(m.zotero_status, 'not_saved') AS zotero_status
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            WHERE date(COALESCE(a.published_at, a.fetched_at, a.created_at)) >= date(?)
              AND COALESCE(m.read_status, 'unread') != 'filtered'
            ORDER BY
                COALESCE(m.favorite, 0) DESC,
                CASE WHEN COALESCE(m.read_status, 'unread') = 'to_read' THEN 0 ELSE 1 END,
                datetime(COALESCE(a.published_at, a.fetched_at, a.created_at)) DESC,
                a.article_id DESC
            LIMIT ?
            """,
            (start, limit),
        ).fetchall()


def get_articles_for_title_translation(limit: int | None = None) -> list[sqlite3.Row]:
    init_db()
    query = """
        SELECT * FROM articles
        WHERE title_status IN ('pending', 'failed')
        ORDER BY datetime(COALESCE(published_at, fetched_at, created_at)) DESC, article_id DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def get_translated_articles(limit: int | None = None) -> list[sqlite3.Row]:
    init_db()
    query = """
        SELECT * FROM articles
        WHERE title_status = 'translated' AND COALESCE(translated_title, '') != ''
        ORDER BY datetime(COALESCE(published_at, fetched_at, created_at)) DESC, article_id DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def get_original_feed_articles(limit: int | None = None) -> list[sqlite3.Row]:
    init_db()
    query = """
        SELECT * FROM articles
        ORDER BY datetime(COALESCE(published_at, fetched_at, created_at)) DESC, article_id DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def update_title_status(article_id: int, status: str, translated_title: str | None = None) -> None:
    init_db()
    with get_connection() as conn:
        if translated_title is None:
            conn.execute(
                "UPDATE articles SET title_status = ?, updated_at = ? WHERE article_id = ?",
                (status, now_iso(), article_id),
            )
        else:
            conn.execute(
                """
                UPDATE articles
                SET title_status = ?, translated_title = ?, updated_at = ?
                WHERE article_id = ?
                """,
                (status, translated_title, now_iso(), article_id),
            )
        conn.commit()


def update_summary(
    article_id: int,
    status: str,
    line_1: str | None = None,
    line_2: str | None = None,
    line_3: str | None = None,
) -> None:
    init_db()
    with get_connection() as conn:
        if line_1 is None and line_2 is None and line_3 is None:
            conn.execute(
                "UPDATE articles SET summary_status = ?, updated_at = ? WHERE article_id = ?",
                (status, now_iso(), article_id),
            )
        else:
            conn.execute(
                """
                UPDATE articles
                SET summary_status = ?, summary_line_1 = ?, summary_line_2 = ?,
                    summary_line_3 = ?, updated_at = ?
                WHERE article_id = ?
                """,
                (status, line_1, line_2, line_3, now_iso(), article_id),
            )
        conn.commit()


def get_stats() -> dict[str, int]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'unread' THEN 1 ELSE 0 END) AS unread,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'opened' THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'read' THEN 1 ELSE 0 END) AS read,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'to_read' THEN 1 ELSE 0 END) AS to_read,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'filtered' THEN 1 ELSE 0 END) AS filtered,
                SUM(CASE WHEN COALESCE(m.reading_level, 'none') = 'skim' THEN 1 ELSE 0 END) AS skim,
                SUM(CASE WHEN COALESCE(m.reading_level, 'none') = 'readable' THEN 1 ELSE 0 END) AS readable,
                SUM(CASE WHEN COALESCE(m.reading_level, 'none') = 'deep_read' THEN 1 ELSE 0 END) AS deep_read,
                SUM(CASE WHEN COALESCE(m.favorite, 0) = 1 THEN 1 ELSE 0 END) AS favorite,
                SUM(CASE WHEN COALESCE(m.zotero_status, 'not_saved') = 'saved' THEN 1 ELSE 0 END) AS zotero_saved,
                SUM(CASE WHEN title_status = 'translated' THEN 1 ELSE 0 END) AS translated,
                SUM(CASE WHEN summary_status = 'summarized' THEN 1 ELSE 0 END) AS summarized,
                SUM(CASE WHEN title_status = 'failed' OR summary_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM articles
            LEFT JOIN article_meta m ON m.article_id = articles.article_id
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "unread": int(row["unread"] or 0),
        "opened": int(row["opened"] or 0),
        "read": int(row["read"] or 0),
        "to_read": int(row["to_read"] or 0),
        "filtered": int(row["filtered"] or 0),
        "skim": int(row["skim"] or 0),
        "readable": int(row["readable"] or 0),
        "deep_read": int(row["deep_read"] or 0),
        "favorite": int(row["favorite"] or 0),
        "zotero_saved": int(row["zotero_saved"] or 0),
        "translated": int(row["translated"] or 0),
        "summarized": int(row["summarized"] or 0),
        "failed": int(row["failed"] or 0),
    }


def update_article_meta(
    article_id: int,
    read_status: str | None = None,
    reading_level: str | None = None,
    favorite: bool | None = None,
    user_note: str | None = None,
    tags: str | None = None,
    pdf_url: str | None = None,
    doi: str | None = None,
    zotero_status: str | None = None,
    system_tags: str | None = None,
) -> sqlite3.Row:
    init_db()
    if get_article(article_id) is None:
        raise KeyError(f"Article not found: {article_id}")

    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO article_meta (article_id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(article_id) DO NOTHING
            """,
            (article_id, timestamp, timestamp),
        )
        fields = []
        params: list[Any] = []
        if read_status is not None:
            fields.append("read_status = ?")
            params.append(read_status)
        if reading_level is not None:
            fields.append("reading_level = ?")
            params.append(reading_level)
        if favorite is not None:
            fields.append("favorite = ?")
            params.append(1 if favorite else 0)
        if user_note is not None:
            fields.append("user_note = ?")
            fields.append("noted_at = ?")
            params.extend([user_note, timestamp])
        if tags is not None:
            fields.append("tags = ?")
            params.append(tags)
        if pdf_url is not None:
            fields.append("pdf_url = ?")
            params.append(pdf_url)
        if doi is not None:
            fields.append("doi = ?")
            params.append(doi)
        if zotero_status is not None:
            fields.append("zotero_status = ?")
            params.append(zotero_status)
        if system_tags is not None:
            fields.append("system_tags = ?")
            params.append(system_tags)
        if fields:
            fields.append("updated_at = ?")
            params.append(timestamp)
            params.append(article_id)
            conn.execute(
                f"UPDATE article_meta SET {', '.join(fields)} WHERE article_id = ?",
                params,
            )
        conn.commit()
        return conn.execute(
            """
            SELECT
                a.*,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level,
                COALESCE(m.favorite, 0) AS favorite,
                COALESCE(m.user_note, '') AS user_note,
                COALESCE(m.tags, '') AS tags,
                COALESCE(m.system_tags, '') AS system_tags,
                COALESCE(m.pdf_url, '') AS pdf_url,
                COALESCE(NULLIF(a.doi, ''), m.doi, '') AS doi,
                COALESCE(m.zotero_status, 'not_saved') AS zotero_status,
                m.opened_at,
                m.noted_at
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            WHERE a.article_id = ?
            """,
            (article_id,),
        ).fetchone()


def list_tags(limit: int | None = None) -> list[dict[str, Any]]:
    rows = iter_article_details()
    tags: dict[str, dict[str, Any]] = {}
    for row in rows:
        user_tags = _split_tag_values(row["tags"])
        system_tags = _split_tag_values(row["system_tags"])
        for tag in _split_tag_values(row["tags"], row["system_tags"]):
            bucket = tags.setdefault(
                tag.casefold(),
                {
                    "tag": tag,
                    "total": 0,
                    "user_count": 0,
                    "system_count": 0,
                    "unread": 0,
                    "opened": 0,
                    "read": 0,
                    "to_read": 0,
                    "filtered": 0,
                    "skim": 0,
                    "readable": 0,
                    "deep_read": 0,
                    "favorite": 0,
                    "noted": 0,
                    "latest_at": "",
                },
            )
            bucket["total"] += 1
            if tag in user_tags:
                bucket["user_count"] += 1
            if tag in system_tags:
                bucket["system_count"] += 1
            read_status = str(row["read_status"] or "unread")
            reading_level = str(row["reading_level"] or "none")
            if read_status in {"unread", "opened", "read", "to_read", "filtered"}:
                bucket[read_status] += 1
            if reading_level in {"skim", "readable", "deep_read"}:
                bucket[reading_level] += 1
            if row["favorite"]:
                bucket["favorite"] += 1
            if str(row["user_note"] or "").strip():
                bucket["noted"] += 1
            latest_at = str(row["published_at"] or row["fetched_at"] or row["created_at"] or "")
            if latest_at > bucket["latest_at"]:
                bucket["latest_at"] = latest_at
    result = sorted(tags.values(), key=lambda item: (-int(item["total"]), str(item["tag"]).casefold()))
    if limit is not None:
        return result[:limit]
    return result


def get_tag_summary(tag: str) -> dict[str, Any] | None:
    target = tag.strip().casefold()
    for item in list_tags():
        if str(item["tag"]).casefold() == target:
            return item
    return None


def list_articles_by_tag(tag: str, limit: int = 500) -> list[sqlite3.Row]:
    rows = list_articles(limit=max(limit * 2, 500), tag=tag)
    exact_rows = [row for row in rows if _row_has_tag(row, tag)]
    return exact_rows[:limit]


def get_database_overview() -> dict[str, Any]:
    init_db()
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    with get_connection() as conn:
        table_counts = {
            "articles": int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] or 0),
            "article_meta": int(conn.execute("SELECT COUNT(*) FROM article_meta").fetchone()[0] or 0),
            "deleted_articles": int(conn.execute("SELECT COUNT(*) FROM deleted_articles").fetchone()[0] or 0),
            "source_health": int(conn.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] or 0),
        }
        read_statuses = conn.execute(
            """
            SELECT COALESCE(m.read_status, 'unread') AS name, COUNT(*) AS count
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            GROUP BY COALESCE(m.read_status, 'unread')
            ORDER BY count DESC, name
            """
        ).fetchall()
        reading_levels = conn.execute(
            """
            SELECT COALESCE(m.reading_level, 'none') AS name, COUNT(*) AS count
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            GROUP BY COALESCE(m.reading_level, 'none')
            ORDER BY count DESC, name
            """
        ).fetchall()
        title_statuses = conn.execute(
            """
            SELECT COALESCE(title_status, 'unknown') AS name, COUNT(*) AS count
            FROM articles
            GROUP BY COALESCE(title_status, 'unknown')
            ORDER BY count DESC, name
            """
        ).fetchall()
        summary_statuses = conn.execute(
            """
            SELECT COALESCE(summary_status, 'unknown') AS name, COUNT(*) AS count
            FROM articles
            GROUP BY COALESCE(summary_status, 'unknown')
            ORDER BY count DESC, name
            """
        ).fetchall()
        sources = conn.execute(
            """
            SELECT
                source_name,
                COUNT(*) AS total,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'unread' THEN 1 ELSE 0 END) AS unread,
                SUM(CASE WHEN COALESCE(m.read_status, 'unread') = 'filtered' THEN 1 ELSE 0 END) AS filtered,
                MAX(COALESCE(a.published_at, a.fetched_at, a.created_at)) AS latest_at
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            GROUP BY source_name
            ORDER BY total DESC, source_name
            LIMIT 25
            """
        ).fetchall()
        recent_articles = conn.execute(
            """
            SELECT
                a.article_id,
                a.source_name,
                a.original_title,
                a.translated_title,
                COALESCE(a.published_at, a.fetched_at, a.created_at) AS latest_at,
                COALESCE(m.read_status, 'unread') AS read_status,
                COALESCE(m.reading_level, 'none') AS reading_level
            FROM articles a
            LEFT JOIN article_meta m ON m.article_id = a.article_id
            ORDER BY datetime(COALESCE(a.fetched_at, a.created_at, a.published_at)) DESC, a.article_id DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "db_path": str(DB_PATH),
        "db_size": db_size,
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "table_counts": table_counts,
        "stats": get_stats(),
        "read_statuses": read_statuses,
        "reading_levels": reading_levels,
        "title_statuses": title_statuses,
        "summary_statuses": summary_statuses,
        "sources": sources,
        "tags": list_tags(limit=30),
        "recent_articles": recent_articles,
    }


def mark_article_opened(article_id: int) -> None:
    init_db()
    if get_article(article_id) is None:
        raise KeyError(f"Article not found: {article_id}")
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO article_meta (article_id, read_status, opened_at, created_at, updated_at)
            VALUES (?, 'read', ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                read_status = 'read',
                opened_at = COALESCE(article_meta.opened_at, excluded.opened_at),
                updated_at = excluded.updated_at
            """,
            (article_id, timestamp, timestamp, timestamp),
        )
        conn.commit()


def update_source_health_success(
    source_name: str,
    url: str,
    source_type: str,
    item_count: int,
    http_status: int | None = None,
) -> None:
    init_db()
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO source_health (
                source_name, url, source_type, enabled, last_success_at,
                last_http_status, last_error, last_item_count, success_count,
                failure_count, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?, NULL, ?, 1, 0, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                url = excluded.url,
                source_type = excluded.source_type,
                enabled = 1,
                last_success_at = excluded.last_success_at,
                last_http_status = excluded.last_http_status,
                last_error = NULL,
                last_item_count = excluded.last_item_count,
                success_count = source_health.success_count + 1,
                updated_at = excluded.updated_at
            """,
            (source_name, url, source_type, timestamp, http_status, item_count, timestamp),
        )
        conn.commit()


def update_source_health_failure(
    source_name: str,
    url: str,
    source_type: str,
    error: str,
    http_status: int | None = None,
) -> None:
    init_db()
    timestamp = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO source_health (
                source_name, url, source_type, enabled, last_failure_at,
                last_http_status, last_error, last_item_count, success_count,
                failure_count, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, 0, 0, 1, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                url = excluded.url,
                source_type = excluded.source_type,
                enabled = 1,
                last_failure_at = excluded.last_failure_at,
                last_http_status = excluded.last_http_status,
                last_error = excluded.last_error,
                last_item_count = 0,
                failure_count = source_health.failure_count + 1,
                updated_at = excluded.updated_at
            """,
            (source_name, url, source_type, timestamp, http_status, error[:500], timestamp),
        )
        conn.commit()


def list_source_health() -> list[sqlite3.Row]:
    init_db()
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM source_health
            ORDER BY
                CASE
                    WHEN last_failure_at IS NOT NULL
                         AND (last_success_at IS NULL OR datetime(last_failure_at) > datetime(last_success_at))
                    THEN 0
                    ELSE 1
                END,
                source_name
            """
        ).fetchall()
