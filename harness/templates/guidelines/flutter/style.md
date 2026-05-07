# Flutter — Style Guidelines

## ThemeData 단일화

`lib/app/theme.dart` 의 `ThemeData` 한 곳에서 색상 / 폰트 / spacing / shape 정의. 모든 위젯이 `Theme.of(context)` 경유.

```dart
// lib/app/theme.dart
final lightTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
  textTheme: GoogleFonts.notoSansKrTextTheme(),
  cardTheme: CardTheme(elevation: 1, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
);

final darkTheme = lightTheme.copyWith(
  colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo, brightness: Brightness.dark),
);
```

`MaterialApp(theme: lightTheme, darkTheme: darkTheme, themeMode: ThemeMode.system)` 로 연결.

## 위젯에서 Theme 사용

```dart
// ❌ BAD — 인라인 색상/스타일
Container(
  decoration: BoxDecoration(
    color: const Color(0xFF6366F1),
    borderRadius: BorderRadius.circular(12),
  ),
  child: Text('Hello', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
)

// ✅ GOOD — Theme 경유
Container(
  decoration: BoxDecoration(
    color: Theme.of(context).colorScheme.primary,
    borderRadius: BorderRadius.circular(12),
  ),
  child: Text('Hello', style: Theme.of(context).textTheme.titleMedium),
)
```

## 인라인 BoxDecoration 2개 이상 금지 (LESSON-STYLE-001)

같은 BoxDecoration 이 여러 위젯에 중복되면 — 추출:

```dart
// ❌ BAD
Container(decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)));
Container(decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)));

// ✅ GOOD — Theme extension
extension AppDecorations on ThemeData {
  BoxDecoration get cardSurface => BoxDecoration(
    color: colorScheme.surface,
    borderRadius: BorderRadius.circular(12),
  );
}
// 사용: decoration: Theme.of(context).cardSurface
```

또는 공용 위젯 (`AppCard`) 으로.

## 다크 모드

`Theme.of(context).colorScheme.surface` / `.onSurface` / `.primary` / `.onPrimary` — 자동으로 light/dark 전환.

명시적 분기 (드물게):
```dart
final isDark = Theme.of(context).brightness == Brightness.dark;
```

## SafeArea

모든 화면 root:
```dart
SafeArea(
  child: Scaffold(
    appBar: AppBar(title: const Text('Home')),
    body: ...,
  ),
)
```

또는 `MediaQuery.of(context).viewPadding` 으로 manual.

## Dynamic Type / 폰트 스케일

기본적으로 `Theme.of(context).textTheme.*` 가 시스템 textScaleFactor 따름. 절대 픽셀 (`fontSize: 14`) 금지 — `Theme.of(context).textTheme.bodyMedium` 등.

## 이미지

```dart
CachedNetworkImage(
  imageUrl: url,
  placeholder: (c, u) => const ShimmerPlaceholder(),
  errorWidget: (c, u, e) => const Icon(Icons.error),
  fit: BoxFit.cover,
)
```

> `Image.network` 직접 사용 안 함 (캐시 없음 — 네트워크 낭비).

## 접근성

```dart
Semantics(
  label: '프로필 사진 변경',
  hint: '카메라 또는 갤러리에서 사진 선택',
  button: true,
  child: GestureDetector(...),
)
```

또는 `IconButton` / `ElevatedButton` 등 표준 위젯이 자동으로 Semantics 추가.

## 반응형 (selective)

태블릿 / 폴더블 지원 시:
```dart
final width = MediaQuery.of(context).size.width;
final isWide = width > 600;
return isWide ? const TwoColumnLayout() : const SingleColumnLayout();
```

또는 `LayoutBuilder` 의 `constraints.maxWidth`.

## 금지 사항

- 인라인 색상 hex (`Color(0xFF...)`) — Theme.colorScheme 만
- 인라인 BoxDecoration 2개 이상 (LESSON-STYLE-001) — 추출
- 절대 픽셀 fontSize (`fontSize: 14`) — Theme.textTheme 토큰
- `Container(width: double.infinity, ...)` 남용 — `SizedBox.expand` 또는 flex
- `MediaQuery.of(context).size.width` 를 layout 근거로 매번 계산 — `LayoutBuilder` 또는 컨테이너 크기 기반
- `Image.network` (CachedNetworkImage 사용)
- 픽셀 단위 padding/margin 일관성 0 (`8`, `16`, `24` 등 spacing 토큰화)
