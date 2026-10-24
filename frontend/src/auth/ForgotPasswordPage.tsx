import { useState } from 'react';
import { Alert, Anchor, Button, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { requestPasswordReset } from '../api/endpoints';
import { SuccessNotice } from '../pages/SuccessNotice';
import { AuthCard } from './AuthCard';
import { commonErrorMessage } from './passwordRules';

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [sent, setSent] = useState(false);
  const form = useForm({
    initialValues: { email: '' },
    validate: { email: (value) => (value.trim() ? null : t('auth.emailRequired')) },
  });
  const request = useMutation({
    mutationFn: (email: string) => requestPasswordReset(email.trim()),
    onSuccess: () => setSent(true),
  });

  return (
    <AuthCard title={t('auth.forgot.title')}>
      {sent ? (
        // The same message whether or not the account exists (as the API does).
        <SuccessNotice>{t('auth.forgot.sent')}</SuccessNotice>
      ) : (
        <form noValidate onSubmit={form.onSubmit(({ email }) => request.mutate(email))}>
          <Stack gap="md">
            <Text size="sm">{t('auth.forgot.intro')}</Text>
            {request.isError && (
              <Alert color="red">
                {commonErrorMessage(t, request.error)}
              </Alert>
            )}
            <TextInput
              label={t('auth.email')}
              type="email"
              autoComplete="email"
              required
              {...form.getInputProps('email')}
            />
            <Button type="submit" loading={request.isPending} fullWidth>
              {t('auth.forgot.submit')}
            </Button>
          </Stack>
        </form>
      )}
      <Anchor component={Link} to="/login" size="sm">
        {t('auth.forgot.back')}
      </Anchor>
    </AuthCard>
  );
}
