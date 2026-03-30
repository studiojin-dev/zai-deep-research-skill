# Eval Workflow

Read this file when you need to benchmark `zai-deep-research`, compare the current skill against an older snapshot, or review output quality regressions.

## Baseline model

- The default benchmark backend is `codex`.
- The default comparison target is an `old_skill` snapshot, not a no-skill baseline.
- Initial eval cases are web-centric on purpose. They prioritize source hygiene, structure, and explicit uncertainty handling. Human review is still required for factual accuracy.

## Definitions

- `evals/evals.json` is the authored source of truth.
- `assertions` are human-readable expectations.
- `checks` are machine-checkable grading rules used by `scripts/eval.py`.

Supported `checks.type` values:

- `status_equals`
- `markdown_h1`
- `has_section`
- `contains_regex`
- `min_source_links`
- `min_absolute_dates`

## Snapshot the baseline

Create an `old_skill` snapshot before editing the skill:

```bash
python scripts/eval.py snapshot --dest ./.zai-deep-research-evals/skill-snapshot
```

The snapshot command copies the current skill directory only and excludes generated files such as `__pycache__`, `.DS_Store`, and `config.json`.

## Run a full iteration

```bash
python scripts/eval.py run --client codex --baseline-skill ./.zai-deep-research-evals/skill-snapshot
```

By default, artifacts are written under:

```text
./.zai-deep-research-evals/iteration-N/
├── <eval-id>/
│   ├── with_skill/
│   │   ├── outputs/
│   │   ├── result.json
│   │   ├── timing.json
│   │   └── grading.json
│   └── old_skill/
│       ├── outputs/
│       ├── result.json
│       ├── timing.json
│       └── grading.json
├── benchmark.json
└── feedback.json
```

## Timing and token policy

- `timing.json` always records `duration_ms`.
- `total_tokens` is best-effort and may be `null` when the backend does not expose stable usage metadata.
- `benchmark.json` keeps token statistics as `null` when token counts are unavailable.

## Human review

`feedback.json` is intentionally created as an empty stub map:

```json
{
  "latest-api-pricing-comparison": "",
  "latest-mcp-server-landscape": "",
  "conflicting-guidance-brief": ""
}
```

Use it to record review comments that automation cannot catch. Focus on:

- whether the cited sources actually support the claims
- whether the brief overstates certainty
- whether the comparisons are useful rather than merely formatted
- whether the newest information is called out with explicit dates

## Benchmark interpretation

- A higher pass rate with modest extra runtime is a good trade.
- If `with_skill` and `old_skill` both pass all checks, use `feedback.json` to decide whether the newer skill is meaningfully better.
- If time increases sharply without a pass-rate gain, tighten prompts or remove wasted work.
