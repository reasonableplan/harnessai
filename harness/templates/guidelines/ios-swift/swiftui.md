# iOS Swift — SwiftUI Guidelines

## NavigationStack (iOS 16+)

```swift
struct AppRouter: View {
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            HomeView()
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .item(let id): ItemDetailView(id: id)
                    case .settings: SettingsView()
                    case .profile(let userId): ProfileView(userId: userId)
                    }
                }
        }
    }
}

enum Route: Hashable {
    case item(id: Int)
    case settings
    case profile(userId: String)
}
```

> **NavigationView deprecated** — NavigationStack 만 사용.

## State 관리 (Swift 5.9+)

```swift
struct ItemsView: View {
    @State private var model = ItemsModel(repo: ItemRepositoryImpl())
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            switch model.state {
            case .loading: ProgressView()
            case .empty: EmptyStateView(message: "항목이 없습니다")
            case .loaded: ItemList(items: model.items)
            case .error(let msg): ErrorView(message: msg, onRetry: { Task { await model.load() } })
            }
        }
        .task { await model.load() }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active { Task { await model.refresh() } }
        }
    }
}
```

## ViewModifier 추출 (LESSON-STYLE-001)

5개 이상 modifier 체인 시 추출:

```swift
// ❌ BAD
Text("Hello")
    .font(.title)
    .foregroundStyle(.primary)
    .padding(.horizontal, 16)
    .padding(.vertical, 12)
    .background(Color.accentColor)
    .clipShape(RoundedRectangle(cornerRadius: 12))
    .shadow(radius: 2)

// ✅ GOOD
struct PrimaryBadge: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(.title)
            .foregroundStyle(.primary)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color.accentColor)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(radius: 2)
    }
}

extension View {
    func primaryBadge() -> some View { modifier(PrimaryBadge()) }
}

// 사용
Text("Hello").primaryBadge()
```

## Color / Font 단일화

`Sources/<App>/Views/Theme/`:

```swift
extension Color {
    static let appBackground = Color("AppBackground")    // Assets.xcassets
    static let appAccent = Color("AppAccent")
}

extension Font {
    static let appTitle = Font.system(size: 24, weight: .semibold, design: .rounded)
    static let appBody = Font.system(.body, design: .rounded)
}
```

> 인라인 hex (`Color(hex: "#...")`) 금지 — Asset Catalog + Color 토큰만.

## Dynamic Type / 폰트 스케일

```swift
// ✅ GOOD — semantic font (시스템 textScaleFactor 따름)
Text("Title").font(.title)
Text("Body").font(.body)
Text("Caption").font(.caption)

// ❌ BAD — 절대 픽셀
Text("Title").font(.system(size: 24))
```

## 모달 / 시트

```swift
@State private var isShowingSheet = false

var body: some View {
    Button("Edit") { isShowingSheet = true }
        .sheet(isPresented: $isShowingSheet) {
            EditView()
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
}
```

> 큰 폼 / 상세는 `.fullScreenCover`, 작은 옵션은 `.sheet` 또는 `.popover`.

## 백 버튼 / 제스처

```swift
struct EditView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var isDirty = false
    @State private var showDiscardAlert = false

    var body: some View {
        Form { ... }
            .interactiveDismissDisabled(isDirty)   // dirty 시 swipe-back 차단
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("취소") {
                        if isDirty { showDiscardAlert = true } else { dismiss() }
                    }
                }
            }
            .confirmationDialog("저장 안 함", isPresented: $showDiscardAlert) {
                Button("저장 안 함", role: .destructive) { dismiss() }
                Button("계속 편집", role: .cancel) {}
            }
    }
}
```

## 접근성

```swift
Button(action: changePhoto) {
    Image(systemName: "camera")
}
.accessibilityLabel("프로필 사진 변경")
.accessibilityHint("카메라 또는 갤러리에서 사진 선택")
```

## SafeArea

기본적으로 SwiftUI 가 SafeArea 자동 처리. 필요 시:

```swift
// 전체 화면 (배경 등) 으로 확장
Color.appBackground.ignoresSafeArea()

// 특정 edge 만
.padding(.top, 0).ignoresSafeArea(edges: .top)

// SafeArea 영역 가져오기
GeometryReader { proxy in
    let safeArea = proxy.safeAreaInsets
    ...
}
```

## Preview (모든 공용 View 필수)

```swift
#Preview("Light") {
    ItemRow(item: Item(id: 1, title: "Sample"))
}

#Preview("Dark") {
    ItemRow(item: Item(id: 1, title: "Sample"))
        .preferredColorScheme(.dark)
}

#Preview("Empty State") {
    EmptyStateView(message: "항목이 없습니다")
        .frame(width: 375, height: 200)
}
```

## 금지 사항

- UIKit 신규 사용 (UIViewRepresentable 통해서만, 사유 명시 필수)
- `@StateObject` + `ObservableObject` 신규 (`@Observable` 만)
- 절대 픽셀 fontSize (`Font.system(size: ...)` — semantic font 만)
- 인라인 hex 색상 (Asset Catalog + Color 토큰)
- Modal 안에서 Modal 무한 중첩 (3단계 이상 시 재설계)
- ScrollView 안 LazyVStack 없이 100+ 아이템 (성능)
- `force unwrap (!)` — `if let` / `guard let` / `??`
- `print()` — `Logger` (os.log) 또는 `swift-log`
