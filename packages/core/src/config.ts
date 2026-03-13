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
    claude: {
      apiKey: env('ANTHROPIC_API_KEY'),
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
