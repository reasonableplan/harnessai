import pino from 'pino';

// process.env를 직접 참조한다. loadConfig()보다 logger가 먼저 초기화되어야 하므로
// AppConfig DI를 사용할 수 없다. 로거는 모든 모듈에서 import하는 최하위 의존성이다.
const LOG_LEVEL = process.env.LOG_LEVEL ?? 'info';

const rootLogger = pino({
  level: LOG_LEVEL,
  transport:
    process.env.NODE_ENV !== 'production'
      ? { target: 'pino/file', options: { destination: 1 } }
      : undefined,
});

/**
 * 모듈별 child logger를 생성한다.
 * 예: createLogger('BoardWatcher') → { module: 'BoardWatcher' } 필드 자동 포함
 */
export function createLogger(module: string) {
  return rootLogger.child({ module });
}

export type Logger = ReturnType<typeof createLogger>;
