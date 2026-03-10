import type { ApiSpec } from '@agent/core';

/**
 * Issue body에서 API 스펙 JSON 블록을 추출한다.
 * Backend Agent가 생성한 follow-up issue body에서 API 스펙을 파싱한다.
 * 형식: ## API 스펙\n```json\n{...}\n```
 *
 * @returns 파싱된 ApiSpec 또는 null (포맷 불일치 시)
 */
export function parseApiSpec(issueBody: string): ApiSpec | null {
  const match = issueBody.match(/## API 스펙\s*```json\s*([\s\S]*?)```/);
  if (!match) return null;

  try {
    return JSON.parse(match[1]) as ApiSpec;
  } catch {
    return null;
  }
}
