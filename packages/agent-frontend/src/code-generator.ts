import { BaseCodeGenerator } from '@agent/core';
import type { FrontendTaskType } from './task-router.js';

/**
 * Claude API를 사용하여 프론트엔드 코드를 생성하는 엔진.
 * 각 task type에 맞는 시스템 프롬프트를 제공한다.
 */
export class CodeGenerator extends BaseCodeGenerator<FrontendTaskType> {
  constructor(claude: ConstructorParameters<typeof BaseCodeGenerator>[0], workDir?: string) {
    super(claude, workDir, 'FrontendCodeGen');
  }

  protected buildSystemPrompt(taskType: FrontendTaskType): string {
    const base = `You are a frontend code generator for a React/TypeScript project.
Generate production-quality code following these conventions:
- React 18+ with functional components and hooks
- TypeScript strict mode
- Tailwind CSS for styling
- Zustand for state management
- Named exports (not default exports)
- Props interface defined above component
- File naming: PascalCase for components, camelCase for hooks/utils
- Vitest + Testing Library for tests

IMPORTANT: Respond with valid JSON only. No markdown, no explanation.
{
  "files": [
    {
      "path": "src/components/Example.tsx",
      "content": "// full file content here",
      "action": "create",
      "language": "typescriptreact"
    }
  ],
  "summary": "Brief description of what was generated"
}`;

    const typeSpecific: Record<string, string> = {
      'component.create': `\n\nGenerate a React component with:
- Component file (src/components/<Name>/<Name>.tsx) with props interface
- Test file (src/components/<Name>/<Name>.test.tsx) with Vitest + Testing Library
- Index file (src/components/<Name>/index.ts) for re-export`,

      'component.modify': `\n\nModify an existing React component. Update only the files that need changes.
Use action "update" for modified files.`,

      'page.create': `\n\nGenerate a page component with:
- Page file (src/pages/<Name>.tsx) with route-specific logic
- Route registration update (src/router.tsx, action: "update")
- Any required hooks for API integration`,

      'page.modify': `\n\nModify an existing page. Update only the affected files.`,

      'hook.create': `\n\nGenerate a custom React hook with:
- Hook file (src/hooks/use<Name>.ts) following React hooks conventions
- Test file (src/hooks/use<Name>.test.ts)
- Proper TypeScript typing for parameters and return values`,

      'store.create': `\n\nGenerate a Zustand store with:
- Store file (src/stores/use<Name>Store.ts) with typed state and actions
- Test file (src/stores/use<Name>Store.test.ts)
- Selectors for computed values if applicable`,

      'style.generate': `\n\nGenerate styling with Tailwind CSS:
- Utility classes directly in components
- Custom CSS only when Tailwind classes are insufficient`,

      'test.create': `\n\nGenerate test files with:
- Test file (src/__tests__/<target>.test.tsx) using Vitest + Testing Library
- Mock setup for external dependencies (API calls, stores)
- Cover happy path + error cases + edge cases`,

      analyze: `\n\nAnalyze the described frontend code and respond with:
- files: [] (empty — analysis produces no files)
- summary: detailed analysis results as a string`,
    };

    return base + (typeSpecific[taskType] ?? '');
  }
}
