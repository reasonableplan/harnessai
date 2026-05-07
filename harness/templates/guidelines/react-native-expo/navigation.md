# React Native + Expo — Navigation Guidelines

## Expo Router (file-based)

`app/` 디렉토리 구조가 그대로 라우트 트리. 별도 router config X.

```
app/
  _layout.tsx              # Root: Providers / SplashScreen / Theme
  (auth)/                  # group — URL 에 (auth) 안 나옴
    _layout.tsx            # 인증 가드 (redirect to /(main))
    login.tsx              # /login
    signup.tsx             # /signup
  (main)/
    _layout.tsx            # Tab layout
    index.tsx              # /  (홈 탭)
    profile.tsx            # /profile
    settings/
      _layout.tsx          # nested stack
      index.tsx            # /settings
      account.tsx          # /settings/account
  [+not-found].tsx         # 404
```

## Layout 패턴

**Root `_layout.tsx`**: Provider 체인 + SplashScreen 제어
```tsx
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="(main)" />
        </Stack>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
```

**Group `_layout.tsx` 의 가드** (예: `(main)/_layout.tsx`):
```tsx
export default function MainLayout() {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Redirect href="/(auth)/login" />;
  return <Tabs>{/* ... */}</Tabs>;
}
```

> **금지**: 화면 컴포넌트 안에서 `useEffect` + `router.replace` 로 redirect — race condition 발생. `_layout.tsx` 의 `<Redirect>` 만.

## Deep Linking

`app.config.ts`:
```ts
export default {
  expo: {
    scheme: "myapp",                          // myapp://
    ios: { associatedDomains: ["applinks:..."] },
    android: { intentFilters: [{ action: "VIEW", data: [{ scheme: "https", host: "..." }] }] },
  },
};
```

라우트 → URL 자동 매핑. `myapp://item/123` → `/item/[id]` (param=`123`).

## Route Params (typed)

```tsx
import { useLocalSearchParams } from "expo-router";

export default function ItemScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  // ...
}
```

> **금지**: `useGlobalSearchParams` (cross-route 누수). `useLocalSearchParams` 만.

## 백 버튼 / 제스처

- Modal / Bottom Sheet 열림 → 백 버튼 = 닫기 (router 변경 X)
- 폼 dirty → 백 버튼 = "저장 안 함" 모달
- 루트 탭 → 더블 백 = 앱 종료 (Android) — `BackHandler.exitApp()`
- iOS swipe-back 비활성화: `<Stack.Screen options={{ gestureEnabled: false }} />`

## 모달

```tsx
<Stack.Screen
  name="modal/edit-profile"
  options={{ presentation: "modal" }}
/>
```

`router.push("/modal/edit-profile")` 로 호출. `router.back()` 으로 닫기.

## 금지 사항

- `react-navigation` 직접 사용 (Expo Router 가 wrap)
- `useEffect(() => { router.replace(...) }, [])` 안티패턴 — `<Redirect>` 사용
- 화면 컴포넌트가 자기 라우트 path 를 hardcoded — `pathname` 또는 typed routes 사용
- nested 4단계 이상 stack — 평평하게 재설계
