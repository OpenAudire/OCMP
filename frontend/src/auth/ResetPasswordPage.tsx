import { useEffect, useState } from 'react';
import { Alert, Anchor, Button, PasswordInput, Stack } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { isApiError } from '../api/client';
import { confirmPasswordReset, queryKeys } from '../api/endpoints';
import { SuccessNotice } from '../pages/SuccessNotice';
import { AuthCard } from './AuthCard';
import { commonErrorMessage, newPasswordValidators, usePasswordLimits } from './passwordRules';

/** The token arrives in the URL fragment (never sent to servers): #token=... */
function tokenFrom(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, '')).get('token');
}

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const limits = usePasswordLimits();
  // Read once, then take the token out of the address bar and browser history.
  const [token] = useState(() => tokenFrom(location.hash));
  const [outcome, setOutcome] = useState<'done' | 'invalid' | null>(null);

  useEffect(() => {
    if (location.hash) navigate(location.pathname, { replace: true });
  }, [location.hash, location.pathname, navigate]);

  const form = useForm({
    initialValues: { newPassword: '', confirmPassword: '' },
    validate: newPasswordValidators(t, limits),
  });

  const reset = useMutation({
    mutationFn: (newPassword: string) => confirmPasswordReset(token ?? '', newPassword),
    onSuccess: () => {
      // Every session was signed out by the server.
      queryClient.removeQueries({ queryKey: queryKeys.session });
      setOutcome('done');
    },
    onError: (error) => {
      if (isApiError(error, 400)) setOutcome('invalid');
    },
  });

  const requestNew = (
    <Anchor component={Link} to="/forgot-password" size="sm">
      {t('auth.reset.requestNew')}
    </Anchor>
  );

  if (!token || outcome === 'invalid') {
    return (
      <AuthCard title={t('auth.reset.title')}>
        <Alert color="red">
          {t(token ? 'auth.reset.invalidLink' : 'auth.reset.missingToken')}
        </Alert>
        {requestNew}
      </AuthCard>
    );
  }

  if (outcome === 'done') {
    return (
      <AuthCard title={t('auth.reset.title')}>
        <SuccessNotice>{t('auth.reset.done')}</SuccessNotice>
        <Button component={Link} to="/login" fullWidth>
          {t('auth.login')}
        </Button>
      </AuthCard>
    );
  }

  const errorMessage =
    reset.isError &&
    (isApiError(reset.error, 422)
      ? t('auth.password_rules.rejected', limits)
      : commonErrorMessage(t, reset.error));

  return (
    <AuthCard title={t('auth.reset.title')}>
      {errorMessage && (
        <Alert color="red">
          {errorMessage}
        </Alert>
      )}
      <form noValidate onSubmit={form.onSubmit((values) => reset.mutate(values.newPassword))}>
        <Stack gap="md">
          <PasswordInput
            label={t('auth.reset.newPassword')}
            description={t('auth.password_rules.hint', limits)}
            autoComplete="new-password"
            required
            {...form.getInputProps('newPassword')}
          />
          <PasswordInput
            label={t('auth.reset.confirmPassword')}
            autoComplete="new-password"
            required
            {...form.getInputProps('confirmPassword')}
          />
          <Button type="submit" loading={reset.isPending} fullWidth>
            {t('auth.reset.submit')}
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
