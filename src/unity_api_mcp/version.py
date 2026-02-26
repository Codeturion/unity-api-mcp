"""Unity version detection and per-version database management."""

import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

_RELEASE_TAG = "db-v1"
_REPO = "Codeturion/unity-api-mcp"
_VALID_VERSIONS = ("2022", "2023", "6")

# Legacy bundled DB path (for backwards compatibility during transition)
_BUNDLED_DB = Path(__file__).resolve().parent / "data" / "unity_docs.db"


def detect_version() -> str:
    """Detect the Unity version to use.

    Priority:
    1. UNITY_VERSION env var (explicit override)
    2. UNITY_PROJECT_PATH -> ProjectSettings/ProjectVersion.txt
    3. Default to "6"
    """
    # 1. Explicit env var
    env_ver = os.environ.get("UNITY_VERSION", "").strip()
    if env_ver:
        mapped = _map_version(env_ver)
        if mapped:
            return mapped
        if env_ver in _VALID_VERSIONS:
            return env_ver
        print(
            f"WARNING: UNITY_VERSION='{env_ver}' not recognized. "
            f"Expected 2022, 2023, or 6. Defaulting to 6.",
            file=sys.stderr,
        )
        return "6"

    # 2. Auto-detect from project
    project_path = os.environ.get("UNITY_PROJECT_PATH", "").strip()
    if project_path:
        version = _read_project_version(Path(project_path))
        if version:
            return version

    # 3. Default
    return "6"


def _map_version(raw: str) -> str | None:
    """Map a full version string like '6000.3.8f1' to a major version."""
    if raw.startswith("6000"):
        return "6"
    if raw.startswith("2023"):
        return "2023"
    if raw.startswith("2022"):
        return "2022"
    return None


def _read_project_version(project_dir: Path) -> str | None:
    """Read Unity version from ProjectSettings/ProjectVersion.txt."""
    version_file = project_dir / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.is_file():
        return None

    try:
        text = version_file.read_text(encoding="utf-8")
    except OSError:
        return None

    # Format: "m_EditorVersion: 6000.3.8f1" or "m_EditorVersion: 2022.3.62f1"
    match = re.search(r"m_EditorVersion:\s*(\S+)", text)
    if not match:
        return None

    return _map_version(match.group(1))


def get_cache_dir() -> Path:
    """Return the cache directory for downloaded databases."""
    return Path.home() / ".unity-api-mcp"


def get_cache_path(version: str) -> Path:
    """Return the expected path for a version's database file."""
    return get_cache_dir() / f"unity_docs_{version}.db"


def ensure_db(version: str) -> Path:
    """Ensure the database for the given version exists locally.

    Returns the path to the database file. Downloads from GitHub Release
    if not already cached. Falls back to bundled DB if available.
    """
    cached = get_cache_path(version)
    if cached.is_file():
        return cached

    # Concurrent launches may download in parallel; atomic .tmp rename keeps it safe.
    # Try downloading from GitHub Release
    url = (
        f"https://github.com/{_REPO}/releases/download/"
        f"{_RELEASE_TAG}/unity_docs_{version}.db"
    )

    print(f"Downloading Unity {version} database from {url} ...", file=sys.stderr)

    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".db.tmp")

        req = urllib.request.Request(url, headers={"User-Agent": "unity-api-mcp"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        tmp.write_bytes(data)
        tmp.rename(cached)
        size_mb = len(data) / (1024 * 1024)
        print(
            f"Downloaded Unity {version} database ({size_mb:.1f} MB) to {cached}",
            file=sys.stderr,
        )
        return cached

    except (urllib.error.URLError, OSError) as exc:
        # Clean up partial download
        tmp = cached.with_suffix(".db.tmp")
        if tmp.exists():
            tmp.unlink()

        # Fall back to bundled DB if it exists (transition period)
        if _BUNDLED_DB.is_file():
            print(
                f"Download failed ({exc}). Using bundled database.",
                file=sys.stderr,
            )
            return _BUNDLED_DB

        raise RuntimeError(
            f"Could not download Unity {version} database from {url}.\n"
            f"Error: {exc}\n"
            f"Check your internet connection, or build locally with:\n"
            f"  python -m unity_api_mcp.ingest --unity-version {version}"
        ) from exc
