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

한국어 문서입니다. 영문 문서는 [README.md](./README.md)를 참고해 주세요.

## 설명

`zai-deep-research` 는 다음 전제를 갖는 범용 Agent Skills 호환 딥 리서치 스킬입니다.

- z.ai Coding Plan 접근 권한
- 설정된 z.ai MCP 서버 4개
  - `web-search-zai`
  - `web-reader-zai`
  - `vision-zai`
  - `zread`

스킬 자체는 특정 코딩 에이전트 하나에 묶여 있지 않습니다. 다만 번들된 Python 런처는 현재 `codex`, `claude`, `opencode`, `gemini` backend 를 지원합니다.

반대로 말씀드리면, z.ai Coding Plan 과 위 MCP 4개가 없으면 이 저장소는 실질적으로 쓸 수 없습니다.

## 지원 매트릭스

| Client | Skill package | `scripts/run.py` 런처 | 비고 |
| --- | --- | --- | --- |
| `codex` | 지원 | 지원 | 지원 backend 중 하나일 뿐입니다 |
| `claude` | 지원 | 지원 | non-interactive print mode 사용 |
| `opencode` | 지원 | 지원 | `opencode run` 사용 |
| `gemini` | 지원 | 지원 | headless prompt mode 사용 |

클라이언트마다 non-interactive 실행 방식과 MCP 인터페이스가 달라 세부 동작은 조금씩 다를 수 있습니다. 다만 외부 계약은 같습니다. 먼저 전제를 검증하고, 근거를 반복적으로 수집한 뒤, 최종 마크다운 보고서를 만듭니다.

## 동작 원리

이 스킬은 `agents/` 아래의 네 개 프롬프트 템플릿을 조합해서 동작합니다.

- `planner` 는 요청을 정리하고, 추가 질문이 필요한지 판단하며, 어떤 MCP 가 필요한지 고릅니다.
- `researcher` 는 설정된 z.ai MCP 서버를 통해 근거를 수집합니다.
- `summarizer` 는 각 조사 라운드를 요약하고 다음 질의를 제안합니다.
- `synthesizer` 는 최종 마크다운 보고서를 작성합니다.

선택적 런처인 `zai-deep-research/scripts/run.py` 는 다음을 담당합니다.

- backend 자동 감지 또는 명시 선택
- 선택한 클라이언트에 필요한 MCP 이름 4개가 잡혀 있는지 검증
- 네 단계 프롬프트를 반복 실행
- 기본적으로 `./.zai-deep-research` 에 런타임 상태 저장
- 기본적으로 `./research/` 에 최종 보고서 저장

## 설치 전 유의사항

먼저 사용하는 클라이언트에 z.ai MCP 네 개를 등록해 두셔야 합니다. 이름은 `config.json` 으로 바꾸지 않는 한 아래와 정확히 일치해야 합니다.

| 필수 이름 | z.ai 서비스 |
| --- | --- |
| `vision-zai` | Vision MCP Server |
| `web-search-zai` | Web Search MCP Server |
| `web-reader-zai` | Web Content Reading |
| `zread` | Zread MCP Server |

클라이언트마다 MCP 설정 형식은 다르지만, 이 스킬에서 중요한 것은 서버 이름과 런타임에서 MCP 도구를 실제로 노출할 수 있는지입니다.

## 설치 방법

### 권장 공유 설치 경로

이 저장소는 공유 Agent Skills 경로를 기본 설치 대상으로 권장합니다.

- 사용자 전역: `~/.agents/skills`
- 워크스페이스: `./.agents/skills`

이미 저장소를 clone 해 두셨다면:

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope project
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope project --dry-run
```

`curl | sh` 흐름을 원하시면:

```bash
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --scope project
```

실제 복사 전에 source 와 destination 을 먼저 확인하고 싶으면 `--dry-run` 을 사용해 주세요.

### 선택적 native layout

설치 스크립트는 문서로 명시된 native layout 만 관리합니다. 현재는 다음만 제공합니다.

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --scope user --layout gemini
```

그 외 native 위치가 필요하면 해당 클라이언트 문서에 맞춰 수동 설치해 주세요.

## 설치 후

### 먼저 클라이언트 검증

처음 사용하시기 전에 반드시 검증해 주세요.

```bash
python zai-deep-research/scripts/run.py --validate --client codex
python zai-deep-research/scripts/run.py --validate --client claude
python zai-deep-research/scripts/run.py --validate --client opencode
python zai-deep-research/scripts/run.py --validate --client gemini
python zai-deep-research/scripts/run.py --validate --client codex --json
```

지원 CLI 가 여러 개 설치되어 있어 `--client auto` 가 모호하면, 반드시 `--client` 를 명시해서 다시 실행해 주세요.

`codex mcp list` 는 local command 표와 remote URL 표를 같이 출력할 수 있습니다. 런처는 이제 두 형식을 모두 올바르게 파싱하고, 텍스트 모드에서 감지한 MCP 이름을 같이 보여 줍니다.

### 저장 경로나 기본 backend 설정

