import { eq, and, desc } from 'drizzle-orm';
import type { Database } from '../db/index.js';
import { agents, epics, tasks, messages, artifacts } from '../db/schema.js';
import type {
  AgentInsert,
  AgentRow,
  TaskInsert,
  TaskRow,
  EpicInsert,
  EpicRow,
  ArtifactInsert,
  Message,
  TaskStatus,
  IStateStore,
} from '../types/index.js';
import { isValidTransition } from './task-state-machine.js';
import { createLogger } from '../logging/logger.js';

const log = createLogger('StateStore');

export class StateStore implements IStateStore {
  constructor(private db: Database) {}

  /**
   * Drizzle transaction wrapper. 여러 DB 작업을 하나의 트랜잭션으로 묶는다.
   * 에러 발생 시 자동 rollback.
   */
  async transaction<T>(fn: (tx: Database) => Promise<T>): Promise<T> {
    return this.db.transaction(fn as unknown as Parameters<Database['transaction']>[0]) as Promise<T>;
  }

  // ===== Agent =====

  async registerAgent(agent: AgentInsert): Promise<void> {
    await this.db
      .insert(agents)
      .values(agent)
      .onConflictDoUpdate({
        target: agents.id,
        set: { status: agent.status ?? 'idle', lastHeartbeat: new Date() },
      });
  }

  async getAgent(id: string): Promise<AgentRow | null> {
    const rows = await this.db.select().from(agents).where(eq(agents.id, id));
    return rows[0] ?? null;
  }

  async updateAgentStatus(id: string, status: string): Promise<void> {
    await this.db.update(agents).set({ status }).where(eq(agents.id, id));
  }

  async updateHeartbeat(id: string): Promise<void> {
    await this.db.update(agents).set({ lastHeartbeat: new Date() }).where(eq(agents.id, id));
  }

  // ===== Task =====

  async createTask(task: TaskInsert): Promise<void> {
    await this.db.insert(tasks).values(task);
  }

  async getTask(id: string): Promise<TaskRow | null> {
    const rows = await this.db.select().from(tasks).where(eq(tasks.id, id));
    return rows[0] ?? null;
  }

  async updateTask(id: string, updates: Partial<TaskRow>): Promise<void> {
    // 상태 전환 검증: status가 포함된 경우에만 현재 상태를 조회하여 검증
    if (updates.status) {
      const current = await this.db.select({ status: tasks.status }).from(tasks).where(eq(tasks.id, id));
      if (current.length > 0) {
        const from = current[0].status as TaskStatus;
        const to = updates.status as TaskStatus;
        if (!isValidTransition(from, to)) {
          log.warn({ taskId: id, from, to }, 'Invalid task status transition, skipping');
          return;
        }
      }
    }
    await this.db.update(tasks).set(updates).where(eq(tasks.id, id));
  }

  async getTasksByColumn(column: string): Promise<TaskRow[]> {
    return this.db.select().from(tasks).where(eq(tasks.boardColumn, column));
  }

  async getTasksByAgent(agentId: string): Promise<TaskRow[]> {
    return this.db.select().from(tasks).where(eq(tasks.assignedAgent, agentId));
  }

  async getReadyTasksForAgent(agentId: string): Promise<TaskRow[]> {
    return this.db
      .select()
      .from(tasks)
      .where(and(eq(tasks.boardColumn, 'Ready'), eq(tasks.assignedAgent, agentId)));
  }

  async claimTask(taskId: string): Promise<boolean> {
    const result = await this.db
      .update(tasks)
      .set({
        boardColumn: 'In Progress',
        status: 'in-progress',
        startedAt: new Date(),
      })
      .where(and(eq(tasks.id, taskId), eq(tasks.boardColumn, 'Ready'), eq(tasks.status, 'ready')));

    // Drizzle pg driver returns QueryResult with rowCount
    const rowCount = (result as { rowCount?: number }).rowCount ?? 0;
    return rowCount > 0;
  }

  // ===== Epic =====

  async createEpic(epic: EpicInsert): Promise<void> {
    await this.db.insert(epics).values(epic);
  }

  async getEpic(id: string): Promise<EpicRow | null> {
    const rows = await this.db.select().from(epics).where(eq(epics.id, id));
    return rows[0] ?? null;
  }

  async updateEpic(id: string, updates: Partial<EpicRow>): Promise<void> {
    await this.db.update(epics).set(updates).where(eq(epics.id, id));
  }

  // ===== Message =====

  async saveMessage(message: Message): Promise<void> {
    await this.db.insert(messages).values({
      id: message.id,
      type: message.type,
      fromAgent: message.from,
      toAgent: message.to,
      payload: message.payload,
      traceId: message.traceId,
      createdAt: message.timestamp,
    });
  }

  // ===== Artifact =====

  async saveArtifact(artifact: ArtifactInsert): Promise<void> {
    await this.db.insert(artifacts).values(artifact);
  }

  // ===== Dashboard Queries =====

  async getAllAgents(): Promise<AgentRow[]> {
    return this.db.select().from(agents);
  }

  async getAllTasks(): Promise<TaskRow[]> {
    return this.db.select().from(tasks);
  }

  async getAllEpics(): Promise<EpicRow[]> {
    return this.db.select().from(epics);
  }

  async getRecentMessages(limit: number): Promise<Message[]> {
    const rows = await this.db
      .select()
      .from(messages)
      .orderBy(desc(messages.createdAt))
      .limit(limit);
    return rows.map((r) => ({
      id: r.id,
      type: r.type,
      from: r.fromAgent,
      to: r.toAgent,
      payload: r.payload as Record<string, unknown>,
      traceId: r.traceId ?? '',
      timestamp: r.createdAt ?? new Date(),
    }));
  }
}
