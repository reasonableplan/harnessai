import { eq, and } from 'drizzle-orm';
import type { Database } from './db/index.js';
import { agents, epics, tasks, messages, artifacts } from './db/schema.js';
import type {
  AgentInsert,
  AgentRow,
  TaskInsert,
  TaskRow,
  EpicInsert,
  EpicRow,
  ArtifactInsert,
  Message,
  IStateStore,
} from './types/index.js';

export class StateStore implements IStateStore {
  constructor(private db: Database) {}

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
    await this.db
      .update(agents)
      .set({ lastHeartbeat: new Date() })
      .where(eq(agents.id, id));
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
      .where(and(eq(tasks.id, taskId), eq(tasks.boardColumn, 'Ready')));

    // Drizzle pg returns { rowCount } for update operations
    return (result as unknown as { rowCount: number }).rowCount > 0;
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
}
