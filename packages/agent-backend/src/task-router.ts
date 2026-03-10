import type { Task } from '@agent/core';

export type BackendTaskType =
  | 'api.create'
  | 'api.modify'
  | 'model.create'
  | 'model.modify'
  | 'middleware.create'
  | 'test.create'
  | 'analyze'
  | 'unknown';

/**
 * Task 타입을 판별한다.
 * 1순위: GitHub Issue labels (type:api.create, type:model.create, ...)
 * 2순위: title/description 문자열 매칭 (fallback)
 */
export function detectTaskType(task: Task): BackendTaskType {
  // Labels 기반 (DirectorAgent가 붙이는 type:* labels)
  const labels = task.labels;
  if (labels && labels.length > 0) {
    for (const label of labels) {
      if (label.startsWith('type:')) {
        const type = label.replace('type:', '') as BackendTaskType;
        if (isValidTaskType(type)) return type;
      }
    }
  }

  // Title + description 기반 (fallback)
  const text = `${task.title} ${task.description}`.toLowerCase();

  if (text.includes('analyze') || text.includes('분석') || text.includes('scan')) return 'analyze';
  if (text.includes('test') || text.includes('테스트')) return 'test.create';
  if (text.includes('middleware') || text.includes('미들웨어')) return 'middleware.create';

  // model vs api 판별
  if (text.includes('model') || text.includes('schema') || text.includes('모델') || text.includes('스키마') || text.includes('migration')) {
    return text.includes('modify') || text.includes('수정') || text.includes('변경') ? 'model.modify' : 'model.create';
  }

  if (text.includes('api') || text.includes('endpoint') || text.includes('route') || text.includes('controller')) {
    return text.includes('modify') || text.includes('수정') || text.includes('변경') ? 'api.modify' : 'api.create';
  }

  return 'unknown';
}

const VALID_TYPES: Set<string> = new Set([
  'api.create', 'api.modify', 'model.create', 'model.modify',
  'middleware.create', 'test.create', 'analyze',
]);

function isValidTaskType(type: string): type is BackendTaskType {
  return VALID_TYPES.has(type);
}
