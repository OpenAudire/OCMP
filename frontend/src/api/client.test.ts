import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { api, ApiError, isApiError } from './client';

describe('api client', () => {
  it('sends the session cookie and the CSRF header expected by the API', () => {
    expect(api.defaults.baseURL).toBe('/api/v1');
    expect(api.defaults.withCredentials).toBe(true);
    expect(api.defaults.xsrfCookieName).toBe('ocmp_csrf');
    expect(api.defaults.xsrfHeaderName).toBe('X-CSRF-Token');
  });

  it('turns failed responses into ApiError with status and server message', async () => {
    const adapter = async (config: InternalAxiosRequestConfig) => {
      const response = {
        data: { detail: 'You do not have permission to do this.' },
        status: 403,
        statusText: 'Forbidden',
        headers: {},
        config,
      };
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, response);
    };

    const error = await api.get('/users', { adapter }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error, 403)).toBe(true);
    expect(isApiError(error, 401)).toBe(false);
    expect((error as ApiError).message).toBe('You do not have permission to do this.');
  });

  it('reports network failures with status 0', async () => {
    const adapter = async (config: InternalAxiosRequestConfig) => {
      throw new AxiosError('Network Error', 'ERR_NETWORK', config);
    };

    const error = await api.get('/auth/me', { adapter }).catch((e: unknown) => e);

    expect(isApiError(error, 0)).toBe(true);
  });
});
