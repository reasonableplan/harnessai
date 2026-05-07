# iOS Swift — Architecture Guidelines

## MV pattern (Apple 공식 SwiftUI 권장)

ViewModel 추상화 없이 View ↔ Model 직접 바인딩. 단순 화면은 그대로, 복잡 도메인은 Service / Repository 별도.

```
Views/                       ← SwiftUI View (stateless 우선)
  └─ binds to → Model
Models/                      ← @Observable class (state + actions)
  └─ depends on → Services
Services/                    ← Business logic (pure Swift)
Repositories/                ← Data gateway
  └─ depends on → Data layer (CoreData / URLSession)
```

> **MVVM 강제 X** — Apple 의 SwiftUI 가이드는 MV. 작은 화면은 ViewModel 없이 `@State` + `@Environment` 로 충분.

## @Observable Model (Swift 5.9+)

```swift
@Observable
final class ItemsModel {
    private let repo: ItemRepository

    var state: ViewState = .loading
    var items: [Item] = []

    init(repo: ItemRepository) {
        self.repo = repo
    }

    @MainActor
    func load() async {
        state = .loading
        do {
            items = try await repo.fetch()
            state = items.isEmpty ? .empty : .loaded
        } catch {
            state = .error(error.localizedDescription)
        }
    }

    @MainActor
    func toggleFavorite(_ id: Int) async {
        // 낙관적 업데이트
        if let idx = items.firstIndex(where: { $0.id == id }) {
            items[idx].isFavorite.toggle()
        }
        do {
            try await repo.toggleFavorite(id)
        } catch {
            // 롤백
            if let idx = items.firstIndex(where: { $0.id == id }) {
                items[idx].isFavorite.toggle()
            }
            state = .error(error.localizedDescription)
        }
    }
}

enum ViewState: Equatable {
    case loading
    case loaded
    case empty
    case error(String)
}
```

## Service / UseCase (도메인 로직)

```swift
// Domain/Services/AuthService.swift
protocol AuthService {
    func login(email: String, password: String) async throws -> AuthSession
    func logout() async
    var isAuthenticated: Bool { get }
}

final class AuthServiceImpl: AuthService {
    private let api: APIClient
    private let keychain: KeychainStore

    func login(email: String, password: String) async throws -> AuthSession {
        let res = try await api.post("/auth/login", body: LoginRequest(email: email, password: password))
        try keychain.saveTokens(access: res.accessToken, refresh: res.refreshToken)
        return AuthSession(userId: res.userId)
    }
}
```

## Repository (Data 게이트웨이)

```swift
// Domain/Repositories/ItemRepository.swift (protocol)
protocol ItemRepository {
    func fetch() async throws -> [Item]
    func create(_ input: CreateItemInput) async throws -> Item
    func observe() -> AsyncStream<[Item]>   // CoreData → AsyncStream
}

// Data/Repositories/ItemRepositoryImpl.swift
final class ItemRepositoryImpl: ItemRepository {
    private let api: APIClient
    private let local: ItemLocalDataSource

    func fetch() async throws -> [Item] {
        let dtos = try await api.get("/items", as: [ItemDTO].self)
        let items = dtos.map { $0.toDomain() }
        try await local.upsertAll(items.map { $0.toEntity() })
        return items
    }
}
```

## DI — SwiftUI Environment 또는 hand-rolled

작은 앱:
```swift
@main
struct MyApp: App {
    @State private var auth = AuthServiceImpl(api: ..., keychain: ...)
    @State private var repo: any ItemRepository = ItemRepositoryImpl(api: ...)

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(auth)
                .environment(repo)
        }
    }
}

// View
struct ItemsView: View {
    @Environment(any ItemRepository.self) private var repo
    @State private var model: ItemsModel

    init() {
        // model 은 onAppear 또는 init 에서 repo 주입 필요 — Environment 가 init 단계에서 안 잡힘
        // → ViewState 패턴 또는 hand-rolled DI 필요
    }
}
```

큰 앱: hand-rolled DI 컨테이너 (싱글톤 회피).

## DTO ↔ Domain 매핑

```swift
// Data/Remote/DTOs/ItemDTO.swift
struct ItemDTO: Codable {
    let id: Int
    let title: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title
        case createdAt = "created_at"
    }
}

extension ItemDTO {
    func toDomain() -> Item {
        Item(id: id, title: title, createdAt: createdAt)
    }
}

// Domain/Models/Item.swift — pure Swift
struct Item: Identifiable, Hashable {
    let id: Int
    var title: String
    let createdAt: Date
    var isFavorite: Bool = false
}
```

> **Domain 모델은 Codable 강제 X** — DTO 가 Codable, Domain 은 pure.

## 금지 사항

- Domain 레이어가 SwiftUI / CoreData / URLSession import (도메인 순수성)
- View 가 Repository / API 직접 호출 (Model 경유)
- `@StateObject` + `@ObservableObject` 신규 (Swift 5.9+ `@Observable` 만)
- Singleton mutable state (Service / Repository 만 Singleton, state 는 Model 안)
- `class` Domain model — `struct` 우선 (value semantics)
- `Combine` 신규 사용 (async/await + AsyncStream)
- force unwrap (`!`) — Domain 모델 / Repository 어디든 `guard let`
