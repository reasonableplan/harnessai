import type { BaseAgent } from './base-agent.js';
import type { IStateStore, UserInput } from '../types/index.js';

/**
 * 자연어가 아닌 시스템 명령을 처리하는 핸들러.
 * Director가 없어도 시스템 관리가 가능하다.
 */
export class SystemController {
  private systemCommands = ['pause', 'resume', 'status', 'help'] as const;

  constructor(
    private agents: BaseAgent[],
    private stateStore: IStateStore,
  ) {}

  isSystemCommand(content: string): boolean {
    const command = content.trim().split(' ')[0].toLowerCase();
    return (this.systemCommands as readonly string[]).includes(command);
  }

  async handleSystemCommand(input: UserInput): Promise<string> {
    const command = input.content.trim().split(' ')[0].toLowerCase();

    switch (command) {
      case 'pause':
        return this.handlePause();
      case 'resume':
        return this.handleResume();
      case 'status':
        return this.handleStatus();
      case 'help':
        return this.handleHelp();
      default:
        return `Unknown command: ${command}`;
    }
  }

  private async handlePause(): Promise<string> {
    let paused = 0;
    for (const agent of this.agents) {
      await agent.pause();
      await this.stateStore.updateAgentStatus(agent.id, 'paused');
      paused++;
    }
    return `${paused} agents paused.`;
  }

  private async handleResume(): Promise<string> {
    let resumed = 0;
    for (const agent of this.agents) {
      await agent.resume();
      await this.stateStore.updateAgentStatus(agent.id, 'idle');
      resumed++;
    }
    return `${resumed} agents resumed.`;
  }

  private handleStatus(): string {
    const lines = this.agents.map(
      (a) => `  ${a.id.padEnd(12)} ${a.status.padEnd(8)} (${a.domain})`,
    );
    return `Agent Status:\n${lines.join('\n')}`;
  }

  private handleHelp(): string {
    return [
      'Available commands:',
      '  pause    — Stop all agent polling',
      '  resume   — Start all agent polling',
      '  status   — Show agent statuses',
      '  help     — Show this help',
      '',
      'Any other input is sent to the Director agent as a natural language request.',
    ].join('\n');
  }
}
