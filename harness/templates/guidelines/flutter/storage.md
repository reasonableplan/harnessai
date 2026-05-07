# Flutter — Storage Guidelines

## 저장 종류 → 라이브러리 결정 표

| 데이터 종류 | 라이브러리 | 사유 |
|----|----|----|
| 사용자 설정 / UI 토글 | `shared_preferences` | 단순 KV, async, 표준 |
| 시크릿 (JWT / refresh / API key) | **`flutter_secure_storage`** | iOS Keychain / Android EncryptedSharedPreferences |
| 관계형 (목록 / 검색 / 인덱스) | **`drift`** (sqflite 위) | type-safe, build_runner 통합 |
| 대용량 / 빠른 KV | `hive` 또는 `isar` | object DB (의존성 주의) |
| 큰 파일 (이미지 캐시 / 다운로드) | `path_provider` + `dart:io` | 파일 시스템 |

## shared_preferences

```dart
final prefs = await SharedPreferences.getInstance();
await prefs.setString('locale', 'ko_KR');
final locale = prefs.getString('locale') ?? 'en_US';
```

> JSON 객체 저장: `jsonEncode` → setString. 1MB 이상은 SQLite 로.

## flutter_secure_storage (시크릿 전용)

```dart
const storage = FlutterSecureStorage(
  aOptions: AndroidOptions(encryptedSharedPreferences: true),
  iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
);

await storage.write(key: 'refresh_token', value: token);
final token = await storage.read(key: 'refresh_token');
await storage.delete(key: 'refresh_token');   // 로그아웃
```

> **모든 인증 토큰** (access + refresh) 은 secure storage. shared_preferences 는 root 잡힌 디바이스에서 추출 가능.

## drift (관계형)

`pubspec.yaml`:
```yaml
dependencies:
  drift: ^x.y
  sqlite3_flutter_libs: ^x.y
  path_provider: ^x.y
dev_dependencies:
  drift_dev: ^x.y
  build_runner: ^x.y
```

테이블 정의:
```dart
// lib/data/db/items_table.dart
class Items extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get title => text()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}

@DriftDatabase(tables: [Items])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  @override
  int get schemaVersion => 1;

  @override
  MigrationStrategy get migration => MigrationStrategy(
    onCreate: (m) => m.createAll(),
    onUpgrade: (m, from, to) async {
      if (from < 2) await m.addColumn(items, items.tags);
    },
  );
}
```

`dart run build_runner build` 로 코드 생성.

## 마이그레이션

- drift: `schemaVersion` + `MigrationStrategy.onUpgrade` — forward only 권장
- shared_preferences: key prefix 로 버전 관리 (`v1.locale` → `v2.locale`) + migrator
- secure_storage: 마이그레이션 시 read → 새 형식 write → 기존 delete

## 백업 / 복구 (플랫폼)

- iOS iCloud Backup: `flutter_secure_storage` 의 `accessibility: first_unlock_this_device` 시 백업 제외
- Android Auto Backup: `AndroidManifest.xml` 의 `android:allowBackup="false"` (시크릿 포함 시)

## 동시성

- drift: 트랜잭션 (`transaction { ... }`) 으로 multi-statement atomic
- shared_preferences: 단일 instance — 동시 write 안전
- secure_storage: 동시 write 시 race 가능 (자체 lock 권장)

## 금지 사항

- shared_preferences 에 시크릿 (secure_storage 사용)
- 동기 storage 호출 (전부 async/await)
- raw SQL string concatenation (prepared statement / drift 만)
- 마이그레이션 없이 schema 변경 (drift `schemaVersion` 누락)
- 큰 객체 (>1MB) shared_preferences 저장 (SQLite / 파일로)
- 평문 JWT 를 cookie / shared_preferences 에 저장
