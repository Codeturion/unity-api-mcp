# Benchmark harness

Reproducible benchmark behind the README's accuracy numbers.

- Project questions (11): asked against a private Unity 6 game project, so that question set and its raw results are not published; their aggregate scores are in the README table and chart. Point `run.py` at your own project with your own questions to reproduce that scenario
- `questions-api.json`: 8 pure Unity API lookups (overloads, signatures, deprecations), ground truth from the docs database
- `questions-bigfile.json`: 6 questions answered inside 2,700 to 4,600 line files of the Input System package source
- `run.py`: runs each question through 3 agent configs (MCP + Grep/Read, Grep/Read, Read only) via headless `claude -p` sessions, collects real token usage, and judges every answer against ground truth with a separate model session
- `results*.json`: raw outputs of the July 2026 runs
- `gen_charts.py`: renders the README charts (light + dark) from the results

Re-run:

```bash
python run.py --project /path/to/UnityProject                       # project questions
python run.py --project /path/to/UnityProject --questions questions-api.json --out results-api.json
python run.py --project "<PackageCache>/com.unity.inputsystem@..." --questions questions-bigfile.json --out results-bigfile.json
python gen_charts.py
```

Requires an authenticated `claude` CLI and `uvx`. Each full sweep is roughly 30 to 60 short sessions. Agent behavior changes as models improve, so re-run before quoting numbers.
