# Client Notes

Read this file only when you are installing the skill or debugging a specific client backend.

## Shared install path
- Prefer the shared Agent Skills path:
  - workspace: `./.agents/skills`
  - user: `~/.agents/skills`
- This is the canonical path for this repository because it is portable across clients.

## Launcher backends
- `codex`
  - Prompt execution: `codex exec --skip-git-repo-check -`
  - MCP validation: `codex mcp list`
- `claude`
  - Prompt execution: `claude -p "<prompt>" --permission-mode bypassPermissions --add-dir <cwd>`
  - MCP validation: `claude mcp list`
- `opencode`
  - Prompt execution: `opencode run --dir <cwd> "<prompt>"`
  - MCP validation: `opencode mcp list`
- `gemini`
  - Prompt execution: `gemini -p "<prompt>" --output-format json`
  - MCP validation: `gemini mcp list`

## Notes
- The launcher keeps the same research contract across clients, but backend behavior may differ because each product has different non-interactive interfaces, trust models, and output formats.
- `claude` automation requires a non-interactive permission mode because the launcher cannot answer approval prompts.
- `gemini mcp list` may show `stdio` servers as disconnected in an untrusted folder even when they are configured.
- If `auto` backend selection is ambiguous, rerun with `--client codex|claude|opencode|gemini`.
