# unity-api-mcp

[![PyPI Version](https://img.shields.io/pypi/v/unity-api-mcp.svg)](https://pypi.org/project/unity-api-mcp/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/unity-api-mcp.svg)](https://pypi.org/project/unity-api-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**MCP server that gives AI agents accurate Unity API documentation. Prevents hallucinated signatures, wrong namespaces, and deprecated API usage.**

Supports **Unity 2022 LTS**, **2023**, and **Unity 6** with separate databases for each version. Works with Claude Code, Cursor, Windsurf, or any MCP-compatible AI tool. No Unity installation required.

## Quick Start

```bash
pip install unity-api-mcp
```

Then add to your `.mcp.json`, setting `UNITY_VERSION` to match your project:

```json
{
  "mcpServers": {
    "unity-api": {
      "command": "unity-api-mcp",
      "args": [],
      "env": {
        "UNITY_VERSION": "2022"
      }
    }
  }
}
```

Valid values: `"2022"`, `"2023"`, or `"6"`.

On first run the server downloads the correct database (~18-24 MB) to `~/.unity-api-mcp/`. Restart your AI tool and ask: *"What namespace does SceneManager belong to?"*

## How It Works

1. **Version detection.** The server figures out which Unity version to serve:

| Priority | Source | Example |
|----------|--------|---------|
| 1 | `UNITY_VERSION` env var | `"2022"`, `"6"`, or `"6000.3.8f1"` |
| 2 | `UNITY_PROJECT_PATH` -> `ProjectSettings/ProjectVersion.txt` | Reads `2022.3.62f1`, maps to `"2022"` |
| 3 | Default | `"6"` |

2. **Database download.** If the database for that version isn't cached locally, it downloads from GitHub (~18-24 MB, one time).

3. **Serve.** All tool calls query the version-specific SQLite database. Queries return in <15ms.

Each version has its own database with the correct signatures, deprecation warnings, and member lists for that release.

## Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `search_unity_api` | Find APIs by keyword | "Tilemap SetTile", "async load scene" |
| `get_method_signature` | Exact signatures with all overloads | `UnityEngine.Physics.Raycast` |
| `get_namespace` | Resolve `using` directives | "SceneManager" -> `using UnityEngine.SceneManagement;` |
| `get_class_reference` | Full class reference card | "InputAction" -> 31 methods/fields/properties |
| `get_deprecation_warnings` | Check if an API is obsolete | "WWW" -> Use UnityWebRequest instead |

**Coverage:** All UnityEngine/UnityEditor modules, Input System, Addressables, UI/TextMeshPro, AI Navigation, Netcode.

## Benchmarks

Measured on the Unity 6 database (42K records). Unity 2022 and 2023 databases are smaller (~32K records) but performance is the same. All queries run locally via SQLite FTS5. Token estimates use ~3.5 chars/token.

| Question | MCP | Without MCP | Savings |
|----------|-----|-------------|---------|
| "What namespace does Tilemap need?" | `get_namespace` -- **~30 tokens**, 1 call | Grep + Read XML -- ~500-2,000 tokens, 2-3 calls | 15-65x |
| "Params for Tilemap.SetTile?" | `get_method_signature` -- **~900 tokens**, 1 call | Read `TilemapModule.xml` (68KB) -- ~19,500 tokens, 2-3 calls | ~20x |
| "Everything on InputAction?" | `get_class_reference` -- **~830 tokens**, 1 call | Read `InputAction.cs` (129KB) -- ~36,800 tokens, 2-5 calls | ~44x |
| "Is WWW deprecated?" | `get_deprecation_warnings` -- **~590 tokens**, 1 call | Grep XML + read matches -- ~2,000-5,000 tokens, 2-3 calls | 3-8x |

Every MCP call completes in <15ms (local SQLite), returns structured data, and works offline.

<details>
<summary>Disclaimer</summary>

"Without MCP" token counts assume the AI reads the full source file to find the answer. In practice, a targeted grep or partial file read can be much cheaper. And if the AI already knows the answer from training data, the cost is 0 tokens. MCP doesn't always win on token count. What it guarantees is a correct, structured answer in 1 call every time. No multi-step searching, no parsing raw files, no risk of outdated or hallucinated results. MCP token counts are measured from real tool responses. All estimates use ~3.5 chars/token and may vary ~20% depending on the tokenizer.

</details>

<details>
<summary>Accuracy</summary>

| Test | Result |
|------|--------|
| Search top-1 relevance (12 common queries) | 100% |
| Namespace resolution (6 key classes) | 100% |
| Key class coverage (17 common Unity classes) | 94% (16/17) |

Ranking uses BM25 with tuned column weights (member name 10x, class name 5x) plus core namespace boosting to ensure `Object.Instantiate` ranks above niche APIs like `InstantiationParameters.Instantiate`.

</details>

## Setup Details

<details>
<summary>Claude Code configuration</summary>

Add to `~/.claude/mcp.json` (global) or `<project>/.mcp.json` (per-project).

**Set version explicitly** (recommended):
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "unity-api-mcp",
      "args": [],
      "env": {
        "UNITY_VERSION": "2022"
      }
    }
  }
}
```

On Windows, use `unity-api-mcp.exe`. If the command isn't on PATH, use the full path (e.g. `/path/to/venv/bin/unity-api-mcp`).

**Auto-detect from project path** (reads `ProjectSettings/ProjectVersion.txt`):
```json
{
  "mcpServers": {
    "unity-api": {
      "command": "unity-api-mcp",
      "args": [],
      "env": {
        "UNITY_PROJECT_PATH": "/path/to/your/unity-project"
      }
    }
  }
}
```

</details>

<details>
<summary>Cursor / Windsurf</summary>

Add the same config to your MCP settings file. The server uses stdio transport (default).

</details>

<details>
<summary>CLAUDE.md snippet (recommended)</summary>

Add the following to your project's `CLAUDE.md` (or equivalent instructions file). **This step is important.** Without it, the AI has the tools but won't know when to reach for them.

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
- Does NOT cover: DOTween, VContainer, Newtonsoft.Json (third-party -- rely on project source)
```

