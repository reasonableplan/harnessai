import { describe, it, expect, vi } from 'vitest';
import { FollowUpCreator } from './follow-up-creator.js';
import type { IGitService, Task, FollowUp } from '../types/index.js';

function createMockGitService(): IGitService {
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn().mockResolvedValue(100),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn(),
    getIssuesByLabel: vi.fn().mockResolvedValue([]),
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn(),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn(),
  };
}

function createTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: 'epic-1',
    title: 'Create user API',
    description: 'Create REST API for users',
    assignedAgent: 'backend',
    status: 'in-progress',
    githubIssueNumber: 42,
    boardColumn: 'In Progress',
    dependencies: [],
    priority: 3,
    complexity: 'medium',
    retryCount: 0,
    artifacts: [],
    ...overrides,
  };
}

describe('FollowUpCreator', () => {
  it('후속 이슈를 생성한다', async () => {
    const gitService = createMockGitService();
    const creator = new FollowUpCreator(gitService);
    const task = createTask();

    const followUps: FollowUp[] = [
      {
        title: '[FE] API 연동: Create user API',
        targetAgent: 'frontend',
        type: 'api-hook',
        description: 'Frontend API hook 구현',
        dependencies: [42],
      },
    ];

    const created = await creator.createFollowUps(task, followUps);
    expect(created).toEqual([100]);
    expect(gitService.createIssue).toHaveBeenCalledTimes(1);
  });

  it('중복 이슈가 있으면 생성하지 않는다', async () => {
    const gitService = createMockGitService();
    (gitService.getEpicIssues as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        issueNumber: 99,
        title: '[FE] API 연동: Create user API',
        body: '',
        labels: [],
        column: 'Backlog',
        dependencies: [],
        assignee: null,
        generatedBy: '',
        epicId: null,
      },
    ]);

    const creator = new FollowUpCreator(gitService);
    const task = createTask();

    const followUps: FollowUp[] = [
      {
        title: '[FE] API 연동: Create user API',
        targetAgent: 'frontend',
        type: 'api-hook',
        description: 'Frontend API hook 구현',
        dependencies: [42],
      },
    ];

    const created = await creator.createFollowUps(task, followUps);
    expect(created).toEqual([]);
    expect(gitService.createIssue).not.toHaveBeenCalled();
  });

  it('이슈 생성 실패 시 다른 후속 이슈에 영향을 주지 않는다', async () => {
    const gitService = createMockGitService();
    (gitService.createIssue as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('API error'))
      .mockResolvedValueOnce(101);

    const creator = new FollowUpCreator(gitService);
    const task = createTask();

    const followUps: FollowUp[] = [
      {
        title: '[FE] Hook 1',
        targetAgent: 'frontend',
        type: 'api-hook',
        description: 'test',
        dependencies: [],
      },
      {
        title: '[DOCS] Docs 1',
        targetAgent: 'docs',
        type: 'docs',
        description: 'test',
        dependencies: [],
      },
    ];

    const created = await creator.createFollowUps(task, followUps);
    expect(created).toEqual([101]);
  });
});

describe('FollowUpCreator.backendFollowUps', () => {
  it('API 파일이 있으면 FE/DOCS 후속 이슈를 생성한다', () => {
    const task = createTask();
    const files = ['src/routes/users.ts', 'src/controllers/users.controller.ts'];
    const followUps = FollowUpCreator.backendFollowUps(task, 'Created user API', files);

    expect(followUps).toHaveLength(2);
    expect(followUps[0].targetAgent).toBe('frontend');
    expect(followUps[1].targetAgent).toBe('docs');
  });

  it('API 파일이 없으면 후속 이슈를 생성하지 않는다', () => {
    const task = createTask();
    const files = ['src/utils/helpers.ts'];
    const followUps = FollowUpCreator.backendFollowUps(task, 'Added helper', files);

    expect(followUps).toHaveLength(0);
  });
});

describe('FollowUpCreator.frontendFollowUps', () => {
  it('컴포넌트 파일이 있으면 DOCS 후속 이슈를 생성한다', () => {
    const task = createTask();
    const files = ['src/components/UserCard.tsx'];
    const followUps = FollowUpCreator.frontendFollowUps(task, 'Created UserCard', files);

    expect(followUps).toHaveLength(1);
    expect(followUps[0].targetAgent).toBe('docs');
  });
});
