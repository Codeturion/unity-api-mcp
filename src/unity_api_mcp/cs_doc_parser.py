"""Parse C# XML doc comments (///) from source files into structured records.

Used for Unity packages that ship as source code (Input System, Addressables)
rather than pre-built DLLs with XML IntelliSense files.
"""

import re
from pathlib import Path


# Match /// comment blocks and the declaration that follows
_DOC_COMMENT_LINE = re.compile(r"^\s*///\s?(.*)")
_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)")
_CLASS_RE = re.compile(
    r"^\s*(?:public|internal|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?(?:sealed\s+)?(?:partial\s+)?"
    r"(?:class|struct|interface|enum)\s+(\w+)"
)
_METHOD_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+(?:static\s+)?(?:virtual\s+)?(?:override\s+)?(?:abstract\s+)?(?:new\s+)?"
    r"(?:async\s+)?(?:[\w<>\[\],\s?]+?)\s+(\w+)\s*(?:<[^>]+>)?\s*\("
)
_PROPERTY_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+(?:static\s+)?(?:virtual\s+)?(?:override\s+)?(?:abstract\s+)?(?:new\s+)?"
    r"([\w<>\[\],\s?]+?)\s+(\w+)\s*\{"
)
_FIELD_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+(?:static\s+)?(?:readonly\s+)?(?:const\s+)?"
    r"([\w<>\[\],\s?]+?)\s+(\w+)\s*[;=]"
)
_EVENT_RE = re.compile(
    r"^\s*(?:public|internal|protected)\s+(?:static\s+)?event\s+"
    r"([\w<>\[\],\s?]+?)\s+(\w+)\s*[;{]"
)
_PARAM_RE = re.compile(r"<param\s+name=[\"'](\w+)[\"']>(.*?)</param>")
_RETURNS_RE = re.compile(r"<returns>(.*?)</returns>")
_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
_SEE_CREF_RE = re.compile(r"<see\s+cref=[\"']([^\"']+)[\"']\s*/>")
_XML_TAG_RE = re.compile(r"<[^>]+>")

_DEPRECATED_PATTERNS = re.compile(
    r"\b(obsolete|deprecated)\b|use\s+\S+\s+instead",
    re.IGNORECASE,
)


def parse_cs_directory(directory: Path) -> list[dict]:
    """Recursively parse all .cs files in a directory for XML doc comments."""
    records = []
    cs_files = list(directory.rglob("*.cs"))

    for cs_file in cs_files:
        # Skip test files, samples, editor-only
        rel = str(cs_file.relative_to(directory))
        if any(skip in rel.lower() for skip in ("test", "sample", "example", "doccode")):
            continue

        try:
            file_records = _parse_cs_file(cs_file)
            records.extend(file_records)
        except Exception:
            continue

    return records


