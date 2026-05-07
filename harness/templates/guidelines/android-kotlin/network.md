# Android Kotlin — Network Guidelines

## Retrofit + OkHttp + Coroutines

```kotlin
// data/remote/api/ItemApi.kt
interface ItemApi {
    @GET("items")
    suspend fun getItems(): List<ItemDto>

    @GET("items/{id}")
    suspend fun getItem(@Path("id") id: Long): ItemDto

    @POST("items")
    suspend fun createItem(@Body input: CreateItemDto): ItemDto

    @PATCH("items/{id}")
    suspend fun updateItem(@Path("id") id: Long, @Body input: UpdateItemDto): ItemDto

    @DELETE("items/{id}")
    suspend fun deleteItem(@Path("id") id: Long)
}
```

> 모든 메서드 `suspend` 또는 `Flow<T>` 반환. `Call<T>` 는 신규 사용 금지.

## OkHttp Interceptor

### Auth (토큰 주입 + refresh)

```kotlin
class AuthInterceptor @Inject constructor(
    private val tokenStore: SecureTokenStore,   // EncryptedSharedPreferences 또는 Keystore
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = runBlocking { tokenStore.accessToken() }
        val req = chain.request().newBuilder()
            .apply { token?.let { addHeader("Authorization", "Bearer $it") } }
            .build()
        val res = chain.proceed(req)
        if (res.code == 401 && token != null) {
            res.close()
            return refreshAndRetry(chain, req)
        }
        return res
    }

    private fun refreshAndRetry(chain: Interceptor.Chain, originalReq: Request): Response {
        val newToken = runBlocking { tokenStore.refresh() } ?: return chain.proceed(originalReq)
        val retryReq = originalReq.newBuilder()
            .removeHeader("Authorization")
            .addHeader("Authorization", "Bearer $newToken")
            .build()
        return chain.proceed(retryReq)
    }
}
```

### Logging (debug 변형만)

```kotlin
@Provides
@Singleton
fun provideOkHttp(
    authInterceptor: AuthInterceptor,
): OkHttpClient = OkHttpClient.Builder()
    .addInterceptor(authInterceptor)
    .apply {
        if (BuildConfig.DEBUG) {
            addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BODY })
        }
    }
    .connectTimeout(15, TimeUnit.SECONDS)
    .readTimeout(15, TimeUnit.SECONDS)
    .build()
```

> release 빌드에서 `BODY` 로깅은 시크릿 누수 위험 — 절대 활성 X.

## JSON — Moshi (또는 kotlinx.serialization)

### Moshi
```kotlin
@JsonClass(generateAdapter = true)
data class ItemDto(
    val id: Long,
    val title: String,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String?,
)
```

### kotlinx.serialization
```kotlin
@Serializable
data class ItemDto(
    val id: Long,
    val title: String,
    @SerialName("created_at") val createdAt: String,
)
```

> 한 프로젝트에서 둘 중 하나만 (혼용 X).

## Repository 에러 처리

```kotlin
class ItemRepositoryImpl @Inject constructor(
    private val api: ItemApi,
) : ItemRepository {
    override suspend fun fetch(): Result<List<Item>> = withContext(Dispatchers.IO) {
        runCatching {
            api.getItems().map { it.toDomain() }
        }.recoverCatching {
            when (it) {
                is HttpException -> when (it.code()) {
                    401 -> throw AuthRequiredException()
                    in 500..599 -> throw ServerErrorException(it.message())
                    else -> throw NetworkException(it.message())
                }
                is IOException -> throw NetworkException("connection failed")
                else -> throw it
            }
        }
    }
}
```

## 오프라인 우선 패턴

```kotlin
override fun observe(): Flow<List<Item>> = flow {
    // 1. 로컬 즉시 emit (stale 데이터)
    emitAll(dao.observeAll().map { list -> list.map { it.toDomain() } })
}.onStart {
    // 2. background 에서 remote 동기화
    coroutineScope { launch { runCatching { syncFromRemote() } } }
}
```

## 금지 사항

- `Call<T>` enqueue / RxJava (Coroutines + Flow 만)
- `OkHttpClient` 인스턴스 여러 개 (Hilt Singleton 단일)
- `runBlocking` (Interceptor 안에서만 한정적 — viewModelScope 안 X)
- 에러 응답 swallow (`.getOrNull()` 만 — 사용자에게 에러 표시 안 함)
- API key / token 을 `User-Agent` 또는 로그에 (interceptor 가 redact)
- `application/json` 외 Content-Type (multipart 는 별도 파일)
- baseUrl 을 release 빌드에 dev URL hardcode (`BuildConfig.API_BASE_URL` 만)
