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
  private inProgress = new Map<string, Promise<string>>();

  constructor(
    private workDir: string,
    private gitCli: GitCli,
    private wsConfig: WorkspaceConfig,
  ) {}

  async getEpicWorkDir(epicId: string): Promise<string> {
    const existing = this.inProgress.get(epicId);
    if (existing) return existing;
    const promise = this._doGetEpicWorkDir(epicId).finally(() => {
      this.inProgress.delete(epicId);
    });
    this.inProgress.set(epicId, promise);
    return promise;
  }

  private async _doGetEpicWorkDir(epicId: string): Promise<string> {
    const epicDir = path.resolve(this.workDir, epicId);
    try {
      // .git 디렉토리가 있으면 이미 클론된 repo
      await fs.access(path.join(epicDir, '.git'));
    } catch {
      // .git not found — clone needed (expected path)
      log.debug({ epicId }, 'No .git directory found, cloning');
      await fs.mkdir(epicDir, { recursive: true });
      const repoUrl = `https://github.com/${this.wsConfig.githubOwner}/${this.wsConfig.githubRepo}.git`;
      const branchName = `epic/${epicId}`;
      try {
        await this.gitCli.exec(this.workDir, 'clone', '--branch', branchName, repoUrl, epicId);
      } catch (cloneErr) {
        // branch가 아직 없으면 main으로 clone 후 branch 생성
        log.info(
          { err: cloneErr instanceof Error ? cloneErr.message : String(cloneErr), branchName },
          'Branch clone failed, falling back to main',
        );
        try {
          await this.gitCli.exec(this.workDir, 'clone', repoUrl, epicId);
          await this.gitCli.exec(epicDir, 'checkout', '-b', branchName);
        } catch (err) {
          // 두 번째 clone도 실패 시 orphaned 디렉토리 정리
          await fs.rm(epicDir, { recursive: true, force: true }).catch(() => {});
          throw err;
        }
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
