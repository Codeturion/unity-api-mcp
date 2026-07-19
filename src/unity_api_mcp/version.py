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
_MINOR_RE = re.compile(r"^6000\.\d+$")
_UPDATE_CHECK_TIMEOUT = 5

# Legacy bundled DB path (for backwards compatibility during transition)
_BUNDLED_DB = Path(__file__).resolve().parent / "data" / "unity_docs.db"


def detect_version() -> str:
    """Detect the Unity version to use.

    Priority:
    1. UNITY_VERSION env var (explicit override)
    2. UNITY_PROJECT_PATH -> ProjectSettings/ProjectVersion.txt
    3. Default to "6"

    Returns "2022", "2023", "6", or a Unity 6 minor stream like "6000.3".
    """
    # 1. Explicit env var
    env_ver = os.environ.get("UNITY_VERSION", "").strip()
    if env_ver:
        if env_ver in _VALID_VERSIONS or _MINOR_RE.match(env_ver):
            return env_ver
        mapped = _map_version(env_ver)
        if mapped:
            return mapped
        print(
            f"WARNING: UNITY_VERSION='{env_ver}' not recognized. "
            f"Expected 2022, 2023, 6, or a Unity 6 stream like 6000.3. "
            f"Defaulting to 6.",
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
    """Map a full version string like '6000.3.8f1' to a DB version.

    Unity 6 full versions map to their minor stream ("6000.3.8f1" ->
    "6000.3") so the most accurate per-stream database is used, with
    "6" as the download fallback (see _db_candidates).
    """
    match = re.match(r"^(6000\.\d+)\.", raw)
    if match:
        return match.group(1)
    if raw.startswith("6000"):
        return "6"
    if raw.startswith("2023"):
        return "2023"
    if raw.startswith("2022"):
        return "2022"
    return None


def _db_candidates(version: str) -> list[str]:
    """DB versions to try, most specific first.

    A Unity 6 minor stream falls back to the generic "6" database when a
    per-stream database is not available (older cache or missing asset).
    """
    if _MINOR_RE.match(version):
        return [version, "6"]
    return [version]


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


def _asset_url(version: str) -> str:
    return (
        f"https://github.com/{_REPO}/releases/download/"
        f"{_RELEASE_TAG}/unity_docs_{version}.db"
    )


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "unity-api-mcp"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    dest.write_bytes(data)


def _check_for_update(local_path: Path, version: str) -> None:
    """Re-download the cached database if the release asset changed.

    Compares local file size with the remote Content-Length via a HEAD
    request. Silently does nothing if the check fails (offline, timeout,
    no Content-Length header, etc.), so startup never breaks.
    """
    url = _asset_url(version)
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "unity-api-mcp"}
        )
        with urllib.request.urlopen(req, timeout=_UPDATE_CHECK_TIMEOUT) as resp:
            remote_size = int(resp.headers.get("Content-Length", 0))
        if remote_size <= 0 or remote_size == local_path.stat().st_size:
            return
        print(
            f"Database update available for Unity {version} "
            f"(local: {local_path.stat().st_size / 1024 / 1024:.1f} MB, "
            f"remote: {remote_size / 1024 / 1024:.1f} MB), downloading...",
            file=sys.stderr,
        )
        tmp = local_path.with_suffix(".db.tmp")
        try:
            _download(url, tmp)
            tmp.replace(local_path)
            size_mb = local_path.stat().st_size / 1024 / 1024
            print(f"  Updated -> {local_path} ({size_mb:.1f} MB)", file=sys.stderr)
        except Exception:
            tmp.unlink(missing_ok=True)
    except Exception:
        pass


def ensure_db(version: str) -> Path:
    """Ensure a database for the given version exists locally.

    Tries the most specific candidate first (e.g. "6000.3" then "6"),
    checking the local cache before downloading from the GitHub Release.
    Cached databases are freshness-checked against the release asset so
    weekly rebuilds reach existing installs. Falls back to the bundled DB
    if downloads fail.
    """
    candidates = _db_candidates(version)

    # Cached copy wins; keep it fresh.
    for v in candidates:
        cached = get_cache_path(v)
        if cached.is_file() and cached.stat().st_size > 0:
            _check_for_update(cached, v)
            return cached

    get_cache_dir().mkdir(parents=True, exist_ok=True)

    last_exc: Exception | None = None
    for v in candidates:
        cached = get_cache_path(v)
        url = _asset_url(v)
        print(f"Downloading Unity {v} database from {url} ...", file=sys.stderr)

        tmp = cached.with_suffix(".db.tmp")
        try:
            _download(url, tmp)
            tmp.replace(cached)
            size_mb = cached.stat().st_size / (1024 * 1024)
            print(
                f"Downloaded Unity {v} database ({size_mb:.1f} MB) to {cached}",
                file=sys.stderr,
            )
            return cached
        except urllib.error.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            last_exc = exc
            if exc.code == 404 and v != candidates[-1]:
                print("  Not found, trying fallback...", file=sys.stderr)
                continue
        except (urllib.error.URLError, OSError) as exc:
            tmp.unlink(missing_ok=True)
            last_exc = exc

    # Fall back to bundled DB if it exists (transition period)
    if _BUNDLED_DB.is_file():
        print(
            f"Download failed ({last_exc}). Using bundled database.",
            file=sys.stderr,
        )
        return _BUNDLED_DB

    raise RuntimeError(
        f"Could not download a Unity {version} database "
        f"(tried: {', '.join(candidates)}).\n"
        f"Error: {last_exc}\n"
        f"Check your internet connection, or build locally with:\n"
        f"  python -m unity_api_mcp.ingest --unity-version {version}"
    ) from last_exc
