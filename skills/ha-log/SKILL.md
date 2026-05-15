---
name: ha-log
description: |
  HarnessAI v0.10.0 - 작업 일지 (worklog.md) 에 수동 append.
  사용자가 논의/결정/다음 단계를 박을 때. AI 자동 append 는 ha-design/ha-build/ha-redesign 이 처리.
  Use when: "이거 일지에 박아줘", "/ha-log <내용>", "오늘 결정한 거 기록"
allowed-tools:
  - Bash
  - Read
---

## 역할

`backend/docs/worklog.md` 에 사용자 입력을 *논의 / 합의 / 다음* 카테고리 중 하나로 append.

**입력**: 사용자가 박은 텍스트 (한 줄~여러 줄)
**출력**: worklog.md 의 오늘 날짜 섹션에 append

## 실행

```bash
python ~/.claude/skills/ha-log/run.py append \
  --category "<discussion | change | next>" \
  --message "<텍스트>"
```

`--category` 기본: `discussion` (논의 / 합의).

run.py 가:
- `backend/docs/worklog.md` 찾음 (없으면 생성)
- 오늘 (UTC) 날짜 섹션 없으면 생성 (`## YYYY-MM-DD`)
- `### 논의 / 합의` (discussion) / `### 변경` (change) / `### 다음` (next) sub-section 에 bullet 으로 박음
- 항상 *최신이 위* - 새 날짜는 파일 *최상단* (Title 직후) 삽입

## 가드레일

- *append-only* - 기존 항목 수정 X (사용자 직접 편집은 OK, git history 로 추적)
- worklog.md 없으면 자동 생성 (Title + 가이드 헤더)
