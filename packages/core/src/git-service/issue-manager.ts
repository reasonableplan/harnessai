import type { IssueSpec, BoardIssue } from '../types/index.js';
import type { GitHubContext } from './types.js';
import type { ProjectSetup } from './project-setup.js';
import type { BoardOperations } from './board-operations.js';
import { toBoardIssue } from './issue-parser.js';

export class IssueManager {
  private ctx: GitHubContext;
  private setup: ProjectSetup;
  private boardOps: BoardOperations | null = null;

  constructor(ctx: GitHubContext, setup: ProjectSetup) {
    this.ctx = ctx;
    this.setup = setup;
  }

  /** BoardOperations 참조 설정 (순환 의존 방지용 lazy init) */
  setBoardOperations(boardOps: BoardOperations): void {
    this.boardOps = boardOps;
  }

  async createIssue(spec: IssueSpec): Promise<number> {
    // Build body with dependencies info
    let body = spec.body;
    if (spec.dependencies.length > 0) {
      const depLinks = spec.dependencies.map((n) => `- #${n}`).join('\n');
      body += `\n\n### Dependencies\n${depLinks}`;
    }

    const { data: issue } = await this.ctx.octokit.rest.issues.create({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      title: spec.title,
      body,
      labels: spec.labels,
      milestone: spec.milestone,
    });

    // Add issue to project board
    if (this.setup.projectId) {
      await this.addIssueToProject(issue.node_id);
    }

    return issue.number;
  }

  async updateIssue(issueNumber: number, updates: Partial<IssueSpec>): Promise<void> {
    await this.ctx.octokit.rest.issues.update({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      issue_number: issueNumber,
      ...(updates.title && { title: updates.title }),
      ...(updates.body && { body: updates.body }),
      ...(updates.labels && { labels: updates.labels }),
    });
  }

  async closeIssue(issueNumber: number): Promise<void> {
    await this.ctx.octokit.rest.issues.update({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      issue_number: issueNumber,
      state: 'closed',
    });
  }

  async addComment(issueNumber: number, body: string): Promise<void> {
    await this.ctx.octokit.rest.issues.createComment({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      issue_number: issueNumber,
      body,
    });
  }

  async getIssue(issueNumber: number): Promise<BoardIssue> {
    const { data: issue } = await this.ctx.octokit.rest.issues.get({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      issue_number: issueNumber,
    });

    const column = await this.getIssueColumn(issue.node_id);
    return toBoardIssue(issue, column);
  }

  async getIssuesByLabel(label: string): Promise<BoardIssue[]> {
    // 최적화: BoardOperations 캐시가 있으면 단일 GraphQL 호출(getAllProjectItems)로 일괄 필터링
    // O(n) 개별 getIssueColumn 호출을 제거 → O(1) 배치 처리
    if (this.boardOps) {
      const allItems = await this.boardOps.getAllProjectItems();
      return allItems.filter((item) => item.labels.includes(label));
    }

    // Fallback: BoardOperations 미연결 시 기존 방식
    const { data: issues } = await this.ctx.octokit.rest.issues.listForRepo({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      labels: label,
      state: 'open',
      per_page: 100,
    });

    const boardIssues: BoardIssue[] = [];
    for (const issue of issues) {
      if (issue.pull_request) continue; // skip PRs
      const column = await this.getIssueColumn(issue.node_id);
      boardIssues.push(toBoardIssue(issue, column));
    }
    return boardIssues;
  }

  async getEpicIssues(epicId: string): Promise<BoardIssue[]> {
    return this.getIssuesByLabel(`epic:${epicId}`);
  }

  async addIssueToProject(issueNodeId: string): Promise<string> {
    const result = await this.ctx.graphqlWithAuth<{
      addProjectV2ItemById: { item: { id: string } };
    }>(
      `mutation($projectId: ID!, $contentId: ID!) {
        addProjectV2ItemById(input: { projectId: $projectId, contentId: $contentId }) {
          item { id }
        }
      }`,
      { projectId: this.setup.projectId, contentId: issueNodeId },
    );
    return result.addProjectV2ItemById.item.id;
  }

  async getProjectItemId(issueNodeId: string): Promise<string | null> {
    let cursor: string | null = null;
    let hasNextPage = true;

    while (hasNextPage) {
      const result = await this.ctx.graphqlWithAuth<{
        node: {
          items: {
            nodes: Array<{
              id: string;
              content: { id: string } | null;
            }>;
            pageInfo: { hasNextPage: boolean; endCursor: string };
          };
        };
      }>(
        `query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $cursor) {
                nodes {
                  id
                  content { ... on Issue { id } }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }`,
        { projectId: this.setup.projectId, cursor },
      );

      const page = result.node.items;
      const item = page.nodes.find((i) => i.content?.id === issueNodeId);
      if (item) return item.id;

      hasNextPage = page.pageInfo.hasNextPage;
      cursor = page.pageInfo.endCursor;
    }

    return null;
  }

  async getIssueColumn(issueNodeId: string): Promise<string> {
    const itemId = await this.getProjectItemId(issueNodeId);
    if (!itemId) return 'Backlog';

    const result = await this.ctx.graphqlWithAuth<{
      node: {
        fieldValues: {
          nodes: Array<{
            name?: string;
            field?: { name: string };
          }>;
        };
      };
    }>(
      `query($itemId: ID!) {
        node(id: $itemId) {
          ... on ProjectV2Item {
            fieldValues(first: 10) {
              nodes {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                  field { ... on ProjectV2SingleSelectField { name } }
                }
              }
            }
          }
        }
      }`,
      { itemId },
    );

    const statusValue = result.node.fieldValues.nodes.find(
      (fv) => fv.field?.name === 'Status',
    );
    return statusValue?.name ?? 'Backlog';
  }
}
