[![GitHub](https://img.shields.io/badge/GitHub-studiojin--dev%2Fzai--deep--research--skill-181717?logo=github&logoColor=white)](https://github.com/studiojin-dev/zai-deep-research-skill)
[![GitHub stars](https://img.shields.io/github/stars/studiojin-dev/zai-deep-research-skill?style=flat&logo=github)](https://github.com/studiojin-dev/zai-deep-research-skill/stargazers)
[![GitHub license](https://img.shields.io/github/license/studiojin-dev/zai-deep-research-skill)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/studiojin-dev/zai-deep-research-skill)](https://github.com/studiojin-dev/zai-deep-research-skill/releases)
[![GitHub last commit](https://img.shields.io/github/last-commit/studiojin-dev/zai-deep-research-skill)](https://github.com/studiojin-dev/zai-deep-research-skill/commits/main)
[![Docs: English](https://img.shields.io/badge/Docs-English-0A7CFF)](./README.md)
[![문서: 한국어](https://img.shields.io/badge/%EB%AC%B8%EC%84%9C-%ED%95%9C%EA%B5%AD%EC%96%B4-00A86B)](./README.ko.md)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-0A7CFF)](https://agentskills.io/specification)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/studiojin-dev/zai-deep-research-skill)
[![MCP](https://img.shields.io/badge/MCP-z.ai%20x4-6C47FF)](https://github.com/studiojin-dev/zai-deep-research-skill)
[![z.ai Coding Plan](https://img.shields.io/badge/z.ai%20Coding%20Plan-required-FF6B35)](https://github.com/studiojin-dev/zai-deep-research-skill)

# zai-deep-research

English documentation. For Korean documentation, please see [README.ko.md](./README.ko.md).

## Overview

`zai-deep-research` is an Agent Skills-compatible research skill built for people who already subscribe to the z.ai Coding Plan. It is designed around four z.ai MCP servers and uses them to perform structured, iterative deep research with planning, evidence collection, summarization, and final synthesis.

For users who do not have access to the z.ai Coding Plan and its MCP services, this repository is effectively not useful in practice. The skill depends on those MCP endpoints for discovery, reading, vision, and repository inspection. Without them, the workflow cannot produce its intended result.

## How It Works

The skill coordinates four prompt templates under `agents/`:

- `planner` refines the request, decides whether clarification is necessary, and selects the MCPs that matter.
- `researcher` gathers evidence through the configured z.ai MCP servers.
- `summarizer` turns each research pass into a concise iteration summary and proposes the next queries.
- `synthesizer` writes the final markdown report.

The execution logic lives in `zai-deep-research/scripts/run.py`. Runtime configuration lives in `config.json` when present, or falls back to sensible defaults. By default, persistent state is stored under `./.zai-deep-research` in the current working directory, while final reports are written to `./research/` unless `--output-dir` is provided.

## Before You Install

Please configure the four z.ai MCP servers in your agent first. The names must match exactly:

| Required name | z.ai service |
| --- | --- |
| `vision-zai` | Vision MCP Server |
| `web-search-zai` | Web Search MCP Server |
| `web-reader-zai` | Web Content Reading |
| `zread` | Zread MCP Server |

Each agent product uses its own MCP configuration format. What matters for this skill is the exact server name, not the surrounding config syntax. The included validation command checks that these four names are available from your local agent runtime.

## Installation

### Installation script

This repository includes `zai-deep-research/scripts/install.sh`. The installer supports:

- global shared installation into `~/.agents/skills`
- global client-specific installation into `~/.<client>/skills`
- local project installation into `./.agents/skills` or `./.<client>/skills`

If you want a `curl | sh` flow, you can run:

```bash
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client agents --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client codex --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client agents --scope project
```

If you already cloned this repository, you can install directly from the current checkout:

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client agents --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client codex --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client agents --scope project
```

Installer behavior:

- `--client agents` installs to the cross-client `.agents/skills` convention.
- `--client codex` installs to the native Codex skills directory.
- any other client name installs to `~/.<client>/skills` or `./.<client>/skills`.
- `--scope user` means a user-level installation.
- `--scope project` means installation into the current directory.

## After Installation

### Validate the skill

Please validate the skill before first use:

```bash
python zai-deep-research/scripts/run.py --validate
```

This command checks:

- the skill name and directory wiring
- that the `agents/*.md` templates are loaded at runtime
- that each agent template includes the four MCP names
- that your local agent runtime exposes the four MCP servers

### Configure storage

Copy the example config and adjust paths when needed:

```bash
cp zai-deep-research/assets/config.example.json zai-deep-research/config.json
```

The storage section controls:

- `memory_db_path`: SQLite database for iteration summaries, reports, and artifacts
- `vector_index_path`: FAISS index file for semantic retrieval
- `vector_metadata_path`: JSONL metadata paired with the FAISS vectors
- `data_dir`: base directory for runtime state

Relative storage paths are resolved from the current working directory. If you run the skill from `~/realrepo`, the default storage root becomes `~/realrepo/.zai-deep-research`.

### Run the skill

```bash
python zai-deep-research/scripts/run.py "Compare the latest open-source browser automation MCP servers"
python zai-deep-research/scripts/run.py "Assess the risks of vendor lock-in for model gateways" --output-dir ./research
python zai-deep-research/scripts/run.py "Analyze pricing changes" --config ./zai-deep-research/config.json
```

## Data Storage

By default, the skill stores runtime data under `./.zai-deep-research` in the current working directory.

For example, if you run Codex from `~/realrepo`, the default storage paths become:

- `~/realrepo/.zai-deep-research/memory.sqlite`
- `~/realrepo/.zai-deep-research/vector.index`
- `~/realrepo/.zai-deep-research/vector.jsonl`

The final markdown report is written to `./research/` in the current working directory by default. If you prefer a different directory, please pass `--output-dir`.

## Repository Structure

```text
zai-deep-research/
├── SKILL.md
├── agents/
├── assets/
├── references/
└── scripts/
```

This layout follows the Agent Skills specification, which expects scripts in `scripts/`, supporting documentation in `references/`, and reusable resources in `assets/`.
