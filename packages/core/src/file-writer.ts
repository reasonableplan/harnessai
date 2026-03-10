import * as fs from 'fs/promises';
import * as path from 'path';
import * as crypto from 'crypto';
import type { GeneratedCode, GeneratedFile } from './types/index.js';
import { createLogger } from './logger.js';

const log = createLogger('FileWriter');

/** 확장자 → 언어 매핑 (syntax validation 대상) */
const TS_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.mts']);
const JSON_EXTENSIONS = new Set(['.json']);

export class FileWriter {
  constructor(private workDir: string) {}

  /**
   * GeneratedCode의 파일을 디스크에 기록한다.
   * 경로 검증 → syntax 검증 → 디렉토리 생성 → 파일 쓰기/삭제
   * @returns 처리된 파일 경로 목록
   */
  async writeFiles(generated: GeneratedCode): Promise<string[]> {
    const writtenFiles: string[] = [];
    const resolvedWorkDir = path.resolve(this.workDir);

    for (const file of generated.files) {
      const absolutePath = path.resolve(resolvedWorkDir, file.path);

      // Sandbox: workDir 밖으로 나가는 경로 차단
      if (!absolutePath.startsWith(resolvedWorkDir + path.sep)) {
        throw new Error(`Path escapes sandbox: ${file.path}`);
      }

      if (file.action === 'delete') {
        await fs.unlink(absolutePath).catch(() => {});
      } else {
        // Syntax validation: 기본 구조 검증 (완전한 파싱은 아님)
        FileWriter.validateSyntax(file);
        await fs.mkdir(path.dirname(absolutePath), { recursive: true });
        await fs.writeFile(absolutePath, file.content, 'utf-8');
      }

      writtenFiles.push(file.path);
    }

    return writtenFiles;
  }

  /**
   * 생성된 파일의 기본 syntax를 검증한다.
   * - JSON: JSON.parse 통과 여부
   * - TS/JS: 괄호/중괄호/대괄호 균형, 빈 파일 감지
   * 실패 시 에러를 throw하여 잘못된 코드가 디스크에 기록되는 것을 방지.
   */
  static validateSyntax(file: GeneratedFile): void {
    const ext = path.extname(file.path).toLowerCase();
    const content = file.content;

    if (!content.trim()) {
      throw new Error(`Empty file content: ${file.path}`);
    }

    if (JSON_EXTENSIONS.has(ext)) {
      try {
        JSON.parse(content);
      } catch (err) {
        throw new Error(`Invalid JSON in ${file.path}: ${err instanceof Error ? err.message : err}`);
      }
      return;
    }

    if (TS_EXTENSIONS.has(ext)) {
      // 괄호 균형 검증 (문자열/주석 내 괄호 무시)
      const stripped = FileWriter.stripStringsAndComments(content);
      const balance = { '{': 0, '(': 0, '[': 0 };
      const pairs: Record<string, keyof typeof balance> = { '}': '{', ')': '(', ']': '[' };

      for (const ch of stripped) {
        if (ch in balance) balance[ch as keyof typeof balance]++;
        else if (ch in pairs) balance[pairs[ch]]--;
      }

      for (const [bracket, count] of Object.entries(balance)) {
        if (count !== 0) {
          log.warn({ file: file.path, bracket, count }, 'Bracket imbalance detected');
          throw new Error(`Syntax error in ${file.path}: unbalanced '${bracket}' (${count > 0 ? 'unclosed' : 'extra closing'})`);
        }
      }
    }
  }

  /** 문자열 리터럴과 주석을 제거하여 구조만 남긴다. */
  static stripStringsAndComments(code: string): string {
    // 순서: 템플릿 리터럴, 문자열, 정규식, 주석 제거
    return code.replace(
      /`(?:[^`\\]|\\.)*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\/\/[^\n]*|\/\*[\s\S]*?\*\//g,
      '',
    );
  }

  /**
   * 파일 내용의 SHA-256 해시를 계산한다. (artifact 추적용)
   */
  static contentHash(content: string): string {
    return crypto.createHash('sha256').update(content, 'utf-8').digest('hex');
  }
}
