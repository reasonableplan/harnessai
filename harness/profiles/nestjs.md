---
id: nestjs
name: NestJS Backend
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "backend/", "apps/backend/", "apps/api/", "services/api/"]
detect:
  files: [package.json, nest-cli.json]
  contains:
    package.json: ['"@nestjs/core"']

components:
  - id: persistence
    required: true
    skeleton_section: persistence
    description: TypeORM Entity + @Column 스타일 + migration
  - id: auth
    required: false
    skeleton_section: auth
    description: Passport JWT (access/refresh) + JwtAuthGuard + token_version
  - id: interface.http
    required: true
    skeleton_section: interface.http
    description: NestJS Controller + DTO (class-validator) + Swagger 데코레이터
  - id: integrations
    required: false
    skeleton_section: integrations
    description: 3rd party API 클라이언트 (HttpModule) + webhook
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 함수 (core/) + I/O 분리 — Service 레이어와 분리
  - id: errors
    required: true
    skeleton_section: errors
    description: AppException 계층 + GlobalExceptionFilter → { error, code, details }

skeleton_sections:
  required: [overview, stack, errors, interface.http, core.logic, tasks, notes]
  optional: [requirements, configuration, environments, auth, persistence, integrations, state.flow, observability, deployment, test_strategy, ci_cd, rate_limiting]
  order: [overview, requirements, stack, configuration, environments, errors, auth, persistence, integrations, interface.http, rate_limiting, state.flow, core.logic, observability, deployment, test_strategy, ci_cd, tasks, notes]

toolchain:
  install: "pnpm install"
  test: "pnpm test"
  lint: "pnpm lint"
  type: "pnpm exec tsc --noEmit"
  format: "pnpm format"

whitelist:
  runtime:
    - "@nestjs/core"
    - "@nestjs/common"
    - "@nestjs/platform-express"
    - "@nestjs/config"
    - "@nestjs/typeorm"
    - "@nestjs/jwt"
    - "@nestjs/passport"
    - "@nestjs/swagger"
    - "@nestjs/throttler"
    - typeorm
    - passport
    - passport-jwt
    - class-validator
    - class-transformer
    - bcrypt
    - rxjs
    - reflect-metadata
  dev:
    - "@nestjs/testing"
    - "@nestjs/cli"
    - jest
    - ts-jest
    - supertest
    - typescript
    - eslint
    - prettier
    - "@types/node"
    - "@types/jest"
    - "@types/express"
    - "@types/express"
    - "@types/passport-jwt"
    - "@types/bcrypt"
    - "@types/supertest"
  prefix_allowed:
    - "@nestjs/"

file_structure: |
  backend/
    package.json
    nest-cli.json
    tsconfig.json
    tsconfig.build.json
    .env.example
    src/
      main.ts                       # NestJS bootstrap (ValidationPipe, CORS, Swagger)
      app.module.ts                 # Root Module
      config/
        configuration.ts            # @nestjs/config 스키마
      common/
        filters/
          http-exception.filter.ts  # GlobalExceptionFilter → { error, code, details }
        interceptors/
          transform.interceptor.ts  # 응답 래핑 (camelCase 변환)
        guards/
          jwt-auth.guard.ts
        decorators/
          current-user.decorator.ts
        dto/
          pagination.dto.ts         # PageOptionsDto / PageDto<T>
      auth/
        auth.module.ts
        auth.controller.ts
        auth.service.ts
        strategies/
          jwt.strategy.ts           # access token
          jwt-refresh.strategy.ts   # refresh token (httpOnly 쿠키)
        dto/
          login.dto.ts
          token-response.dto.ts
      <domain>/
        <domain>.module.ts
        <domain>.controller.ts
        <domain>.service.ts
        dto/
          create-<domain>.dto.ts
          update-<domain>.dto.ts
          <domain>-response.dto.ts
        entities/
          <domain>.entity.ts        # TypeORM @Entity
      database/
        database.module.ts          # TypeORM forRoot (DataSource)
        migrations/
    test/
      app.e2e-spec.ts
      jest-e2e.json

