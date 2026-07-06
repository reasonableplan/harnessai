---
name: ha-map
description: |
  HarnessAI 보조 (독립 스킬) — skeleton.md 를 읽어 아키텍처 다이어그램(Mermaid)을 생성한다.
  긴 skeleton 을 한눈에 보는 파생 뷰(docs/architecture.md): 컴포넌트 맵 · 요청 흐름 · 인터페이스 맵.
  v2 상태기계에 의존하지 않음 — skeleton.md 만 있으면 어디서나 동작. 필요한 사람만 돌린다.
  Use when: skeleton 이 길어 읽기 부담될 때, "아키텍처 그림 그려줘", "/ha-map"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
---

## 역할

`docs/skeleton.md`(진실의 원천)를 읽어 `docs/architecture.md`(파생 뷰)를 생성한다.
**read-only 파생 뷰** — skeleton 을 대체하지 않고, 긴 문서를 빠르게 훑는 지도를 옆에 둔다.

**입력**: `docs/skeleton.md`
**출력**: `docs/architecture.md` (Mermaid 3종, GitHub 자동 렌더) + (mmdc 있으면) `architecture-{i}.png`
**다음**: 없음 (보조 스킬). skeleton 갱신 시 재실행.

> ⚠️ **파생 뷰 원칙**: architecture.md 는 *항상 skeleton 에서 재생성*된다. 손편집 금지 —
> skeleton ↔ 그림 split-brain 방지. 헤더에 "자동 생성, 손대지 말 것" 명시.

## 실행 순서

### 1. skeleton 위치 확인
```bash
python ~/.claude/skills/ha-map/run.py locate "<PROJECT_ROOT>"
```
JSON: `{found, skeleton_path, docs_dir, mmdc_available}`. `found=false` 면 사용자에게
skeleton.md 경로를 묻거나 `/ha-design` 선행을 안내하고 중단.

### 2. skeleton 정독
`skeleton_path` 를 **끝까지** Read. 다음을 추출:
- **컴포넌트/레이어**: 도메인 로직 섹션의 순수(core) / I/O(adapters) / orchestrator 분리, interface(CLI/HTTP/IPC/SDK), persistence
- **요청 흐름**: orchestrator 의 번호 매겨진 파이프라인 단계
- **인터페이스**: CLI 커맨드 / HTTP 엔드포인트 + exit code / 에러
> skeleton 섹션 번호·이름은 프로젝트마다 다르다 — **번호가 아니라 의미로** 찾을 것.

### 3. architecture.md 작성 (다이어그램 3종)
`docs_dir/architecture.md` 생성. 각 Mermaid 블록 상단에 **아래 락된 테마 블록을 그대로** 박는다.

| 그림 | 내용 | skeleton 출처 |
|------|------|--------------|
| 1. 컴포넌트 맵 | 레이어(interface→orchestrator→core/adapters→external) 의존 | 도메인 로직 순수/impure/orchestrator + interface + persistence |
| 2. 요청 흐름 | 핵심 동작 1~2개의 단계 흐름 | orchestrator 파이프라인 단계 |
| 3. 인터페이스 맵 | 커맨드/엔드포인트 + 옵션 + exit code | interface + 에러 섹션 |

> DB ER 다이어그램은 `/ha-design` 이 data_model 섹션에 이미 생성 — **재생성 X**, 링크만.

### 4. (있으면) PNG 렌더
```bash
python ~/.claude/skills/ha-map/run.py render "<docs_dir>/architecture.md"
```
`architecture-1.png` … 생성. `mmdc_available=false` 면 .md 만 두고 안내
(`npm i -g @mermaid-js/mermaid-cli`).

### 5. 결과 보고
생성 경로 + 다이어그램 수 + (렌더됐으면) PNG 경로. 본문 전체를 채팅에 재출력하지 말 것.

## 락된 테마 블록 (모든 다이어그램 상단에 복붙)

```
%%{init: {'theme':'base','flowchart':{'htmlLabels':true,'padding':12,'nodeSpacing':55,'rankSpacing':55},'themeVariables':{
  'fontFamily':'Segoe UI, Helvetica, Arial, sans-serif',
  'primaryColor':'#fbfbfc','primaryTextColor':'#1f2329',
  'primaryBorderColor':'#c4c8ce','lineColor':'#8a9099',
  'clusterBkg':'#f6f7f9','clusterBorder':'#dfe3e8','fontSize':'14px'}}}%%
```
> `flowchart.htmlLabels:true` 가 노드 글자 짤림을 막는다 ([verified] — 빼면 마지막 글자 클립). 그대로 둘 것.

그리고 노드 분류용 classDef (다이어그램 끝에):
```
classDef default fill:#fbfbfc,stroke:#c4c8ce,color:#1f2329;
classDef io fill:#f1f3f5,stroke:#aeb4bc,color:#1f2329;
classDef ext fill:#eef1fb,stroke:#4c6ef5,color:#2b3a67,stroke-width:1.5px;
classDef core fill:#fcfcfd,stroke:#ccd1d7,color:#1f2329;
```
external/외부 의존만 `ext`(단일 액센트), I/O 경계는 `io`, 순수 로직은 `core`.
> `classDef default` **필수** — 분류 안 한 노드까지 명시 색을 박아야 **다크 모드 뷰어(Obsidian 등)가
> 노드를 자기 테마로 덮어써 글자가 안 보이는 사고를 막는다** ([verified] — `-t dark` 강제 렌더로 확인).

## 가드레일 (디자인 — anti-AI-slop)

- **이모지 금지** — ✅⚠️ 등 노드/제목에 넣지 말 것.
- **폰트는 락된 블록 그대로** (Segoe UI 1순위 + 폴백). 임의 폰트 지정 금지 —
  렌더 기계에 폰트 없으면 제목이 짤린다 (검증된 결함).
- **무지개 자동색 금지** — 단색조 + 액센트 1색만.
- **범례는 Mermaid 안에 넣지 말 것** — in-diagram 범례 subgraph 는 자동 레이아웃을
  망친다. 범례는 architecture.md 의 **마크다운 표**로.
- **선에 기술 라벨** (`HTTP /v1`, `subprocess` 등), 관련 컴포넌트는 `subgraph` 그룹 (C4 규율).
- **추상화 균형** — 한 그림에 과밀 금지. 컴포넌트가 너무 많으면 흐름도와 분리.

## 안 하는 것 (단순함)

- 인터뷰 X — 전부 skeleton 에서 결정론적 도출.
- 편집 가능 다이어그램(Excalidraw 등) X — read-only 파생 뷰.
- skeleton hash/freeze 결합 X — 상태 추적 안 함, 항상 재생성.
