import { Octokit } from '@octokit/rest';
import { graphql } from '@octokit/graphql';
import type { IGitService, IssueSpec, BoardIssue } from './types/index.js';

export interface GitServiceConfig {
  token: string;
  owner: string;
  repo: string;
  projectNumber?: number;
}

const REQUIRED_COLUMNS: readonly string[] = [
  'Backlog',
  'Ready',
  'In Progress',
  'Review',
  'Failed',
  'Done',
];

interface ProjectItemsResponse {
  node: {
    items: {
      nodes: Array<{
        content: {
          number: number;
          title: string;
          body: string;
          assignees: { nodes: Array<{ login: string }> };
          labels: { nodes: Array<{ name: string }> };
        } | null;
        fieldValues: {
          nodes: Array<{
            name?: string;
            field?: { name: string };
          }>;
        };
      }>;
      pageInfo: { hasNextPage: boolean; endCursor: string };
    };
  };
}

export class GitService implements IGitService {
  private octokit: Octokit;
  private graphqlWithAuth: typeof graphql;
  private owner: string;
  private repo: string;
  private projectNumber?: number;

  // Cached after validateConnection
  private projectId: string | null = null;
  private columnFieldId: string | null = null;
  private columnOptions: Map<string, string> = new Map(); // column name → option id

  constructor(config: GitServiceConfig) {
    this.octokit = new Octokit({ auth: config.token });
    this.graphqlWithAuth = graphql.defaults({
      headers: { authorization: `token ${config.token}` },
    });
    this.owner = config.owner;
    this.repo = config.repo;
    this.projectNumber = config.projectNumber;
  }

  // ========== Connection & Board Setup ==========

  async validateConnection(): Promise<void> {
    // 1. Verify GitHub API access
    const { data: user } = await this.octokit.rest.users.getAuthenticated();
    console.log(`[GitService] Authenticated as ${user.login}`);

    // 2. Find or create Project
    if (this.projectNumber) {
      this.projectId = await this.findProject(this.projectNumber);
      if (!this.projectId) {
        throw new Error(`Project #${this.projectNumber} not found`);
      }
    } else {
      this.projectId = await this.findProjectByTitle('Agent Orchestration Board');
      if (!this.projectId) {
        this.projectId = await this.createProject('Agent Orchestration Board');
        console.log(`[GitService] Project created`);
      }
    }

    // 3. Ensure required columns (Status field options)
    await this.ensureColumns();
    console.log(`[GitService] Board validated with ${this.columnOptions.size} columns`);
  }

  private async findProject(number: number): Promise<string | null> {
    try {
      const result = await this.graphqlWithAuth<{
        user: { projectV2: { id: string } };
      }>(
        `query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) { id }
          }
        }`,
        { login: this.owner, number },
      );
      return result.user.projectV2.id;
    } catch {
      // Try as organization
      try {
        const result = await this.graphqlWithAuth<{
          organization: { projectV2: { id: string } };
        }>(
          `query($login: String!, $number: Int!) {
            organization(login: $login) {
              projectV2(number: $number) { id }
            }
          }`,
          { login: this.owner, number },
        );
        return result.organization.projectV2.id;
      } catch {
        return null;
      }
    }
  }

  private async findProjectByTitle(title: string): Promise<string | null> {
    try {
      const result = await this.graphqlWithAuth<{
        user: { projectsV2: { nodes: Array<{ id: string; title: string }> } };
      }>(
        `query($login: String!) {
          user(login: $login) {
            projectsV2(first: 20) {
              nodes { id title }
            }
          }
        }`,
        { login: this.owner },
      );
      const project = result.user.projectsV2.nodes.find((p) => p.title === title);
      return project?.id ?? null;
    } catch {
      return null;
    }
  }

