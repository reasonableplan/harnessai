# React Native + Expo — Storage Guidelines

## 저장 종류 → 사용 라이브러리 결정 표

| 데이터 종류 | 라이브러리 | 사유 |
|----|----|----|
| 사용자 설정 / UI state | `@react-native-async-storage/async-storage` | 단순 KV, JSON 직렬화, async |
| 성능 critical KV (1000+ 쓰기/초) | `react-native-mmkv` | C++ native, sync API |
| 시크릿 (JWT / refresh token / API key) | **`expo-secure-store`** | iOS Keychain / Android EncryptedSharedPreferences |
| 관계형 (목록 / 검색 / 인덱스) | `expo-sqlite` | SQLite, 트랜잭션 |
| 큰 파일 (이미지 캐시 / 다운로드) | `expo-file-system` | 파일 시스템 |

## AsyncStorage 패턴

```ts
import AsyncStorage from "@react-native-async-storage/async-storage";

// 단순 조회/저장 — try/catch 필수 (storage 가득 / OS 권한)
async function saveSetting(key: string, value: unknown) {
  try {
    await AsyncStorage.setItem(`setting:${key}`, JSON.stringify(value));
  } catch (e) {
    logger.error("storage write failed", { key, error: e });
  }
}
```

> `getAllKeys` / `multiGet` 은 1MB 한도 — 큰 데이터는 SQLite 로

## SecureStore (시크릿 전용)

```ts
import * as SecureStore from "expo-secure-store";

// 저장
await SecureStore.setItemAsync("refresh_token", token, {
  keychainAccessible: SecureStore.WHEN_UNLOCKED,  // 잠금 해제 시만 접근
});

// 읽기
const token = await SecureStore.getItemAsync("refresh_token");

// 삭제 (로그아웃)
await SecureStore.deleteItemAsync("refresh_token");
```

> **모든 인증 토큰** (refresh / access 둘 다) 은 SecureStore. AsyncStorage 사용 시 root 잡힌 디바이스에서 추출 가능.

## SQLite (expo-sqlite)

```ts
import * as SQLite from "expo-sqlite";

const db = await SQLite.openDatabaseAsync("app.db");

// 마이그레이션 — PRAGMA user_version 으로 관리
const { user_version } = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
if (user_version < 1) {
  await db.execAsync(`
    CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT, created_at INTEGER);
    PRAGMA user_version = 1;
  `);
}

// 쿼리 — 항상 prepared statement
await db.runAsync("INSERT INTO items (title, created_at) VALUES (?, ?)", title, Date.now());
const rows = await db.getAllAsync<Item>("SELECT * FROM items WHERE created_at > ?", since);
```

> **금지**: 문자열 concatenation 으로 SQL 작성 (SQL injection)

## MMKV (성능 critical only)

```ts
import { MMKV } from "react-native-mmkv";

const storage = new MMKV({ id: "user-cache", encryptionKey: SecureKey });
storage.set("recent.searches", JSON.stringify(searches));
const value = storage.getString("recent.searches");
```

> AsyncStorage 보다 30배 빠름 — 채팅 앱 / 게임 등 high-frequency 만. 일반 앱은 AsyncStorage 충분.

## 마이그레이션 / 버전

- AsyncStorage: key prefix 로 버전 관리 (`v1:setting:...` → `v2:setting:...`) + migrator 함수
- SQLite: `PRAGMA user_version`
- 시크릿: 마이그레이션 시 read → 새 형식 write → 기존 delete (atomic 보장 X — 두 토큰 동시 존재 가능 인지)

## 백업 / 복구

- iOS iCloud Backup: `expo-secure-store` 의 `keychainAccessible: AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY` 시 백업 제외
- Android Auto Backup: `android.allowBackup = false` (시크릿 포함 시) — `app.config.ts`

## 금지 사항

- AsyncStorage 에 시크릿 저장 (SecureStore)
- 동기적 storage 호출 (전부 async/await)
- 마이그레이션 없이 schema 변경
- SecureStore 에 큰 객체 (KEY MAX 2KB — JSON 직렬화 시 주의)
- SQL injection (parameterized query 만)
