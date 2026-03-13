import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export class GitCli {
  constructor(private githubToken?: string) {}

  async exec(cwd: string, ...args: string[]): Promise<{ stdout: string; stderr: string }> {
    const env = { ...process.env };

    // GITHUB_TOKEN 기반 HTTPS 인증 — git push 시 패스워드 프롬프트 방지
    // 보안: 토큰을 프로세스 인자가 아닌 환경변수로 전달 (ps aux 노출 방지)
    if (this.githubToken) {
      env.GIT_ASKPASS = 'echo';
      env.GIT_TERMINAL_PROMPT = '0';
      env.GIT_CONFIG_COUNT = '1';
      env.GIT_CONFIG_KEY_0 = 'http.extraHeader';
      env.GIT_CONFIG_VALUE_0 = `Authorization: Bearer ${this.githubToken}`;
    }

    return execFileAsync('git', args, { cwd, env });
  }
}
