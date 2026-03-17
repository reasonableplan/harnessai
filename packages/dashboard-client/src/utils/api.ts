/** 공통 API fetch wrapper — 인증 헤더 자동 추가. */

const BASE_URL = import.meta.env.VITE_API_URL ?? '';
const AUTH_TOKEN = import.meta.env.VITE_DASHBOARD_AUTH_TOKEN as string | undefined;

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }
  return headers;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = authHeaders(
    init?.headers as Record<string, string> | undefined,
  );
  return fetch(`${BASE_URL}${path}`, { ...init, headers });
}

export async function apiGet(path: string): Promise<Response> {
  return apiFetch(path);
}

export async function apiPut(path: string, body: unknown): Promise<Response> {
  return apiFetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
