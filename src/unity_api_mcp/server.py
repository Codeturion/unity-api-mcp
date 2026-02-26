"""MCP server providing Unity API documentation from XML IntelliSense files."""

import json
import sys

from mcp.server.fastmcp import FastMCP

from . import db
from .version import detect_version, ensure_db

_unity_version = detect_version()
print(f"unity-api-mcp: serving Unity {_unity_version} API docs", file=sys.stderr)

mcp = FastMCP(
    "unity-api",
    instructions=(
        f"Unity {_unity_version} API documentation server. Use these tools to look up "
        "accurate Unity API signatures, namespaces, and member details instead of guessing."
    ),
)

_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        db_path = ensure_db(_unity_version)
        _conn = db.get_connection(db_path)
    return _conn


def _format_record(r: dict) -> str:
    """Format a single API record into readable text."""
    lines = []

    # Header: type + FQN
    type_label = r.get("member_type", "").upper()
    fqn = r.get("fqn", "")
    lines.append(f"[{type_label}] {fqn}")

    # Namespace
    ns = r.get("namespace", "")
    if ns:
        lines.append(f"  Namespace: {ns}")
        lines.append(f"  Using: using {ns};")

    # Class
    cls = r.get("class_name", "")
    if cls and r.get("member_type") != "type":
        lines.append(f"  Class: {cls}")

    # Summary
    summary = r.get("summary", "")
    if summary:
        lines.append(f"  Summary: {summary}")

    # Parameters
    params_raw = r.get("params_json", "[]")
    if isinstance(params_raw, str):
        params = json.loads(params_raw)
    else:
        params = params_raw
    if params:
        lines.append("  Parameters:")
        for p in params:
            lines.append(f"    - {p['name']}: {p['description']}")

    # Returns
    returns = r.get("returns_text", "")
    if returns:
        lines.append(f"  Returns: {returns}")

    # Deprecation
    if r.get("deprecated"):
        hint = r.get("deprecation_hint", "")
        dep_msg = "DEPRECATED"
        if hint:
            dep_msg += f" — Use {hint} instead"
        lines.append(f"  *** {dep_msg} ***")

    return "\n".join(lines)


@mcp.tool()
def search_unity_api(
    query: str,
    n_results: int = 5,
    member_type: str | None = None,
) -> str:
    """Search Unity API documentation by keyword.

    Use this to find Unity classes, methods, properties, and fields.
    Returns ranked results with summaries.

    Args:
        query: Search terms (e.g. "Physics Raycast", "SceneManager load", "Transform position")
        n_results: Max results to return (default 5, max 20)
        member_type: Optional filter — "type", "method", "property", "field", or "event"
    """
    n_results = min(max(n_results, 1), 20)
    conn = _get_conn()
    results = db.search(conn, query, n=n_results, member_type=member_type)

    if not results:
        return f"No results found for '{query}'. Try broader search terms."

    parts = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, r in enumerate(results, 1):
        parts.append(f"--- Result {i} ---")
        parts.append(_format_record(r))
        parts.append("")

    return "\n".join(parts)


@mcp.tool()
def get_method_signature(fqn: str) -> str:
    """Look up the exact signature of a Unity API member by fully-qualified name.

    Use this when you know the specific API (e.g. from autocomplete or docs reference)
    and need its exact parameters, return type, and deprecation status.

    Args:
        fqn: Fully-qualified name, e.g. "UnityEngine.Physics.Raycast" or
             "UnityEngine.SceneManagement.SceneManager.LoadScene"
             Method overloads include params: "UnityEngine.Physics.Raycast(UnityEngine.Ray)"
    """
    conn = _get_conn()

    # 1. Try exact match
    record = db.get_by_fqn(conn, fqn)
    if record:
        return _format_record(record)

    # 2. Try prefix match (all overloads)
    rows = conn.execute(
        "SELECT * FROM api_records WHERE fqn LIKE ? ORDER BY fqn",
        (fqn + "%",),
    ).fetchall()
    if rows:
        parts = [f"Found {len(rows)} overload(s) for '{fqn}':\n"]
        for r in rows:
            parts.append(_format_record(dict(r)))
            parts.append("")
        return "\n".join(parts)

    # 3. Fallback to FTS search
    results = db.search(conn, fqn, n=5)
    if results:
        parts = [f"No exact match for '{fqn}'. Did you mean:\n"]
        for r in results:
            parts.append(_format_record(r))
            parts.append("")
        return "\n".join(parts)

    return f"No results found for '{fqn}'. Check the fully-qualified name."


@mcp.tool()
def get_namespace(name: str) -> str:
    """Find the correct namespace and using directive for a Unity class or member.

    Use this when you need to know which namespace to import for a Unity type.

    Args:
        name: Class or member name, e.g. "SceneManager", "NavMeshAgent", "Rigidbody"
    """
    conn = _get_conn()
    matches = db.resolve_namespace(conn, name)

    if not matches:
        # Try FTS as fallback
        results = db.search(conn, name, n=5, member_type="type")
        if results:
            parts = [f"No exact match for '{name}'. Similar types:\n"]
            for r in results:
                ns = r.get("namespace", "")
                cls = r.get("class_name", "")
                parts.append(f"  {cls} → using {ns};  (FQN: {r['fqn']})")
            return "\n".join(parts)
        return f"No namespace found for '{name}'."

    if len(matches) == 1:
        m = matches[0]
        ns = m["namespace"]
        cls = m.get("class_name", name)
        return (
            f"Class: {cls}\n"
            f"Namespace: {ns}\n"
            f"Using: using {ns};\n"
            f"FQN: {m['fqn']}"
        )

    # Multiple matches — list all
    parts = [f"Multiple matches for '{name}':\n"]
    for m in matches:
        ns = m["namespace"]
        cls = m.get("class_name", name)
        fqn = m.get("fqn", "")
        mtype = m.get("member_type", "")
        parts.append(f"  [{mtype}] {cls} → using {ns};  (FQN: {fqn})")
    return "\n".join(parts)


