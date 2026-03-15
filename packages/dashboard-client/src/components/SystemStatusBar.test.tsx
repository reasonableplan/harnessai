import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useOfficeStore } from '@/stores/office-store';
import SystemStatusBar from './SystemStatusBar';

beforeEach(() => {
  useOfficeStore.setState({
    connected: false,
    isPaused: false,
    elapsedTime: 0,
    agents: {},
    tasks: {},
    epics: {},
    messages: [],
    toasts: [],
    selectedAgent: null,
    boardExpanded: false,
    tokenUsage: {},
    tokenBudget: 10_000_000,
    agentStats: {},
    agentConfigs: {},
    hooksList: [],
    settingsModalAgent: null,
    characterModalAgent: null,
    characterVersion: 0,
  });
});

describe('SystemStatusBar', () => {
  it('타이머 초기값 00:00:00 표시', () => {
    render(<SystemStatusBar />);
    expect(screen.getByText('00:00:00')).toBeInTheDocument();
  });

  it('PAUSE 버튼 렌더링', () => {
    render(<SystemStatusBar />);
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
  });

  it('PAUSE 클릭 시 RESUME으로 변경', async () => {
    const user = userEvent.setup();
    render(<SystemStatusBar />);
    const btn = screen.getByRole('button', { name: /pause/i });
    await user.click(btn);
    expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
  });

  it('에이전트 없을 때 0 active 표시', () => {
    render(<SystemStatusBar />);
    expect(screen.getByText(/0 active/i)).toBeInTheDocument();
  });

  it('active 에이전트 카운트 표시', () => {
    useOfficeStore.setState({
      agents: {
        a1: { id: 'a1', status: 'working', currentTask: null, bubble: null, domain: 'backend', slot: 0 },
        a2: { id: 'a2', status: 'idle', currentTask: null, bubble: null, domain: 'frontend', slot: 1 },
      },
    });
    render(<SystemStatusBar />);
    expect(screen.getByText(/1 active/i)).toBeInTheDocument();
    expect(screen.getByText(/1 idle/i)).toBeInTheDocument();
  });

  it('태스크 없을 때 BOARD: empty 표시', () => {
    render(<SystemStatusBar />);
    expect(screen.getByText(/empty/i)).toBeInTheDocument();
  });

  it('active epic 제목 표시', () => {
    useOfficeStore.setState({
      epics: {
        'e1': { id: 'e1', title: 'My Epic', progress: 0.5 },
      },
    });
    render(<SystemStatusBar />);
    expect(screen.getByText('My Epic')).toBeInTheDocument();
  });

  it('epic 없을 때 "No active epic" 표시', () => {
    render(<SystemStatusBar />);
    expect(screen.getByText(/no active epic/i)).toBeInTheDocument();
  });
});
