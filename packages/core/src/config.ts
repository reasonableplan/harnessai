import { config as loadDotenv } from 'dotenv';
import { ConfigError } from './errors.js';

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
    if (requireAll && !fallback) return requiredEnv(key);
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
      projectNumber: process.env.GITHUB_PROJECT_NUMBER
        ? (Number.isNaN(Number(process.env.GITHUB_PROJECT_NUMBER)) ? undefined : Number(process.env.GITHUB_PROJECT_NUMBER))
        : undefined,
    },
    claude: {
      apiKey: env('ANTHROPIC_API_KEY'),
    },
    workspace: {
      workDir: process.env.GIT_WORK_DIR ?? './workspace',
    },
    dashboard: {
      port: Number(process.env.DASHBOARD_PORT) || 3001,
      corsOrigins: process.env.CORS_ALLOWED_ORIGINS
        ? process.env.CORS_ALLOWED_ORIGINS.split(',').map((o) => o.trim())
        : ['http://localhost:3000', 'http://localhost:5173'],
    },
    logging: {
      level: process.env.LOG_LEVEL ?? 'info',
      isProduction: process.env.NODE_ENV === 'production',
    },
  };
}
