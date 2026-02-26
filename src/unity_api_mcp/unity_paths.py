"""Locate Unity XML IntelliSense files and package source directories on disk."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Top-level XML filenames (always present)
_TOP_XML_FILES = ("UnityEngine.xml", "UnityEditor.xml")

# Common Unity install search roots by platform
_SEARCH_ROOTS = {
    "win32": [
        Path("C:/Program Files/Unity/Hub/Editor"),
        Path("H:/Unity"),
        Path("D:/Unity"),
    ],
    "darwin": [
        Path("/Applications/Unity/Hub/Editor"),
    ],
    "linux": [
        Path(os.path.expanduser("~/Unity/Hub/Editor")),
    ],
}

# Relative path from Unity install root to the Managed XML docs
_MANAGED_REL = Path("Editor/Data/Managed")
_MODULES_REL = _MANAGED_REL / "UnityEngine"

# Version prefix mapping for auto-detection in Hub/Editor directories
_VERSION_PREFIXES = {
    "6": "6000.",
    "2023": "2023.",
    "2022": "2022.",
}


def _find_unity_root(unity_version: str | None = None) -> Path:
    """Resolve the Unity install root directory.

    Search order:
    1. UNITY_INSTALL_PATH env var
    2. Auto-detect by scanning common Hub/Editor directories

    Args:
        unity_version: Target version ("2022", "2023", or "6"). If None,
                       searches for any version (preferring newest).
    """
    env_path = os.environ.get("UNITY_INSTALL_PATH")
    if env_path:
        root = Path(env_path)
        managed = root / _MANAGED_REL
        if managed.is_dir():
            return root
        raise FileNotFoundError(
            f"UNITY_INSTALL_PATH={env_path} set but Managed dir not found at {managed}"
        )

    # Build the list of prefixes to search for
    if unity_version and unity_version in _VERSION_PREFIXES:
        prefixes = [_VERSION_PREFIXES[unity_version]]
    else:
        # Search all versions, newest first
        prefixes = list(_VERSION_PREFIXES.values())

    platform = sys.platform
    roots = _SEARCH_ROOTS.get(platform, [])
    for prefix in prefixes:
        for root in roots:
            if not root.exists():
                continue
            try:
                for child in sorted(root.iterdir(), reverse=True):
                    if child.is_dir() and child.name.startswith(prefix):
                        managed = child / _MANAGED_REL
                        if managed.is_dir():
                            return child
            except PermissionError:
                continue

    version_hint = f" {unity_version}" if unity_version else ""
    raise FileNotFoundError(
        f"Could not find Unity{version_hint} installation. "
        "Set UNITY_INSTALL_PATH env var to your Unity install root "
        "(e.g. H:/Unity/6000.3.8f1)"
    )


def find_xml_paths(unity_version: str | None = None) -> dict[str, Path]:
    """Return a dict of {filename: Path} for ALL Unity XML doc files.

    Includes:
    - Top-level: UnityEngine.xml, UnityEditor.xml
    - Module XMLs: Editor/Data/Managed/UnityEngine/*.xml (137+ files)

    Args:
        unity_version: Target version ("2022", "2023", or "6"). Passed
                       through to _find_unity_root() for install detection.
    """
    unity_root = _find_unity_root(unity_version)
    managed = unity_root / _MANAGED_REL
    modules_dir = unity_root / _MODULES_REL

    result = {}

    # Top-level XMLs
    for name in _TOP_XML_FILES:
        p = managed / name
        if p.is_file():
            result[name] = p

    if not result:
        raise FileNotFoundError(
            f"No XML files found in {managed}. Check your Unity installation."
        )

    # Module XMLs (the big win — 137+ additional files)
    if modules_dir.is_dir():
        for xml_file in sorted(modules_dir.glob("*.xml")):
            key = f"modules/{xml_file.name}"
            result[key] = xml_file

    return result


def find_package_source_dirs() -> dict[str, Path]:
    """Find Unity package source directories for C# doc comment parsing.

    Checks both:
    1. UNITY_PROJECT_PATH env var → Library/PackageCache/
    2. Current working directory (if it has a Library/PackageCache/)

    Returns dict of {package_id: source_dir}, e.g.:
      {"com.unity.inputsystem": Path("...PackageCache/com.unity.inputsystem@hash")}
    """
    # Packages we care about (add more as needed)
    _WANTED_PACKAGES = [
        "com.unity.inputsystem",
        "com.unity.addressables",
        "com.unity.resourcemanager",
        "com.unity.ugui",
        "com.unity.textmeshpro",
        "com.unity.ai.navigation",
        "com.unity.netcode.gameobjects",
    ]

    project_path = os.environ.get("UNITY_PROJECT_PATH")
    search_dirs = []

    if project_path:
        pkg_cache = Path(project_path) / "Library" / "PackageCache"
        if pkg_cache.is_dir():
            search_dirs.append(pkg_cache)

    # Also check cwd
    cwd_cache = Path.cwd() / "Library" / "PackageCache"
    if cwd_cache.is_dir() and cwd_cache not in search_dirs:
        search_dirs.append(cwd_cache)

    result = {}
    for cache_dir in search_dirs:
        try:
            for child in cache_dir.iterdir():
                if not child.is_dir():
                    continue
                # Package folders are named like "com.unity.inputsystem@hash"
                pkg_id = child.name.split("@")[0]
                if pkg_id in _WANTED_PACKAGES and pkg_id not in result:
                    result[pkg_id] = child
        except PermissionError:
            continue

    return result
