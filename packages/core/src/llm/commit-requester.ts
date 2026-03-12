import type { IGitService, Task } from '../types/index.js';
import { createLogger } from '../logging/logger.js';

const log = createLogger('CommitRequester');

/**
 * 코드 생성 후 Git Agent에게 commit을 요청하는 follow-up issue를 생성한다.
 * Board-Driven 패턴: Worker → Follow-up Issue → Git Agent
 *
 * commitPrefix를 생성자에서 받아 도메인별 커밋 메시지를 구분한다.
 * 예: 'feat(backend):', 'feat(frontend):', 'docs:'
 */
export class CommitRequester {
  constructor(
    private gitService: IGitService,
    private commitPrefix: string,
  ) {}

  async requestCommit(task: Task, writtenFiles: string[], summary: string): Promise<number> {
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
        `${this.commitPrefix} ${summary}`,
      ].join('\n'),
      labels: ['agent:git', 'type:commit', ...(task.epicId ? [`epic:${task.epicId}`] : [])],
      dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
    });

    log.info({ issueNumber, fileCount: writtenFiles.length }, 'Commit request issue created');
    return issueNumber;
  }
}
