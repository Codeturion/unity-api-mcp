# unity-docs-mcp

Local MCP server that gives AI agents accurate Unity 6 API documentation. Prevents hallucinated method signatures, wrong namespaces, and deprecated API usage.

Works with Claude Code, Cursor, Windsurf, or any MCP-compatible AI tool.

## What it does

5 tools your AI can call:

| Tool | Purpose | Example |
|------|---------|---------|
| `search_unity_api` | Find APIs by keyword | "Tilemap SetTile", "async load scene" |
| `get_method_signature` | Get exact signatures with all overloads | `UnityEngine.Physics.Raycast` |
| `get_namespace` | Resolve `using` directives | "SceneManager" → `using UnityEngine.SceneManagement;` |
| `get_class_reference` | Full class reference card (all members) | "InputAction" → 31 methods/fields/properties |
| `get_deprecation_warnings` | Check if an API is obsolete + get replacement | "WWW" → Use UnityWebRequest instead |

**Coverage:** All UnityEngine/UnityEditor modules (~75K records), Input System, Addressables. Parsed from Unity's own XML IntelliSense files + package C# source docs.

## Requirements

- Python 3.10+
- Unity 6 installed (6000.x)
- A Unity project (for package source parsing — optional)

## Setup

### 1. Clone and create virtual environment

```bash
git clone <repo-url> unity-docs-mcp
cd unity-docs-mcp
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -e .
```

### 2. Run ingestion

This parses Unity's XML docs and builds the SQLite database. Run once, then again when Unity is updated.

```bash
# Basic — Unity engine APIs only
python -m unity_docs_mcp.ingest

# With package sources (Input System, Addressables)
python -m unity_docs_mcp.ingest --project "path/to/your/unity/project"
```

If Unity isn't auto-detected, set the install path:

```bash
# Windows (Command Prompt)
set UNITY_INSTALL_PATH=C:\Program Files\Unity\Hub\Editor\6000.3.8f1

# Windows (PowerShell)
$env:UNITY_INSTALL_PATH = "C:\Program Files\Unity\Hub\Editor\6000.3.8f1"

# macOS/Linux
export UNITY_INSTALL_PATH=/Applications/Unity/Hub/Editor/6000.3.8f1
```

You should see output like:
```
Found 2 top-level + 137 module XML files (139 total)
...
Parsing com.unity.inputsystem: 1929 members parsed
Parsing com.unity.addressables: 1192 members parsed
...
77997 records inserted
```

### 3. Add to your AI tool

#### Claude Code

Add to `~/.claude/mcp.json` (global) or `<project>/.mcp.json` (per-project):

**macOS / Linux:**
```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "/path/to/unity-docs-mcp/venv/bin/python",
      "args": ["-m", "unity_docs_mcp.server"],
      "cwd": "/path/to/unity-docs-mcp",
      "env": {
        "PYTHONPATH": "/path/to/unity-docs-mcp/src",
        "UNITY_INSTALL_PATH": "/Applications/Unity/Hub/Editor/6000.3.8f1",
        "UNITY_PROJECT_PATH": "/path/to/your/unity/project"
      }
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "C:\\path\\to\\unity-docs-mcp\\venv\\Scripts\\python.exe",
      "args": ["-m", "unity_docs_mcp.server"],
      "cwd": "C:\\path\\to\\unity-docs-mcp",
      "env": {
        "PYTHONPATH": "C:\\path\\to\\unity-docs-mcp\\src",
        "UNITY_INSTALL_PATH": "C:\\Program Files\\Unity\\Hub\\Editor\\6000.3.8f1",
        "UNITY_PROJECT_PATH": "C:\\path\\to\\your\\unity\\project"
      }
    }
  }
}
```

#### Cursor / Windsurf

Add the same config to your MCP settings file. The server uses stdio transport (default).

### 4. Verify it's working

Ask your AI: *"What namespace does SceneManager belong to?"*

If everything is connected, it should call `get_namespace("SceneManager")` and answer `using UnityEngine.SceneManagement;` with confidence. If it guesses without calling a tool, the MCP server isn't connected — check the config paths and restart your AI tool.

