import type { Task } from '@agent/core';

export type DocsTaskType =
  | 'readme.generate'
  | 'readme.update'
  | 'api-docs.generate'
  | 'api-docs.update'
  | 'changelog.update'
  | 'architecture.generate'
  | 'jsdoc.add'
  | 'contributing.generate'
  | 'env-example.update'
  | 'activity-log.generate'
  | 'report.daily'
  | 'report.epic'
  | 'analyze'
  | 'unknown';

const VALID_TYPES: Set<string> = new Set([
  'readme.generate', 'readme.update',
  'api-docs.generate', 'api-docs.update',
  'changelog.update',
  'architecture.generate',
  'jsdoc.add',
  'contributing.generate',
  'env-example.update',
  'activity-log.generate',
  'report.daily', 'report.epic',
  'analyze',
]);

/**
 * Task 타입을 판별한다.
 * 1순위: GitHub Issue labels (type:readme.generate, type:changelog.update, ...)
 * 2순위: title/description 문자열 매칭 (fallback, 한국어 포함)
 */
export function detectTaskType(task: Task): DocsTaskType {
  // Labels 기반 (DirectorAgent가 붙이는 type:* labels)
  const labels = task.labels;
  if (labels && labels.length > 0) {
    for (const label of labels) {
      if (label.startsWith('type:')) {
        const type = label.replace('type:', '');
        if (VALID_TYPES.has(type)) return type as DocsTaskType;
      }
    }
  }

  // Title + description 기반 (fallback)
  const text = `${task.title} ${task.description}`.toLowerCase();

  // 1. 명확한 의도 키워드
  if (text.includes('analyze') || text.includes('분석')) return 'analyze';
  if (text.includes('report') || text.includes('리포트') || text.includes('보고서')) {
    if (text.includes('epic') || text.includes('에픽')) return 'report.epic';
    return 'report.daily';
  }

  // 2. 문서 타입별 키워드 (변경 이력 → changelog 먼저 체크, 이력 단독 → activity-log)
  if (text.includes('jsdoc') || text.includes('tsdoc') || text.includes('주석')) return 'jsdoc.add';
  if (text.includes('changelog') || text.includes('변경 이력') || text.includes('변경이력') || text.includes('릴리스 노트')) return 'changelog.update';
  if (text.includes('activity') || text.includes('작업 이력') || text.includes('작업 기록')) return 'activity-log.generate';
  if (text.includes('contributing') || text.includes('기여 가이드')) return 'contributing.generate';
  if (text.includes('.env') || text.includes('환경 변수') || text.includes('env example')) return 'env-example.update';
  if (text.includes('architecture') || text.includes('아키텍처') || text.includes('구조도')) return 'architecture.generate';

  // 3. API 문서
  if (text.includes('api doc') || text.includes('api 문서') || text.includes('swagger') || text.includes('openapi')) {
    return text.includes('update') || text.includes('수정') || text.includes('갱신') ? 'api-docs.update' : 'api-docs.generate';
  }

  // 4. README (가장 일반적이므로 마지막)
  if (text.includes('readme') || text.includes('리드미')) {
    return text.includes('update') || text.includes('수정') || text.includes('갱신') ? 'readme.update' : 'readme.generate';
  }

  // 5. 문서 관련 키워드 — 생성/작성 의도가 명확한 경우만 readme로, 아니면 analyze
  if (text.includes('document') || text.includes('문서')) {
    if (text.includes('generate') || text.includes('create') || text.includes('작성') || text.includes('생성')) {
      return 'readme.generate';
    }
    return 'analyze';
  }

  return 'unknown';
}
