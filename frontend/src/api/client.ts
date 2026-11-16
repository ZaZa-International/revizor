import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type { ErrorResponse, TokenResponse, User } from './types';

const SESSION_KEY = 'revizor.session';
export const UNAUTHORIZED_EVENT = 'revizor:unauthorized';

export interface Session {
  token: string;
  expiresAt: number;
  user: User;
}

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.token || session.expiresAt <= Date.now()) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function setSession(token: TokenResponse): Session {
  const session: Session = {
    token: token.access_token,
    expiresAt: Date.now() + token.expires_in_minutes * 60_000 - 30_000,
    user: token.user,
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: { field?: string | null; message?: string | null }[];
  readonly requestId: string | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details: ErrorResponse['error']['details'] = [],
    requestId: string | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details ?? [];
    this.requestId = requestId;
  }

  get retryable(): boolean {
    return this.status >= 500 || this.code === 'rate_limited';
  }
}

export const api = createClient<paths>({ baseUrl: '' });

api.use({
  onRequest({ request }) {
    const session = getSession();
    if (session) request.headers.set('Authorization', `Bearer ${session.token}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && getSession()) {
      clearSession();
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    return response;
  },
});

interface Fetched<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

export async function unwrap<T>(promise: Promise<Fetched<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined) {
    const body = error as Partial<ErrorResponse>;
    if (body?.error?.code) {
      throw new ApiError(
        body.error.code,
        body.error.message,
        response.status,
        body.error.details,
        body.error.request_id ?? response.headers.get('x-request-id'),
      );
    }
    throw new ApiError('internal_error', `Ошибка сервера (${response.status})`, response.status);
  }
  if (data === undefined) {
    throw new ApiError('internal_error', 'Пустой ответ сервера', response.status);
  }
  return data;
}

export function networkError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(
    'network_error',
    'Не удалось связаться с сервером. Проверьте подключение или откройте демо-режим.',
    0,
  );
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Неизвестная ошибка';
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}