# unity-api-mcp

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

**Coverage:** All UnityEngine/UnityEditor modules (~75K records), Input System, Addressables. 78K total records ship pre-built — no ingestion step required.

## Requirements

- Python 3.10+
- That's it. The database ships pre-built. Unity does not need to be installed.

## Setup

### 1. Install

```bash
pip install unity-api-mcp
```

Or install from source:
```bash
git clone <repo-url> unity-api-mcp
cd unity-api-mcp
pip install .
```

### 2. Add to your AI tool

#### Claude Code

Add to `~/.claude/mcp.json` (global) or `<project>/.mcp.json` (per-project):

**macOS / Linux:**
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "unity-api-mcp",
      "args": []
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "unity-api-mcp.exe",
      "args": []
    }
  }
}
```

If the command isn't found (not on PATH), use the full path to the script:

**macOS / Linux:**
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "/path/to/venv/bin/unity-api-mcp",
      "args": []
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "C:\\path\\to\\venv\\Scripts\\unity-api-mcp.exe",
      "args": []
    }
  }
}
```

#### Cursor / Windsurf

Add the same config to your MCP settings file. The server uses stdio transport (default).

### 3. Verify it's working

Restart your AI tool (or run `/mcp` in Claude Code to reconnect), then ask:

*"What namespace does SceneManager belong to?"*

If everything is connected, it should call `get_namespace("SceneManager")` and answer `using UnityEngine.SceneManagement;`. If it guesses without calling a tool, the MCP server isn't connected — check the config paths and restart.

You can also try: *"Show me all methods on the Tilemap class"* — this should call `get_class_reference` and return 60+ methods.

### 4. Tell your AI to use it proactively

Add the following to your project's `CLAUDE.md` (or equivalent instructions file). **This step is important** — without it, the AI has the tools but won't know when to reach for them.

```markdown
## Unity API Lookup (unity-api MCP)

Use the `unity-api` MCP tools to verify Unity API usage instead of guessing. **Do not hallucinate signatures.**

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

## AI-Assisted Setup

If an AI agent (Claude Code, etc.) is setting this up for you, give it these instructions:

> Read the README at `<path>/unity-api-mcp/README.md` and set up the MCP server for my Unity project at `<project-path>`.

The agent should:
1. **Install** — `pip install unity-api-mcp` (or `pip install .` if cloned locally)
2. **Find the executable** — run `which unity-api-mcp` (macOS/Linux) or `where unity-api-mcp` (Windows) to get the full path
3. **Write MCP config** — add to `~/.claude/mcp.json` with `"command": "<full-path-to-unity-api-mcp>"`
4. **Add CLAUDE.md instructions** — append the "Unity API Lookup" snippet from Step 4 above to the project's `CLAUDE.md`
5. **Verify** — reconnect MCP (`/mcp` in Claude Code) and test: `get_namespace("SceneManager")` should return `using UnityEngine.SceneManagement;`

## Advanced: Rebuild or extend the database

The shipped database covers Unity 6 (6000.x) engine APIs + Input System + Addressables. If you need to:
- **Update for a newer Unity version** — re-run ingestion
- **Add more packages** (e.g. Cinemachine, TextMeshPro) — re-run with `--project`
- **Match your exact package versions** — re-run with `--project`

### Run ingestion

```bash
# Activate venv first, then:

# Engine APIs only (requires Unity 6 installed)
python -m unity_api_mcp.ingest

# Engine APIs + packages from your project
python -m unity_api_mcp.ingest --project "/path/to/your/unity/project"
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

You can also add these to the MCP config `env` block so they're always available:

```json
"env": {
  "PYTHONPATH": "...",
  "UNITY_INSTALL_PATH": "...",
  "UNITY_PROJECT_PATH": "..."
}
```

### What ingestion parses

**XML IntelliSense files** — Ship with every Unity installation at `Editor/Data/Managed/`. 139 XML files covering all UnityEngine and UnityEditor modules.

**C# source doc comments** — Unity packages (Input System, Addressables, etc.) ship as source code in your project's `Library/PackageCache/`. The ingestion pipeline parses `///` XML doc comments from `.cs` files.

## Project structure

```
unity-api-mcp/
├── src/unity_api_mcp/
│   ├── server.py          # MCP server — 5 tools
│   ├── db.py              # SQLite + FTS5 database layer
│   ├── xml_parser.py      # Parse Unity XML IntelliSense files
│   ├── cs_doc_parser.py   # Parse C# doc comments from package source
│   ├── unity_paths.py     # Locate Unity install + package dirs
│   ├── ingest.py          # CLI ingestion pipeline
│   └── data/
│       └── unity_docs.db  # Pre-built SQLite database (78K records, ships with package)
├── pyproject.toml
└── .env.example
```

## Troubleshooting

**"No results found" for a query**
- The pre-built database should be included in the package. If missing, reinstall: `pip install --force-reinstall unity-api-mcp`
- Or re-run ingestion to rebuild (see Advanced section)

**Server won't start**
- Check Python version: `python --version` (needs 3.10+)
- Check the command path: run `which unity-api-mcp` (macOS/Linux) or `where unity-api-mcp` (Windows)
- If not found, use the full path in your MCP config

**Third-party packages return no results**
- DOTween, VContainer, Newtonsoft.Json are not indexed (third-party, not Unity packages)
- Only Unity first-party packages are supported via ingestion with `--project`

**Want to add more packages**
- Run `python -m unity_api_mcp.ingest --project "/path/to/project"` to parse all Unity packages in your project's `Library/PackageCache/`

## License

MIT
