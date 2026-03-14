import { timingSafeEqual } from 'crypto';
import type { Request, Response, NextFunction } from 'express';
import { createLogger } from '@agent/core';

const log = createLogger('AuthMiddleware');

/**
 * Timing-safe string comparison.
 * Pads both buffers to the same length to prevent length-based timing leaks.
 */
function safeCompare(a: string, b: string): boolean {
  const maxLen = Math.max(a.length, b.length);
  const bufA = Buffer.alloc(maxLen);
  const bufB = Buffer.alloc(maxLen);
  Buffer.from(a).copy(bufA);
  Buffer.from(b).copy(bufB);
  return a.length === b.length && timingSafeEqual(bufA, bufB);
}

/**
 * Express middleware that validates Bearer token on /api/* routes.
 * If `expectedToken` is undefined or empty, auth is skipped (dev mode).
 * 프로덕션(NODE_ENV=production)에서 토큰 미설정 시 경고 로그를 출력한다.
 */
export function createAuthMiddleware(
  expectedToken: string | undefined,
): (req: Request, res: Response, next: NextFunction) => void {
  // Dev mode: no token configured → skip auth (with production warning)
  if (!expectedToken) {
    if (process.env.NODE_ENV === 'production') {
      log.error('DASHBOARD_AUTH_TOKEN is not set in production — all API endpoints are unauthenticated!');
    }
    return (_req, _res, next) => next();
  }

  return (req: Request, res: Response, next: NextFunction) => {
    const header = req.headers.authorization;
    if (!header || !header.startsWith('Bearer ')) {
      log.warn({ path: req.path }, 'Missing or invalid Authorization header');
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }

    const token = header.slice('Bearer '.length);
    if (!safeCompare(token, expectedToken)) {
      log.warn({ path: req.path }, 'Invalid auth token');
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }

    next();
  };
}

/**
 * Validate a WebSocket connection token.
 * If `expectedToken` is undefined or empty, always returns true (dev mode).
 */
export function validateWsToken(
  expectedToken: string | undefined,
  clientToken: string | undefined,
): boolean {
  if (!expectedToken) return true;
  if (!clientToken) return false;
  return safeCompare(clientToken, expectedToken);
}
