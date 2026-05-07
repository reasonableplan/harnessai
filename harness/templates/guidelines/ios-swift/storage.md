# iOS Swift — Storage Guidelines

## 저장 종류 → 라이브러리 결정 표

| 데이터 종류 | 라이브러리 | 사유 |
|----|----|----|
| 사용자 설정 / UI 토글 | `@AppStorage` (UserDefaults wrapper) | SwiftUI 통합 + 단순 KV |
| 시크릿 (JWT / refresh / API key) | **Keychain** (KeychainAccess SPM) | iOS 표준 시크릿 저장소 |
| 관계형 (목록 / 검색 / 인덱스) | **CoreData** 또는 **SwiftData** (iOS 17+) | type-safe + 마이그레이션 + iCloud sync 옵션 |
| 큰 파일 (이미지 캐시 / 다운로드) | `FileManager` + `URLCache` | 표준 |

> **`UserDefaults` 에 시크릿 저장 절대 금지** — Keychain 만.

## @AppStorage (단순 설정)

```swift
struct SettingsView: View {
    @AppStorage("locale") private var locale: String = "en_US"
    @AppStorage("isDark") private var isDark: Bool = false

    var body: some View {
        Form {
            Picker("Language", selection: $locale) {
                Text("English").tag("en_US")
                Text("한국어").tag("ko_KR")
            }
            Toggle("Dark Mode", isOn: $isDark)
        }
    }
}
```

> `@AppStorage` 는 UserDefaults 위 wrapper — 자동 SwiftUI 갱신.

## Keychain (시크릿 전용)

```swift
import KeychainAccess

final class SecureTokenStore {
    private let keychain: Keychain

    init(service: String = Bundle.main.bundleIdentifier ?? "app") {
        self.keychain = Keychain(service: service)
            .accessibility(.afterFirstUnlockThisDeviceOnly)   // 백업 제외
            .synchronizable(false)                            // iCloud sync 안 함
    }

    func saveTokens(access: String, refresh: String) throws {
        try keychain.set(access, key: "access_token")
        try keychain.set(refresh, key: "refresh_token")
    }

    func accessToken() -> String? {
        try? keychain.getString("access_token")
    }

    func clear() throws {
        try keychain.removeAll()
    }
}
```

### Accessibility 옵션

| 옵션 | 백업 포함 | 잠금 시 접근 | 권장 |
|----|----|----|----|
| `whenUnlocked` | ✅ | ❌ | 일반 시크릿 |
| `whenUnlockedThisDeviceOnly` | ❌ | ❌ | 디바이스 전용 시크릿 |
| `afterFirstUnlock` | ✅ | ✅ (재부팅 후 1회 잠금 해제 시까지) | 백그라운드 push 처리용 |
| `afterFirstUnlockThisDeviceOnly` | ❌ | ✅ | **JWT / refresh token 권장** |

## SwiftData (iOS 17+)

```swift
import SwiftData

@Model
final class ItemEntity {
    @Attribute(.unique) var id: Int
    var title: String
    var createdAt: Date
    var isFavorite: Bool

    init(id: Int, title: String, createdAt: Date, isFavorite: Bool = false) {
        self.id = id
        self.title = title
        self.createdAt = createdAt
        self.isFavorite = isFavorite
    }
}

// App.swift
@main
struct MyApp: App {
    let modelContainer: ModelContainer

    init() {
        do {
            modelContainer = try ModelContainer(for: ItemEntity.self)
        } catch {
            fatalError("ModelContainer init 실패: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .modelContainer(modelContainer)
        }
    }
}

// View
struct ItemsView: View {
    @Query(sort: \ItemEntity.createdAt, order: .reverse) private var items: [ItemEntity]
    @Environment(\.modelContext) private var context

    var body: some View {
        List(items) { item in
            ItemRow(item: item)
        }
    }
}
```

## CoreData (iOS 13+ — 더 넓은 호환)

`Data/Local/CoreDataStack.swift`:
```swift
final class CoreDataStack {
    static let shared = CoreDataStack()

    lazy var container: NSPersistentContainer = {
        let container = NSPersistentContainer(name: "AppModel")
        container.loadPersistentStores { description, error in
            if let error = error {
                fatalError("CoreData load 실패: \(error)")
            }
        }
        // 마이그레이션 — lightweight 자동
        container.persistentStoreDescriptions.first?.shouldMigrateStoreAutomatically = true
        container.persistentStoreDescriptions.first?.shouldInferMappingModelAutomatically = true
        return container
    }()

    var viewContext: NSManagedObjectContext { container.viewContext }

    func newBackgroundContext() -> NSManagedObjectContext {
        container.newBackgroundContext()
    }
}
```

## 백업 / iCloud 정책

### 시크릿 백업 제외 (Keychain)
```swift
.accessibility(.afterFirstUnlockThisDeviceOnly)   // ThisDeviceOnly = 백업 제외
```

### 파일 백업 제외
```swift
extension URL {
    func setExcludedFromBackup() throws {
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var url = self
        try url.setResourceValues(values)
    }
}

let cacheDir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
try cacheDir.setExcludedFromBackup()
```

> Cache 디렉토리는 자동으로 백업 제외 — `Documents/` 만 백업 포함.

## 마이그레이션

### CoreData
- Lightweight migration (자동) — 컬럼 추가 / 삭제 / 이름 변경
- Custom migration (수동) — 데이터 변환 필요 시 NSEntityMigrationPolicy

### SwiftData
- `@Migration` macro (iOS 17+) — schema version 명시
- `Schema(versionedSchema:)` 통해 버전 관리

## Concurrency

```swift
// CoreData — 백그라운드 컨텍스트
let context = CoreDataStack.shared.newBackgroundContext()
await context.perform {
    let item = ItemEntity(context: context)
    item.title = "..."
    try? context.save()
}

// SwiftData — actor isolation 자동
@ModelActor actor ItemRepository {
    func upsertAll(_ items: [Item]) {
        for item in items {
            modelContext.insert(ItemEntity(item: item))
        }
        try? modelContext.save()
    }
}
```

## 금지 사항

- 시크릿을 `UserDefaults` 에 저장 (Keychain 만)
- 시크릿을 `@AppStorage` 사용 (`UserDefaults` wrapper 라 동일)
- CoreData / SwiftData 메인 컨텍스트에서 무거운 fetch (백그라운드 컨텍스트 사용)
- 여러 ModelContainer 인스턴스 (앱 단일 — 테스트 제외)
- `try!` 로 storage 작업 (force-unwrap 금지)
- 동기 disk I/O on main thread (`await context.perform { ... }`)
- iCloud sync 활성 + `Documents/` 에 시크릿 보관 조합
- Realm / Firebase Firestore 신규 사용 (CoreData / SwiftData 우선)
