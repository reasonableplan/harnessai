import type { Task } from '@agent/core';

export type FrontendTaskType =
  | 'component.create'
  | 'component.modify'
  | 'page.create'
  | 'page.modify'
  | 'hook.create'
  | 'store.create'
  | 'style.generate'
  | 'test.create'
  | 'analyze'
  | 'unknown';

/**
 * Task 타입을 판별한다.
 * 1순위: GitHub Issue labels (type:component.create, type:page.create, ...)
 * 2순위: title/description 문자열 매칭 (fallback, 한국어 포함)
 *
 * 매칭 순서: 구체적인 키워드 → 넓은 키워드 순서로 배치하여 false positive를 방지한다.
 */
export function detectTaskType(task: Task): FrontendTaskType {
  // Labels 기반 (DirectorAgent가 붙이는 type:* labels)
  const labels = task.labels;
  if (labels && labels.length > 0) {
    for (const label of labels) {
      if (label.startsWith('type:')) {
        const type = label.replace('type:', '') as FrontendTaskType;
        if (VALID_TYPES.has(type)) return type;
      }
    }
  }

  // Title + description 기반 (fallback)
  const text = `${task.title} ${task.description}`.toLowerCase();
  const original = `${task.title} ${task.description}`;

  // 1. 명확한 의도 키워드 (다른 타입과 겹칠 가능성 낮음)
  if (text.includes('analyze') || text.includes('분석') || text.includes('scan')) return 'analyze';
  if (text.includes('test') || text.includes('테스트')) return 'test.create';

  // 2. hook (useXxx 패턴은 원본 케이스로 매칭)
  if (text.includes('hook') || text.includes('훅') || /\buse[A-Z]/.test(original)) return 'hook.create';

  // 3. store (Zustand 등) — \bstore\b로 restore 등 false positive 방지
  if (/\bstore\b/.test(text) || text.includes('zustand') || text.includes('state management') || text.includes('상태관리')) return 'store.create';

  // 4. page vs component (구체적 키워드)
  if (text.includes('page') || text.includes('페이지') || text.includes('route') || text.includes('라우트')) {
    return text.includes('modify') || text.includes('수정') || text.includes('변경') ? 'page.modify' : 'page.create';
  }

  if (text.includes('component') || text.includes('컴포넌트') || text.includes('modal') || text.includes('widget')) {
    return text.includes('modify') || text.includes('수정') || text.includes('변경') ? 'component.modify' : 'component.create';
  }

  // 5. style — 가장 넓은 키워드이므로 마지막에 배치
  if (text.includes('style') || text.includes('스타일') || text.includes('css') || text.includes('tailwind')) return 'style.generate';

  return 'unknown';
}

const VALID_TYPES: Set<string> = new Set([
  'component.create', 'component.modify', 'page.create', 'page.modify',
  'hook.create', 'store.create', 'style.generate', 'test.create', 'analyze',
]);
