# Config Reference

Read this file only when you need to override the default client backend, storage paths, or MCP server names.

`zai-deep-research` loads `config.json` from the current working directory first, then the skill root, or from the path passed with `--config`.

## Schema

```json
{
  "skill_name": "zai-deep-research",
  "runtime": {
    "client": "auto"
  },
  "storage": {
    "data_dir": "./.zai-deep-research",
    "memory_db_path": "./.zai-deep-research/memory.sqlite",
    "vector_index_path": "./.zai-deep-research/vector.index",
    "vector_metadata_path": "./.zai-deep-research/vector.jsonl"
  },
  "mcp_servers": {
    "search": "web-search-zai",
    "reader": "web-reader-zai",
    "vision": "vision-zai",
    "repository": "zread"
  }
}
```

## Behavior
- `skill_name` must remain `zai-deep-research` so it matches the directory name and Agent Skills naming rules.
- `runtime.client` may be `auto`, `codex`, `claude`, `opencode`, or `gemini`.
- Backend auto-detection order is:
  1. explicit `--client`
  2. `runtime.client`
  3. parent process name match
  4. installed backend probe
- If auto-detection finds multiple installed clients and cannot disambiguate the current runtime, `scripts/run.py` fails and asks for `--client`.
- The default storage root is `./.zai-deep-research` under the current working directory.
- `storage.data_dir` is the base directory for runtime state.
- `memory_db_path`, `vector_index_path`, and `vector_metadata_path` may be absolute or relative.
- Relative `storage.data_dir` values resolve from the current working directory.
- Relative storage file paths resolve from `storage.data_dir`.
- `mcp_servers` lets you rename the four MCP endpoints without editing Python code.
