import type { IGitService, Task, FollowUp } from '../types/index.js';
import { createLogger } from '../logging/logger.js';

const log = createLogger('FollowUpCreator');

/**
 * Worker 에이전트가 코드 생성 후 도메인 간 후속 이슈를 자동 생성한다.
 *
 * 패턴:
 * - Backend → [FE] API 연동 훅, [DOCS] API 문서, [GIT] 커밋
 * - Frontend → [DOCS] 컴포넌트 문서, [GIT] 커밋
 * - Docs → [GIT] 커밋
 */
export class FollowUpCreator {
  constructor(private gitService: IGitService) {}

  /**
   * FollowUp 목록을 기반으로 후속 이슈를 생성한다.
   * 중복 이슈를 방지하기 위해 제목 기반 검사를 수행한다.
   */
  async createFollowUps(task: Task, followUps: FollowUp[]): Promise<number[]> {
    const createdIssues: number[] = [];

    for (const followUp of followUps) {
      try {
        const issueNumber = await this.createFollowUpIfNotExists(task, followUp);
        if (issueNumber) {
          createdIssues.push(issueNumber);
        }
      } catch (error) {
        log.warn(
          { err: error instanceof Error ? error.message : error, title: followUp.title },
          'Failed to create follow-up issue (non-fatal)',
        );
      }
    }

    return createdIssues;
  }

  /**
   * 중복 검사 후 후속 이슈를 생성한다.
   * 같은 Epic 내에 동일 제목의 이슈가 이미 있으면 생성하지 않는다.
   */
  private async createFollowUpIfNotExists(task: Task, followUp: FollowUp): Promise<number | null> {
    // 중복 검사: 같은 Epic 내 같은 제목의 이슈가 있는지 확인
    if (task.epicId) {
      const existingIssues = await this.gitService.getEpicIssues(task.epicId);
      const duplicate = existingIssues.find((i) => i.title === followUp.title);
      if (duplicate) {
        log.info(
          { title: followUp.title, existingIssue: duplicate.issueNumber },
          'Skipping duplicate follow-up',
        );
        return null;
      }
    }

    const agentLabel = `agent:${followUp.targetAgent}`;
    const typeLabel = `type:${followUp.type}`;

    const issueNumber = await this.gitService.createIssue({
      title: followUp.title,
      body: [
        followUp.description,
        '',
        ...(task.epicId ? [`**Epic:** ${task.epicId}`] : []),
        `**Source Task:** #${task.githubIssueNumber ?? task.id}`,
        ...(followUp.additionalContext ? ['', '### Context', followUp.additionalContext] : []),
      ].join('\n'),
      labels: [agentLabel, typeLabel, ...(task.epicId ? [`epic:${task.epicId}`] : [])],
      dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
    });

    log.info(
      { issueNumber, title: followUp.title, targetAgent: followUp.targetAgent },
      'Follow-up issue created',
    );
    return issueNumber;
  }

  /**
   * Backend 코드 생성 후 표준 후속 이슈 목록을 생성한다.
   */
  static backendFollowUps(task: Task, summary: string, files: string[]): FollowUp[] {
    const followUps: FollowUp[] = [];

    // API 엔드포인트가 생성된 경우 Frontend 연동 훅 생성
    const hasApiFiles = files.some((f) => f.includes('/routes/') || f.includes('/controllers/'));
    if (hasApiFiles) {
      followUps.push({
        title: `[FE] API 연동: ${task.title}`,
        targetAgent: 'frontend',
        type: 'api-hook',
        description: `Backend API가 생성되었으므로 Frontend에서 API 연동 훅/서비스를 구현해야 합니다.\n\n**Backend 변경:** ${summary}`,
        dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
        additionalContext: `생성된 파일:\n${files.map((f) => `- ${f}`).join('\n')}`,
      });
    }

    // API 문서 생성 요청
    if (hasApiFiles) {
      followUps.push({
        title: `[DOCS] API 문서: ${task.title}`,
        targetAgent: 'docs',
        type: 'docs',
        description: `Backend API가 생성되었으므로 API 문서를 업데이트해야 합니다.\n\n**Backend 변경:** ${summary}`,
        dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
      });
    }

    return followUps;
  }

  /**
   * Frontend 코드 생성 후 표준 후속 이슈 목록을 생성한다.
   */
  static frontendFollowUps(task: Task, summary: string, files: string[]): FollowUp[] {
    const followUps: FollowUp[] = [];

    // 컴포넌트 문서 생성 요청
    const hasComponents = files.some((f) => f.includes('/components/') || f.includes('/pages/'));
    if (hasComponents) {
      followUps.push({
        title: `[DOCS] 컴포넌트 문서: ${task.title}`,
        targetAgent: 'docs',
        type: 'docs',
        description: `Frontend 컴포넌트가 생성되었으므로 문서를 업데이트해야 합니다.\n\n**Frontend 변경:** ${summary}`,
        dependencies: task.githubIssueNumber ? [task.githubIssueNumber] : [],
      });
    }

    return followUps;
  }
}
