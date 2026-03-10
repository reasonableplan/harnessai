import { Octokit } from '@octokit/rest';
import { graphql } from '@octokit/graphql';
import type { IGitService, IssueSpec, BoardIssue } from '../types/index.js';
import type { GitHubContext } from './types.js';
import { ProjectSetup } from './project-setup.js';
import { IssueManager } from './issue-manager.js';
import { BoardOperations } from './board-operations.js';
import { GitOperations } from './git-operations.js';

export interface GitServiceConfig {
  token: string;
  owner: string;
  repo: string;
  projectNumber?: number;
}

export class GitService implements IGitService {
  private projectNumber?: number;
  private setup: ProjectSetup;
  private issueManager: IssueManager;
  private boardOps: BoardOperations;
  private gitOps: GitOperations;

  constructor(config: GitServiceConfig) {
    const octokit = new Octokit({ auth: config.token });
    const graphqlWithAuth = graphql.defaults({
      headers: { authorization: `token ${config.token}` },
    });

    const ctx: GitHubContext = {
      octokit,
      graphqlWithAuth,
      owner: config.owner,
      repo: config.repo,
    };

    this.projectNumber = config.projectNumber;
    this.setup = new ProjectSetup(ctx);
    this.issueManager = new IssueManager(ctx, this.setup);
    this.boardOps = new BoardOperations(ctx, this.setup, this.issueManager);
    this.issueManager.setBoardOperations(this.boardOps); // batch query 최적화 연결
    this.gitOps = new GitOperations(ctx);
  }

  // ========== Connection & Board Setup ==========

  async validateConnection(): Promise<void> {
    await this.setup.validateConnection(this.projectNumber);
  }

  // ========== Issues ==========

  async createIssue(spec: IssueSpec): Promise<number> {
    return this.issueManager.createIssue(spec);
  }

  async updateIssue(issueNumber: number, updates: Partial<IssueSpec>): Promise<void> {
    return this.issueManager.updateIssue(issueNumber, updates);
  }

  async closeIssue(issueNumber: number): Promise<void> {
    return this.issueManager.closeIssue(issueNumber);
  }

  async addComment(issueNumber: number, body: string): Promise<void> {
    return this.issueManager.addComment(issueNumber, body);
  }

  async getIssue(issueNumber: number): Promise<BoardIssue> {
    return this.issueManager.getIssue(issueNumber);
  }

  async getIssuesByLabel(label: string): Promise<BoardIssue[]> {
    return this.issueManager.getIssuesByLabel(label);
  }

  async getEpicIssues(epicId: string): Promise<BoardIssue[]> {
    return this.issueManager.getEpicIssues(epicId);
  }

  // ========== Board Operations ==========

  async moveIssueToColumn(issueNumber: number, column: string): Promise<void> {
    return this.boardOps.moveIssueToColumn(issueNumber, column);
  }

  async getAllProjectItems(): Promise<BoardIssue[]> {
    return this.boardOps.getAllProjectItems();
  }

  // ========== Git Operations ==========

  async createBranch(branchName: string, baseBranch = 'main'): Promise<void> {
    return this.gitOps.createBranch(branchName, baseBranch);
  }

  async createPR(
    title: string,
    body: string,
    head: string,
    base = 'main',
    linkedIssues: number[] = [],
  ): Promise<number> {
    return this.gitOps.createPR(title, body, head, base, linkedIssues);
  }
}
