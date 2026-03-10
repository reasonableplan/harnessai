import type { AnyPgColumn } from 'drizzle-orm/pg-core';
import { index, pgTable, text, integer, real, timestamp, jsonb, uuid } from 'drizzle-orm/pg-core';

// 에이전트 등록 및 상태 관리
export const agents = pgTable('agents', {
  id: text('id').primaryKey(),
  domain: text('domain').notNull(),
  level: integer('level').notNull().default(2),
  status: text('status').notNull().default('idle'),
  parentId: text('parent_id').references((): AnyPgColumn => agents.id),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  lastHeartbeat: timestamp('last_heartbeat'),
});

// 에픽 (대규모 기능 단위)
export const epics = pgTable('epics', {
  id: text('id').primaryKey(),
  title: text('title').notNull(),
  description: text('description'),
  status: text('status').notNull().default('draft'),
  githubMilestoneNumber: integer('github_milestone_number'),
  progress: real('progress').notNull().default(0.0),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  completedAt: timestamp('completed_at'),
});

// 태스크 (Board 이슈와 1:1 매핑)
export const tasks = pgTable('tasks', {
  id: text('id').primaryKey(),
  epicId: text('epic_id').references(() => epics.id),
  title: text('title').notNull(),
  description: text('description'),
  assignedAgent: text('assigned_agent').references(() => agents.id),
  status: text('status').notNull().default('backlog'),
  githubIssueNumber: integer('github_issue_number'),
  boardColumn: text('board_column').notNull().default('Backlog'),
  priority: integer('priority').notNull().default(3),
  complexity: text('complexity').default('medium'),
  dependencies: jsonb('dependencies').default([]),
  labels: jsonb('labels').default([]),
  retryCount: integer('retry_count').notNull().default(0),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  startedAt: timestamp('started_at'),
  completedAt: timestamp('completed_at'),
  reviewNote: text('review_note'),
}, (table) => [
  index('idx_tasks_board_column').on(table.boardColumn),
  index('idx_tasks_assigned_agent').on(table.assignedAgent),
  index('idx_tasks_epic_id').on(table.epicId),
  index('idx_tasks_status').on(table.status),
  index('idx_tasks_github_issue').on(table.githubIssueNumber),
]);

// 에이전트 간 메시지 로그
export const messages = pgTable('messages', {
  id: uuid('id').primaryKey().defaultRandom(),
  type: text('type').notNull(),
  fromAgent: text('from_agent').notNull(),
  toAgent: text('to_agent'),
  payload: jsonb('payload').notNull().default({}),
  traceId: text('trace_id'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  ackedAt: timestamp('acked_at'),
}, (table) => [
  index('idx_messages_type').on(table.type),
  index('idx_messages_trace_id').on(table.traceId),
]);

// 생성된 산출물 (파일) 추적
export const artifacts = pgTable('artifacts', {
  id: uuid('id').primaryKey().defaultRandom(),
  taskId: text('task_id')
    .notNull()
    .references(() => tasks.id),
  filePath: text('file_path').notNull(),
  contentHash: text('content_hash').notNull(),
  createdBy: text('created_by')
    .notNull()
    .references(() => agents.id),
  createdAt: timestamp('created_at').notNull().defaultNow(),
});
