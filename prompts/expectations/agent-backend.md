# Backend Agent 기대사항

이 파일에 백엔드 에이전트에게 바라는 점을 작성하세요.
Director가 태스크 분해 시 이 내용을 자동으로 반영합니다.

## 예시
- API 설계 시 RESTful 원칙 준수
- 모든 엔드포인트에 Pydantic 스키마 정의
- 에러 응답은 RFC 7807 Problem Details 형식
- DB 쿼리는 SQLAlchemy ORM 사용, raw SQL 지양
- 테스트 커버리지 80% 이상 유지
