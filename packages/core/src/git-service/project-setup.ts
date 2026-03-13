import type { GitHubContext } from './types.js';
import { createLogger } from '../logging/logger.js';

const log = createLogger('GitService');

function isNotFoundError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  if (msg.includes('not found') || msg.includes('404') || msg.includes('could not resolve')) return true;
  const gqlErrors = (err as { errors?: Array<{ type?: string }> }).errors;
  if (gqlErrors?.some((e) => e.type === 'NOT_FOUND')) return true;
  return false;
}

const REQUIRED_COLUMNS: readonly string[] = [
  'Backlog',
  'Ready',
  'In Progress',
  'Review',
  'Failed',
  'Done',
];

export class ProjectSetup {
  private ctx: GitHubContext;

  // Shared mutable state — set by ensureColumns, read by other modules
  projectId: string | null = null;
  columnFieldId: string | null = null;
  columnOptions: Map<string, string> = new Map(); // column name → option id

  constructor(ctx: GitHubContext) {
    this.ctx = ctx;
  }

  async validateConnection(projectNumber?: number): Promise<void> {
    // 1. Verify GitHub API access + check token scopes
    const response = await this.ctx.octokit.rest.users.getAuthenticated();
    const user = response.data;
    log.info({ user: user.login }, 'Authenticated');

    // Token scope 경고: classic PAT의 경우 x-oauth-scopes 헤더에서 확인 가능
    // Octokit headers 타입에 x-oauth-scopes 미포함 — unknown으로 안전 접근 후 String 변환
    const scopes = String(
      (response.headers as Record<string, unknown>)['x-oauth-scopes'] ?? '',
    );
    if (scopes) {
      const scopeList = scopes.split(',').map((s) => s.trim());
      if (!scopeList.some((s) => s === 'project' || s === 'read:project')) {
        log.warn('Token may lack "project" scope — Board operations may fail');
      }
    }

    // 2. Find or create Project
    if (projectNumber) {
      this.projectId = await this.findProject(projectNumber);
      if (!this.projectId) {
        throw new Error(`Project #${projectNumber} not found`);
      }
    } else {
      this.projectId = await this.findProjectByTitle('Agent Orchestration Board');
      if (!this.projectId) {
        this.projectId = await this.createProject('Agent Orchestration Board');
        log.info('Project created');
      }
    }

    // 3. Ensure required columns (Status field options)
    await this.ensureColumns();
    log.info({ columnCount: this.columnOptions.size }, 'Board validated');
  }

  async findProject(number: number): Promise<string | null> {
    try {
      const result = await this.ctx.graphqlWithAuth<{
        user: { projectV2: { id: string } };
      }>(
        `query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) { id }
          }
        }`,
        { login: this.ctx.owner, number },
      );
      return result.user.projectV2.id;
    } catch (err) {
      if (!isNotFoundError(err)) throw err;
      // Try as organization
      try {
        const result = await this.ctx.graphqlWithAuth<{
          organization: { projectV2: { id: string } };
        }>(
          `query($login: String!, $number: Int!) {
            organization(login: $login) {
              projectV2(number: $number) { id }
            }
          }`,
          { login: this.ctx.owner, number },
        );
        return result.organization.projectV2.id;
      } catch (err2) {
        if (!isNotFoundError(err2)) throw err2;
        return null;
      }
    }
  }

  private async findProjectByTitle(title: string): Promise<string | null> {
    // user 소유 프로젝트 검색, 실패 시 organization fallback (findProject와 동일 패턴)
    try {
      const result = await this.ctx.graphqlWithAuth<{
        user: { projectsV2: { nodes: Array<{ id: string; title: string }> } };
      }>(
        `query($login: String!) {
          user(login: $login) {
            projectsV2(first: 20) {
              nodes { id title }
            }
          }
        }`,
        { login: this.ctx.owner },
      );
      const project = result.user.projectsV2.nodes.find((p) => p.title === title);
      if (project) return project.id;
    } catch (err) {
      if (!isNotFoundError(err)) throw err;
    }

    // Organization fallback
    try {
      const result = await this.ctx.graphqlWithAuth<{
        organization: { projectsV2: { nodes: Array<{ id: string; title: string }> } };
      }>(
        `query($login: String!) {
          organization(login: $login) {
            projectsV2(first: 20) {
              nodes { id title }
            }
          }
        }`,
        { login: this.ctx.owner },
      );
      const project = result.organization.projectsV2.nodes.find((p) => p.title === title);
      return project?.id ?? null;
    } catch (err) {
      if (!isNotFoundError(err)) throw err;
      return null;
    }
  }

