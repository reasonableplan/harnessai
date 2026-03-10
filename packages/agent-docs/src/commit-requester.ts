import type { IGitService, Task } from '@agent/core';
import { createLogger } from '@agent/core';

const log = createLogger('DocsCommitReq');

/**
 * 문서 생성 후 Git Agent에게 commit을 요청하는 follow-up issue를 생성한다.
 * Board-Driven 패턴: Worker → Follow-up Issue → Git Agent
 */
export class CommitRequester {
  constructor(private gitService: IGitService) {}

  async requestCommit(
    task: Task,
    writtenFiles: string[],
    summary: string,
  ): Promise<number> {
    if (writtenFiles.length === 0) {
      throw new Error('No files to commit');
    }

    const fileList = writtenFiles.map((f) => `- \`${f}\``).join('\n');

    const issueNumber = await this.gitService.createIssue({
      title: `[GIT] Commit: ${summary}`,
      body: [
        ...(task.epicId ? [`**Epic:** ${task.epicId}`] : []),
        `**Source Task:** #${task.githubIssueNumber ?? task.id}`,
        '',
        '### Files',
        fileList,
        '',
        '### Commit Message',
        `docs: ${summary}`,
      ].join('\n'),
      labels: ['agent:git', 'type:commit', ...(task.epicId ? [`epic:${task.epicId}`] : [])],
      dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
    });

    log.info({ issueNumber, fileCount: writtenFiles.length }, 'Commit request issue created');
    return issueNumber;
  }
}
