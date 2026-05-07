# iOS Swift — Network Guidelines

## URLSession + async/await + Codable

별도 HTTP 라이브러리 (Alamofire 등) 사용 금지 — 표준 URLSession + Codable 충분.

```swift
// Data/Remote/APIClient.swift
actor APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let tokenProvider: () async -> String?

    init(
        baseURL: URL,
        tokenProvider: @escaping () async -> String?,
        session: URLSession = .shared,
    ) {
        self.baseURL = baseURL
        self.session = session
        self.tokenProvider = tokenProvider
        self.decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        self.encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        try await request(path, method: "GET", body: Empty(), as: type)
    }

    func post<Body: Encodable, T: Decodable>(_ path: String, body: Body, as type: T.Type = T.self) async throws -> T {
        try await request(path, method: "POST", body: body, as: type)
    }

    private func request<Body: Encodable, T: Decodable>(
        _ path: String,
        method: String,
        body: Body,
        as type: T.Type,
    ) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = await tokenProvider() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if !(body is Empty) {
            req.httpBody = try encoder.encode(body)
        }

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        switch http.statusCode {
        case 200..<300:
            return try decoder.decode(T.self, from: data)
        case 401:
            throw APIError.authRequired
        case 400..<500:
            throw APIError.client(statusCode: http.statusCode, data: data)
        case 500..<600:
            throw APIError.server(statusCode: http.statusCode)
        default:
            throw APIError.invalidResponse
        }
    }
}

private struct Empty: Codable {}

enum APIError: LocalizedError {
    case invalidResponse
    case authRequired
    case client(statusCode: Int, data: Data)
    case server(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "응답을 파싱할 수 없습니다"
        case .authRequired: return "다시 로그인이 필요합니다"
        case .client(let code, _): return "요청 오류 (\(code))"
        case .server(let code): return "서버 오류 (\(code))"
        }
    }
}
```

## 401 Refresh + Retry

```swift
extension APIClient {
    /// 401 발생 시 refresh → 원 요청 재시도 (1회).
    func authenticatedRequest<Body: Encodable, T: Decodable>(
        _ path: String,
        method: String,
        body: Body,
        as type: T.Type,
        authService: AuthService,
    ) async throws -> T {
        do {
            return try await request(path, method: method, body: body, as: type)
        } catch APIError.authRequired {
            try await authService.refreshTokens()
            return try await request(path, method: method, body: body, as: type)
        }
    }
}
```

> **무한 재시도 금지** — 1회만. refresh 도 실패하면 logout flow.

## DTO 정의

```swift
struct ItemDTO: Codable {
    let id: Int
    let title: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title
        case createdAt = "created_at"
    }
}
```

> snake_case 자동 변환 사용 시 `CodingKeys` 생략 가능. 단 일부 필드만 다른 경우는 명시.

## 로깅 (debug Configuration 만)

```swift
#if DEBUG
private final class LoggingDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, didFinishCollecting metrics: URLSessionTaskMetrics) {
        Logger.api.debug("\(task.originalRequest?.httpMethod ?? "?") \(task.originalRequest?.url?.absoluteString ?? "?") — \(metrics.taskInterval.duration * 1000, format: .fixed(precision: 0))ms")
    }
}
#endif
```

> Release 빌드에서 BODY 로깅은 시크릿 누수 위험 — 절대 활성 X.

## Repository 패턴

```swift
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

## 오프라인 우선 패턴

```swift
func observe() -> AsyncStream<[Item]> {
    AsyncStream { continuation in
        let task = Task {
            // 1. 로컬 즉시 emit
            continuation.yield(local.all().map { $0.toDomain() })

            // 2. background 에서 remote 동기화
            do {
                let remote = try await fetch()
                continuation.yield(remote)
            } catch {
                Logger.repo.error("sync failed: \(error)")
                // stale 데이터 유지
            }
        }
        continuation.onTermination = { _ in task.cancel() }
    }
}
```

## 금지 사항

- Alamofire / Moya / 별도 HTTP 라이브러리 (URLSession + Codable 만)
- `URLSession.shared.dataTask(with:completionHandler:)` 신규 (async/await 만)
- Combine 의 `URLSession.dataTaskPublisher` 신규 사용 (async/await 만)
- 에러 swallow (`try?` — 사용자에게 에러 표시 안 함)
- API key / token 을 로그에 출력 (Logger 가 redact)
- `application/json` 외 Content-Type (multipart 는 별도)
- baseURL 을 release 빌드에 dev URL hardcode (xcconfig 의 `API_BASE_URL` 만)
- `sleep` / 동기 wait (URLSession.shared.synchronousRequest 같은 hack)
