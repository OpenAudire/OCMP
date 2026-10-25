import { useState } from 'react';
import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  Group,
  PasswordInput,
  Stack,
  Stepper,
  Table,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate } from 'react-router';

import { isApiError } from '../api/client';
import { fetchSetupStatus, queryKeys, runSetup } from '../api/endpoints';
import { AuthCard } from '../auth/AuthCard';
import { commonErrorMessage, newPasswordValidators, usePasswordLimits } from '../auth/passwordRules';
import { FullPageLoader } from '../pages/StatusPages';

const STEP_FIELDS = [
  ['token', 'institutionName', 'institutionShortCode', 'country'],
  ['adminName', 'adminEmail', 'newPassword', 'confirmPassword'],
] as const;

/** First-run setup: the institution and the first platform admin. */
export function SetupPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const limits = usePasswordLimits();
  const [step, setStep] = useState(0);
  const status = useQuery({ queryKey: queryKeys.setupStatus, queryFn: fetchSetupStatus });

  const required = (value: string) => (value.trim() ? null : t('setup.errors.required'));
  const form = useForm({
    initialValues: {
      token: '',
      institutionName: '',
      institutionShortCode: '',
      country: 'ZA',
      healthProfile: false,
      adminName: '',
      adminEmail: '',
      newPassword: '',
      confirmPassword: '',
    },
    validate: {
      token: required,
      institutionName: required,
      institutionShortCode: (value) =>
        /^[A-Za-z0-9-]{2,32}$/.test(value.trim()) ? null : t('setup.errors.shortCode'),
      country: (value) => (/^[A-Za-z]{2}$/.test(value.trim()) ? null : t('setup.errors.country')),
      adminName: required,
      adminEmail: required,
      ...newPasswordValidators(t, limits),
    },
  });

  const setup = useMutation({
    mutationFn: () => {
      const v = form.values;
      return runSetup({
        token: v.token.trim(),
        institution_name: v.institutionName.trim(),
        institution_short_code: v.institutionShortCode.trim(),
        country: v.country.trim().toUpperCase(),
        health_profile: v.healthProfile,
        admin_display_name: v.adminName.trim(),
        admin_email: v.adminEmail.trim(),
        admin_password: v.newPassword,
      });
    },
    onSuccess: async () => {
      await Promise.all(
        [queryKeys.session, queryKeys.setupStatus, queryKeys.institution].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey })
        )
      );
      navigate('/', { replace: true });
    },
    onError: (error) => {
      if (isApiError(error, 403)) setStep(0);
      else if (isApiError(error, 422)) setStep(1);
    },
  });

  if (status.isPending) return <FullPageLoader />;
  if (status.data && !status.data.needs_setup && !setup.isSuccess) {
    return <Navigate to="/login" replace />;
  }

  const nextStep = () => {
    const fields = STEP_FIELDS[step] ?? [];
    const invalid = fields.map((field) => form.validateField(field).hasError).some(Boolean);
    if (!invalid) setStep((current) => current + 1);
  };

  let error: string | null = null;
  if (setup.isError) {
    if (isApiError(setup.error, 403)) error = t('setup.errors.token');
    else if (isApiError(setup.error, 409)) error = t('setup.errors.alreadyDone');
    else if (isApiError(setup.error, 422)) error = t('setup.errors.invalidAccount', limits);
    else error = commonErrorMessage(t, setup.error);
  }
  const v = form.values;
  const summary: [string, string][] = [
    [t('setup.institutionName'), v.institutionName],
    [t('setup.institutionShortCode'), v.institutionShortCode.toUpperCase()],
    [t('setup.country'), v.country.toUpperCase()],
    [t('setup.healthProfile'), t(v.healthProfile ? 'setup.yes' : 'setup.no')],
    [t('setup.adminName'), v.adminName],
    [t('setup.adminEmail'), v.adminEmail],
  ];

  return (
    <AuthCard title={t('setup.title')}>
      <Text size="sm">{t('setup.intro')}</Text>
      {error && (
        <Alert color="red">
          {error}
          {isApiError(setup.error, 409) && (
            <>
              {' '}
              <Anchor component={Link} to="/login">
                {t('auth.login')}
              </Anchor>
            </>
          )}
        </Alert>
      )}
      <Stepper active={step} size="sm" allowNextStepsSelect={false}>
        <Stepper.Step label={t('setup.steps.institution')}>
          <Stack gap="md" pt="md">
            <TextInput
              label={t('setup.token')}
              description={t('setup.tokenHelp')}
              autoComplete="off"
              required
              {...form.getInputProps('token')}
            />
            <TextInput
              label={t('setup.institutionName')}
              autoComplete="organization"
              required
              {...form.getInputProps('institutionName')}
            />
            <TextInput
              label={t('setup.institutionShortCode')}
              description={t('setup.shortCodeHelp')}
              required
              {...form.getInputProps('institutionShortCode')}
            />
            <TextInput
              label={t('setup.country')}
              description={t('setup.countryHelp')}
              maxLength={2}
              required
              {...form.getInputProps('country')}
            />
            <Checkbox
              label={t('setup.healthProfile')}
              description={t('setup.healthProfileHelp')}
              {...form.getInputProps('healthProfile', { type: 'checkbox' })}
            />
          </Stack>
        </Stepper.Step>
        <Stepper.Step label={t('setup.steps.admin')}>
          <Stack gap="md" pt="md">
            <TextInput
              label={t('setup.adminName')}
              autoComplete="name"
              required
              {...form.getInputProps('adminName')}
            />
            <TextInput
              label={t('setup.adminEmail')}
              type="email"
              autoComplete="username"
              required
              {...form.getInputProps('adminEmail')}
            />
            <PasswordInput
              label={t('setup.adminPassword')}
              description={t('auth.password_rules.hint', limits)}
              autoComplete="new-password"
              required
              {...form.getInputProps('newPassword')}
            />
            <PasswordInput
              label={t('setup.confirmPassword')}
              autoComplete="new-password"
              required
              {...form.getInputProps('confirmPassword')}
            />
          </Stack>
        </Stepper.Step>
        <Stepper.Step label={t('setup.steps.confirm')}>
          <Stack gap="md" pt="md">
            <Text size="sm">{t('setup.review')}</Text>
            <Table>
              <Table.Tbody>
                {summary.map(([label, value]) => (
                  <Table.Tr key={label}>
                    <Table.Th scope="row">{label}</Table.Th>
                    <Table.Td>{value}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Stepper.Step>
      </Stepper>
      <Group justify="space-between">
        <Button
          variant="default"
          onClick={() => setStep((current) => current - 1)}
          disabled={step === 0 || setup.isPending}
        >
          {t('setup.back')}
        </Button>
        {step < 2 ? (
          <Button onClick={nextStep}>{t('setup.next')}</Button>
        ) : (
          <Button onClick={() => setup.mutate()} loading={setup.isPending}>
            {t('setup.submit')}
          </Button>
        )}
      </Group>
    </AuthCard>
  );
}
