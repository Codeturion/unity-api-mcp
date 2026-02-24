"""CLI ingestion: parse Unity XML docs + package C# sources → SQLite FTS5 database.

Usage: python -m unity_docs_mcp.ingest [--project PATH]

Options:
  --project PATH   Path to a Unity project for package source parsing.
                   Also settable via UNITY_PROJECT_PATH env var.
"""

import argparse
import os
import sys
import time

from . import db, unity_paths, xml_parser, cs_doc_parser


def main() -> None:
    parser = argparse.ArgumentParser(description="Unity Docs MCP — Ingestion")
    parser.add_argument(
        "--project",
        help="Path to Unity project (for parsing package sources like Input System)",
        default=os.environ.get("UNITY_PROJECT_PATH"),
    )
    args = parser.parse_args()

    # Push project path into env so unity_paths can find it
    if args.project:
        os.environ["UNITY_PROJECT_PATH"] = args.project

    print("Unity Docs MCP — Ingestion")
    print("=" * 50)

    all_records: list[dict] = []

    # ── Phase 1: XML IntelliSense files ──────────────────────────────────
    print("\n[Phase 1] Locating Unity XML files...")
    try:
        xml_paths = unity_paths.find_xml_paths()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    top_count = sum(1 for k in xml_paths if not k.startswith("modules/"))
    mod_count = sum(1 for k in xml_paths if k.startswith("modules/"))
    print(f"  Found {top_count} top-level + {mod_count} module XML files ({len(xml_paths)} total)")

    for name, path in xml_paths.items():
        size_mb = path.stat().st_size / (1024 * 1024)
        if not name.startswith("modules/"):
            print(f"  {name}: {path} ({size_mb:.1f} MB)")

    # Parse all XML files
    for name, path in xml_paths.items():
        t0 = time.perf_counter()
        records = xml_parser.parse_xml(path)
        elapsed = time.perf_counter() - t0
        if records:
            short_name = name.replace("modules/", "")
            print(f"  Parsed {short_name}: {len(records)} members ({elapsed:.2f}s)")
        all_records.extend(records)

    print(f"\n  XML total: {len(all_records)} records")

    # ── Phase 2: Package C# source docs ──────────────────────────────────
    print("\n[Phase 2] Scanning Unity packages for C# doc comments...")
    pkg_dirs = unity_paths.find_package_source_dirs()

    if not pkg_dirs:
        print("  No package source directories found.")
        if not args.project:
            print("  Tip: pass --project <path> or set UNITY_PROJECT_PATH to index packages")
    else:
        pkg_record_count = 0
        for pkg_id, pkg_dir in pkg_dirs.items():
            print(f"\n  Parsing {pkg_id} from {pkg_dir}...")
            t0 = time.perf_counter()
            records = cs_doc_parser.parse_cs_directory(pkg_dir)
            elapsed = time.perf_counter() - t0
            print(f"    {len(records)} members parsed in {elapsed:.2f}s")
            all_records.extend(records)
            pkg_record_count += len(records)
        print(f"\n  Package total: {pkg_record_count} records")

    # ── Phase 3: Write to SQLite ─────────────────────────────────────────
    print(f"\n[Phase 3] Writing {len(all_records)} total records to SQLite...")
    conn = db.get_connection()
    db.clear_all(conn)
    t0 = time.perf_counter()
    count = db.insert_records(conn, all_records)
    elapsed = time.perf_counter() - t0
    print(f"  {count} records inserted in {elapsed:.2f}s")

    # Stats
    stats = db.get_stats(conn)
    print(f"\nDatabase stats:")
    for mtype in ("type", "method", "property", "field", "event"):
        if mtype in stats:
            print(f"  {mtype:>10}: {stats[mtype]:,}")
    print(f"  {'TOTAL':>10}: {stats['total']:,}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
