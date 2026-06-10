---
id: view.screens
name: 화면 목록
required_when: has.ui
description: 경로 → 컨테이너 매핑, 사용자 흐름
---

<!-- placeholder/표기 컨벤션: 같은 디렉토리의 _README.md 참조 -->
<!-- HUMAN-LOCKED:view.screens — 이 섹션은 사용자 인터뷰로만 채움. /ha-redesign 거쳐서만 변경 허용. -->

## {{section_number}}. 화면 목록

### 디자인 레퍼런스 (필수 — 사용자 입력)
> AI 가 색상/타이포/레이아웃 직접 결정 = 밋밋한 결과 (LESSON-014).
> 반드시 외부 레퍼런스 URL 박음. 사용자가 `/ha-design` 단계에서 직접 입력.

<!-- AI-WRITABLE:view-screens-design-reference — /ha-design 인터뷰 중 사용자 입력 + AI 제안 레퍼런스 URL 채우는 영역. hook 통과. -->
| 항목 | 레퍼런스 출처 (URL) | 비고 |
|------|--------------------|------|
| 메인 흐름 / 화면 톤 | `<Mobbin / Dribbble / 실제 앱 캡처 URL>` | 어떤 앱이 닮길 원하는가 |
| 컬러 팔레트 | `<shadcn/ui 기본 / Tailwind 기본 / 커스텀 시 출처>` | 직접 색상 정의 시 출처 필수 |
| 타이포그래피 | `<Inter / Pretendard / 시스템 폰트 + 사용 사례 URL>` | 한국어 가독성 검증된 폰트 |
| 아이콘 세트 | `<lucide-react / heroicons / custom URL>` | 일관된 출처 1개 |
| 모션 / 인터랙션 | `<framer-motion 예시 / 레퍼런스 영상 URL>` | 없으면 "정적" 명시 |

#### Wireframe / Mockup (선택 — 강력 권장)
> 텍스트 명세만으로는 디자인 의도 전달 한계.
> 다음 중 하나 이상 채움:

- Figma 링크: `<URL 또는 N/A>`
- ASCII wireframe (핵심 화면 1-2 개):
  ```
  ┌─────────────────────────────┐
  │  <화면 1 ASCII wireframe>   │
  └─────────────────────────────┘
  ```
- 또는 손그림 사진 URL: `<URL 또는 N/A>`
<!-- /AI-WRITABLE -->

### 경로 매핑
| 경로 | 화면명 | 컨테이너 | Auth | 주요 API | 비고 |
|------|--------|----------|:---:|----------|------|
| `<예: /login>` | <예: 로그인> | `<예: LoginContainer>` | ❌ | `POST /api/auth/login` | |
| `<예: />` | <예: 홈> | `<예: HomeContainer>` | ✅ | `GET /api/<resource>` | |
| `/<resource>/:id` | <상세> | `<Container>` | ✅ | `GET /api/<resource>/{id}` | |

> 주요 API 는 `interface.http` 에 선언된 **`METHOD /path`** 표기 그대로 —
> commit 시 cross-section 검증이 선언 여부를 대조한다. Auth 칸 공백도 검증 대상.

### 사용자 흐름

#### 미인증
```
/login → 로그인 성공 → /
/register → 가입 + 자동 로그인 → /
```

#### 메인 흐름
```
홈 (/)
  ├─ <액션 1> → <결과 화면>
  ├─ <액션 2> → <모달/시트>
  └─ 로그아웃 → /login
```

#### 에러 케이스
- 401 → 토큰 갱신 → 실패 시 `/login`
- 403 → toast "권한이 없습니다"
- 404 → NotFound 화면 또는 toast
- 5xx → toast "잠시 후 다시 시도"

### 빈 상태 / 첫 사용자 경험

> 가장 흔한 설계 누락 — 정하지 않으면 코더가 추정한다.

- 목록이 비었을 때: <예: 일러스트 + "첫 ~를 추가해보세요" CTA / 단순 안내 문구>
- 첫 로그인 직후 화면: <예: 온보딩 1장 / 빈 홈 + 가이드 / 샘플 데이터 시드>
- 검색/필터 결과 0건: <예: "조건에 맞는 항목 없음" + 필터 초기화 버튼>

### 반응형 / 접근성
- 모바일 우선 / 데스크탑 우선: `<정책>`
- 최대 폭: `<예: 448px / 1280px>`
- 접근성: WCAG 2.1 AA 준수 (키보드 네비, 콘트라스트, aria 라벨)

<!-- /HUMAN-LOCKED:view.screens -->

> 작성 가이드:
> - 각 경로에 Auth 표시 (auth 섹션과 일치)
> - 흐름은 단방향 화살표 + 분기만
> - 모달/시트는 경로 없이 컨테이너 이름만
> - **HITL 규칙**: 디자인 레퍼런스 + Wireframe = LOCKED. `/ha-design` 인터뷰 단계에서만 사용자가 채움.
