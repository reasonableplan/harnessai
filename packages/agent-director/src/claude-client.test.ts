import { describe, it, expect } from 'vitest';
import { ClaudeClient } from '@agent/core';

describe('ClaudeClient.extractJSON', () => {
  it('extracts JSON from markdown code block', () => {
    const input = '```json\n{"action": "create_epic", "title": "test"}\n```';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual({
      action: 'create_epic',
      title: 'test',
    });
  });

  it('extracts JSON from code block without language tag', () => {
    const input = '```\n{"action": "clarify"}\n```';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual({ action: 'clarify' });
  });

  it('extracts JSON with preamble text', () => {
    const input = 'Here is the JSON:\n{"action": "status_query", "query": "progress"}';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual({
      action: 'status_query',
      query: 'progress',
    });
  });

  it('extracts JSON with postamble text', () => {
    const input = '{"action": "clarify", "message": "hello"}\n\nLet me know if you need more.';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual({
      action: 'clarify',
      message: 'hello',
    });
  });

  it('handles pure JSON input', () => {
    const input = '{"action": "create_epic"}';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual({ action: 'create_epic' });
  });

  it('extracts JSON array', () => {
    const input = 'Tasks: [{"title": "a"}, {"title": "b"}]';
    expect(JSON.parse(ClaudeClient.extractJSON(input))).toEqual([{ title: 'a' }, { title: 'b' }]);
  });

  it('handles nested JSON objects', () => {
    const input = '```json\n{"tasks": [{"title": "a", "deps": [0]}]}\n```';
    const result = JSON.parse(ClaudeClient.extractJSON(input));
    expect(result.tasks[0].deps).toEqual([0]);
  });

  it('returns raw text when no JSON found', () => {
    const input = 'no json here';
    expect(ClaudeClient.extractJSON(input)).toBe('no json here');
  });
});
