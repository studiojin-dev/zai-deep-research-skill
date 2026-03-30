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

`zai-deep-research` is a generic Agent Skills-compatible deep research skill whose hard requirements are:

- z.ai Coding Plan access
- four configured z.ai MCP servers:
  - `web-search-zai`
  - `web-reader-zai`
  - `vision-zai`
  - `zread`

The skill itself is not tied to one AI coding product. It is intended to work across Agent Skills-compatible clients, while the bundled Python launcher provides backend adapters for `codex`, `claude`, `opencode`, and `gemini`.

Without z.ai Coding Plan access and those four MCP servers, this repository is not useful in practice.

## Support Matrix

| Client | Skill package | `scripts/run.py` launcher | Notes |
| --- | --- | --- | --- |
| `codex` | Supported | Supported | One supported backend, not the identity of the skill |
| `claude` | Supported | Supported | Launcher uses non-interactive print mode |
| `opencode` | Supported | Supported | Launcher uses `opencode run` |
| `gemini` | Supported | Supported | Launcher uses headless prompt mode |

Runtime behavior can differ slightly by client because each CLI exposes different non-interactive and MCP interfaces. The external contract stays the same: validate prerequisites, gather evidence iteratively, and produce a final Markdown report.

## How It Works

The skill coordinates four prompt templates under `agents/`:

- `planner` refines the request, decides whether clarification is necessary, and selects the MCPs that matter.
- `researcher` gathers evidence through the configured z.ai MCP servers.
- `summarizer` turns each research pass into a concise iteration summary and proposes the next queries.
- `synthesizer` writes the final markdown report.

The optional launcher lives in `zai-deep-research/scripts/run.py`. It:

- auto-detects or accepts an explicit client backend
- validates that the required MCP names are configured in that client
- runs the four stages iteratively
- stores runtime state under `./.zai-deep-research` by default
- writes the final report under `./research/` by default

## Before You Install

Please configure the four z.ai MCP servers in your client first. The names must match exactly unless you override them in `config.json`:

| Required name | z.ai service |
| --- | --- |
| `vision-zai` | Vision MCP Server |
| `web-search-zai` | Web Search MCP Server |
| `web-reader-zai` | Web Content Reading |
| `zread` | Zread MCP Server |

Each client has its own MCP configuration format. What matters for this skill is the server name and the client’s ability to expose MCP tools at runtime.

## Installation

### Canonical shared install

The recommended install target is the shared Agent Skills path:

- user scope: `~/.agents/skills`
- workspace scope: `./.agents/skills`

If you already cloned this repository:

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope project
```

If you want a `curl | sh` flow:

```bash
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --scope project
```

### Optional native layout

The installer only manages native layouts that are explicitly documented. Today that means:

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope user --layout gemini
```

For other native locations, install manually if your client requires them.

## After Installation

### Validate the selected client

Always validate before first use:

```bash
python zai-deep-research/scripts/run.py --validate --client codex
python zai-deep-research/scripts/run.py --validate --client claude
python zai-deep-research/scripts/run.py --validate --client opencode
python zai-deep-research/scripts/run.py --validate --client gemini
```

If `--client auto` is ambiguous because multiple supported CLIs are installed, rerun with an explicit backend.

### Configure storage or default client

Copy the example config if you need to change storage paths, MCP names, or the default launcher backend:

```bash
cp zai-deep-research/assets/config.example.json zai-deep-research/config.json
```

Important config fields:

- `runtime.client`: default launcher backend (`auto`, `codex`, `claude`, `opencode`, `gemini`)
- `memory_db_path`: SQLite database for iteration summaries, reports, and artifacts
- `vector_index_path`: FAISS index file for semantic retrieval
- `vector_metadata_path`: JSONL metadata paired with the FAISS vectors
- `data_dir`: base directory for runtime state

Relative storage paths resolve from the current working directory.

### Run the launcher

```bash
python zai-deep-research/scripts/run.py "Compare the latest open-source browser automation MCP servers" --client codex
python zai-deep-research/scripts/run.py "Assess the risks of vendor lock-in for model gateways" --client claude --output-dir ./research
python zai-deep-research/scripts/run.py "Analyze pricing changes" --client opencode --config ./zai-deep-research/config.json
python zai-deep-research/scripts/run.py "Review the latest changes in model gateway pricing" --client gemini --max-iterations 3
```

## Data Storage

By default, runtime data is stored under `./.zai-deep-research` in the current working directory.

For example, if you run the launcher from `~/realrepo`, the default storage paths become:

- `~/realrepo/.zai-deep-research/memory.sqlite`
- `~/realrepo/.zai-deep-research/vector.index`
- `~/realrepo/.zai-deep-research/vector.jsonl`

The final Markdown report is written to `./research/` in the current working directory by default. If you prefer a different directory, pass `--output-dir`.

## Repository Structure

```text
zai-deep-research/
├── SKILL.md
├── agents/
├── assets/
├── references/
└── scripts/
```

- `SKILL.md`: the portable skill contract
- `agents/`: prompt templates for the four research stages
- `references/CONFIG.md`: config and backend selection details
- `references/CLIENTS.md`: client-specific launcher and troubleshooting notes
- `scripts/`: optional launcher, installer, and runtime helpers
