---
id: view.components
name: 컴포넌트 트리
required_when: has.ui and scale.small_or_larger
description: App 컴포넌트 계층, 공용 컴포넌트, 디자인 가이드
---

## {{section_number}}. 컴포넌트 트리

### App 계층
```
App
├─ <Provider/Router>
│   ├─ ProtectedRoute
│   │   ├─ <HomeContainer /> (/)
│   │   │   ├─ <Header />
│   │   │   ├─ <DomainList>
│   │   │   │   └─ <DomainCard />[]
│   │   │   └─ <AddDomainSheet />
│   │   └─ ...
│   └─ <AuthLayout>
│       ├─ <LoginContainer /> (/login)
│       └─ <RegisterContainer /> (/register)
```

### 공용 컴포넌트 (shared/components)
| 컴포넌트 | 용도 | props |
|----------|------|-------|
| `<Button>` | 버튼 | `variant, size, onClick` |
| `<Input>` | 입력 | `value, onChange, error` |
| `<Modal>` | 모달 | `open, onClose, title` |
| `<Sheet>` | 바텀 시트 (모바일) | `open, onClose` |
| `<Toast>` | 알림 | `type, message` |

### 디자인 가이드

**색상 (CSS 변수)**
```css
/* 값은 view.screens 의 디자인 레퍼런스에서 추출 — 고정 팔레트 제시 금지.
   프로젝트마다 테마 변주 (AI티 방지 — LESSON-014, ha-build 슬롭 룰 9) */
--bg-base:       <레퍼런스에서 추출>
--bg-surface:    <레퍼런스에서 추출>
--text-primary:  <레퍼런스에서 추출>
--text-secondary:<레퍼런스에서 추출>
--accent:        <레퍼런스에서 추출>
--success:       <레퍼런스에서 추출>
--error:         <레퍼런스에서 추출>
```

**타이포그래피**
- 제목: <폰트 패밀리, 크기>
- 본문: <...>

**스타일 규칙**
- 활성 프로파일의 `guidelines/<profile>/style.md` 를 따른다 — 스택별 규칙은
  프로파일이 단일 진실원천 (이 섹션은 has.ui 로 Flutter/Android/iOS 에도 활성되므로
  특정 스택 규칙을 여기 나열하지 않는다)
- 예: react 계열 CVA + `index.style.ts` / Flutter ThemeData / Compose Theme / SwiftUI ViewModifier

### 상태 관리 매핑
| Store | 담당 | 경로 |
|-------|------|------|
| `authStore` | 인증/사용자 | `shared/store/auth.store.ts` |
| `<domainStore>` | <도메인> | `containers/<domain>/store/` |

> 작성 가이드:
> - 계층은 실제 JSX 구조와 1:1 일치
> - 공용 컴포넌트는 도메인 로직 0 — 순수 UI만
> - 컨테이너는 store와 직접 연결, 프레젠테이션 컴포넌트는 props로만