provides_capabilities:
  - http_server
  - env_config
  - production_concerns

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-eng-review]
  after_build: [review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-002   # limit 상한 화면별
  - LESSON-003   # updated_at 자동 갱신 — @UpdateDateColumn()
  - LESSON-004   # DateTime timezone — Column({ type: 'timestamptz' })
  - LESSON-007   # ID 타입 통일 — @PrimaryGeneratedColumn() vs UUID
  - LESSON-018   # 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수)
  - LESSON-022   # JWT type claim — "access" / "refresh" 구분
  - LESSON-023   # token_version — logout 시 증가, 검증 필수
  - LESSON-024   # refresh endpoint — httpOnly 쿠키 전용
  - LESSON-027   # access token — 인메모리 저장, localStorage 금지
---

# NestJS Backend Profile

## 핵심 원칙

- **Module 단위 캡슐화** — 도메인별 `<Domain>Module` (UserModule, AuthModule 등)
- **Controller는 HTTP 처리만** — 비즈니스 로직은 Service 레이어
- **DTO + class-validator** — `ValidationPipe({ whitelist: true, transform: true })` 전역 적용
- **GlobalExceptionFilter** — 모든 예외를 `{ error, code, details }` 형식으로 통일
- **응답 camelCase** — `TransformInterceptor` 또는 TypeORM Entity 에 `@Expose()` + `excludeExtraneousValues`
- **HTTP 500 내부 에러 미노출** — `SERVER_001` 코드만 반환
- **datetime은 `timestamptz`** — timezone-naive 금지 (LESSON-004)

## components.persistence

- TypeORM `@Entity()` + `@Column()` 스타일 일관성
- BaseEntity 상속:
  ```typescript
  @Entity()
  export abstract class BaseEntity {
    @PrimaryGeneratedColumn()
    id: number;

    @CreateDateColumn({ type: 'timestamptz' })
    createdAt: Date;

    @UpdateDateColumn({ type: 'timestamptz' })   // LESSON-003
    updatedAt: Date;
  }
  ```
- 마이그레이션: `typeorm migration:generate` 후 **생성된 파일 수동 검토**
- 인덱스: `@Index(['column'])` — skeleton.persistence 섹션과 1:1 일치

## components.interface.http

- 에러 응답 공통 래퍼: `{ error: string, code: string, details?: object }`
- 페이지네이션: `{ items: T[], total: number, page: number, limit: number }` (LESSON-002)
- `@ApiTags()` / `@ApiOperation()` / `@ApiResponse()` — Swagger 데코레이터 필수
- 인증 필요 엔드포인트: `@UseGuards(JwtAuthGuard)` + `@ApiBearerAuth()`
- DTO: `class-validator` 데코레이터 전부 명시 (`@IsString()`, `@IsInt()`, `@Min()` 등)

## components.auth

- Passport JWT 2-strategy: `JwtStrategy` (access) + `JwtRefreshStrategy` (refresh)
- JWT payload: `{ sub: userId, type: 'access'|'refresh', ver: tokenVersion, exp }` (LESSON-022)
- User Entity 에 `tokenVersion: number` 필드 — logout 시 증가 (LESSON-023)
- refresh endpoint: `@Post('/auth/refresh')` — httpOnly 쿠키에서만 읽음, body 수락 금지 (LESSON-024)
- access token 저장: **인메모리** — localStorage/sessionStorage 금지 (LESSON-027)

## components.core.logic

- `core/` 디렉토리: 순수 함수만. I/O 금지. NestJS Provider 아님 (DI 컨테이너 outside)
- `common/` 디렉토리: Guards, Interceptors, Filters, Decorators, 공통 DTO
- 테스트: core/ 는 단위 테스트 커버리지 ≥ 90%, Service 는 통합 테스트

## 에러 코드 체계

```
AUTH_001: 인증 실패 (401)
AUTH_002: 토큰 만료 (401)
AUTH_003: 권한 없음 (403)
VALIDATION_001: 입력값 검증 실패 (422)
RESOURCE_001: 리소스 없음 (404)
RESOURCE_002: 중복 리소스 (409)
SERVER_001: 내부 서버 에러 (500)
```

## 금지 사항

- `any` 타입 — `unknown` + type guard 사용
- Controller 안에서 직접 DB 쿼리 (TypeORM Repository 는 Service 에서만)
- `console.log` — NestJS Logger 사용 (`this.logger = new Logger(ClassName.name)`)
- `except Exception: pass` 에 해당하는 `catch (e) {}` 빈 catch — 최소 Logger.error
- raw SQL 문자열 concat — TypeORM QueryBuilder 또는 `Repository.find()`
- `@Injectable()` 없는 클래스에 비즈니스 로직 — 반드시 Service Provider
- forRoot / forRootAsync 에 시크릿 하드코딩 — `@nestjs/config` 경유

## 검증 명령

```bash
cd backend
pnpm install
pnpm test
pnpm lint
pnpm exec tsc --noEmit
```
