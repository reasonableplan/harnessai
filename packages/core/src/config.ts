import { config as loadDotenv } from 'dotenv';
import { ConfigError } from './errors.js';

/** 에이전트가 기본적으로 사용하는 Claude 모델 식별자. */
export const DEFAULT_CLAUDE_MODEL = 'claude-sonnet-4-20250514';

export interface AppConfig {
  database: {
    url: string;
  };
  github: {
    token: string;
    owner: string;
    repo: string;
    projectNumber?: number;
  };
  claude: {
    apiKey: string;
    /** true이면 Claude Code CLI를 LLM 백엔드로 사용 (Max 구독용, API 크레딧 불필요) */
    useCli: boolean;
  };
  localModel: {
    /** true이면 OpenAI 호환 모델을 LLM 백엔드로 사용 (Ollama, LM Studio, vLLM, HuggingFace, OpenRouter 등) */
    enabled: boolean;
    /** OpenAI 호환 API base URL (예: http://localhost:11434/v1) */
    baseUrl: string;
    /** 모델 이름 (예: llama3.1, codellama, deepseek-coder) */
    model: string;
    /** API 키. 로컬 모델은 불필요, HuggingFace/OpenRouter 등 클라우드 서비스는 필수. */
    apiKey?: string;
  };
  workspace: {
    workDir: string;
  };
  dashboard: {
    port: number;
    corsOrigins: string[];
    /** Bearer token for REST + WS auth. If empty/undefined, auth is skipped (dev mode). */
    authToken?: string;
  };
  logging: {
    level: string;
    isProduction: boolean;
  };
}

function requiredEnv(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new ConfigError(
      `Missing required environment variable: ${key}\nSee .env.example for reference.`,
    );
  }
  return value;
}

/**
 * 환경변수에서 숫자를 파싱한다. NaN이면 ConfigError를 던지고,
 * 변수가 없으면 defaultValue를 반환한다.
 */
function optionalEnvNumber(key: string, defaultValue: number): number {
  const raw = process.env[key];
  if (raw == null || raw === '') return defaultValue;
  const v = Number(raw);
  if (Number.isNaN(v)) throw new ConfigError(`Invalid numeric environment variable: ${key}="${raw}"`);
  return v;
}

/**
 * 환경 변수를 한번에 로드하여 타입이 있는 설정 객체를 반환한다.
 * entry point(main)에서 한번만 호출하고, DI로 전달한다.
 *
 * @param opts.requireAll true이면 모든 필수 환경변수를 검증 (프로덕션 모드).
 *                        false이면 선택적 로드 (테스트/개발용).
 */
export function loadConfig(opts: { requireAll?: boolean } = {}): AppConfig {
  loadDotenv();

  const requireAll = opts.requireAll ?? true;
  const env = (key: string, fallback?: string): string => {
    if (requireAll) return requiredEnv(key);
    return process.env[key] ?? fallback ?? '';
  };

  return {
    database: {
      url: env('DATABASE_URL'),
    },
    github: {
      token: env('GITHUB_TOKEN'),
      owner: env('GITHUB_OWNER'),
      repo: env('GITHUB_REPO'),
      projectNumber: process.env.GITHUB_PROJECT_NUMBER != null && process.env.GITHUB_PROJECT_NUMBER !== ''
        ? optionalEnvNumber('GITHUB_PROJECT_NUMBER', 0)
        : undefined,
    },
    claude: (() => {
      const localEnabled = process.env.USE_LOCAL_MODEL === 'true';
      const useCli = !localEnabled && (process.env.USE_CLAUDE_CLI === 'true' || !process.env.ANTHROPIC_API_KEY);
      const apiKey = process.env.ANTHROPIC_API_KEY ?? '';
      // requireAll=true(프로덕션)일 때만 apiKey 필수 검증 — 테스트/개발에서는 빈 값 허용
      if (requireAll && !useCli && !localEnabled && !apiKey) {
        throw new ConfigError(
          'ANTHROPIC_API_KEY is required when USE_CLAUDE_CLI and USE_LOCAL_MODEL are not enabled.\n'
          + 'Set ANTHROPIC_API_KEY, USE_CLAUDE_CLI=true, or USE_LOCAL_MODEL=true.',
        );
      }
      return { apiKey, useCli };
    })(),
    localModel: {
      enabled: process.env.USE_LOCAL_MODEL === 'true',
      baseUrl: process.env.LOCAL_MODEL_BASE_URL ?? 'http://localhost:11434/v1',
      model: process.env.LOCAL_MODEL_NAME ?? 'llama3.1',
      apiKey: process.env.LOCAL_MODEL_API_KEY || undefined,
    },
    workspace: {
      workDir: process.env.GIT_WORK_DIR ?? './workspace',
    },
    dashboard: {
      port: optionalEnvNumber('DASHBOARD_PORT', 3001),
      corsOrigins: process.env.CORS_ORIGINS
        ? process.env.CORS_ORIGINS.split(',').map((o) => o.trim())
        : ['http://localhost:3000', 'http://localhost:5173'],
      authToken: process.env.DASHBOARD_AUTH_TOKEN || undefined,
    },
    logging: {
      level: process.env.LOG_LEVEL ?? 'info',
      isProduction: process.env.NODE_ENV === 'production',
    },
  };
}
