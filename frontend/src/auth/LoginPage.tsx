import { useEffect, useState } from 'react';
import { Alert, Anchor, Button, Divider, PasswordInput, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';

import { isApiError } from '../api/client';
import { login, queryKeys, ssoLoginUrl } from '../api/endpoints';
import { FullPageLoader } from '../pages/StatusPages';
import { useSession } from '../session/useSession';
import { AuthCard } from './AuthCard';
import { commonErrorMessage, useAuthOptions } from './passwordRules';
import { safeNext } from './safeNext';

const SSO_ERRORS = new Set([
  'sso_unavailable',
  'sso_failed',
  'sso_cancelled',
  'sso_expired',
  'account_disabled',
  'account_exists',
  'no_email',
  'not_provisioned',
  'too_many_attempts',
]);

/** After this long, explain that sign-in is being slowed by earlier failures. */
const SLOW_SIGN_IN_MS = 3000;

export function LoginPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const ssoError = params.get('sso_error');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: session, isPending: sessionPending } = useSession();
  const { data: options } = useAuthOptions();
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  const form = useForm({
    initialValues: { email: '', password: '' },
    validate: {
      email: (value) => (value.trim() ? null : t('auth.emailRequired')),
      password: (value) => (value ? null : t('auth.passwordRequired')),
    },
  });

  const signIn = useMutation({
    mutationFn: (values: { email: string; password: string }) =>
      login(values.email.trim(), values.password),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.session });
      navigate(next, { replace: true });
    },
    onError: (err) => {
      form.setFieldValue('password', '');
      setError(
        isApiError(err, 401) ? t('auth.errors.invalidCredentials') : commonErrorMessage(t, err)
      );
    },
  });

  useEffect(() => {
    if (!signIn.isPending) {
      setSlow(false);
      return undefined;
    }
    const timer = setTimeout(() => setSlow(true), SLOW_SIGN_IN_MS);
    return () => clearTimeout(timer);
  }, [signIn.isPending]);

  if (sessionPending) return <FullPageLoader />;
  if (session) return <Navigate to={next} replace />;

  const ssoMessage = ssoError && t(`auth.sso.${SSO_ERRORS.has(ssoError) ? ssoError : 'sso_failed'}`);

  return (
    <AuthCard title={t('auth.login')}>
      {(error || ssoMessage) && (
        <Alert color="red">
          {error ?? ssoMessage}
        </Alert>
      )}
      <form
        noValidate
        onSubmit={form.onSubmit((values) => {
          setError(null);
          signIn.mutate(values);
        })}
      >
        <Stack gap="md">
          <TextInput
            label={t('auth.email')}
            type="email"
            autoComplete="username"
            required
            {...form.getInputProps('email')}
          />
          <PasswordInput
            label={t('auth.password')}
            autoComplete="current-password"
            required
            {...form.getInputProps('password')}
          />
          <Button type="submit" loading={signIn.isPending} fullWidth>
            {t('auth.login')}
          </Button>
          {slow && (
            <Text size="sm" c="dimmed" role="status">
              {t('auth.slowSignIn')}
            </Text>
          )}
          <Anchor component={Link} to="/forgot-password" size="sm">
            {t('auth.forgotPassword')}
          </Anchor>
        </Stack>
      </form>
      {options?.sso_enabled && (
        <>
          <Divider label={t('auth.or')} labelPosition="center" />
          <Button component="a" href={ssoLoginUrl(next)} variant="default" fullWidth>
            {t('auth.loginWithSSO', { provider: options.sso_provider_name })}
          </Button>
        </>
      )}
    </AuthCard>
  );
}
