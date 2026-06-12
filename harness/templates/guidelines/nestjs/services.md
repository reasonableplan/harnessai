# NestJS — Service / 비즈니스 로직 컨벤션

> Service, Provider, 순수 로직 코드 작성 시 읽어라.

## Service 레이어

- 비즈니스 로직은 전부 `@Injectable()` Service — Controller/Module 에 로직 금지
- 의존성은 생성자 주입만 (`constructor(private readonly usersRepo: Repository<User>)`) — `new` 직접 생성 금지
- Repository 는 Service 에서만 사용 — `@InjectRepository(Entity)` 패턴
- Service 간 호출은 Module `exports`/`imports` 로 명시 — 순환 의존 발생 시 설계 재검토 (`forwardRef` 는 최후 수단 + 사유 주석)

## core/ — 순수 함수 분리

- 계산/변환/검증 등 I/O 없는 로직은 `core/` 의 순수 함수로 — NestJS DI 컨테이너 밖 (데코레이터 없음)
- `core/` 는 NestJS/TypeORM import 금지 — 프레임워크 독립
- 단위 테스트 커버리지 ≥ 90% — mock 없이 입출력만으로 검증 가능해야 정상

## 트랜잭션

- 다중 쓰기는 `DataSource.transaction()` 으로 묶기 — 부분 커밋 금지

```typescript
await this.dataSource.transaction(async (manager) => {
  await manager.save(order);
  await manager.decrement(Stock, { id: stockId }, 'quantity', qty);
});
```

- 트랜잭션 경계는 Service 메서드 1개 — Controller 에서 여러 Service 호출로 흉내내기 금지

## 로깅 / 에러

- `console.log` 금지 — `private readonly logger = new Logger(ClassName.name)`
- 빈 catch (`catch (e) {}`) 금지 — 최소 `this.logger.error(...)` 후 re-throw 또는 AppException 변환
- 예상 가능한 실패 (중복, 미존재) 는 AppException 으로 — 일반 Error 를 위로 흘리지 않는다

## 외부 API (integrations 있을 때)

- `HttpModule` (axios) 주입 — 타임아웃 명시 필수, 무한 대기 금지
- 외부 응답은 신뢰 경계 밖 — zod 또는 class-transformer 로 파싱 후 사용, raw 객체 그대로 전파 금지
- 실패 시 도메인 AppException 으로 변환 — axios 에러를 Controller 까지 노출 금지
