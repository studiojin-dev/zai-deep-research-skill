---
name: zai-deep-research
description: Codex-native iterative deep research that coordinates planner, researcher, summarizer, and synthesizer agents with MCP-backed web, reader, vision, and repository evidence collection. Use when a task needs multi-step research, source verification, and a synthesized markdown report.
compatibility: Requires Codex CLI plus configured MCP servers for web-search-zai, web-reader-zai, vision-zai, and zread.
metadata:
  author: zai
  config-example: assets/config.example.json
---

# ZAI Deep Research

This skill runs iterative deep research inside a coding agent while keeping the skill layout aligned with the Agent Skills specification.

## Runtime rules
- Model execution must happen through Codex CLI.
- The planner finalizes the quality goal before research begins.
- The researcher gathers evidence.
- The summarizer produces the iteration summary and next queries.
- The synthesizer writes the final markdown report.
- Total refinement iterations must not exceed 7.

## MCP servers available to this skill
### `web-search-zai`
Use for broad discovery, fresh facts, current events, prices, schedules, news, weather, and finding candidate URLs.

### `web-reader-zai`
Use after search results are selected. Read full page content, metadata, and links from promising URLs before making claims.

### `vision-zai`
Use when the task involves local images, screenshots, charts, diagrams, PDFs rendered to images, or videos.

### `zread`
Use when the research requires understanding an open source repository, GitHub documentation, directory structure, or code files.

## Directory layout
- `scripts/run.py`: executable orchestration entry point
- `scripts/config.py`: config loading and default path resolution
- `scripts/memory.py`: sqlite-backed storage for iteration summaries and final reports
- `scripts/vector_store.py`: optional FAISS-backed semantic indexing and retrieval helper
- `agents/planner.md`: planning prompt template
- `agents/researcher.md`: evidence-collection prompt template
- `agents/summarizer.md`: iteration summarization prompt template
- `agents/synthesizer.md`: final report prompt template
- `references/CONFIG.md`: config schema and behavior
- `assets/config.example.json`: example config file

## Config
The skill looks for `config.json` in the current working directory first, then the skill root, or you can pass `--config`.

See [the config reference](references/CONFIG.md) for details.

## Usage
Run validation:

```bash
python scripts/run.py --validate
```

Run research:

```bash
python scripts/run.py "your research query"
python scripts/run.py "your research query" --max-iterations 7
python scripts/run.py "your research query" --output-dir ./research
python scripts/run.py "your research query" --config ./config.json
```

## Notes
- Scripts live under `scripts/` per the Agent Skills specification.
- Agent prompt templates live under `agents/` and are loaded at runtime by `scripts/run.py`.
- Storage paths are configurable through `config.json`; they are no longer hardcoded to `.codex`.
- By default, runtime storage lives under `./.zai-deep-research` and final reports are written to `./research/` in the current working directory.
- If FAISS dependencies are unavailable, vector memory degrades gracefully instead of failing the whole run.
