# NestJS — API 레이어 컨벤션

> Controller, DTO, 에러 응답 코드 작성 시 읽어라.

## Controller 규칙

- Controller 는 HTTP 처리만 — 비즈니스 로직/DB 쿼리는 Service 경유
- 도메인별 1 Controller (`users.controller.ts`) — 라우트 prefix 는 복수형 (`@Controller('users')`)
- HTTP 상태: 생성 `201`, 삭제 `204` (`@HttpCode(204)`), 조회 `200`
- Swagger 데코레이터 필수: `@ApiTags()` / `@ApiOperation()` / `@ApiResponse()`
- 인증 엔드포인트: `@UseGuards(JwtAuthGuard)` + `@ApiBearerAuth()` + `@CurrentUser()` 데코레이터

## DTO + 검증

```typescript
// dto/create-user.dto.ts
export class CreateUserDto {
  @ApiProperty()
  @IsEmail()
  email: string;

  @ApiProperty({ minLength: 8 })
  @IsString()
  @MinLength(8)
  password: string;
}
```

- 모든 body/query 는 DTO class + class-validator 데코레이터 — `any` / 인라인 객체 타입 금지
- `ValidationPipe({ whitelist: true, transform: true })` 전역 적용 전제 — DTO 에 없는 필드는 자동 제거
- 응답도 DTO (`<domain>-response.dto.ts`) — Entity 직접 반환 금지 (password 등 컬럼 누출)

## 에러 응답 — 공통 래퍼

- GlobalExceptionFilter 가 모든 예외를 `{ error, code, details? }` 로 통일
- 도메인 예외는 AppException 계층에서 던지고 code 는 skeleton errors 섹션의 체계와 1:1 (`AUTH_001`, `RESOURCE_001` ...)
- HTTP 500 에 내부 에러 메시지/스택 미포함 — `SERVER_001` 코드만

## 페이지네이션

- 요청: `PageOptionsDto` (`page`, `limit` — `@Max()` 상한 필수, LESSON-002)
- 응답: `{ items: T[], total: number, page: number, limit: number }`

## 금지 사항

- Controller 에서 Repository 직접 주입/쿼리
- DTO 없이 `@Body() body: any`
- 핸들러에서 raw `throw new Error()` — AppException 계층 사용
- 응답 형식 엔드포인트마다 제각각 — 래퍼/페이지네이션 형식 고정