  async createProject(title: string): Promise<string> {
    // Get owner node ID
    const { data: user } = await this.ctx.octokit.rest.users.getByUsername({
      username: this.ctx.owner,
    });

    const result = await this.ctx.graphqlWithAuth<{
      createProjectV2: { projectV2: { id: string } };
    }>(
      `mutation($ownerId: ID!, $title: String!) {
        createProjectV2(input: { ownerId: $ownerId, title: $title }) {
          projectV2 { id }
        }
      }`,
      { ownerId: user.node_id, title },
    );
    return result.createProjectV2.projectV2.id;
  }

  async ensureColumns(): Promise<void> {
    // Get the Status field and its options
    const result = await this.ctx.graphqlWithAuth<{
      node: {
        fields: {
          nodes: Array<{
            id: string;
            name: string;
            options?: Array<{ id: string; name: string }>;
          }>;
        };
      };
    }>(
      `query($projectId: ID!) {
        node(id: $projectId) {
          ... on ProjectV2 {
            fields(first: 20) {
              nodes {
                ... on ProjectV2SingleSelectField {
                  id name options { id name }
                }
              }
            }
          }
        }
      }`,
      { projectId: this.projectId },
    );

    if (!result.node) {
      throw new Error(`Project node not found for projectId: ${this.projectId}`);
    }
    const statusField = result.node.fields.nodes.find((f) => f.name === 'Status');
    if (!statusField) {
      throw new Error('Status field not found in project');
    }

    this.columnFieldId = statusField.id;
    this.columnOptions.clear();

    for (const opt of statusField.options ?? []) {
      this.columnOptions.set(opt.name, opt.id);
    }

    // Create missing columns
    for (const col of REQUIRED_COLUMNS) {
      if (!this.columnOptions.has(col)) {
        await this.createColumnOption(col);
      }
    }
  }

  private async createColumnOption(name: string): Promise<void> {
    if (!this.columnFieldId) {
      throw new Error('columnFieldId is not initialized — call ensureColumns first');
    }

    // Build merged options list: existing options + new one
    // GitHub API no longer accepts 'id' in ProjectV2SingleSelectFieldOptionInput
    const existingOptionNames = Array.from(this.columnOptions.keys());
    const singleSelectOptions = [
      ...existingOptionNames.map((optName) => ({ name: optName, color: 'GRAY' as const, description: '' })),
      { name, color: 'GRAY' as const, description: '' },
    ];

    const result = await this.ctx.graphqlWithAuth<{
      updateProjectV2Field: {
        projectV2Field: {
          options: Array<{ id: string; name: string }>;
        };
      };
    }>(
      `mutation($fieldId: ID!, $singleSelectOptions: [ProjectV2SingleSelectFieldOptionInput!]!) {
        updateProjectV2Field(input: {
          fieldId: $fieldId
          singleSelectOptions: $singleSelectOptions
        }) {
          projectV2Field {
            ... on ProjectV2SingleSelectField { options { id name } }
          }
        }
      }`,
      { fieldId: this.columnFieldId, singleSelectOptions },
    );

    // mutation 응답에서 직접 캐시 업데이트 (ensureColumns 재호출로 인한 무한재귀 방지)
    const updatedOptions = result.updateProjectV2Field.projectV2Field.options;
    for (const opt of updatedOptions) {
      this.columnOptions.set(opt.name, opt.id);
    }
    log.info({ columnName: name }, 'Column created');
  }
}
