import * as fs from 'fs/promises';
import * as path from 'path';
import * as crypto from 'crypto';
import type { GeneratedCode } from './types/index.js';

export class FileWriter {
  constructor(private workDir: string) {}

  /**
   * GeneratedCode의 파일을 디스크에 기록한다.
   * 경로 검증 → 디렉토리 생성 → 파일 쓰기/삭제
   * @returns 처리된 파일 경로 목록
   */
  async writeFiles(generated: GeneratedCode): Promise<string[]> {
    const writtenFiles: string[] = [];
    const resolvedWorkDir = path.resolve(this.workDir);

    for (const file of generated.files) {
      const absolutePath = path.resolve(resolvedWorkDir, file.path);

      // Sandbox: workDir 밖으로 나가는 경로 차단
      if (!absolutePath.startsWith(resolvedWorkDir)) {
        throw new Error(`Path escapes sandbox: ${file.path}`);
      }

      if (file.action === 'delete') {
        await fs.unlink(absolutePath).catch(() => {});
      } else {
        await fs.mkdir(path.dirname(absolutePath), { recursive: true });
        await fs.writeFile(absolutePath, file.content, 'utf-8');
      }

      writtenFiles.push(file.path);
    }

    return writtenFiles;
  }

  /**
   * 파일 내용의 SHA-256 해시를 계산한다. (artifact 추적용)
   */
  static contentHash(content: string): string {
    return crypto.createHash('sha256').update(content, 'utf-8').digest('hex');
  }
}