</details>

<details>
<summary>AI-Assisted Setup</summary>

If an AI agent (Claude Code, etc.) is setting this up for you, give it these instructions:

> Read the README at `<path>/unity-api-mcp/README.md` and set up the MCP server for my Unity project at `<project-path>`.

The agent should:
1. **Install** -- `pip install unity-api-mcp`
2. **Find the executable** -- run `which unity-api-mcp` (macOS/Linux) or `where unity-api-mcp` (Windows) to get the full path
3. **Write MCP config** -- add to `~/.claude/mcp.json` with `"command": "<full-path-to-unity-api-mcp>"` and `"env": {"UNITY_VERSION": "<version>"}`
4. **Add CLAUDE.md instructions** -- append the "Unity API Lookup" snippet above to the project's `CLAUDE.md`
5. **Verify** -- reconnect MCP (`/mcp` in Claude Code) and test: `get_namespace("SceneManager")` should return `using UnityEngine.SceneManagement;`

</details>

<details>
<summary>Environment variables</summary>

| Variable | Purpose | Example |
|----------|---------|---------|
| `UNITY_VERSION` | Override Unity version detection | `2022`, `2023`, `6`, or `6000.3.8f1` |
| `UNITY_PROJECT_PATH` | Auto-detect version from project + parse package sources | `F:/Unity Projects/my-project` |
| `UNITY_INSTALL_PATH` | Override Unity install path (for `ingest` only) | `D:/Unity/6000.3.8f1` |

</details>

<details>
<summary>Building databases locally</summary>

If you want to build a database from your own Unity installation instead of downloading:

```bash
# Install with ingest dependencies
pip install unity-api-mcp[ingest]

# Build for a specific version
python -m unity_api_mcp.ingest --unity-version 6 --unity-install "D:/Unity/6000.3.8f1" --project "F:/Unity Projects/MyProject"
python -m unity_api_mcp.ingest --unity-version 2022 --unity-install "D:/Unity/2022.3.62f1"
python -m unity_api_mcp.ingest --unity-version 2023 --unity-install "D:/Unity/2023.1.22f1"
```

Databases are written to `~/.unity-api-mcp/unity_docs_{version}.db` by default.

</details>

<details>
<summary>Project structure</summary>

```
unity-api-mcp/
├── src/unity_api_mcp/
│   ├── server.py          # MCP server -- 5 tools
│   ├── db.py              # SQLite + FTS5 database layer
│   ├── version.py         # Version detection + DB download
│   ├── xml_parser.py      # Parse Unity XML IntelliSense files
│   ├── cs_doc_parser.py   # Parse C# doc comments from package source
│   ├── unity_paths.py     # Locate Unity install + package dirs
│   └── ingest.py          # CLI ingestion pipeline
└── pyproject.toml
```

Databases are stored in `~/.unity-api-mcp/` (downloaded on first run).

</details>

<details>
<summary>Troubleshooting</summary>

**"Could not download Unity X database"**
- Check your internet connection. The server downloads ~18-24 MB on first run.
- Build locally instead: `python -m unity_api_mcp.ingest --unity-version 2022`

**Wrong API version being served**
- Set `UNITY_VERSION` explicitly in your MCP config's `env` block.
- Check the server startup log (stderr): `unity-api-mcp: serving Unity 6 API docs`

**Server won't start**
- Check Python version: `python --version` (needs 3.10+)
- Check the command path: run `which unity-api-mcp` (macOS/Linux) or `where unity-api-mcp` (Windows)
- If not found, use the full path in your MCP config

**Third-party packages return no results**
- DOTween, VContainer, Newtonsoft.Json are not indexed (third-party, not Unity packages)

</details>

---

## Contact

Need a custom MCP server for your engine or framework? I build MCP tools that cut token waste and prevent hallucinations for AI-assisted game development. If you want something similar for your team's stack, reach out.

fuatcankoseoglu@gmail.com

## License

MIT
