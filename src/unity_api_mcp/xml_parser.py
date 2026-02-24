"""Parse Unity XML IntelliSense files into structured records."""

import re
from pathlib import Path

from lxml import etree

# Member name prefix → type label
_PREFIX_MAP = {
    "T:": "type",
    "M:": "method",
    "P:": "property",
    "F:": "field",
    "E:": "event",
}

_DEPRECATED_PATTERNS = re.compile(
    r"\b(obsolete|deprecated)\b|use\s+\S+\s+instead",
    re.IGNORECASE,
)


def parse_xml(path: Path) -> list[dict]:
    """Parse a Unity XML doc file and return a list of record dicts."""
    tree = etree.parse(str(path))
    root = tree.getroot()
    records = []

    for member in root.iter("member"):
        name_attr = member.get("name", "")
        if not name_attr or len(name_attr) < 3 or name_attr[1] != ":":
            continue

        prefix = name_attr[:2]
        member_type = _PREFIX_MAP.get(prefix)
        if member_type is None:
            continue

        fqn = name_attr[2:]  # Strip T:/M:/P:/F:/E: prefix

        # Extract summary text
        summary = _extract_text(member.find("summary"))

        # Extract params
        params = []
        for param_el in member.findall("param"):
            params.append({
                "name": param_el.get("name", ""),
                "description": _extract_text(param_el),
            })

        # Extract returns
        returns_text = _extract_text(member.find("returns"))

        # Split FQN into namespace, class, member
        namespace, class_name, member_name = _split_fqn(fqn, member_type)

        # Detect deprecation
        deprecated = bool(_DEPRECATED_PATTERNS.search(summary)) if summary else False
        deprecation_hint = ""
        if deprecated and summary:
            # Try to extract the "Use X instead" hint
            match = re.search(r"(?:use|Use)\s+(\S+?)[\s.]", summary)
            if match:
                deprecation_hint = match.group(1)

        records.append({
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
        })

    return records


def _extract_text(el) -> str:
    """Recursively extract text content from an element, stripping XML tags."""
    if el is None:
        return ""
    # itertext() yields all text fragments including tail text of children
    parts = el.itertext()
    text = " ".join(parts)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_fqn(fqn: str, member_type: str) -> tuple[str, str, str]:
    """Split a fully-qualified name into (namespace, class_name, member_name).

    For types: namespace=everything before last dot, class_name=last part, member_name=""
    For methods: handle params in parens, split on dots
    For properties/fields/events: namespace.class.member
    """
    # Strip method parameters for splitting
    base = fqn.split("(")[0]

    # Handle constructor names like Namespace.Class.#ctor
    parts = base.split(".")

    if member_type == "type":
        # For nested types like Namespace.OuterClass+InnerClass
        # and generic types like Namespace.Class`1
        if len(parts) >= 2:
            class_name = parts[-1]
            namespace = ".".join(parts[:-1])
        else:
            class_name = parts[0]
            namespace = ""
        return namespace, class_name, ""

    if len(parts) >= 3:
        member_name = parts[-1]
        class_name = parts[-2]
        namespace = ".".join(parts[:-2])
    elif len(parts) == 2:
        member_name = parts[-1]
        class_name = parts[0]
        namespace = ""
    else:
        member_name = parts[0]
        class_name = ""
        namespace = ""

    return namespace, class_name, member_name
