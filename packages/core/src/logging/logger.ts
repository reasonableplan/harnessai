import pino from 'pino';

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
