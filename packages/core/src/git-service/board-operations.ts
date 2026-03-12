import type { BoardIssue } from '../types/index.js';
import type { GitHubContext } from './types.js';
import type { ProjectSetup } from './project-setup.js';
import type { IssueManager } from './issue-manager.js';
import type { ProjectItemsResponse } from './types.js';
import { parseDependencies, parseGeneratedBy, parseEpicId } from './issue-parser.js';
import { withRetry } from '../resilience/api-retry.js';

export class BoardOperations {
  private ctx: GitHubContext;
  private setup: ProjectSetup;
  private issueManager: IssueManager;
  private itemIdCache: Map<number, string> = new Map(); // issueNumber → project item id

  constructor(ctx: GitHubContext, setup: ProjectSetup, issueManager: IssueManager) {
    this.ctx = ctx;
    this.setup = setup;
    this.issueManager = issueManager;
  }

  async moveIssueToColumn(issueNumber: number, column: string): Promise<void> {
    const optionId = this.setup.columnOptions.get(column);
    if (!optionId) {
      throw new Error(`Unknown column: ${column}`);
    }

    // 캐시 히트: getAllProjectItems가 BoardWatcher cycle마다 갱신하므로 대부분 캐시 히트
    let itemId = this.itemIdCache.get(issueNumber);

    if (!itemId) {
      // 캐시 미스: 새로 추가된 이슈 등 — REST + GraphQL fallback
      const { data: issue } = await withRetry(
        () =>
          this.ctx.octokit.rest.issues.get({
            owner: this.ctx.owner,
            repo: this.ctx.repo,
            issue_number: issueNumber,
          }),
        {},
        'getIssue (board cache miss)',
      );

      itemId = await this.issueManager.getProjectItemId(issue.node_id);
      if (!itemId) {
        throw new Error(`Issue #${issueNumber} is not on the project board`);
      }

      // 캐시에 추가
      this.itemIdCache.set(issueNumber, itemId);
    }

    await withRetry(
      () =>
        this.ctx.graphqlWithAuth(
          `mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: $projectId
            itemId: $itemId
            fieldId: $fieldId
            value: { singleSelectOptionId: $optionId }
          }) {
            projectV2Item { id }
          }
        }`,
          {
            projectId: this.setup.projectId,
            itemId,
            fieldId: this.setup.columnFieldId,
            optionId,
          },
        ),
      {},
      'moveIssueToColumn',
    );
  }

  async getAllProjectItems(): Promise<BoardIssue[]> {
    const allItems: BoardIssue[] = [];
    const newItemIdCache = new Map<number, string>();
    let cursor: string | null = null;
    let hasNextPage = true;

    while (hasNextPage) {
      const result: ProjectItemsResponse = await this.ctx.graphqlWithAuth(
        `query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $cursor) {
                nodes {
                  id
                  content {
                    ... on Issue {
                      id number title body
                      assignees(first: 5) { nodes { login } }
                      labels(first: 20) { nodes { name } }
                    }
                  }
                  fieldValues(first: 10) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field { ... on ProjectV2SingleSelectField { name } }
                      }
                    }
                  }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }`,
        { projectId: this.setup.projectId, cursor },
      );

      const page = result.node.items;

      for (const item of page.nodes) {
        if (!item.content) continue;

        // Cache: issueNumber → project item id (for moveIssueToColumn)
        newItemIdCache.set(item.content.number, item.id);

        const statusValue = item.fieldValues.nodes.find((fv) => fv.field?.name === 'Status');
        const column = statusValue?.name ?? 'Backlog';
        const labels = item.content.labels.nodes.map((l) => l.name);

        allItems.push({
          issueNumber: item.content.number,
          title: item.content.title,
          body: item.content.body,
          labels,
          column,
          dependencies: parseDependencies(item.content.body),
          assignee: item.content.assignees.nodes[0]?.login ?? null,
          generatedBy: parseGeneratedBy(labels),
          epicId: parseEpicId(labels),
        });
      }

      hasNextPage = page.pageInfo.hasNextPage;
      cursor = page.pageInfo.endCursor;
    }

    // Atomically replace cache after full fetch
    this.itemIdCache = newItemIdCache;

    return allItems;
  }
}
