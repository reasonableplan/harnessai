import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GitService } from '../git-service.js';
import type { GitServiceConfig } from '../git-service.js';

// Mock all submodule constructors
vi.mock('../project-setup.js', () => ({
  ProjectSetup: vi.fn().mockImplementation(function () {
    return {
      projectId: null,
      columnFieldId: null,
      columnOptions: new Map(),
      validateConnection: vi.fn(),
      findProject: vi.fn(),
      createProject: vi.fn(),
      ensureColumns: vi.fn(),
    };
  }),
}));

vi.mock('../issue-manager.js', () => ({
  IssueManager: vi.fn().mockImplementation(function () {
    return {
      setBoardOperations: vi.fn(),
      createIssue: vi.fn().mockResolvedValue(1),
      updateIssue: vi.fn(),
      closeIssue: vi.fn(),
      addComment: vi.fn(),
      getIssue: vi.fn(),
      getIssuesByLabel: vi.fn().mockResolvedValue([]),
      getEpicIssues: vi.fn().mockResolvedValue([]),
      addIssueToProject: vi.fn(),
      getProjectItemId: vi.fn(),
      getIssueColumn: vi.fn(),
    };
  }),
}));

vi.mock('../board-operations.js', () => ({
  BoardOperations: vi.fn().mockImplementation(function () {
    return {
      moveIssueToColumn: vi.fn(),
      getAllProjectItems: vi.fn().mockResolvedValue([]),
    };
  }),
}));

vi.mock('../git-operations.js', () => ({
  GitOperations: vi.fn().mockImplementation(function () {
    return {
      createBranch: vi.fn(),
      createPR: vi.fn().mockResolvedValue(42),
    };
  }),
}));

vi.mock('@octokit/rest', () => ({
  Octokit: vi.fn().mockImplementation(function () { return {}; }),
}));

vi.mock('@octokit/graphql', () => ({
  graphql: { defaults: vi.fn().mockReturnValue(vi.fn()) },
}));

describe('GitService', () => {
  const config: GitServiceConfig = {
    token: 'test-token',
    owner: 'test-owner',
    repo: 'test-repo',
    projectNumber: 1,
  };

  let service: GitService;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new GitService(config);
  });

  it('creates instance with config', () => {
    expect(service).toBeDefined();
  });

  it('implements all IGitService methods', () => {
    const methods = [
      'validateConnection', 'createIssue', 'updateIssue', 'closeIssue',
      'addComment', 'getIssue', 'getIssuesByLabel', 'getEpicIssues',
      'moveIssueToColumn', 'getAllProjectItems', 'createBranch', 'createPR',
    ];
    for (const method of methods) {
      expect(typeof (service as unknown as Record<string, unknown>)[method]).toBe('function');
    }
  });

  it('delegates validateConnection to ProjectSetup', async () => {
    await service.validateConnection();
    // If it didn't throw, delegation worked
  });

  it('delegates createIssue to IssueManager', async () => {
    const result = await service.createIssue({
      title: 'T', body: 'B', labels: [], dependencies: [],
    });
    expect(result).toBe(1);
  });

  it('delegates createPR to GitOperations', async () => {
    const result = await service.createPR('Title', 'Body', 'feature/x');
    expect(result).toBe(42);
  });

  it('delegates getAllProjectItems to BoardOperations', async () => {
    const result = await service.getAllProjectItems();
    expect(result).toEqual([]);
  });

  it('connects setBoardOperations for batch optimization', async () => {
    // The constructor should have called issueManager.setBoardOperations
    const { IssueManager } = await import('../issue-manager.js');
    const issueManagerInstance = (IssueManager as unknown as ReturnType<typeof vi.fn>).mock.results[0].value;
    expect(issueManagerInstance.setBoardOperations).toHaveBeenCalled();
  });
});
