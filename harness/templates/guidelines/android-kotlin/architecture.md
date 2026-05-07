# Android Kotlin — Architecture Guidelines

## MVVM + Clean Architecture

3 레이어 명확 분리, 의존성은 안쪽으로만:

```
ui/                            ← Presentation (Compose + ViewModel)
  └─ depends on → domain/
domain/                        ← Business logic (pure Kotlin)
  └─ depends on → (nothing — interface 만 노출)
data/                          ← Implementation (Room / Retrofit)
  └─ depends on → domain/      (Repository interface 구현)
```

## ViewModel — 상태 보유

```kotlin
@HiltViewModel
class ItemsViewModel @Inject constructor(
    private val getItems: GetItemsUseCase,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val _state = MutableStateFlow<UiState>(UiState.Loading)
    val state: StateFlow<UiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            _state.update { runCatching { UiState.Success(getItems()) }.getOrElse { UiState.Error(it.message ?: "") } }
        }
    }
}

sealed class UiState {
    data object Loading : UiState()
    data class Success(val items: List<Item>) : UiState()
    data class Error(val message: String) : UiState()
}
```

## UseCase — 도메인 로직

```kotlin
class GetItemsUseCase @Inject constructor(
    private val repo: ItemRepository,    // domain interface
) {
    suspend operator fun invoke(): List<Item> = repo.fetch()
}
```

> 단순 pass-through 면 UseCase 생략 OK — Repository 직접 주입.

## Repository — 데이터 게이트웨이

```kotlin
// domain/repository/ItemRepository.kt
interface ItemRepository {
    suspend fun fetch(): List<Item>
    suspend fun create(input: CreateItemInput): Item
    fun observe(): Flow<List<Item>>   // Room → Flow
}

// data/repository/ItemRepositoryImpl.kt
class ItemRepositoryImpl @Inject constructor(
    private val api: ItemApi,         // Retrofit
    private val dao: ItemDao,         // Room
) : ItemRepository {
    override suspend fun fetch(): List<Item> = withContext(Dispatchers.IO) {
        val remote = api.getItems().map { it.toDomain() }
        dao.upsertAll(remote.map { it.toEntity() })
        remote
    }
    override fun observe(): Flow<List<Item>> = dao.observeAll().map { list -> list.map { it.toDomain() } }
}
```

## DI (Hilt)

```kotlin
@HiltAndroidApp
class App : Application()

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    @Singleton
    fun provideRetrofit(): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .addConverterFactory(MoshiConverterFactory.create())
        .build()
}

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    abstract fun bindItemRepository(impl: ItemRepositoryImpl): ItemRepository
}
```

## DTO ↔ Domain 매핑

```kotlin
// data/remote/dto/ItemDto.kt
@JsonClass(generateAdapter = true)
data class ItemDto(val id: Long, val title: String, val created_at: String)

// 매핑 — data 레이어에서만
fun ItemDto.toDomain(): Item = Item(id = id, title = title, createdAt = Instant.parse(created_at))
fun Item.toEntity(): ItemEntity = ItemEntity(id = id, title = title, createdAt = createdAt.toEpochMilli())
```

> **domain 모델은 절대 DTO/Entity 의존 X** — pure Kotlin data class.

## 금지 사항

- domain 레이어가 androidx / Retrofit / Room import (도메인 순수성)
- UI 가 Repository / API 직접 호출 (ViewModel 경유)
- ViewModel 안 LiveData 신규 사용 (StateFlow / SharedFlow)
- Singleton mutable state (Repository 만 Singleton, state 는 ViewModel 안)
- Hilt 외 DI 라이브러리 (Koin / 수동 등)