@mcp.tool()
def get_class_reference(class_name: str) -> str:
    """Get a complete reference card for a Unity class — all public methods, properties, fields, and events.

    Use this when you want to see everything available on a class at a glance.

    Args:
        class_name: Class name with or without namespace. Examples: "Rigidbody", "Tilemap", "InputAction", "SceneManager"
    """
    conn = _get_conn()

    # Strip namespace if provided (e.g. "UnityEngine.Physics" → "Physics")
    short_name = class_name.rsplit(".", 1)[-1]

    members = db.get_class_members(conn, short_name)

    if not members:
        # Try FTS fallback
        results = db.search(conn, class_name, n=5, member_type="type")
        if results:
            parts = [f"No class '{class_name}' found. Did you mean:\n"]
            for r in results:
                parts.append(f"  {r['fqn']} — {r.get('summary', '')[:80]}")
            return "\n".join(parts)
        return f"No class '{class_name}' found. Check the class name."

    # Find the type record for header info
    type_record = next((m for m in members if m["member_type"] == "type"), None)
    ns = type_record["namespace"] if type_record else members[0].get("namespace", "")

    parts = [f"Class: {short_name}"]
    if ns:
        parts.append(f"Namespace: {ns}")
        parts.append(f"Using: using {ns};")
    if type_record:
        summary = type_record.get("summary", "")
        if summary:
            parts.append(f"Summary: {summary}")
        if type_record.get("deprecated"):
            hint = type_record.get("deprecation_hint", "")
            parts.append(f"*** DEPRECATED{' — Use ' + hint + ' instead' if hint else ''} ***")
    parts.append("")

    # Group by member type
    groups: dict[str, list[dict]] = {}
    for m in members:
        if m["member_type"] == "type":
            continue
        groups.setdefault(m["member_type"], []).append(m)

    for mtype in ("method", "property", "field", "event"):
        group = groups.get(mtype, [])
        if not group:
            continue
        parts.append(f"── {mtype.upper()}S ({len(group)}) ──")
        for m in group:
            dep = " [DEPRECATED]" if m.get("deprecated") else ""
            summary = m.get("summary", "")
            # Truncate long summaries for the reference card
            if len(summary) > 100:
                summary = summary[:97] + "..."
            parts.append(f"  {m['member_name']}{dep}: {summary}")
        parts.append("")

    total = sum(len(g) for g in groups.values())
    parts.append(f"Total: {total} members")

    return "\n".join(parts)


@mcp.tool()
def get_deprecation_warnings(name: str) -> str:
    """Check whether a Unity class, method, or property is deprecated, and find the replacement.

    Use this before using any API you suspect might be outdated. Catches common mistakes
    like using FindObjectOfType (deprecated) instead of FindAnyObjectByType.

    Args:
        name: Class or member name to check. Examples: "WWW", "FindObjectOfType", "GUIText",
              "UnityEngine.Component.BroadcastMessage"
    """
    conn = _get_conn()

    # First check: is this specific thing deprecated?
    # Try exact FQN
    record = db.get_by_fqn(conn, name)
    if record:
        if record.get("deprecated"):
            return _format_deprecation(record)
        return f"'{name}' is NOT deprecated in Unity {_unity_version}. Safe to use."

    # Try searching deprecated records
    deprecated = db.search_deprecated(conn, name, n=10)
    if deprecated:
        parts = [f"Found {len(deprecated)} deprecated member(s) matching '{name}':\n"]
        for r in deprecated:
            parts.append(_format_deprecation(r))
            parts.append("")
        return "\n".join(parts)

    # Check if it exists at all but is not deprecated
    results = db.search(conn, name, n=3)
    if results:
        non_dep = [r for r in results if not r.get("deprecated")]
        if non_dep:
            parts = [f"'{name}' is NOT deprecated. Found these matching members:\n"]
            for r in non_dep:
                parts.append(f"  [{r['member_type'].upper()}] {r['fqn']} — {r.get('summary', '')[:80]}")
            return "\n".join(parts)
        # All results are deprecated
        parts = [f"All matches for '{name}' are deprecated:\n"]
        for r in results:
            parts.append(_format_deprecation(r))
            parts.append("")
        return "\n".join(parts)

    return f"No API member found matching '{name}'."


def _format_deprecation(r: dict) -> str:
    """Format a single deprecation warning."""
    lines = [f"[DEPRECATED] {r['fqn']}"]
    ns = r.get("namespace", "")
    if ns:
        lines.append(f"  Namespace: {ns}")
    summary = r.get("summary", "")
    if summary:
        lines.append(f"  Summary: {summary}")
    hint = r.get("deprecation_hint", "")
    if hint:
        lines.append(f"  Replacement: Use {hint} instead")
    else:
        lines.append("  Replacement: Check Unity 6 documentation for the recommended alternative")
    return "\n".join(lines)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