def _parse_cs_file(path: Path) -> list[dict]:
    """Parse a single .cs file and extract documented members."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    lines = text.splitlines()
    records = []
    current_namespace = ""
    class_stack = []  # Stack of class names for nesting

    i = 0
    while i < len(lines):
        line = lines[i]

        # Track namespace
        ns_match = _NAMESPACE_RE.match(line)
        if ns_match:
            current_namespace = ns_match.group(1)
            i += 1
            continue

        # Track class/struct/interface nesting
        cls_match = _CLASS_RE.match(line)
        if cls_match and not _is_doc_comment(line):
            # Check if there's a doc comment block above
            doc_block, params, returns_text = _extract_doc_block(lines, i)
            class_name = cls_match.group(1)
            class_stack.append(class_name)

            if doc_block:
                fqn = f"{current_namespace}.{class_name}" if current_namespace else class_name
                summary = _clean_xml_text(doc_block)
                deprecated = bool(_DEPRECATED_PATTERNS.search(summary))
                records.append({
                    "fqn": fqn,
                    "namespace": current_namespace,
                    "class_name": class_name,
                    "member_name": "",
                    "member_type": "type",
                    "summary": summary,
                    "params_json": [],
                    "returns_text": "",
                    "deprecated": deprecated,
                    "deprecation_hint": _extract_deprecation_hint(summary) if deprecated else "",
                })

            i += 1
            continue

        # Track scope for class stack (simplified brace counting)
        if "}" in line and not "//" in line.split("}")[0]:
            # This is a rough heuristic — good enough for top-level classes
            pass

        # Check for doc comment block
        if _is_doc_comment(line):
            # Collect the full doc block
            doc_start = i
            while i < len(lines) and _is_doc_comment(lines[i]):
                i += 1

            # Now lines[i] should be the declaration
            if i < len(lines):
                decl_line = lines[i]
                doc_text = "\n".join(
                    _DOC_COMMENT_LINE.match(lines[j]).group(1)
                    for j in range(doc_start, i)
                    if _DOC_COMMENT_LINE.match(lines[j])
                )

                record = _parse_declaration(
                    decl_line, doc_text, current_namespace,
                    class_stack[-1] if class_stack else ""
                )
                if record:
                    records.append(record)
            continue

        i += 1

    return records


def _is_doc_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("///")


def _extract_doc_block(lines: list[str], decl_index: int) -> tuple[str, list[dict], str]:
    """Look backwards from a declaration to find its doc comment block."""
    doc_lines = []
    i = decl_index - 1
    while i >= 0 and _is_doc_comment(lines[i]):
        match = _DOC_COMMENT_LINE.match(lines[i])
        if match:
            doc_lines.insert(0, match.group(1))
        i -= 1

    if not doc_lines:
        return "", [], ""

    doc_text = "\n".join(doc_lines)

    # Extract summary
    summary_match = _SUMMARY_RE.search(doc_text)
    summary = summary_match.group(1).strip() if summary_match else doc_text

    # Extract params
    params = [
        {"name": m.group(1), "description": _clean_xml_text(m.group(2))}
        for m in _PARAM_RE.finditer(doc_text)
    ]

    # Extract returns
    returns_match = _RETURNS_RE.search(doc_text)
    returns_text = _clean_xml_text(returns_match.group(1)) if returns_match else ""

    return summary, params, returns_text


def _parse_declaration(decl_line: str, doc_text: str,
                       namespace: str, class_name: str) -> dict | None:
    """Parse a C# declaration line and combine with doc text into a record."""

    # Extract summary
    summary_match = _SUMMARY_RE.search(doc_text)
    summary = _clean_xml_text(summary_match.group(1).strip() if summary_match else doc_text)

    if not summary or len(summary) < 3:
        return None

    # Extract params
    params = [
        {"name": m.group(1), "description": _clean_xml_text(m.group(2))}
        for m in _PARAM_RE.finditer(doc_text)
    ]

    # Extract returns
    returns_match = _RETURNS_RE.search(doc_text)
    returns_text = _clean_xml_text(returns_match.group(1)) if returns_match else ""

    # Detect deprecation
    deprecated = bool(_DEPRECATED_PATTERNS.search(summary))
    deprecation_hint = _extract_deprecation_hint(summary) if deprecated else ""

    # Try to match declaration type
    # Check class/struct/interface first
    cls_match = _CLASS_RE.match(decl_line)
    if cls_match:
        member_name_str = cls_match.group(1)
        fqn = f"{namespace}.{member_name_str}" if namespace else member_name_str
        return {
            "fqn": fqn,
            "namespace": namespace,
            "class_name": member_name_str,
            "member_name": "",
            "member_type": "type",
            "summary": summary,
            "params_json": params,
            "returns_text": returns_text,
            "deprecated": deprecated,
            "deprecation_hint": deprecation_hint,
        }

    if not class_name:
        return None

    # Event (check before property — similar syntax)
    event_match = _EVENT_RE.match(decl_line)
    if event_match:
        member_name_str = event_match.group(2)
        fqn = f"{namespace}.{class_name}.{member_name_str}" if namespace else f"{class_name}.{member_name_str}"
        return _build_record(fqn, namespace, class_name, member_name_str, "event",
                           summary, params, returns_text, deprecated, deprecation_hint)

    # Method
    method_match = _METHOD_RE.match(decl_line)
    if method_match:
        member_name_str = method_match.group(1)
        # Skip property accessors
        if member_name_str in ("get", "set", "add", "remove"):
            return None
        fqn = f"{namespace}.{class_name}.{member_name_str}" if namespace else f"{class_name}.{member_name_str}"
        return _build_record(fqn, namespace, class_name, member_name_str, "method",
                           summary, params, returns_text, deprecated, deprecation_hint)

    # Property
    prop_match = _PROPERTY_RE.match(decl_line)
    if prop_match:
        member_name_str = prop_match.group(2)
        # Skip common false positives
        if member_name_str in ("class", "struct", "interface", "enum", "namespace",
                               "if", "else", "for", "while", "switch", "try", "catch"):
            return None
        fqn = f"{namespace}.{class_name}.{member_name_str}" if namespace else f"{class_name}.{member_name_str}"
        return _build_record(fqn, namespace, class_name, member_name_str, "property",
                           summary, params, returns_text, deprecated, deprecation_hint)

    # Field
    field_match = _FIELD_RE.match(decl_line)
    if field_match:
        member_name_str = field_match.group(2)
        fqn = f"{namespace}.{class_name}.{member_name_str}" if namespace else f"{class_name}.{member_name_str}"
        return _build_record(fqn, namespace, class_name, member_name_str, "field",
                           summary, params, returns_text, deprecated, deprecation_hint)

    return None


def _build_record(fqn, namespace, class_name, member_name, member_type,
                  summary, params, returns_text, deprecated, deprecation_hint):
    return {
        "fqn": fqn,
        "namespace": namespace,
        "class_name": class_name,
        "member_name": member_name,
        "member_type": member_type,
        "summary": summary,
        "params_json": params,
        "returns_text": returns_text,
        "deprecated": deprecated,
        "deprecation_hint": deprecation_hint,
    }


def _clean_xml_text(text: str) -> str:
    """Strip XML tags and normalize whitespace."""
    # Replace <see cref="Foo"/> with Foo
    text = _SEE_CREF_RE.sub(lambda m: m.group(1).split(".")[-1], text)
    # Strip remaining XML tags
    text = _XML_TAG_RE.sub("", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_deprecation_hint(summary: str) -> str:
    match = re.search(r"(?:use|Use)\s+(\S+?)[\s.]", summary)
    return match.group(1) if match else ""
