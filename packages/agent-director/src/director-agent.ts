import {
  BaseAgent,
  ClaudeClient,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
  type Message,
  type IClaudeClient,
  MESSAGE_TYPES,
  createLogger,
} from '@agent/core';

const log = createLogger('Director');
import { EpicPlanner } from './epic-planner.js';
import { Dispatcher } from './dispatcher.js';
import { ReviewProcessor } from './review-processor.js';
import type {
  CreateEpicAction,
  StatusQueryAction,
  ClarifyAction,
  DirectorAction,
} from './action-types.js';

export interface DirectorConfig {
  claudeApiKey?: string;
  /** 테스트용 ClaudeClient 주입. 지정하지 않으면 실제 API 클라이언트 생성. */
  claudeClient?: IClaudeClient;
}

/**
 * Director Agent (Level 0) — 시스템의 두뇌.
 *
 * 역할:
 * 1. 사용자 자연어 요청 → Epic + Task DAG 분해 (Planner)
 * 2. Task를 적절한 Agent에게 할당 (Dispatcher)
 * 3. Epic 진행률 추적 + 실패 재시도 (Monitor)
 * 4. Worker 결과물 검토 (Review)
 */
export class DirectorAgent extends BaseAgent {
  private claude: IClaudeClient;
  private epicPlanner: EpicPlanner;
  private dispatcher: Dispatcher;
  private reviewProcessor: ReviewProcessor;

  constructor(deps: AgentDependencies, directorConfig: DirectorConfig = {}) {
    const config: AgentConfig = {
      id: 'director',
      domain: 'orchestration',
      level: 0,
      claudeModel: 'claude-sonnet-4-20250514',
      maxTokens: 8192,
      temperature: 0.3,
      tokenBudget: 200_000,
    };
    super(config, deps);

    if (!directorConfig.claudeClient && !directorConfig.claudeApiKey) {
      throw new Error('DirectorAgent requires either claudeClient or claudeApiKey');
    }
    this.claude =
      directorConfig.claudeClient ??
      new ClaudeClient(
        {
          model: config.claudeModel,
          maxTokens: config.maxTokens,
          temperature: config.temperature,
        },
        directorConfig.claudeApiKey!,
      );

    this.epicPlanner = new EpicPlanner(this.id, this.stateStore, this.gitService, this.messageBus);
    this.dispatcher = new Dispatcher(this.stateStore, this.gitService);
    this.dispatcher.setClaudeClient(this.claude);
    this.dispatcher.setMessageBus(this.messageBus);
    this.reviewProcessor = new ReviewProcessor(
      this.stateStore,
      this.gitService,
      this.claude,
      this.dispatcher,
      this.messageBus,
    );

    // MessageBus 구독 — 비동기 에러 격리
    this.subscribe(MESSAGE_TYPES.REVIEW_REQUEST, async (msg) => {
      try {
        await this.onReviewRequest(msg);
      } catch (err) {
        log.error({ err, msgId: msg.id }, 'onReviewRequest failed');
      }
    });
    this.subscribe(MESSAGE_TYPES.BOARD_MOVE, async (msg) => {
      try {
        await this.onBoardMove(msg);
      } catch (err) {
        log.error({ err, msgId: msg.id }, 'onBoardMove failed');
      }
    });
  }

  // ========== User Input Handler ==========

  /**
   * CLI/Dashboard에서 들어온 사용자 자연어 요청을 처리한다.
   * Claude를 사용하여 요청을 분석하고 적절한 액션을 결정한다.
   */
  async handleUserInput(content: string): Promise<string> {
    const systemPrompt = `You are the Director of a multi-agent software development system.
Your agents: backend (Express/Node.js), frontend (React/Vite), git (branch/commit/PR), docs (documentation).

When a user makes a request, analyze it and respond with a JSON action:

For new feature/project requests:
{"action": "create_epic", "title": "...", "description": "...", "tasks": [{"id": "t1", "title": "...", "agent": "backend|frontend|git|docs", "description": "...", "dependencies": []}]}

Each task MUST have a unique string "id" (e.g. "t1", "t2", "branch-setup", "api-endpoint").
Use these ids in the "dependencies" array to reference other tasks.
Example: {"id": "t2", "title": "Backend API", "agent": "backend", "description": "...", "dependencies": ["t1"]}

For status inquiries:
{"action": "status_query", "query": "..."}

For clarification needed:
{"action": "clarify", "message": "..."}

Rules:
- Break work into small, specific tasks
- Each task should be assignable to exactly one agent domain
- Use string task ids for dependencies (NOT numeric indices)
- Git tasks (branch creation) should come first, commit/PR tasks last
- Always include a docs task for significant features`;

    try {
      const { data, usage } = await this.claude.chatJSON<DirectorAction>(systemPrompt, content);
      await this.publishTokenUsage(usage.inputTokens, usage.outputTokens);
      log.info(
        { inputTokens: usage.inputTokens, outputTokens: usage.outputTokens },
        'Claude usage',
      );

      switch (data.action) {
        case 'create_epic':
          return await this.epicPlanner.createEpic(data as CreateEpicAction);
        case 'status_query':
          return await this.handleStatusQuery(data as StatusQueryAction);
        case 'clarify':
          return (data as ClarifyAction).message;
        default:
          return `[Director] Unknown action: ${(data as { action: string }).action}`;
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      log.error({ err: msg }, 'Failed to process input');
      return `[Director] Error processing request: ${msg}`;
    }
  }

  // ========== Status Query ==========

  private async handleStatusQuery(_action: StatusQueryAction): Promise<string> {
    // 간단한 상태 조회 — SystemController.handleStatus()와 유사하지만 Epic 수준
    // Step 4에서 Claude 기반 자연어 응답으로 확장
    return '[Director] Status query support coming in Step 4.';
  }

  // ========== Delegating methods (exposed for test compatibility) ==========

  private async onBoardMove(msg: Message): Promise<void> {
    return this.dispatcher.onBoardMove(msg);
  }

  private async onReviewRequest(msg: Message): Promise<void> {
    return this.reviewProcessor.onReviewRequest(msg);
  }

  private async checkAndPromoteDependents(completedIssueNumber: number): Promise<void> {
    return this.dispatcher.checkAndPromoteDependents(completedIssueNumber);
  }

  // ========== BaseAgent: executeTask ==========

  /**
   * Director는 Board 기반 Task 실행보다는 MessageBus 이벤트 처리가 주 역할.
   * 하지만 Board에서 director에게 직접 할당된 Task가 있을 수 있다 (예: Epic 계획 요청).
   */
  protected async executeTask(task: Task): Promise<TaskResult> {
    log.info({ title: task.title }, 'Processing task');

    try {
      const response = await this.handleUserInput(task.description || task.title);
      return {
        success: true,
        data: { response },
        artifacts: [],
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        error: { message: msg },
        artifacts: [],
      };
    }
  }
}
