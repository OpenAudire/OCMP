import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';

import { ApiError, isApiError } from '../api/client';
import { fetchAuthOptions, queryKeys } from '../api/endpoints';

/** Used until the server's rules have loaded; the server checks again anyway. */
const FALLBACK = { min: 12, max: 256 };

export function useAuthOptions() {
  return useQuery({ queryKey: queryKeys.authOptions, queryFn: fetchAuthOptions });
}

export function usePasswordLimits(): { min: number; max: number } {
  const { data } = useAuthOptions();
  return data ? { min: data.password_min_length, max: data.password_max_length } : FALLBACK;
}

/** Form validators for a new password and its repetition. */
export function newPasswordValidators(t: TFunction, limits: { min: number; max: number }) {
  return {
    newPassword: (value: string) => {
      if (value.length < limits.min) return t('auth.password_rules.tooShort', limits);
      if (value.length > limits.max) return t('auth.password_rules.tooLong', limits);
      return null;
    },
    confirmPassword: (value: string, values: { newPassword: string }) =>
      value === values.newPassword ? null : t('auth.password_rules.mismatch'),
  };
}

/** A user-facing message for errors shared by the sign-in pages. */
export function commonErrorMessage(t: TFunction, error: unknown): string {
  if (isApiError(error, 429)) {
    const seconds = (error as ApiError).retryAfterSeconds ?? 60;
    return t('auth.errors.tooManyAttempts', { count: Math.max(1, Math.ceil(seconds / 60)) });
  }
  return t('auth.errors.generic');
}
