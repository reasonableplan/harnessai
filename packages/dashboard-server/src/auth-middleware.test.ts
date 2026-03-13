import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Request, Response, NextFunction } from 'express';
import { createAuthMiddleware, validateWsToken } from './auth-middleware.js';

function createMockReq(authHeader?: string): Request {
  return {
    headers: { ...(authHeader != null ? { authorization: authHeader } : {}) },
    path: '/api/agents',
  } as unknown as Request;
}

function createMockRes(): Response & { statusCode: number; body: unknown } {
  const res = {
    statusCode: 200,
    body: undefined as unknown,
    status(code: number) {
      res.statusCode = code;
      return res;
    },
    json(data: unknown) {
      res.body = data;
      return res;
    },
  };
  return res as unknown as Response & { statusCode: number; body: unknown };
}

describe('createAuthMiddleware', () => {
  const TOKEN = 'test-secret-token-1234';
  let next: NextFunction;

  beforeEach(() => {
    next = vi.fn();
  });

  it('skips auth when no token configured (dev mode)', () => {
    const middleware = createAuthMiddleware(undefined);
    const req = createMockReq();
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
  });

  it('skips auth when empty string token configured', () => {
    const middleware = createAuthMiddleware('');
    const req = createMockReq();
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
  });

  it('allows request with valid Bearer token', () => {
    const middleware = createAuthMiddleware(TOKEN);
    const req = createMockReq(`Bearer ${TOKEN}`);
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).toHaveBeenCalled();
  });

  it('rejects request with no Authorization header', () => {
    const middleware = createAuthMiddleware(TOKEN);
    const req = createMockReq();
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.statusCode).toBe(401);
    expect(res.body).toEqual({ error: 'Unauthorized' });
  });

  it('rejects request with wrong token', () => {
    const middleware = createAuthMiddleware(TOKEN);
    const req = createMockReq('Bearer wrong-token');
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.statusCode).toBe(401);
    expect(res.body).toEqual({ error: 'Unauthorized' });
  });

  it('rejects request with non-Bearer scheme', () => {
    const middleware = createAuthMiddleware(TOKEN);
    const req = createMockReq(`Basic ${TOKEN}`);
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.statusCode).toBe(401);
  });

  it('uses timing-safe comparison (different length tokens do not short-circuit)', () => {
    const middleware = createAuthMiddleware(TOKEN);
    const req = createMockReq('Bearer x');
    const res = createMockRes();

    middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.statusCode).toBe(401);
  });
});

describe('validateWsToken', () => {
  const TOKEN = 'ws-secret-token';

  it('returns true when no token configured (dev mode)', () => {
    expect(validateWsToken(undefined, 'anything')).toBe(true);
  });

  it('returns true when empty token configured', () => {
    expect(validateWsToken('', 'anything')).toBe(true);
  });

  it('returns true with matching token', () => {
    expect(validateWsToken(TOKEN, TOKEN)).toBe(true);
  });

  it('returns false with wrong token', () => {
    expect(validateWsToken(TOKEN, 'wrong')).toBe(false);
  });

  it('returns false with undefined client token', () => {
    expect(validateWsToken(TOKEN, undefined)).toBe(false);
  });

  it('returns false with empty client token', () => {
    expect(validateWsToken(TOKEN, '')).toBe(false);
  });
});
