import axios, { AxiosError } from 'axios';

/**
 * HTTP client for the OCMP API.
 *
 * Session cookies are sent automatically (same origin). For state-changing
 * requests axios copies the readable CSRF cookie into the CSRF header, which the
 * API checks against the session (ADR 009).
 */
export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  xsrfCookieName: 'ocmp_csrf',
  xsrfHeaderName: 'X-CSRF-Token',
  headers: { Accept: 'application/json' },
});

/** An API error with its HTTP status and the server's message, if any. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function detailOf(data: unknown): string | undefined {
  if (data && typeof data === 'object' && 'detail' in data) {
    const { detail } = data as { detail: unknown };
    if (typeof detail === 'string') return detail;
  }
  return undefined;
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status ?? 0;
    return Promise.reject(new ApiError(status, detailOf(error.response?.data) ?? error.message));
  }
);

/** Whether an error is an API error with one of the given statuses. */
export function isApiError(error: unknown, ...statuses: number[]): error is ApiError {
  return error instanceof ApiError && (statuses.length === 0 || statuses.includes(error.status));
}
