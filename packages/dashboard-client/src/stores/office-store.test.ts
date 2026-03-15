import { describe, it, expect, beforeEach } from 'vitest';
import { useOfficeStore } from './office-store';

// Reset store state between tests
beforeEach(() => {
  useOfficeStore.setState({
    agents: {
      director: { id: 'director', status: 'idle', currentTask: null, bubble: null, domain: 'director', slot: 0 },
    },
    tasks: {},
    epics: {},
    messages: [],
    toasts: [],
    selectedAgent: null,
    boardExpanded: false,
    isPaused: false,
    elapsedTime: 0,
    tokenUsage: {},
    tokenBudget: 10_000_000,
    agentStats: {},
    agentConfigs: {},
    hooksList: [],
    settingsModalAgent: null,
    characterModalAgent: null,
    characterVersion: 0,
    connected: false,
  });
});

describe('useOfficeStore — agent', () => {
  it('초기 상태: connected = false', () => {
    expect(useOfficeStore.getState().connected).toBe(false);
  });

  it('updateAgent: 기존 에이전트 상태 업데이트', () => {
    useOfficeStore.getState().updateAgent('director', { status: 'busy', currentTask: 'task-1' });
    const agent = useOfficeStore.getState().agents['director'];
    expect(agent.status).toBe('busy');
    expect(agent.currentTask).toBe('task-1');
  });

  it('updateAgent: 새 에이전트 자동 슬롯 배정', () => {
    useOfficeStore.getState().updateAgent('new-agent', { status: 'idle', domain: 'backend' });
    const agent = useOfficeStore.getState().agents['new-agent'];
    expect(agent).toBeDefined();
    expect(agent.domain).toBe('backend');
    expect(typeof agent.slot).toBe('number');
  });

  it('selectAgent: 에이전트 선택/해제', () => {
    useOfficeStore.getState().selectAgent('director');
    expect(useOfficeStore.getState().selectedAgent).toBe('director');
    useOfficeStore.getState().selectAgent(null);
    expect(useOfficeStore.getState().selectedAgent).toBeNull();
  });
});

describe('useOfficeStore — task', () => {
  it('updateTask: 새 태스크 생성', () => {
    useOfficeStore.getState().updateTask('task-1', { title: 'Fix bug', status: 'ready', boardColumn: 'Ready' });
    const task = useOfficeStore.getState().tasks['task-1'];
    expect(task.title).toBe('Fix bug');
    expect(task.boardColumn).toBe('Ready');
  });

  it('updateTask: 기존 태스크 부분 업데이트', () => {
    useOfficeStore.getState().updateTask('task-1', { title: 'Fix bug', status: 'ready', boardColumn: 'Ready' });
    useOfficeStore.getState().updateTask('task-1', { status: 'in-progress', boardColumn: 'In Progress' });
    const task = useOfficeStore.getState().tasks['task-1'];
    expect(task.title).toBe('Fix bug'); // 유지
    expect(task.status).toBe('in-progress'); // 업데이트
  });
});

describe('useOfficeStore — toast', () => {
  it('addToast / removeToast', () => {
    useOfficeStore.getState().addToast({ id: 't1', type: 'success', title: 'Done', message: 'ok' });
    expect(useOfficeStore.getState().toasts).toHaveLength(1);
    useOfficeStore.getState().removeToast('t1');
    expect(useOfficeStore.getState().toasts).toHaveLength(0);
  });

  it('addToast: 최대 5개 유지', () => {
    for (let i = 0; i < 7; i++) {
      useOfficeStore.getState().addToast({ id: `t${i}`, type: 'info', title: `Toast ${i}`, message: '' });
    }
    expect(useOfficeStore.getState().toasts).toHaveLength(5);
  });
});

describe('useOfficeStore — messages', () => {
  it('addMessage: 최신 메시지가 앞으로, 최대 200개', () => {
    for (let i = 0; i < 205; i++) {
      useOfficeStore.getState().addMessage({
        id: `m${i}`, type: 'agent.status', from: 'director',
        content: `msg ${i}`, timestamp: new Date().toISOString(),
      });
    }
    const msgs = useOfficeStore.getState().messages;
    expect(msgs).toHaveLength(200);
    expect(msgs[0].id).toBe('m204'); // 가장 최신
  });
});

describe('useOfficeStore — token usage', () => {
  it('updateTokenUsage: 누적 집계', () => {
    useOfficeStore.getState().updateTokenUsage('director', 100, 200);
    useOfficeStore.getState().updateTokenUsage('director', 50, 100);
    const usage = useOfficeStore.getState().tokenUsage['director'];
    expect(usage.inputTokens).toBe(150);
    expect(usage.outputTokens).toBe(300);
    expect(usage.totalTokens).toBe(450);
    expect(usage.callCount).toBe(2);
  });
});

describe('useOfficeStore — board & pause', () => {
  it('toggleBoard', () => {
    expect(useOfficeStore.getState().boardExpanded).toBe(false);
    useOfficeStore.getState().toggleBoard();
    expect(useOfficeStore.getState().boardExpanded).toBe(true);
  });

  it('togglePause', () => {
    expect(useOfficeStore.getState().isPaused).toBe(false);
    useOfficeStore.getState().togglePause();
    expect(useOfficeStore.getState().isPaused).toBe(true);
  });
});

describe('useOfficeStore — hooks', () => {
  it('setHooks / updateHookEnabled', () => {
    useOfficeStore.getState().setHooks([
      { id: 'h1', event: 'task.completed', name: 'Log', description: null, enabled: true },
    ]);
    useOfficeStore.getState().updateHookEnabled('h1', false);
    expect(useOfficeStore.getState().hooksList[0].enabled).toBe(false);
  });
});

describe('useOfficeStore — modals', () => {
  it('openSettingsModal / closeSettingsModal', () => {
    useOfficeStore.getState().openSettingsModal('director');
    expect(useOfficeStore.getState().settingsModalAgent).toBe('director');
    useOfficeStore.getState().closeSettingsModal();
    expect(useOfficeStore.getState().settingsModalAgent).toBeNull();
  });

  it('openCharacterModal / closeCharacterModal', () => {
    useOfficeStore.getState().openCharacterModal('backend');
    expect(useOfficeStore.getState().characterModalAgent).toBe('backend');
    useOfficeStore.getState().closeCharacterModal();
    expect(useOfficeStore.getState().characterModalAgent).toBeNull();
  });
});

describe('useOfficeStore — setInitialState', () => {
  it('connected = true로 변경', () => {
    useOfficeStore.getState().setInitialState({ agents: {}, tasks: {}, epics: {} });
    expect(useOfficeStore.getState().connected).toBe(true);
  });

  it('에이전트 슬롯 자동 배정', () => {
    useOfficeStore.getState().setInitialState({
      agents: {
        'agent-a': { id: 'agent-a', status: 'idle', currentTask: null, bubble: null, domain: 'backend', slot: 0 },
        'agent-b': { id: 'agent-b', status: 'idle', currentTask: null, bubble: null, domain: 'frontend', slot: 1 },
      },
    });
    const agents = useOfficeStore.getState().agents;
    expect(agents['agent-a'].slot).toBe(0);
    expect(agents['agent-b'].slot).toBe(1);
  });
});