저장 경로, MCP 이름, 기본 backend 를 바꾸려면 예제 config 를 복사해서 수정해 주세요.

```bash
cp zai-deep-research/assets/config.example.json zai-deep-research/config.json
```

중요 필드:

- `runtime.client`: 기본 런처 backend (`auto`, `codex`, `claude`, `opencode`, `gemini`)
- `memory_db_path`: 반복 요약, 보고서, 아티팩트를 저장하는 SQLite 데이터베이스
- `vector_index_path`: 의미 검색용 FAISS 인덱스 파일
- `vector_metadata_path`: FAISS 벡터와 함께 저장되는 JSONL 메타데이터
- `data_dir`: 런타임 상태를 위한 기본 디렉터리

상대 storage 경로는 현재 작업 디렉터리 기준으로 해석됩니다.

### 런처 사용법

```bash
python zai-deep-research/scripts/run.py "Compare the latest open-source browser automation MCP servers" --client codex
python zai-deep-research/scripts/run.py "Assess the risks of vendor lock-in for model gateways" --client claude --output-dir ./research
python zai-deep-research/scripts/run.py "Analyze pricing changes" --client opencode --config ./zai-deep-research/config.json
python zai-deep-research/scripts/run.py "Review the latest changes in model gateway pricing" --client gemini --max-iterations 3
python zai-deep-research/scripts/run.py "Compare the latest open-source browser automation MCP servers" --client codex --json
```

### 기계 판독용 출력

자동화나 eval harness 에서는 `--json` 을 사용해 주세요. 기본 텍스트 출력은 그대로 유지되고, JSON 모드는 opt-in 입니다.

- `--validate --json` 은 validation 상태, 감지한 MCP 이름, 누락 MCP, vector memory 가능 여부, duration 을 반환합니다.
- 일반 `--json` 실행은 status, client, session id, report path, iteration count, clarification questions, duration, best-effort token usage 를 반환합니다.

vector memory 의존성이 없으면 validation 은 hard failure 대신 optional capability 상태로 보고합니다.

## 로컬 eval 워크플로

저장소에는 codex 기준, 웹 중심 eval 세트가 `zai-deep-research/evals/evals.json` 에 포함되어 있습니다.

1. 변경 전 현재 skill 을 snapshot 합니다.

```bash
python zai-deep-research/scripts/eval.py snapshot --dest ./.zai-deep-research-evals/skill-snapshot
```

2. 현재 skill 과 `old_skill` snapshot 을 비교 실행합니다.

```bash
python zai-deep-research/scripts/eval.py run --client codex --baseline-skill ./.zai-deep-research-evals/skill-snapshot
```

아티팩트는 `./.zai-deep-research-evals/iteration-N/` 아래에 생성됩니다. 각 eval 에는 `outputs/`, `result.json`, `timing.json`, `grading.json` 이 생기고, 최상위에는 `benchmark.json`, `feedback.json` 이 생성됩니다.

자세한 절차와 benchmark 해석 기준은 [zai-deep-research/references/EVALS.md](./zai-deep-research/references/EVALS.md)를 참고해 주세요.

## 선택적 vector memory 설정

Vector memory 는 선택 사항이며, semantic recall 이 없어도 런처는 동작합니다.

활성화하고 싶다면 로컬 환경에 아래 pinned 버전을 설치해 주세요.

```bash
python3 -m pip install "faiss-cpu==1.9.0.post1" "numpy==1.26.4" "sentence-transformers==3.4.1"
```

설치 후에는 다음으로 다시 확인할 수 있습니다.

```bash
python zai-deep-research/scripts/run.py --validate --client codex
```

## 데이터 저장소 설명

기본적으로 런타임 데이터는 현재 작업 디렉터리 아래 `./.zai-deep-research` 에 저장됩니다.

예를 들어 `~/realrepo` 에서 런처를 실행하면 기본 경로는 다음과 같습니다.

- `~/realrepo/.zai-deep-research/memory.sqlite`
- `~/realrepo/.zai-deep-research/vector.index`
- `~/realrepo/.zai-deep-research/vector.jsonl`

최종 마크다운 보고서는 기본적으로 현재 작업 디렉터리의 `./research/` 에 생성됩니다. 다른 위치를 쓰고 싶으시면 `--output-dir` 를 사용하시면 됩니다.

## 저장소 구조

```text
zai-deep-research/
├── SKILL.md
├── agents/
├── assets/
├── evals/
├── references/
└── scripts/
```

- `SKILL.md`: 이식 가능한 스킬 계약
- `agents/`: 네 단계 리서치 프롬프트 템플릿
- `evals/`: `scripts/eval.py` 가 사용하는 커밋된 eval 정의
- `references/CONFIG.md`: config 와 backend 선택 설명
- `references/EVALS.md`: benchmark 절차, workspace 구조, human review 가이드
- `references/CLIENTS.md`: 클라이언트별 런처와 문제 해결 메모
- `scripts/`: 런처, 설치 스크립트, eval harness, 런타임 보조 코드