  private async createProject(title: string): Promise<string> {
    // Get owner node ID
    const { data: user } = await this.octokit.rest.users.getByUsername({
      username: this.owner,
    });

    const result = await this.graphqlWithAuth<{
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

  private async ensureColumns(): Promise<void> {
    // Get the Status field and its options
    const result = await this.graphqlWithAuth<{
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
    // ProjectV2 single select field option creation via GraphQL
    await this.graphqlWithAuth(
      `mutation($fieldId: ID!, $projectId: ID!, $name: String!) {
        createProjectV2FieldOption(input: {
          projectId: $projectId,
          fieldId: $fieldId,
          name: $name
        }) {
          projectV2Field {
            ... on ProjectV2SingleSelectField {
              options { id name }
            }
          }
        }
      }`,
      { fieldId: this.columnFieldId, projectId: this.projectId, name },
    );

    // Refresh column options cache
    await this.ensureColumns();
    console.log(`[GitService] Column created: ${name}`);
  }

  // ========== Issues ==========

  async createIssue(spec: IssueSpec): Promise<number> {
    // Build body with dependencies info
    let body = spec.body;
    if (spec.dependencies.length > 0) {
      const depLinks = spec.dependencies.map((n) => `- #${n}`).join('\n');
      body += `\n\n### Dependencies\n${depLinks}`;
    }

    const { data: issue } = await this.octokit.rest.issues.create({
      owner: this.owner,
      repo: this.repo,
      title: spec.title,
      body,
      labels: spec.labels,
      milestone: spec.milestone,
    });

    // Add issue to project board
    if (this.projectId) {
      await this.addIssueToProject(issue.node_id);
    }

    return issue.number;
  }

  async updateIssue(issueNumber: number, updates: Partial<IssueSpec>): Promise<void> {
    await this.octokit.rest.issues.update({
      owner: this.owner,
      repo: this.repo,
      issue_number: issueNumber,
      ...(updates.title && { title: updates.title }),
      ...(updates.body && { body: updates.body }),
      ...(updates.labels && { labels: updates.labels }),
    });
  }

  async closeIssue(issueNumber: number): Promise<void> {
    await this.octokit.rest.issues.update({
      owner: this.owner,
      repo: this.repo,
      issue_number: issueNumber,
      state: 'closed',
    });
  }

  async getIssue(issueNumber: number): Promise<BoardIssue> {
    const { data: issue } = await this.octokit.rest.issues.get({
      owner: this.owner,
      repo: this.repo,
      issue_number: issueNumber,
    });

    const column = await this.getIssueColumn(issue.node_id);
    return this.toBoardIssue(issue, column);
  }

  async getIssuesByLabel(label: string): Promise<BoardIssue[]> {
    const { data: issues } = await this.octokit.rest.issues.listForRepo({
      owner: this.owner,
      repo: this.repo,
      labels: label,
      state: 'open',
      per_page: 100,
    });

    const boardIssues: BoardIssue[] = [];
    for (const issue of issues) {
      if (issue.pull_request) continue; // skip PRs
      const column = await this.getIssueColumn(issue.node_id);
      boardIssues.push(this.toBoardIssue(issue, column));
    }
    return boardIssues;
  }

  async getEpicIssues(epicId: string): Promise<BoardIssue[]> {
    return this.getIssuesByLabel(`epic:${epicId}`);
  }

  // ========== Board Operations ==========

  async moveIssueToColumn(issueNumber: number, column: string): Promise<void> {
    const optionId = this.columnOptions.get(column);
    if (!optionId) {
      throw new Error(`Unknown column: ${column}`);
    }

    // Get the project item ID for this issue
    const { data: issue } = await this.octokit.rest.issues.get({
      owner: this.owner,
      repo: this.repo,
      issue_number: issueNumber,
    });

    const itemId = await this.getProjectItemId(issue.node_id);
    if (!itemId) {
      throw new Error(`Issue #${issueNumber} is not on the project board`);
    }

    await this.graphqlWithAuth(
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
        projectId: this.projectId,
        itemId,
        fieldId: this.columnFieldId,
        optionId,
      },
    );
  }

  async getAllProjectItems(): Promise<BoardIssue[]> {
    const allItems: BoardIssue[] = [];
    let cursor: string | null = null;
    let hasNextPage = true;

    while (hasNextPage) {
      const result: ProjectItemsResponse = await this.graphqlWithAuth(
        `query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $cursor) {
                nodes {
                  content {
                    ... on Issue {
                      number title body
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
        { projectId: this.projectId, cursor },
      );

      const page = result.node.items;

      for (const item of page.nodes) {
        if (!item.content) continue;

        const statusValue = item.fieldValues.nodes.find(
          (fv) => fv.field?.name === 'Status',
        );
        const column = statusValue?.name ?? 'Backlog';
        const labels = item.content.labels.nodes.map((l) => l.name);

        allItems.push({
          issueNumber: item.content.number,
          title: item.content.title,
          body: item.content.body,
          labels,
          column,
          dependencies: this.parseDependencies(item.content.body),
          assignee: item.content.assignees.nodes[0]?.login ?? null,
          generatedBy: this.parseGeneratedBy(labels),
          epicId: this.parseEpicId(labels),
        });
      }

      hasNextPage = page.pageInfo.hasNextPage;
      cursor = page.pageInfo.endCursor;
    }

    return allItems;
  }

  // ========== Git Operations ==========

  async createBranch(branchName: string, baseBranch = 'main'): Promise<void> {
    const { data: ref } = await this.octokit.rest.git.getRef({
      owner: this.owner,
      repo: this.repo,
      ref: `heads/${baseBranch}`,
    });

    await this.octokit.rest.git.createRef({
      owner: this.owner,
      repo: this.repo,
      ref: `refs/heads/${branchName}`,
      sha: ref.object.sha,
    });
  }

  async createPR(
    title: string,
    body: string,
    head: string,
    base = 'main',
  ): Promise<number> {
    const { data: pr } = await this.octokit.rest.pulls.create({
      owner: this.owner,
      repo: this.repo,
      title,
      body,
      head,
      base,
    });
    return pr.number;
  }

  // ========== Private Helpers ==========

  private async addIssueToProject(issueNodeId: string): Promise<string> {
    const result = await this.graphqlWithAuth<{
      addProjectV2ItemById: { item: { id: string } };
    }>(
      `mutation($projectId: ID!, $contentId: ID!) {
        addProjectV2ItemById(input: { projectId: $projectId, contentId: $contentId }) {
          item { id }
        }
      }`,
      { projectId: this.projectId, contentId: issueNodeId },
    );
    return result.addProjectV2ItemById.item.id;
  }

  private async getProjectItemId(issueNodeId: string): Promise<string | null> {
    const result = await this.graphqlWithAuth<{
      node: {
        items: {
          nodes: Array<{
            id: string;
            content: { id: string } | null;
          }>;
        };
      };
    }>(
      `query($projectId: ID!) {
        node(id: $projectId) {
          ... on ProjectV2 {
            items(first: 100) {
              nodes {
                id
                content { ... on Issue { id } }
              }
            }
          }
        }
      }`,
      { projectId: this.projectId },
    );

    const item = result.node.items.nodes.find(
      (i) => i.content?.id === issueNodeId,
    );
    return item?.id ?? null;
  }

  private async getIssueColumn(issueNodeId: string): Promise<string> {
    const itemId = await this.getProjectItemId(issueNodeId);
    if (!itemId) return 'Backlog';

    const result = await this.graphqlWithAuth<{
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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private toBoardIssue(issue: any, column: string): BoardIssue {
    const labels = issue.labels?.map((l: { name: string }) => l.name) ?? [];
    return {
      issueNumber: issue.number,
      title: issue.title,
      body: issue.body ?? '',
      labels,
      column,
      dependencies: this.parseDependencies(issue.body ?? ''),
      assignee: issue.assignee?.login ?? null,
      generatedBy: this.parseGeneratedBy(labels),
      epicId: this.parseEpicId(labels),
    };
  }

  private parseDependencies(body: string): number[] {
    const deps: number[] = [];
    const regex = /- #(\d+)/g;
    let match;
    while ((match = regex.exec(body)) !== null) {
      deps.push(parseInt(match[1], 10));
    }
    return deps;
  }

  private parseGeneratedBy(labels: string[]): string {
    const agentLabel = labels.find((l) => l.startsWith('agent:'));
    return agentLabel?.replace('agent:', '') ?? 'unknown';
  }

  private parseEpicId(labels: string[]): string | null {
    const epicLabel = labels.find((l) => l.startsWith('epic:'));
    return epicLabel?.replace('epic:', '') ?? null;
  }
}
