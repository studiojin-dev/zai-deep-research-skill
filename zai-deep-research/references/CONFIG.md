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
    "memory_db_path": "./.zai-deep-research/memory.sqlite"
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
- `memory_db_path` may be absolute or relative.
- Relative `storage.data_dir` values resolve from the current working directory.
- Relative storage file paths resolve from `storage.data_dir`.
- SQLite FTS5 must be available in the active Python runtime because lexical memory uses the same database file for indexing and retrieval.
- `mcp_servers` lets you rename the four MCP endpoints without editing Python code.

## Compatibility Notes

- `storage.vector_index_path` and `storage.vector_metadata_path` are still accepted during the compatibility grace period, but they are ignored.
- When those legacy keys are present, validation emits a warning so wrappers can migrate safely.
- Validation JSON now exposes both `lexical_memory_available` and the deprecated alias `vector_memory_available`.
- The deprecated alias and ignored vector config keys are scheduled for removal in the next major release.
