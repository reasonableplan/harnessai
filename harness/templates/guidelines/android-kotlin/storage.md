# Android Kotlin — Storage Guidelines

## 저장 종류 → 라이브러리 결정 표

| 데이터 종류 | 라이브러리 | 사유 |
|----|----|----|
| 사용자 설정 / UI 토글 | **DataStore Preferences** | async, type-safe, SharedPreferences 후속 |
| 시크릿 (JWT / refresh / API key) | **EncryptedSharedPreferences** 또는 **Keystore** | AES-256 암호화 + Keystore 백업 |
| 관계형 (목록 / 검색 / 인덱스) | **Room** | type-safe + Flow 통합 + 마이그레이션 도구 |
| 큰 파일 (이미지 캐시 / 다운로드) | `Context.cacheDir` + `Context.filesDir` + Coil/Glide cache | 표준 |
| 동기화 큐 / 작업 | **WorkManager** + Room | Doze / 네트워크 인식 |

> **SharedPreferences 신규 사용 금지** — DataStore 만.

## DataStore Preferences

```kotlin
private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val LOCALE = stringPreferencesKey("locale")
    private val IS_DARK = booleanPreferencesKey("is_dark")

    val locale: Flow<String> = context.settingsDataStore.data.map { it[LOCALE] ?: "en_US" }
    val isDark: Flow<Boolean> = context.settingsDataStore.data.map { it[IS_DARK] ?: false }

    suspend fun setLocale(value: String) {
        context.settingsDataStore.edit { it[LOCALE] = value }
    }
}
```

> Type-safe key + Flow<T> 자동 — UI 가 `collectAsStateWithLifecycle()` 로 구독.

## Room

```kotlin
@Entity(tableName = "items")
data class ItemEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val createdAt: Long,
    val isFavorite: Boolean = false,
)

@Dao
interface ItemDao {
    @Query("SELECT * FROM items ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<ItemEntity>>

    @Query("SELECT * FROM items WHERE id = :id")
    suspend fun findById(id: Long): ItemEntity?

    @Upsert
    suspend fun upsertAll(items: List<ItemEntity>)

    @Query("DELETE FROM items WHERE id = :id")
    suspend fun delete(id: Long)
}

@Database(
    entities = [ItemEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao
}
```

## Room 마이그레이션

```kotlin
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE items ADD COLUMN isFavorite INTEGER NOT NULL DEFAULT 0")
    }
}

@Provides
@Singleton
fun provideDatabase(@ApplicationContext context: Context): AppDatabase = Room
    .databaseBuilder(context, AppDatabase::class.java, "app.db")
    .addMigrations(MIGRATION_1_2)
    .build()
```

> `exportSchema = true` 강제 + `app/schemas/` 디렉토리 git 커밋 (마이그레이션 검증).

## EncryptedSharedPreferences (시크릿)

```kotlin
@Provides
@Singleton
fun provideEncryptedPrefs(@ApplicationContext context: Context): SharedPreferences {
    val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    return EncryptedSharedPreferences.create(
        context,
        "secure_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
}

class SecureTokenStore @Inject constructor(
    private val prefs: SharedPreferences,
) {
    suspend fun accessToken(): String? = withContext(Dispatchers.IO) {
        prefs.getString("access_token", null)
    }
    suspend fun saveTokens(access: String, refresh: String) = withContext(Dispatchers.IO) {
        prefs.edit { putString("access_token", access).putString("refresh_token", refresh) }
    }
    suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit { clear() }
    }
}
```

## 백업 / 복구 정책

`AndroidManifest.xml`:

```xml
<application
    android:allowBackup="false"             <!-- 시크릿 포함 시 false -->
    android:dataExtractionRules="@xml/data_extraction_rules"
    ...>
</application>
```

또는 선택적 백업 (Android 12+):

```xml
<!-- res/xml/data_extraction_rules.xml -->
<data-extraction-rules>
    <cloud-backup>
        <exclude domain="sharedpref" path="secure_prefs.xml" />
        <exclude domain="database" path="app.db" />
    </cloud-backup>
</data-extraction-rules>
```

## WorkManager (백그라운드 작업)

```kotlin
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val repo: ItemRepository,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = runCatching {
        repo.syncFromRemote()
        Result.success()
    }.getOrElse { Result.retry() }
}

// 등록
val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
    .setConstraints(
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()
    )
    .build()
WorkManager.getInstance(context).enqueueUniquePeriodicWork(
    "sync", ExistingPeriodicWorkPolicy.KEEP, request,
)
```

## 금지 사항

- `SharedPreferences` 신규 사용 (DataStore 만)
- 시크릿을 일반 SharedPreferences / DataStore 에 저장 (EncryptedSharedPreferences / Keystore)
- 동기적 disk I/O on main thread (`runBlocking { ... }` 회피, withContext(Dispatchers.IO))
- raw SQL string concatenation (Room `@Query` 만)
- `Room.inMemoryDatabaseBuilder` 프로덕션 사용 (테스트 전용)
- `exportSchema = false` (마이그레이션 검증 불가)
- AndroidManifest `allowBackup="true"` + 시크릿 포함 (조합 금지)
