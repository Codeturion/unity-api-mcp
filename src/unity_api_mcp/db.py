"""SQLite + FTS5 database layer for Unity API documentation."""

import json
import sqlite3
from pathlib import Path

# DB lives inside the package (ships pre-built, works with pip install)
_DB_DIR = Path(__file__).resolve().parent / "data"
_DB_PATH = _DB_DIR / "unity_docs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_records (
    fqn TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT '',
    class_name TEXT NOT NULL DEFAULT '',
    member_name TEXT NOT NULL DEFAULT '',
    member_type TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '[]',
    returns_text TEXT NOT NULL DEFAULT '',
    deprecated INTEGER NOT NULL DEFAULT 0,
    deprecation_hint TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS api_fts USING fts5(
    fqn,
    class_name,
    member_name,
    summary,
    content='api_records',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS api_records_ai AFTER INSERT ON api_records BEGIN
    INSERT INTO api_fts(rowid, fqn, class_name, member_name, summary)
    VALUES (new.rowid, new.fqn, new.class_name, new.member_name, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS api_records_ad AFTER DELETE ON api_records BEGIN
    INSERT INTO api_fts(api_fts, rowid, fqn, class_name, member_name, summary)
    VALUES ('delete', old.rowid, old.fqn, old.class_name, old.member_name, old.summary);
END;
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a connection to the docs database.

    Args:
        db_path: Path to the SQLite database file. If None, uses the
                 legacy bundled path (src/unity_api_mcp/data/unity_docs.db).
    """
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and FTS index if they don't exist."""
    conn.executescript(_SCHEMA)


def clear_all(conn: sqlite3.Connection) -> None:
    """Drop and recreate all tables."""
    conn.executescript("""
        DROP TABLE IF EXISTS api_fts;
        DROP TABLE IF EXISTS api_records;
    """)
    init_db(conn)


def insert_records(conn: sqlite3.Connection, records: list[dict]) -> int:
    """Bulk-insert parsed records. Returns count inserted."""
    sql = """
        INSERT OR REPLACE INTO api_records
        (fqn, namespace, class_name, member_name, member_type,
         summary, params_json, returns_text, deprecated, deprecation_hint)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    rows = [
        (
            r["fqn"],
            r["namespace"],
            r["class_name"],
            r["member_name"],
            r["member_type"],
            r["summary"],
            json.dumps(r["params_json"]),
            r["returns_text"],
            int(r["deprecated"]),
            r["deprecation_hint"],
        )
        for r in records
    ]
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def search(conn: sqlite3.Connection, query: str, n: int = 10,
           member_type: str | None = None) -> list[dict]:
    """Full-text search with BM25 ranking + core namespace boosting.

    Ranking combines:
    - BM25 with column weights: member_name (10x) > class_name (5x) > fqn/summary (1x)
    - Namespace depth penalty: deeper FQNs (more dots) rank lower, favoring core APIs
      like UnityEngine.Object over UnityEngine.ResourceManagement.ResourceProviders
    """
    clean = _escape_fts(query)
    if not clean.strip():
        return []

    # BM25 column order: fqn, class_name, member_name, summary
    # Adjustments (BM25 is negative; more negative = better):
    #   - Namespace depth: +0.5 per dot in namespace → pushes niche APIs down
    #   - Core bonus: -2 for root UnityEngine/UnityEditor, -1 for their sub-namespaces
    #   - Type bonus: -1 for class/struct/enum defs (prefer types over same-named members)
    ranking = """bm25(api_fts, 1.0, 5.0, 10.0, 0.5)
                + (LENGTH(r.namespace) - LENGTH(REPLACE(r.namespace, '.', ''))) * 0.5
                + CASE
                    WHEN r.namespace IN ('UnityEngine', 'UnityEditor') THEN -2.0
                    WHEN r.namespace LIKE 'UnityEngine.%' OR r.namespace LIKE 'UnityEditor.%' THEN -1.0
                    ELSE 0.0
                  END
                + CASE WHEN r.member_type = 'type' THEN -1.0 ELSE 0.0 END"""

    if member_type:
        sql = f"""
            SELECT r.*, {ranking} AS rank
            FROM api_fts f
            JOIN api_records r ON r.rowid = f.rowid
            WHERE api_fts MATCH ? AND r.member_type = ?
            ORDER BY rank
            LIMIT ?
        """
        rows = conn.execute(sql, (clean, member_type, n)).fetchall()
    else:
        sql = f"""
            SELECT r.*, {ranking} AS rank
            FROM api_fts f
            JOIN api_records r ON r.rowid = f.rowid
            WHERE api_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        rows = conn.execute(sql, (clean, n)).fetchall()

    return [dict(row) for row in rows]


def get_by_fqn(conn: sqlite3.Connection, fqn: str) -> dict | None:
    """Exact FQN lookup."""
    row = conn.execute(
        "SELECT * FROM api_records WHERE fqn = ?", (fqn,)
    ).fetchone()
    return dict(row) if row else None


def get_class_members(conn: sqlite3.Connection, class_name: str) -> list[dict]:
    """Get all members of a class by class name."""
    rows = conn.execute(
        "SELECT * FROM api_records WHERE class_name = ? ORDER BY member_type, member_name",
        (class_name,),
    ).fetchall()
    return [dict(row) for row in rows]


def resolve_namespace(conn: sqlite3.Connection, name: str) -> list[dict]:
    """Find namespace for a class or member name. Returns matching records."""
    # Try exact class name first
    rows = conn.execute(
        "SELECT DISTINCT namespace, class_name, member_type, fqn FROM api_records "
        "WHERE class_name = ? AND member_type = 'type' "
        "ORDER BY namespace",
        (name,),
    ).fetchall()
    if rows:
        return [dict(row) for row in rows]

    # Try member name
    rows = conn.execute(
        "SELECT DISTINCT namespace, class_name, member_name, member_type, fqn FROM api_records "
        "WHERE member_name = ? "
        "ORDER BY namespace, class_name",
        (name,),
    ).fetchall()
    return [dict(row) for row in rows]


def search_deprecated(conn: sqlite3.Connection, name: str, n: int = 10) -> list[dict]:
    """Find deprecated members matching a name fragment."""
    # Try exact class or member name first
    rows = conn.execute(
        "SELECT * FROM api_records "
        "WHERE deprecated = 1 AND (class_name = ? OR member_name = ? OR fqn = ?) "
        "ORDER BY fqn LIMIT ?",
        (name, name, name, n),
    ).fetchall()
    if rows:
        return [dict(row) for row in rows]

    # Fallback to FTS with deprecated filter
    clean = _escape_fts(name)
    if not clean.strip():
        return []
    rows = conn.execute(
        "SELECT r.*, bm25(api_fts) AS rank "
        "FROM api_fts f "
        "JOIN api_records r ON r.rowid = f.rowid "
        "WHERE api_fts MATCH ? AND r.deprecated = 1 "
        "ORDER BY rank LIMIT ?",
        (clean, n),
    ).fetchall()
    return [dict(row) for row in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return record counts by type."""
    rows = conn.execute(
        "SELECT member_type, COUNT(*) as cnt FROM api_records GROUP BY member_type"
    ).fetchall()
    stats = {row["member_type"]: row["cnt"] for row in rows}
    stats["total"] = sum(stats.values())
    return stats


def _escape_fts(query: str) -> str:
    """Escape special FTS5 characters and convert dots to spaces for searching."""
    # Replace dots with spaces so "Physics.Raycast" searches for both terms
    q = query.replace(".", " ")
    # Remove FTS operators that could cause syntax errors
    q = q.replace('"', "")
    q = q.replace("*", "")
    q = q.replace("-", " ")
    q = q.replace("(", " ")
    q = q.replace(")", " ")
    # Convert to prefix search for each term (helps with partial matches)
    terms = q.split()
    if terms:
        return " ".join(f'"{t}"' for t in terms if t)
    return q
