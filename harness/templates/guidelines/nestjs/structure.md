# NestJS — 패키지 구조 컨벤션

> Module 생성, 파일 배치, 설정/테스트 작성 시 읽어라.

## 표준 레이아웃

```
src/
  main.ts              # bootstrap — ValidationPipe, CORS, Swagger, GlobalExceptionFilter
  app.module.ts        # Root — ConfigModule.forRoot + 도메인 Module 조립만
  config/
    configuration.ts   # @nestjs/config 스키마 (env 검증)
  common/              # Guards / Interceptors / Filters / Decorators / 공통 DTO
  <domain>/            # 도메인 Module 단위 — module/controller/service/dto/entities
  database/            # TypeORM forRoot + migrations/
```

- 도메인 추가 = 디렉토리 1개 + Module 1개 — 파일을 레이어별 전역 디렉토리 (`controllers/`, `services/`) 에 흩뿌리지 않는다
- `common/` 은 2개 이상 도메인이 쓰는 것만 — 단일 도메인 자원은 해당 도메인 하위에 colocate

## 네이밍

- 파일: kebab-case + 역할 도트 접미사 — `users.controller.ts` / `users.service.ts` / `create-user.dto.ts` / `user.entity.ts`
- 클래스: `UsersController` / `UsersService` / `CreateUserDto` / `User` (Entity 는 단수)
- 커스텀 데코레이터/가드: `current-user.decorator.ts` / `jwt-auth.guard.ts`

## 환경변수 / 설정

- `@nestjs/config` + `configuration.ts` 중앙 관리 — `process.env.X` 직접 접근은 `config/` 안에서만
- 필수 env 는 부팅 시 검증 (Joi 또는 zod) — 누락 시 기동 실패가 정상 (fail fast)
- `.env.example` 동기화 — env 추가 시 같은 커밋에서
- forRoot/forRootAsync 에 시크릿 하드코딩 금지

## Entity (persistence)

- BaseEntity 상속: `@PrimaryGeneratedColumn` + `@CreateDateColumn`/`@UpdateDateColumn({ type: 'timestamptz' })` (LESSON-003/004)
- 마이그레이션: `typeorm migration:generate` 후 생성 파일 수동 검토 — `synchronize: true` 는 prod 금지

## 테스트

- 단위: `Test.createTestingModule` + provider mock — `<name>.service.spec.ts` 를 소스 옆에 colocate
- e2e: `test/` 하위 supertest — 핵심 흐름 (인증, 도메인 CRUD) 만
- `core/` 순수 함수는 mock 없이 직접 검증

## 금지 사항

- 순환 import — Module 의존은 단방향 유지
- Barrel re-export (`index.ts` 로 전역 노출) — 명시적 경로 import
- `synchronize: true` 프로덕션
