import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { FileWriter } from './file-writer.js';
import type { GeneratedCode } from '../types/index.js';

describe('FileWriter', () => {
  let tmpDir: string;
  let writer: FileWriter;

  beforeEach(async () => {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'fw-test-'));
    writer = new FileWriter(tmpDir);
  });

  afterEach(async () => {
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  it('creates files with correct content', async () => {
    const generated: GeneratedCode = {
      files: [
        { path: 'src/index.ts', content: 'export {};\n', action: 'create', language: 'typescript' },
      ],
      summary: 'test',
    };

    const written = await writer.writeFiles(generated);

    expect(written).toEqual(['src/index.ts']);
    const content = await fs.readFile(path.join(tmpDir, 'src/index.ts'), 'utf-8');
    expect(content).toBe('export {};\n');
  });

  it('creates nested directories automatically', async () => {
    const generated: GeneratedCode = {
      files: [{ path: 'a/b/c/deep.ts', content: 'deep', action: 'create', language: 'typescript' }],
      summary: 'test',
    };

    await writer.writeFiles(generated);

    const content = await fs.readFile(path.join(tmpDir, 'a/b/c/deep.ts'), 'utf-8');
    expect(content).toBe('deep');
  });

  it('updates existing files', async () => {
    const dir = path.join(tmpDir, 'src');
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, 'app.ts'), 'old');

    const generated: GeneratedCode = {
      files: [{ path: 'src/app.ts', content: 'new', action: 'update', language: 'typescript' }],
      summary: 'test',
    };

    await writer.writeFiles(generated);

    const content = await fs.readFile(path.join(dir, 'app.ts'), 'utf-8');
    expect(content).toBe('new');
  });

  it('deletes files', async () => {
    const filePath = path.join(tmpDir, 'to-delete.ts');
    await fs.writeFile(filePath, 'bye');

    const generated: GeneratedCode = {
      files: [{ path: 'to-delete.ts', content: '', action: 'delete', language: 'typescript' }],
      summary: 'test',
    };

    await writer.writeFiles(generated);

    await expect(fs.access(filePath)).rejects.toThrow();
  });

  it('delete of nonexistent file does not throw', async () => {
    const generated: GeneratedCode = {
      files: [{ path: 'ghost.ts', content: '', action: 'delete', language: 'typescript' }],
      summary: 'test',
    };

    await expect(writer.writeFiles(generated)).resolves.toEqual(['ghost.ts']);
  });

  it('rejects paths that escape sandbox', async () => {
    const generated: GeneratedCode = {
      files: [{ path: '../../etc/passwd', content: 'bad', action: 'create', language: 'text' }],
      summary: 'test',
    };

    await expect(writer.writeFiles(generated)).rejects.toThrow('Path escapes sandbox:');
  });

  it('handles multiple files in one call', async () => {
    const generated: GeneratedCode = {
      files: [
        { path: 'a.ts', content: 'a', action: 'create', language: 'typescript' },
        { path: 'b.ts', content: 'b', action: 'create', language: 'typescript' },
        { path: 'c.ts', content: 'c', action: 'create', language: 'typescript' },
      ],
      summary: 'test',
    };

    const written = await writer.writeFiles(generated);
    expect(written).toHaveLength(3);
  });

  it('rejects empty file content with validation error', async () => {
    const generated: GeneratedCode = {
      files: [{ path: 'empty.ts', content: '', action: 'create', language: 'typescript' }],
      summary: 'test',
    };

    await expect(writer.writeFiles(generated)).rejects.toThrow('empty file content');
  });

  it('handles paths with spaces and Korean characters', async () => {
    const generated: GeneratedCode = {
      files: [
        {
          path: '프로젝트/my file.ts',
          content: '// 한글 파일',
          action: 'create',
          language: 'typescript',
        },
      ],
      summary: 'test',
    };

    const written = await writer.writeFiles(generated);

    expect(written).toEqual(['프로젝트/my file.ts']);
    const content = await fs.readFile(path.join(tmpDir, '프로젝트/my file.ts'), 'utf-8');
    expect(content).toBe('// 한글 파일');
  });

  it('contentHash returns consistent SHA-256', () => {
    const hash1 = FileWriter.contentHash('hello');
    const hash2 = FileWriter.contentHash('hello');
    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64); // SHA-256 hex
  });
});
