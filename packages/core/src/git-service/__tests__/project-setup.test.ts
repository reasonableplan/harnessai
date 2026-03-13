import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ProjectSetup } from '../project-setup.js';
import type { GitHubContext } from '../types.js';

vi.mock('../../logging/logger.js', () => ({
  createLogger: () => ({
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  }),
}));

function createMockContext(): GitHubContext {
  return {
    octokit: {
      rest: {
        users: {
          getAuthenticated: vi.fn(),
          getByUsername: vi.fn(),
        },
      },
    } as unknown as GitHubContext['octokit'],
    graphqlWithAuth: vi.fn() as unknown as GitHubContext['graphqlWithAuth'],
    owner: 'test-owner',
    repo: 'test-repo',
  };
}

describe('ProjectSetup', () => {
  let ctx: GitHubContext;
  let setup: ProjectSetup;

  beforeEach(() => {
    ctx = createMockContext();
    setup = new ProjectSetup(ctx);
  });

  describe('findProject', () => {
    it('finds project as user', async () => {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        user: { projectV2: { id: 'proj-user' } },
      });

      const result = await setup.findProject(1);
      expect(result).toBe('proj-user');
    });

    it('falls back to organization on user NOT_FOUND', async () => {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('Could not resolve to a User'))
        .mockResolvedValueOnce({
          organization: { projectV2: { id: 'proj-org' } },
        });

      const result = await setup.findProject(1);
      expect(result).toBe('proj-org');
    });

    it('returns null when both user and org fail with NOT_FOUND', async () => {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('Not Found'))
        .mockRejectedValueOnce(new Error('404 Not Found'));

      const result = await setup.findProject(1);
      expect(result).toBeNull();
    });

    it('re-throws non-404 errors from user query', async () => {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('500 Internal Server Error'));

      await expect(setup.findProject(1)).rejects.toThrow('500');
    });

    it('re-throws non-404 errors from org query', async () => {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('Could not resolve to a User'))
        .mockRejectedValueOnce(new Error('403 Forbidden'));

      await expect(setup.findProject(1)).rejects.toThrow('403');
    });

    it('handles GraphQL NOT_FOUND error type', async () => {
      const gqlError = Object.assign(new Error('GraphQL error'), { errors: [{ type: 'NOT_FOUND' }] });
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(gqlError)
        .mockRejectedValueOnce(gqlError);

      const result = await setup.findProject(1);
      expect(result).toBeNull();
    });
  });

  describe('createProject', () => {
    it('creates project via REST + GraphQL', async () => {
      (ctx.octokit.rest.users.getByUsername as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { node_id: 'owner-node-id' },
      });
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValue({
        createProjectV2: { projectV2: { id: 'new-proj-id' } },
      });

      const result = await setup.createProject('My Board');

      expect(result).toBe('new-proj-id');
      expect(ctx.octokit.rest.users.getByUsername).toHaveBeenCalledWith({ username: 'test-owner' });
      expect(ctx.graphqlWithAuth).toHaveBeenCalledWith(
        expect.stringContaining('createProjectV2'),
        expect.objectContaining({ ownerId: 'owner-node-id', title: 'My Board' }),
      );
    });
  });

  describe('ensureColumns', () => {
    it('populates columnFieldId and columnOptions', async () => {
      setup.projectId = 'proj-1';
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [{
              id: 'field-1', name: 'Status',
              options: [
                { id: 'opt-1', name: 'Backlog' },
                { id: 'opt-2', name: 'Ready' },
                { id: 'opt-3', name: 'In Progress' },
                { id: 'opt-4', name: 'Review' },
                { id: 'opt-5', name: 'Failed' },
                { id: 'opt-6', name: 'Done' },
              ],
            }],
          },
        },
      });

      await setup.ensureColumns();

      expect(setup.columnFieldId).toBe('field-1');
      expect(setup.columnOptions.size).toBe(6);
      expect(setup.columnOptions.get('Done')).toBe('opt-6');
    });

    it('creates missing columns', async () => {
      setup.projectId = 'proj-1';
      // Only has 3 existing columns, missing 3
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [{
              id: 'field-1', name: 'Status',
              options: [
                { id: 'opt-1', name: 'Backlog' },
                { id: 'opt-2', name: 'Ready' },
                { id: 'opt-3', name: 'In Progress' },
              ],
            }],
          },
        },
      });

      // Mock createColumnOption mutations for Review, Failed, Done
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce({
          updateProjectV2Field: {
            projectV2Field: {
              options: [
                { id: 'opt-1', name: 'Backlog' }, { id: 'opt-2', name: 'Ready' },
                { id: 'opt-3', name: 'In Progress' }, { id: 'opt-4', name: 'Review' },
              ],
            },
          },
        })
        .mockResolvedValueOnce({
          updateProjectV2Field: {
            projectV2Field: {
              options: [
                { id: 'opt-1', name: 'Backlog' }, { id: 'opt-2', name: 'Ready' },
                { id: 'opt-3', name: 'In Progress' }, { id: 'opt-4', name: 'Review' },
                { id: 'opt-5', name: 'Failed' },
              ],
            },
          },
        })
        .mockResolvedValueOnce({
          updateProjectV2Field: {
            projectV2Field: {
              options: [
                { id: 'opt-1', name: 'Backlog' }, { id: 'opt-2', name: 'Ready' },
                { id: 'opt-3', name: 'In Progress' }, { id: 'opt-4', name: 'Review' },
                { id: 'opt-5', name: 'Failed' }, { id: 'opt-6', name: 'Done' },
              ],
            },
          },
        });

      await setup.ensureColumns();

      // 1 (fields query) + 3 (create column mutations)
      expect(ctx.graphqlWithAuth).toHaveBeenCalledTimes(4);
      expect(setup.columnOptions.size).toBe(6);
    });

    it('throws when node not found', async () => {
      setup.projectId = 'proj-1';
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: null,
      });

      await expect(setup.ensureColumns()).rejects.toThrow('Project node not found');
    });

    it('throws when Status field not found', async () => {
      setup.projectId = 'proj-1';
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [{ id: 'f1', name: 'Priority', options: [] }],
          },
        },
      });

      await expect(setup.ensureColumns()).rejects.toThrow('Status field not found');
    });

    it('handles Status field with no options', async () => {
      setup.projectId = 'proj-1';
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [{ id: 'field-1', name: 'Status' }], // no options property
          },
        },
      });

      // All 6 columns will need to be created
      for (let i = 0; i < 6; i++) {
        (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
          updateProjectV2Field: {
            projectV2Field: { options: [{ id: `opt-${i}`, name: `col-${i}` }] },
          },
        });
      }

      await setup.ensureColumns();

      // 1 (fields query) + 6 (create column mutations)
      expect(ctx.graphqlWithAuth).toHaveBeenCalledTimes(7);
    });
  });

  describe('validateConnection', () => {
    function mockSuccessfulAuth() {
      (ctx.octokit.rest.users.getAuthenticated as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { login: 'test-user' },
        headers: { 'x-oauth-scopes': 'repo,project' },
      });
    }

    function mockEnsureColumnsSuccess() {
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [{
              id: 'field-1', name: 'Status',
              options: [
                { id: 'o1', name: 'Backlog' }, { id: 'o2', name: 'Ready' },
                { id: 'o3', name: 'In Progress' }, { id: 'o4', name: 'Review' },
                { id: 'o5', name: 'Failed' }, { id: 'o6', name: 'Done' },
              ],
            }],
          },
        },
      });
    }

    it('finds project by number and validates', async () => {
      mockSuccessfulAuth();
      // findProject (user)
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        user: { projectV2: { id: 'proj-found' } },
      });
      mockEnsureColumnsSuccess();

      await setup.validateConnection(42);

      expect(setup.projectId).toBe('proj-found');
    });

    it('throws when project number not found', async () => {
      mockSuccessfulAuth();
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('Not Found'))
        .mockRejectedValueOnce(new Error('Not Found'));

      await expect(setup.validateConnection(999)).rejects.toThrow('Project #999 not found');
    });

    it('finds project by title when no number given', async () => {
      mockSuccessfulAuth();
      // findProjectByTitle
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        user: {
          projectsV2: {
            nodes: [{ id: 'proj-by-title', title: 'Agent Orchestration Board' }],
          },
        },
      });
      mockEnsureColumnsSuccess();

      await setup.validateConnection();

      expect(setup.projectId).toBe('proj-by-title');
    });

    it('creates project when not found by title', async () => {
      mockSuccessfulAuth();
      // findProjectByTitle: user returns empty
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        user: { projectsV2: { nodes: [] } },
      });
      // findProjectByTitle: organization fallback also returns empty
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        organization: { projectsV2: { nodes: [] } },
      });
      // createProject
      (ctx.octokit.rest.users.getByUsername as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { node_id: 'owner-node' },
      });
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        createProjectV2: { projectV2: { id: 'new-proj' } },
      });
      mockEnsureColumnsSuccess();

      await setup.validateConnection();

      expect(setup.projectId).toBe('new-proj');
    });
  });

  describe('createColumnOption (via ensureColumns)', () => {
    it('merges existing options with new one and updates cache', async () => {
      setup.projectId = 'proj-1';

      // ensureColumns first call: returns Status field with only Backlog
      (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        node: {
          fields: {
            nodes: [
              {
                id: 'field-1',
                name: 'Status',
                options: [{ id: 'opt-1', name: 'Backlog' }],
              },
            ],
          },
        },
      });

      // createColumnOption calls for: Ready, In Progress, Review, Failed, Done (5 missing columns)
      const missingColumns = ['Ready', 'In Progress', 'Review', 'Failed', 'Done'];
      const cumulativeOptions = [{ id: 'opt-1', name: 'Backlog' }];
      for (const col of missingColumns) {
        cumulativeOptions.push({ id: `opt-${col}`, name: col });
        (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
          updateProjectV2Field: {
            projectV2Field: {
              options: [...cumulativeOptions],
            },
          },
        });
      }

      await setup.ensureColumns();

      // Verify mutation was called without 'id' in singleSelectOptions input
      // First call is the query, subsequent 5 are mutations
      const firstMutationArgs = (ctx.graphqlWithAuth as ReturnType<typeof vi.fn>).mock.calls[1];
      const vars = firstMutationArgs[1];
      expect(vars.singleSelectOptions).toHaveLength(2); // Backlog + Ready
      expect(vars.singleSelectOptions[0]).toEqual({ name: 'Backlog', color: 'GRAY', description: '' });
      expect(vars.singleSelectOptions[1]).toEqual({ name: 'Ready', color: 'GRAY', description: '' });

      // Cache updated from responses
      expect(setup.columnOptions.get('Ready')).toBe('opt-Ready');
      expect(setup.columnOptions.get('Done')).toBe('opt-Done');
      expect(setup.columnOptions.size).toBe(6);
    });
  });
});
