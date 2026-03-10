import type { GitHubContext } from './types.js';

export class GitOperations {
  private ctx: GitHubContext;

  constructor(ctx: GitHubContext) {
    this.ctx = ctx;
  }

  async createBranch(branchName: string, baseBranch = 'main'): Promise<void> {
    const { data: ref } = await this.ctx.octokit.rest.git.getRef({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      ref: `heads/${baseBranch}`,
    });

    await this.ctx.octokit.rest.git.createRef({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      ref: `refs/heads/${branchName}`,
      sha: ref.object.sha,
    });
  }

  async createPR(
    title: string,
    body: string,
    head: string,
    base = 'main',
    linkedIssues: number[] = [],
  ): Promise<number> {
    // Auto-link issues: "Closes #N" 키워드로 GitHub Development 섹션에 자동 연결
    let prBody = body;
    if (linkedIssues.length > 0) {
      const closingLinks = linkedIssues.map((n) => `Closes #${n}`).join('\n');
      prBody += `\n\n### Linked Issues\n${closingLinks}`;
    }

    const { data: pr } = await this.ctx.octokit.rest.pulls.create({
      owner: this.ctx.owner,
      repo: this.ctx.repo,
      title,
      body: prBody,
      head,
      base,
    });
    return pr.number;
  }
}