You can also try: *"Show me all methods on the Tilemap class"* — this should call `get_class_reference` and return 60+ methods.

### 5. Tell your AI to use it

Add the following to your project's `CLAUDE.md` (or equivalent instructions file):

```markdown
## Unity API Lookup (unity-docs MCP)

Use the `unity-docs` MCP tools to verify Unity API usage instead of guessing. **Do not hallucinate signatures.**

| When | Tool | Example |
|------|------|---------|
| Unsure about a method's parameters or return type | `get_method_signature` | `get_method_signature("UnityEngine.Tilemaps.Tilemap.SetTile")` |
| Need the `using` directive for a type | `get_namespace` | `get_namespace("SceneManager")` |
| Want to see all members on a class | `get_class_reference` | `get_class_reference("InputAction")` |
| Searching for an API by keyword | `search_unity_api` | `search_unity_api("async load scene")` |
| Checking if an API is deprecated | `get_deprecation_warnings` | `get_deprecation_warnings("FindObjectOfType")` |

**Rules:**
- Before writing a Unity API call you haven't used in this conversation, verify the signature with `get_method_signature`
- Before adding a `using` directive, verify with `get_namespace` if unsure
- Covers: all UnityEngine/UnityEditor modules, Input System, Addressables
- Does NOT cover: DOTween, VContainer, Newtonsoft.Json (third-party — rely on project source)
```

This is **important** — without these instructions, the AI has the tools available but won't know when to use them proactively. The rules turn passive tools into an active workflow.

## Configuration

| Environment Variable | Required | Description |
|---|---|---|
| `UNITY_INSTALL_PATH` | No (auto-detected) | Path to Unity 6 install root, e.g. `H:/Unity/6000.3.8f1` |
| `UNITY_PROJECT_PATH` | No | Path to a Unity project for parsing package sources (Input System, Addressables) |

Auto-detection searches common install locations:
- Windows: `C:/Program Files/Unity/Hub/Editor/6000.*`, `H:/Unity/6000.*`
- macOS: `/Applications/Unity/Hub/Editor/6000.*`
- Linux: `~/Unity/Hub/Editor/6000.*`

## Data sources

The server ingests documentation from two sources:

**1. XML IntelliSense files** (primary) — Ship with every Unity installation at `Editor/Data/Managed/`. Machine-readable, structured, complete. Covers all UnityEngine and UnityEditor APIs including per-module assemblies (Physics, Tilemaps, Animation, UI Toolkit, etc.).

**2. C# source doc comments** (packages) — Unity packages like Input System and Addressables ship as source code, not DLLs. The ingestion pipeline parses `///` XML doc comments directly from `.cs` files in your project's `Library/PackageCache/`.

## Project structure

```
unity-docs-mcp/
├── src/unity_docs_mcp/
│   ├── server.py          # MCP server — 5 tools
│   ├── db.py              # SQLite + FTS5 database layer
│   ├── xml_parser.py      # Parse Unity XML IntelliSense files
│   ├── cs_doc_parser.py   # Parse C# doc comments from package source
│   ├── unity_paths.py     # Locate Unity install + package dirs
│   └── ingest.py          # CLI ingestion pipeline
├── data/
│   └── unity_docs.db      # SQLite database (generated by ingestion)
├── pyproject.toml
└── .env.example
```

## Troubleshooting

**"No results found" for a query**
- Run ingestion first: `python -m unity_docs_mcp.ingest`
- Check that `data/unity_docs.db` exists and is non-empty
- For Input System / Addressables: pass `--project` flag during ingestion

**"Could not find Unity XML documentation files"**
- Set `UNITY_INSTALL_PATH` to your Unity 6 install root
- Verify the path contains `Editor/Data/Managed/UnityEngine.xml`

**Third-party packages return no results**
- DOTween, VContainer, Newtonsoft.Json are not indexed (third-party, not Unity packages)
- Only Unity first-party packages with C# source in `Library/PackageCache/` are supported

**Server won't start**
- Check Python version: `python --version` (needs 3.10+)
- Check dependencies: `pip install -e .` from the project root
- Check `PYTHONPATH` points to the `src/` directory

## License

MIT
