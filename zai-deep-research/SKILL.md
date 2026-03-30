---
name: zai-deep-research
description: Conduct iterative deep research with z.ai MCP search, reader, vision, and repository tools. Use when a task needs fresh evidence, source verification, cross-source comparison, and a final Markdown brief. Requires z.ai Coding Plan access and the four z.ai MCP servers.
compatibility: Works with Agent Skills-compatible clients that support MCP and non-interactive prompting. The bundled launcher supports codex, claude, opencode, and gemini.
metadata:
  author: zai
  config-example: assets/config.example.json
---

# ZAI Deep Research

Use this skill when the user needs a researched answer grounded in current web pages, repository evidence, or visual material, and the result should be a structured Markdown report instead of a quick chat reply.

## Prerequisites
- z.ai Coding Plan access is required.
- The active client must expose these MCP servers:
  - `web-search-zai`
  - `web-reader-zai`
  - `vision-zai`
  - `zread`
- The optional launcher in `scripts/run.py` currently supports `codex`, `claude`, `opencode`, and `gemini`.

## Default workflow
1. Validate the selected client and MCP wiring:

```bash
python scripts/run.py --validate --client codex
```

2. Run research with an explicit client when auto-detection is unclear:

```bash
python scripts/run.py "your research query" --client claude
python scripts/run.py "your research query" --client opencode --max-iterations 7
python scripts/run.py "your research query" --client gemini --output-dir ./research
```

3. Let the launcher run the four prompt stages in order:
   - `planner`
   - `researcher`
   - `summarizer`
   - `synthesizer`

## Validation
- Always run `--validate` before first use on a new client.
- If `auto` backend detection fails, rerun with `--client codex|claude|opencode|gemini`.
- The launcher writes runtime state under `./.zai-deep-research` and the final report under `./research/` unless you override the paths.

## Gotchas
- This is a generic Agent Skills package, but it is not generic infrastructure-free research. Without z.ai Coding Plan access and the four z.ai MCP servers, it cannot deliver its intended workflow.
- MCP server names must match exactly unless you override them in `config.json`.
- `scripts/run.py` is a convenience launcher, not a requirement of the skill format. Clients may differ internally, but the expected output contract stays the same: validated prerequisites, iterative evidence gathering, and a final Markdown report.
- Vector memory is optional. If FAISS dependencies are unavailable, the launcher still runs without semantic recall.

## References
- Read [references/CONFIG.md](references/CONFIG.md) when you need to change runtime storage, MCP names, or the default client backend.
- Read [references/CLIENTS.md](references/CLIENTS.md) when you need client-specific launcher, installation, or troubleshooting details.
