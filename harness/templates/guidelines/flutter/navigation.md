# Flutter — Navigation Guidelines

## go_router 단일화

`pubspec.yaml` 에 `go_router` 추가, `lib/app/router.dart` 단일 source.

```dart
// lib/app/router.dart
final appRouter = GoRouter(
  initialLocation: '/',
  redirect: (context, state) {
    final isAuth = ref.read(authProvider).isAuthenticated;
    final isLoginRoute = state.matchedLocation == '/login';
    if (!isAuth && !isLoginRoute) return '/login';
    if (isAuth && isLoginRoute) return '/';
    return null;
  },
  routes: [
    GoRoute(path: '/login', builder: (c, s) => const LoginScreen()),
    ShellRoute(
      builder: (c, s, child) => MainShell(child: child),
      routes: [
        GoRoute(path: '/', builder: (c, s) => const HomeScreen()),
        GoRoute(
          path: '/items/:id',
          builder: (c, s) => ItemScreen(id: s.pathParameters['id']!),
        ),
      ],
    ),
  ],
);
```

`MaterialApp.router(routerConfig: appRouter)` 로 연결.

## Route Guard

`redirect` callback 안에서 모든 가드 검사 (auth → role → onboarding):

```dart
redirect: (context, state) {
  final auth = ref.read(authProvider);
  final loc = state.matchedLocation;

  if (!auth.isAuthenticated && loc != '/login') return '/login';
  if (auth.isAuthenticated && !auth.hasOnboarded && loc != '/onboarding') return '/onboarding';
  if (loc.startsWith('/admin') && !auth.isAdmin) return '/403';
  return null;
}
```

> **금지**: 화면 build 안에서 `if (!auth) GoRouter.of(context).go('/login')` — race condition 발생.

## Path Parameters (typed)

```dart
GoRoute(
  path: '/items/:id',
  builder: (c, s) {
    final id = s.pathParameters['id']!;
    return ItemScreen(id: id);
  },
)
```

쿼리 파라미터: `state.uri.queryParameters['filter']`.

## Deep Linking

`pubspec.yaml`:
```yaml
dependencies:
  app_links: ^x.y
```

또는 go_router 의 native scheme:
```dart
GoRouter(
  redirect: (context, state) {
    if (state.uri.scheme == 'myapp') {
      return _handleDeepLink(state.uri);
    }
    return null;
  },
  // ...
);
```

`AndroidManifest.xml` + `Info.plist` 에 scheme 등록 필수.

## ShellRoute (탭 / Drawer / 인증 후 layout)

탭 layout 처럼 child 화면을 wrapping 하는 경우:

```dart
ShellRoute(
  builder: (c, s, child) {
    return Scaffold(
      body: child,
      bottomNavigationBar: AppTabBar(),
    );
  },
  routes: [...],
)
```

## 백 버튼 / 제스처

- Modal / Dialog 열림 → 자동으로 `Navigator.pop` 우선
- 폼 dirty → `WillPopScope` 또는 `PopScope` 로 가드:
```dart
PopScope(
  canPop: !isDirty,
  onPopInvoked: (didPop) async {
    if (didPop || !isDirty) return;
    final shouldDiscard = await _confirmDiscard(context);
    if (shouldDiscard) context.pop();
  },
  child: ...,
)
```
- iOS swipe-back: `MaterialPageRoute` 의 기본 동작 — 비활성화 시 `CupertinoPageRoute` 의 옵션 또는 custom

## 모달 (BottomSheet / Dialog)

`showModalBottomSheet` / `showDialog` 는 router 외부 — 일반적인 화면 전환은 모두 go_router 로.

## 금지 사항

- `Navigator.push` / `Navigator.pop` 직접 (go_router 의 `context.push` / `context.pop` / `context.go` 만)
- 화면 build 안에서 redirect — `redirect` callback 만
- `MaterialApp` (router 없음) + `MaterialApp.router` 혼용
- Path 를 string literal hardcode — 상수 또는 typed routes (`go_router_builder`) 권장
- `setState` 후 즉시 `context.go` (위젯 lifecycle 문제)
