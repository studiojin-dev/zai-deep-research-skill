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

## Available scripts
- `scripts/run.py` — validates MCP wiring, runs the multi-stage research workflow, and optionally emits machine-readable JSON.
- `scripts/install.sh` — installs the skill into the shared Agent Skills path or the documented Gemini layout. Use `--dry-run` to preview the install plan first.
- `scripts/eval.py` — snapshots the current skill, runs the committed eval suite against `with_skill` and `old_skill`, and generates grading plus benchmark artifacts.

## Installation note
- The installer can now prompt target-by-target for `.agents`, `codex`, `opencode`, `gemini`, and `claude`.
- `.agents` means the shared Agent Skills path, not a separate AI coding product.
- Shared installs live under `~/.agents/skills/zai-deep-research` or `./.agents/skills/zai-deep-research`.
- Native client installs use `~/.codex/skills`, `~/.config/opencode/skills`, `~/.gemini/skills`, and `~/.claude/skills`.
- Repository-relative examples like `python scripts/run.py ...` assume your current directory is the skill root. If you installed the skill elsewhere, run the same commands from the installed skill directory or with absolute paths.

## Default workflow
1. Validate the selected client and MCP wiring:

```bash
python scripts/run.py --validate --client codex
python scripts/run.py --validate --client codex --json
```

2. Run research with an explicit client when auto-detection is unclear:

```bash
python scripts/run.py "your research query" --client claude
python scripts/run.py "your research query" --client opencode --max-iterations 7
python scripts/run.py "your research query" --client gemini --output-dir ./research
python scripts/run.py "your research query" --client codex --json
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
- `--json` is opt-in and keeps the default text output backward compatible.
- Validation now shows the detected MCP names, so a false negative from `codex mcp list` parsing is easier to spot and debug.
- Clarification-required runs exit with code `2`.

## Gotchas
- This is a generic Agent Skills package, but it is not generic infrastructure-free research. Without z.ai Coding Plan access and the four z.ai MCP servers, it cannot deliver its intended workflow.
- MCP server names must match exactly unless you override them in `config.json`.
- `scripts/run.py` is a convenience launcher, not a requirement of the skill format. Clients may differ internally, but the expected output contract stays the same: validated prerequisites, iterative evidence gathering, and a final Markdown report.
- On `codex`, launcher sub-runs force `reasoning_effort="medium"` so this skill does not inherit an unexpectedly slow global setting.
- On `codex`, a preflight probe can temporarily disable broken remote MCP transports for the current run. JSON output exposes this as `configured_mcp_names`, `active_mcp_names`, and `disabled_mcp_names`.
- Runtime JSON also includes `step_events`, `run_summary`, and `final_decision` so wrappers can distinguish normal completion, skipped steps, and aborted runs.
- Vector memory is optional. If FAISS dependencies are unavailable, the launcher still runs without semantic recall.
- The skill supports both live web research and repository-backed investigation. Use the web-centric eval suite to watch for regressions in source hygiene, caveats, and freshness handling.

## References
- Read [references/CONFIG.md](references/CONFIG.md) when you need to change runtime storage, MCP names, or the default client backend.
- Read [references/CLIENTS.md](references/CLIENTS.md) when you need client-specific launcher, installation, or troubleshooting details.
- Read [references/EVALS.md](references/EVALS.md) when you need to run benchmarks, compare against an `old_skill` snapshot, or review eval artifacts.
