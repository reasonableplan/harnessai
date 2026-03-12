import * as readline from 'readline';
import type { UserInput } from '../types/index.js';
import type { SystemController } from './system-controller.js';

export interface CLIOptions {
  systemController: SystemController;
  /** 자연어 입력을 Director에게 전달하는 콜백. Director가 없으면 null. */
  onDirectorInput: ((input: UserInput) => Promise<void>) | null;
}

/**
 * readline 기반 CLI. 시스템 명령은 SystemController로,
 * 자연어는 Director 콜백으로 라우팅한다.
 */
export function startCLI(options: CLIOptions): readline.Interface {
  const { systemController, onDirectorInput } = options;

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: 'agent> ',
  });

  rl.prompt();

  rl.on('line', async (line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      rl.prompt();
      return;
    }

    // 처리 중 추가 입력 방지
    rl.pause();

    const input: UserInput = {
      source: 'cli',
      content: trimmed,
      timestamp: new Date(),
    };

    try {
      if (systemController.isSystemCommand(trimmed)) {
        const result = await systemController.handleSystemCommand(input);
        console.log(result);
      } else if (onDirectorInput) {
        await onDirectorInput(input);
      } else {
        console.log('[CLI] Director agent is not registered. Only system commands are available.');
      }
    } catch (err) {
      console.error('[CLI] Command failed:', err);
    }

    rl.resume();
    rl.prompt();
  });

  rl.on('close', () => {
    // process.exit를 직접 호출하지 않고 SIGINT를 보내
    // bootstrap의 시그널 핸들러가 graceful shutdown을 수행하도록 한다.
    console.log('\n[CLI] Closing...');
    process.kill(process.pid, 'SIGINT');
  });

  return rl;
}
