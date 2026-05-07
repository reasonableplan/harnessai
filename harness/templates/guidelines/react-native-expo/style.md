# React Native + Expo — Style Guidelines

## 두 가지 옵션 (skeleton 에서 결정)

### Option A: NativeWind (Tailwind for RN) — 권장

`tailwindcss` 와 동일한 className API. web (`react-vite`) 사용자에게 익숙.

```tsx
import { View, Text } from "react-native";

export function Card({ title }: { title: string }) {
  return (
    <View className="rounded-xl bg-white shadow-sm p-4 mb-2 dark:bg-gray-800">
      <Text className="text-lg font-semibold text-gray-900 dark:text-white">
        {title}
      </Text>
    </View>
  );
}
```

설정:
```ts
// tailwind.config.js
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: { /* ... */ },
};

// global.css (NativeWind v4)
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### Option B: StyleSheet — 전통적

```tsx
import { View, Text, StyleSheet } from "react-native";

export function Card({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { borderRadius: 12, backgroundColor: "white", padding: 16 },
  title: { fontSize: 18, fontWeight: "600" },
});
```

> StyleSheet 객체는 **컴포넌트 파일 하단** 또는 별도 `index.style.ts` (도메인 컨테이너 시).

## 인라인 금지 (LESSON-STYLE-001)

```tsx
// ❌ BAD — 인라인 2개 이상
<View style={{ padding: 16, backgroundColor: "white", borderRadius: 12 }}>

// ✅ GOOD — NativeWind className
<View className="p-4 bg-white rounded-xl">

// ✅ GOOD — StyleSheet
<View style={styles.container}>
```

## 동적 스타일

NativeWind: 조건부 className
```tsx
<View className={cn("p-4", isActive && "bg-blue-500")} />
```
(`cn` = `clsx` 또는 `tailwind-merge`)

StyleSheet: array
```tsx
<View style={[styles.container, isActive && styles.active]} />
```

## 다크 모드

NativeWind v4: `dark:` prefix
```tsx
<View className="bg-white dark:bg-gray-800">
```

StyleSheet: `useColorScheme` hook
```tsx
const scheme = useColorScheme();
<View style={[styles.base, scheme === "dark" && styles.dark]}>
```

## SafeArea / Insets

**모든 화면 root** 는 SafeAreaView 또는 useSafeAreaInsets:

```tsx
import { useSafeAreaInsets } from "react-native-safe-area-context";

function Screen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={{ paddingTop: insets.top, paddingBottom: insets.bottom }}>
      {/* ... */}
    </View>
  );
}
```

## 폰트

`expo-font` 로 로드, root `_layout.tsx` 에서 SplashScreen 동안 로드 완료 보장:

```tsx
import { useFonts } from "expo-font";

const [loaded] = useFonts({ "Inter-Regular": require("../assets/fonts/Inter-Regular.ttf") });
if (!loaded) return null;  // SplashScreen 유지
```

## 접근성

- 모든 인터랙티브 요소: `accessible={true}` + `accessibilityLabel="..."`
- 그래픽: `accessibilityRole="image"` + `accessibilityLabel`
- 헤더: `accessibilityRole="header"`

## 금지 사항

- 인라인 스타일 2개 이상 (LESSON-STYLE-001)
- `style={{ width: "100%" }}` — flex layout 사용 (`flex: 1` 또는 `flexBasis`)
- `style={{ position: "absolute", ... }}` 남용 — flex / SafeArea 우선
- 픽셀 단위 (`style={{ fontSize: 14 }}`) — 시스템 폰트 스케일 따라가게 (relative 단위)
- 색상 hardcode (`"#FFFFFF"`) — Theme 토큰 사용
