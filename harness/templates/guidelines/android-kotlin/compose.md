# Android Kotlin — Jetpack Compose Guidelines

## Stateless + State Hoisting

Composable 자체는 stateless — 부모가 state 보유 + callback 전달.

```kotlin
// ❌ BAD — stateful, 재사용 어려움
@Composable
fun Counter() {
    var count by remember { mutableStateOf(0) }
    Button(onClick = { count++ }) { Text("$count") }
}

// ✅ GOOD — stateless, hoisting
@Composable
fun Counter(count: Int, onIncrement: () -> Unit) {
    Button(onClick = onIncrement) { Text("$count") }
}
```

## Material3 Theme 단일화

```kotlin
@Composable
fun AppTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colorScheme,
        typography = AppTypography,
        shapes = AppShapes,
        content = content,
    )
}

// 사용
AppTheme {
    Surface(color = MaterialTheme.colorScheme.background) {
        // content
    }
}
```

## ViewModel 연결

```kotlin
@Composable
fun ItemsScreen(viewModel: ItemsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    ItemsContent(
        state = state,
        onItemClick = viewModel::onItemClick,
        onRefresh = viewModel::refresh,
    )
}

@Composable
private fun ItemsContent(state: UiState, onItemClick: (Long) -> Unit, onRefresh: () -> Unit) {
    when (state) {
        UiState.Loading -> CircularProgressIndicator()
        is UiState.Error -> ErrorView(message = state.message, onRetry = onRefresh)
        is UiState.Success -> LazyColumn { items(state.items) { ItemRow(it, onClick = { onItemClick(it.id) }) } }
    }
}
```

> `collectAsStateWithLifecycle` 사용 (Lifecycle 인식 — `collectAsState` 대신).

## Modifier 순서

```kotlin
// ❌ BAD — 순서 안 지킴 (visual 이상)
Modifier
    .padding(16.dp)
    .background(Color.White)
    .clickable { ... }
    .size(48.dp)

// ✅ GOOD — size → padding → background → clickable
Modifier
    .size(48.dp)
    .padding(16.dp)
    .background(MaterialTheme.colorScheme.surface)
    .clickable { ... }
```

## 인라인 Modifier 5개 이상 시 추출 (LESSON-STYLE-001)

```kotlin
// 추출 — Modifier extension
fun Modifier.cardStyle(): Modifier = this
    .padding(8.dp)
    .clip(RoundedCornerShape(12.dp))
    .background(MaterialTheme.colorScheme.surface)
    .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
    .shadow(elevation = 2.dp)

// 사용
Box(modifier = Modifier.cardStyle()) { ... }
```

## Preview

```kotlin
@Preview(name = "Light", showBackground = true)
@Preview(name = "Dark", showBackground = true, uiMode = Configuration.UI_MODE_NIGHT_YES)
@Composable
private fun ItemRowPreview() {
    AppTheme {
        ItemRow(item = Item(id = 1, title = "Sample"), onClick = {})
    }
}
```

> 모든 공용 Composable 에 Preview 필수 — design review 효율 ↑

## Side Effect

```kotlin
// 화면 진입 시 한 번만 실행
LaunchedEffect(Unit) { viewModel.load() }

// state 변경에 반응
LaunchedEffect(state.errorEvent) {
    state.errorEvent?.let { snackbarHostState.showSnackbar(it) }
}

// dispose 시 cleanup
DisposableEffect(Unit) {
    val listener = ...
    onDispose { listener.unregister() }
}
```

## 접근성

```kotlin
Image(
    painter = painterResource(R.drawable.profile),
    contentDescription = "프로필 사진 변경",   // 필수
    modifier = Modifier.semantics { role = Role.Button },
)
```

## 금지 사항

- `mutableStateOf` 를 ViewModel 안에서 직접 (StateFlow 사용)
- Composable 안 `runBlocking` / `Thread.sleep`
- `collectAsState` (lifecycle-aware 버전 사용)
- 화면 root 가 `Column { ... }` 만 — `Scaffold` / `Surface` 우선
- 인라인 hex (`Color(0xFF...)`) — `MaterialTheme.colorScheme` 만
- 절대 dp 폰트 (`fontSize = 14.sp` 외 다른 단위 — `MaterialTheme.typography` 토큰 사용)
- View interop (`AndroidView { ... }`) 신규 (마이그레이션 시 별도)
