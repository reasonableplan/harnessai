import { z } from 'zod';

export const agentStatusSchema = z.object({
  agentId: z.string(),
  status: z.string(),
  task: z.string().optional(),
});

export const agentBubbleSchema = z.object({
  agentId: z.string(),
  bubble: z
    .object({
      content: z.string(),
      type: z.enum(['task', 'thinking', 'info', 'error']),
    })
    .nullable(),
});

export const taskUpdateSchema = z.object({
  taskId: z.string(),
  status: z.string().optional(),
  boardColumn: z.string().optional(),
  assignedAgent: z.string().nullable().optional(),
  title: z.string().optional(),
  epicId: z.string().nullable().optional(),
});

export const epicProgressSchema = z.object({
  epicId: z.string(),
  title: z.string().optional(),
  progress: z.number().optional(),
});

export const messageSchema = z.object({
  id: z.string().optional(),
  type: z.string().optional(),
  from: z.string().optional(),
  content: z.string().optional(),
  timestamp: z.string().optional(),
});

export const tokenUsageSchema = z.object({
  agentId: z.string(),
  inputTokens: z.number().default(0),
  outputTokens: z.number().default(0),
});

export const agentConfigSchema = z.object({
  agentId: z.string(),
  config: z.record(z.unknown()),
});

export const toastSchema = z.object({
  type: z.enum(['success', 'error', 'info', 'warning']).default('info'),
  title: z.string().default(''),
  message: z.string().default(''),
});

export const defaultFallbackSchema = z.object({
  from: z.string().optional(),
});

const agentRowSchema = z.object({
  id: z.string(),
  status: z.string().default('idle'),
  domain: z.string().optional(),
});

const taskRowSchema = z.object({
  id: z.string(),
  title: z.string().default(''),
  status: z.string().default(''),
  boardColumn: z.string().default('Backlog'),
  assignedAgent: z.string().nullable().default(null),
  epicId: z.string().nullable().default(null),
});

const epicRowSchema = z.object({
  id: z.string(),
  title: z.string().default(''),
  progress: z.number().default(0),
});

export const initPayloadSchema = z.object({
  agents: z.array(agentRowSchema).optional(),
  tasks: z.array(taskRowSchema).optional(),
  epics: z.array(epicRowSchema).optional(),
});
