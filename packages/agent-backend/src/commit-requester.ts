import type { IGitService, Task } from '@agent/core';

/**
 * 코드 생성 후 Git Agent에게 commit을 요청하는 follow-up issue를 생성한다.
 * Board-Driven 패턴: Worker → Follow-up Issue → Git Agent
 */
export class CommitRequester {
  constructor(private gitService: IGitService) {}

  /**
   * Git commit follow-up issue를 생성한다.
   * @param task 원본 task
   * @param writtenFiles 생성/수정된 파일 경로 목록
   * @param summary 변경 요약 (commit message로 사용)
   */
  async requestCommit(
    task: Task,
    writtenFiles: string[],
    summary: string,
  ): Promise<number> {
    if (writtenFiles.length === 0) {
      throw new Error('No files to commit');
    }

    const epicId = task.epicId ?? 'unknown';
    const fileList = writtenFiles.map((f) => `- \`${f}\``).join('\n');

    const issueNumber = await this.gitService.createIssue({
      title: `[GIT] Commit: ${summary}`,
      body: [
        `**Epic:** ${epicId}`,
        `**Source Task:** #${task.githubIssueNumber ?? task.id}`,
        '',
        '### Files',
        fileList,
        '',
        '### Commit Message',
        summary,
      ].join('\n'),
      labels: ['agent:git', 'type:commit', ...(task.epicId ? [`epic:${task.epicId}`] : [])],
      dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
    });

    console.log(`[BackendAgent] Created commit request issue #${issueNumber} for ${writtenFiles.length} files`);
    return issueNumber;
  }
}
