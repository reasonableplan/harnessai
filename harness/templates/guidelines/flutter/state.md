# Flutter — State Management Guidelines

## Riverpod 단일화

`flutter_riverpod` 만 사용. Provider / GetX / Bloc / setState 를 도메인 상태로 사용 X (UI-local state 만 setState OK).

## Provider 종류 → 사용 결정 표

| 종류 | 용도 |
|----|----|
| `Provider` | 변하지 않는 의존성 (Repository, Service, Theme) |
| `StateProvider<T>` | 단순 enum / bool / int (toggle, 필터 선택) |
| `Notifier<T>` | 동기 UI state (form input 등) |
| `AsyncNotifier<T>` | **비동기 fetch + mutate** (대부분의 도메인 상태) |
| `StreamProvider<T>` | 실시간 (WebSocket, Firestore listener) |
| `FutureProvider<T>` | 한 번만 fetch (init 등) |

> 90% 의 도메인 상태는 **AsyncNotifier**.

## 도메인 provider 패턴

```dart
// lib/screens/items/providers/items_provider.dart
@riverpod
class Items extends _$Items {
  @override
  Future<List<Item>> build() async {
    final api = ref.watch(apiClientProvider);
    return api.fetchItems();
  }

  Future<void> create(CreateItemInput input) async {
    final api = ref.read(apiClientProvider);
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      await api.createItem(input);
      return api.fetchItems();
    });
  }
}
```

`@riverpod` 코드 생성 (build_runner) — pubspec 에 `riverpod_generator` + `riverpod_annotation` 필요.

## 낙관적 업데이트 (모바일에서 중요)

```dart
Future<void> toggleFavorite(int id) async {
  final current = state.value ?? [];
  final optimistic = current.map((i) => i.id == id ? i.copyWith(isFav: !i.isFav) : i).toList();
  state = AsyncValue.data(optimistic);

  try {
    await ref.read(apiClientProvider).toggleFavorite(id);
  } catch (e) {
    state = AsyncValue.data(current);  // 롤백
    rethrow;
  }
}
```

## 화면에서 사용

```dart
class ItemsScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncItems = ref.watch(itemsProvider);
    return asyncItems.when(
      data: (items) => ListView(...),
      loading: () => const CircularProgressIndicator(),
      error: (e, st) => ErrorView(message: extractErrorMessage(e)),
    );
  }
}
```

> Action 호출: `ref.read(itemsProvider.notifier).create(input)` (read 사용, watch 아님).

## ref.watch vs ref.read

- `ref.watch`: 상태 변경 시 위젯/Provider 재빌드 (구독)
- `ref.read`: 한 번만 읽음 (action 호출, init)

## 의존성 주입

```dart
@riverpod
ApiClient apiClient(ApiClientRef ref) {
  return ApiClient(baseUrl: const String.fromEnvironment('API_BASE_URL'));
}
```

테스트에서 override:
```dart
ProviderScope(
  overrides: [apiClientProvider.overrideWithValue(MockApiClient())],
  child: ...,
)
```

## mounted 체크 (필수)

```dart
Future<void> _onSave() async {
  await ref.read(itemsProvider.notifier).create(input);
  if (!context.mounted) return;   // ← async 후 필수
  Navigator.pop(context);
}
```

## 금지 사항

- `Provider` 패키지 (Riverpod 와 혼용 금지) — 둘 중 하나만
- `setState` 로 도메인 상태 관리 (UI-local 만)
- async 후 `setState` / `Navigator` 호출 with no `mounted` check
- `ref.watch` 를 action callback 안에서 (build 안에서만)
- `dispose` 직접 호출 — Riverpod 의 `autoDispose` 또는 lifecycle 자동 관리
- `@override` 누락 (`Notifier.build` / `AsyncNotifier.build`)
