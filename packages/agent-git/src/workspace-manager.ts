import * as fs from 'fs/promises';
import * as path from 'path';
import { createLogger } from '@agent/core';
import type { GitCli } from './git-cli.js';

const log = createLogger('WorkspaceManager');

export interface WorkspaceConfig {
  githubOwner: string;
  githubRepo: string;
}

export class WorkspaceManager {
  constructor(
    private workDir: string,
    private gitCli: GitCli,
    private wsConfig: WorkspaceConfig,
  ) {}

  async getEpicWorkDir(epicId: string): Promise<string> {
    const epicDir = path.resolve(this.workDir, epicId);
    try {
      // .git 디렉토리가 있으면 이미 클론된 repo
      await fs.access(path.join(epicDir, '.git'));
    } catch {
      // 클론되지 않은 경우: repo를 해당 branch로 clone
      await fs.mkdir(epicDir, { recursive: true });
      const repoUrl = `https://github.com/${this.wsConfig.githubOwner}/${this.wsConfig.githubRepo}.git`;
      const branchName = `epic/${epicId}`;
      try {
        await this.gitCli.exec(this.workDir, 'clone', '--branch', branchName, repoUrl, epicId);
      } catch {
        // branch가 아직 없으면 main으로 clone 후 branch 생성
        await this.gitCli.exec(this.workDir, 'clone', repoUrl, epicId);
        await this.gitCli.exec(epicDir, 'checkout', '-b', branchName);
      }
    }
    return epicDir;
  }

  async cleanupEpicWorkDir(epicId: string): Promise<void> {
    const epicDir = path.resolve(this.workDir, epicId);
    try {
      await fs.rm(epicDir, { recursive: true, force: true });
      log.info({ epicDir }, 'Cleaned up workspace');
    } catch (error) {
      log.error({ err: error, epicDir }, 'Failed to cleanup workspace');
    }
  }
}
