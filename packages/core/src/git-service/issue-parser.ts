import type { BoardIssue } from '../types/index.js';

export function parseDependencies(body: string): number[] {
  const deps: number[] = [];
  const regex = /- #(\d+)/g;
  let match;
  while ((match = regex.exec(body)) !== null) {
    deps.push(parseInt(match[1], 10));
  }
  return deps;
}

export function parseGeneratedBy(labels: string[]): string {
  const agentLabel = labels.find((l) => l.startsWith('agent:'));
  return agentLabel?.replace('agent:', '') ?? 'unknown';
}

export function parseEpicId(labels: string[]): string | null {
  const epicLabel = labels.find((l) => l.startsWith('epic:'));
  return epicLabel?.replace('epic:', '') ?? null;
}

export interface GitHubIssueData {
  number: number;
  title: string;
  body?: string | null;
  labels?: Array<{ name: string }>;
  assignee?: { login: string } | null;
}

export function toBoardIssue(issue: GitHubIssueData, column: string): BoardIssue {
  const labels = issue.labels?.map((l) => l.name) ?? [];
  return {
    issueNumber: issue.number,
    title: issue.title,
    body: issue.body ?? '',
    labels,
    column,
    dependencies: parseDependencies(issue.body ?? ''),
    assignee: issue.assignee?.login ?? null,
    generatedBy: parseGeneratedBy(labels),
    epicId: parseEpicId(labels),
  };
}
