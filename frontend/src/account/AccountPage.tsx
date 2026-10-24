import { useState } from 'react';
import { Alert, Button, PasswordInput, Stack, Text, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { changePassword } from '../api/endpoints';
import {
  commonErrorMessage,
  newPasswordValidators,
  usePasswordLimits,
} from '../auth/passwordRules';
import { SuccessNotice } from '../pages/SuccessNotice';
import { useSession } from '../session/useSession';

function ChangePasswordForm() {
  const { t } = useTranslation();
  const limits = usePasswordLimits();
  const [changed, setChanged] = useState(false);
  const form = useForm({
    initialValues: { currentPassword: '', newPassword: '', confirmPassword: '' },
    validate: {
      currentPassword: (value: string) => (value ? null : t('auth.passwordRequired')),
      ...newPasswordValidators(t, limits),
    },
  });
  const change = useMutation({
    mutationFn: (values: typeof form.values) =>
      changePassword(values.currentPassword, values.newPassword),
    onSuccess: () => {
      form.reset();
      setChanged(true);
    },
  });

  let errorMessage: string | null = null;
  if (change.isError) {
    if (isApiError(change.error, 400)) errorMessage = t('account.wrongCurrent');
    else if (isApiError(change.error, 422))
      errorMessage = t('auth.password_rules.rejected', limits);
    else errorMessage = commonErrorMessage(t, change.error);
  }

  return (
    <form
      noValidate
      onSubmit={form.onSubmit((values) => {
        setChanged(false);
        change.mutate(values);
      })}
    >
      <Stack gap="md" maw={420}>
        {changed && (
          <SuccessNotice>{t('account.changed')}</SuccessNotice>
        )}
        {errorMessage && (
          <Alert color="red">
            {errorMessage}
          </Alert>
        )}
        <PasswordInput
          label={t('account.currentPassword')}
          autoComplete="current-password"
          required
          {...form.getInputProps('currentPassword')}
        />
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
        <Button type="submit" loading={change.isPending} w="fit-content">
          {t('account.save')}
        </Button>
      </Stack>
    </form>
  );
}

export function AccountPage() {
  const { t } = useTranslation();
  const { data: session } = useSession();
  if (!session) return null;
  const { user } = session;

  return (
    <Stack gap="lg" py="md">
      <Title order={2}>{t('account.title')}</Title>
      <Stack gap={2}>
        <Text fw={600}>{user.display_name}</Text>
        <Text c="dimmed">{user.email}</Text>
      </Stack>
      <Title order={3}>{t('account.changePassword')}</Title>
      {user.has_password ? <ChangePasswordForm /> : <Text>{t('account.ssoOnly')}</Text>}
    </Stack>
  );
}
