# unity-api-mcp

[![PyPI Version](https://img.shields.io/pypi/v/unity-api-mcp.svg)](https://pypi.org/project/unity-api-mcp/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/unity-api-mcp.svg)](https://pypi.org/project/unity-api-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**MCP server that gives AI agents accurate Unity 6 API documentation — prevents hallucinated signatures, wrong namespaces, and deprecated API usage.**

Works with Claude Code, Cursor, Windsurf, or any MCP-compatible AI tool. The database ships pre-built (42K records) — no Unity installation required.

## Quick Start

```bash
pip install unity-api-mcp
```

Then add to your `.mcp.json`:

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

Restart your AI tool and ask: *"What namespace does SceneManager belong to?"*

## Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `search_unity_api` | Find APIs by keyword | "Tilemap SetTile", "async load scene" |
| `get_method_signature` | Exact signatures with all overloads | `UnityEngine.Physics.Raycast` |
| `get_namespace` | Resolve `using` directives | "SceneManager" → `using UnityEngine.SceneManagement;` |
| `get_class_reference` | Full class reference card | "InputAction" → 31 methods/fields/properties |
| `get_deprecation_warnings` | Check if an API is obsolete | "WWW" → Use UnityWebRequest instead |

**Coverage:** All UnityEngine/UnityEditor modules, Input System, Addressables, UI/TextMeshPro, AI Navigation, Netcode.

## Benchmarks

Measured on the pre-built database (42,223 records). All queries run locally via SQLite FTS5. Token estimates use ~3.5 chars/token. File sizes verified against Unity 6 (6000.0.63f1).

| Question | MCP | Without MCP | Savings |
|----------|-----|-------------|---------|
| "What namespace does Tilemap need?" | `get_namespace` — **~30 tokens**, 1 call | Grep + Read XML — ~500-2,000 tokens, 2-3 calls | 15-65x |
| "Params for Tilemap.SetTile?" | `get_method_signature` — **~900 tokens**, 1 call | Read `TilemapModule.xml` (68KB) — ~19,500 tokens, 2-3 calls | ~20x |
| "Everything on InputAction?" | `get_class_reference` — **~830 tokens**, 1 call | Read `InputAction.cs` (129KB) — ~36,800 tokens, 2-5 calls | ~44x |
| "Is WWW deprecated?" | `get_deprecation_warnings` — **~590 tokens**, 1 call | Grep XML + read matches — ~2,000-5,000 tokens, 2-3 calls | 3-8x |

Every MCP call completes in <15ms (local SQLite), returns structured data, and works offline.

<details>
<summary>Disclaimer</summary>

"Without MCP" token counts assume the AI reads the full source file to find the answer. In practice, a targeted grep or partial file read can be much cheaper — and if the AI already knows the answer from training data, the cost is 0 tokens. MCP doesn't always win on token count. What it guarantees is a correct, structured answer in 1 call every time — no multi-step searching, no parsing raw files, no risk of outdated or hallucinated results. MCP token counts are measured from real tool responses. All estimates use ~3.5 chars/token and may vary ~20% depending on the tokenizer.

</details>

<details>
<summary>Accuracy</summary>

| Test | Result |
|------|--------|
| Search top-1 relevance (10 common queries) | 80% |
| Namespace resolution (6 key classes) | 100% |
| Key class coverage (17 common Unity classes) | 94% (16/17) |

**Search top-1 misses** (correct result present, but not ranked #1):
- "Physics Raycast" → returns `Physics.DefaultRaycastLayers` first (field ranked above method)
- "Instantiate" → returns `ResourceManagement.InstantiationParameters.Instantiate` first (Addressables member ranked above `Object.Instantiate`)

Both are ranking issues — the correct API is still in the results, just not top-1.

</details>

## Setup Details

<details>
<summary>Claude Code configuration</summary>

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

If the command isn't on PATH, use the full path:
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

</details>

<details>
<summary>Cursor / Windsurf</summary>

Add the same config to your MCP settings file. The server uses stdio transport (default).

</details>

<details>
<summary>CLAUDE.md snippet (recommended)</summary>

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

</details>

<details>
<summary>AI-Assisted Setup</summary>

If an AI agent (Claude Code, etc.) is setting this up for you, give it these instructions:

> Read the README at `<path>/unity-api-mcp/README.md` and set up the MCP server for my Unity project at `<project-path>`.

The agent should:
1. **Install** — `pip install unity-api-mcp`
2. **Find the executable** — run `which unity-api-mcp` (macOS/Linux) or `where unity-api-mcp` (Windows) to get the full path
3. **Write MCP config** — add to `~/.claude/mcp.json` with `"command": "<full-path-to-unity-api-mcp>"`
4. **Add CLAUDE.md instructions** — append the "Unity API Lookup" snippet above to the project's `CLAUDE.md`
5. **Verify** — reconnect MCP (`/mcp` in Claude Code) and test: `get_namespace("SceneManager")` should return `using UnityEngine.SceneManagement;`

</details>

<details>
<summary>Project structure</summary>

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
│       └── unity_docs.db  # Pre-built SQLite database (42K records, ships with package)
└── pyproject.toml
```

</details>

<details>
<summary>Troubleshooting</summary>

**"No results found" for a query**
- The pre-built database should be included in the package. If missing, reinstall: `pip install --force-reinstall unity-api-mcp`

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
