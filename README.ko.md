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

`zai-deep-research` 는 z.ai Coding Plan 구독자를 위해 만든 Agent Skills 호환 딥 리서치 스킬입니다. 네 개의 z.ai MCP 서버를 중심으로 설계되어 있으며, 요청 정리, 근거 수집, 반복 요약, 최종 보고서 작성까지 단계적으로 수행합니다.

반대로 말씀드리면, z.ai Coding Plan 과 해당 MCP 서비스에 접근할 수 없는 사용자에게는 이 저장소가 실질적으로 쓸모가 없습니다. 이 스킬의 핵심 기능은 z.ai 의 검색, 읽기, 비전, 저장소 분석 MCP 에 의존하기 때문에, 그 접근 권한이 없으면 의도한 워크플로우가 성립하지 않습니다.

## 동작 원리

이 스킬은 `agents/` 아래의 네 개 프롬프트 템플릿을 조합해서 동작합니다.

- `planner` 는 요청을 정리하고, 추가 질문이 필요한지 판단하며, 어떤 MCP 가 필요한지 고릅니다.
- `researcher` 는 설정된 z.ai MCP 서버를 통해 근거를 수집합니다.
- `summarizer` 는 각 조사 라운드를 요약하고 다음 질의를 제안합니다.
- `synthesizer` 는 최종 마크다운 보고서를 작성합니다.

실행 로직은 `zai-deep-research/scripts/run.py` 에 있고, 런타임 설정은 `config.json` 이 있으면 이를 우선 사용합니다. 기본적으로 지속 데이터는 현재 작업 디렉터리 아래 `./.zai-deep-research` 에 저장되며, 최종 보고서는 `--output-dir` 를 지정하지 않으면 `./research/` 에 생성됩니다.

## 설치 전 유의사항

먼저 사용하는 에이전트에 z.ai MCP 네 개를 등록해 두셔야 합니다. 이름은 반드시 아래와 정확히 일치해야 합니다.

| 필수 이름 | z.ai 서비스 |
| --- | --- |
| `vision-zai` | Vision MCP Server |
| `web-search-zai` | Web Search MCP Server |
| `web-reader-zai` | Web Content Reading |
| `zread` | Zread MCP Server |

에이전트마다 MCP 설정 파일 형식은 다를 수 있습니다. 이 스킬에서 중요한 것은 설정 문법 자체가 아니라 서버 이름이 정확히 맞는지입니다. 포함된 검증 명령은 현재 로컬 에이전트 런타임에 이 네 이름이 실제로 잡혀 있는지 확인해 줍니다.

## 설치 방법

### 설치 스크립트

이 저장소에는 `zai-deep-research/scripts/install.sh` 가 포함되어 있습니다. 설치 스크립트는 다음 시나리오를 지원합니다.

- `~/.agents/skills` 에 전역 공유 설치
- `~/.<client>/skills` 에 클라이언트별 전역 설치
- `./.agents/skills` 또는 `./.<client>/skills` 에 현재 프로젝트 로컬 설치

`curl | sh` 형식으로 설치하려면 아래와 같이 실행하시면 됩니다.

```bash
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client agents --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client codex --scope user
curl -fsSL https://raw.githubusercontent.com/studiojin-dev/zai-deep-research-skill/main/zai-deep-research/scripts/install.sh | sh -s -- --client agents --scope project
```

이미 저장소를 clone 해 두셨다면 현재 체크아웃에서 바로 설치하실 수 있습니다.

```bash
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client agents --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client codex --scope user
sh zai-deep-research/scripts/install.sh --source-dir ./zai-deep-research --client agents --scope project
```

설치 스크립트 동작 방식은 다음과 같습니다.

- `--client agents` 는 범용 `.agents/skills` 규약 경로에 설치합니다.
- `--client codex` 는 Codex 전용 skills 경로에 설치합니다.
- 그 외 클라이언트 이름은 `~/.<client>/skills` 또는 `./.<client>/skills` 로 설치합니다.
- `--scope user` 는 사용자 전역 설치입니다.
- `--scope project` 는 현재 디렉터리 기준 로컬 설치입니다.

## 설치 후

### 먼저 검증

처음 사용하시기 전에 아래 명령으로 검증해 주시는 편이 좋습니다.

```bash
python zai-deep-research/scripts/run.py --validate
```

이 검증은 다음 항목을 확인합니다.

- 스킬 이름과 디렉터리 연결 상태
- `agents/*.md` 템플릿이 런타임에서 실제로 로드되는지
- 각 에이전트 템플릿에 네 개 MCP 이름이 모두 들어 있는지
- 로컬 에이전트 런타임에 해당 MCP 서버들이 실제로 존재하는지

### 설정 방법

필요하면 예제 설정 파일을 복사해서 경로를 조정해 주세요.

```bash
cp zai-deep-research/assets/config.example.json zai-deep-research/config.json
```

저장소 관련 설정은 다음을 제어합니다.

- `memory_db_path`: 반복 요약, 보고서, 아티팩트를 저장하는 SQLite 데이터베이스
- `vector_index_path`: 의미 검색용 FAISS 인덱스 파일
- `vector_metadata_path`: FAISS 벡터와 함께 저장되는 JSONL 메타데이터
- `data_dir`: 런타임 상태를 위한 기본 디렉터리

상대 storage 경로는 현재 작업 디렉터리 기준으로 해석됩니다. 예를 들어 `~/realrepo` 에서 실행하면 기본 storage root 는 `~/realrepo/.zai-deep-research` 가 됩니다.

### 사용법

```bash
python zai-deep-research/scripts/run.py "Compare the latest open-source browser automation MCP servers"
python zai-deep-research/scripts/run.py "Assess the risks of vendor lock-in for model gateways" --output-dir ./research
python zai-deep-research/scripts/run.py "Analyze pricing changes" --config ./zai-deep-research/config.json
```

## 데이터 저장소 설명

기본적으로 런타임 데이터는 현재 작업 디렉터리 아래 `./.zai-deep-research` 에 저장됩니다.

예를 들어 `~/realrepo` 에서 실행하면 기본 경로는 다음과 같습니다.

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
├── references/
└── scripts/
```

이 구조는 Agent Skills specification 에 맞춰 정리되어 있습니다. 실행 파일은 `scripts/`, 참고 문서는 `references/`, 재사용 자원은 `assets/` 에 두는 방식입니다.
