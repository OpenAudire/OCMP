import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  NativeSelect,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconKey } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { createApiToken, fetchApiTokens, queryKeys, revokeApiToken } from '../api/endpoints';
import type { ApiTokenCreated, ApiTokenInfo, TokenScope } from '../api/types';
import adminClasses from '../admin/Admin.module.css';
import { formatDay } from '../admin/adminFormat';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';

const LIFETIMES = [7, 30, 90, 180, 365];

function errorText(t: TFunction, error: unknown): string {
  if (isApiError(error, 409, 422) && error.message) return error.message;
  return t('curriculum.edit.errors.generic');
}

/** Shows a new token once: it cannot be read again. */
function Created({ token, onClose }: { token: ApiTokenCreated; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <EditDialog opened title={t('account.tokens.createdTitle')} onClose={onClose}>
      <Stack gap="md">
        <Alert color="ochre" variant="light">
          {t('account.tokens.copyNow')}
        </Alert>
        <Text fw={600}>{token.name}</Text>
        <code className={adminClasses.tokenSecret} data-testid="new-token">
          {token.token}
        </code>
        <Text size="sm" c="dimmed">
          {t('account.tokens.howToUse')}
        </Text>
        <Group justify="flex-end">
          <Button
            variant="default"
            onClick={() => void navigator.clipboard?.writeText(token.token)}
          >
            {t('account.tokens.copy')}
          </Button>
          <Button onClick={onClose}>{t('account.tokens.done')}</Button>
        </Group>
      </Stack>
    </EditDialog>
  );
}

function NewTokenDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (token: ApiTokenCreated) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<TokenScope[]>(['read']);
  const [days, setDays] = useState(90);
  const make = useMutation({
    mutationFn: () => createApiToken({ name: name.trim(), scopes, days }),
    onSuccess: onCreated,
  });
  return (
    <EditDialog opened title={t('account.tokens.new')} onClose={onClose}>
      <DialogForm
        submitLabel={t('account.tokens.make')}
        error={make.isError ? errorText(t, make.error) : null}
        busy={make.isPending}
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() && scopes.length > 0) make.mutate();
        }}
        onClose={onClose}
      >
        <Stack gap="md">
          <TextInput
            label={t('account.tokens.name')}
            description={t('account.tokens.nameHelp')}
            value={name}
            maxLength={100}
            required
            onChange={(event) => setName(event.currentTarget.value)}
            data-autofocus
          />
          <fieldset className={adminClasses.fieldset}>
            <legend>{t('account.tokens.scopes')}</legend>
            <Stack gap={6}>
              {(['read', 'write'] as TokenScope[]).map((scope) => (
                <Checkbox
                  key={scope}
                  label={t(`account.tokens.scope.${scope}`)}
                  description={t(`account.tokens.scopeHelp.${scope}`)}
                  checked={scopes.includes(scope)}
                  onChange={(event) =>
                    setScopes(
                      event.currentTarget.checked
                        ? [...scopes, scope]
                        : scopes.filter((s) => s !== scope)
                    )
                  }
                />
              ))}
            </Stack>
          </fieldset>
          <NativeSelect
            label={t('account.tokens.lifetime')}
            value={String(days)}
            onChange={(event) => setDays(Number(event.currentTarget.value))}
            data={LIFETIMES.map((d) => ({ value: String(d), label: t('account.tokens.days', { count: d }) }))}
          />
        </Stack>
      </DialogForm>
    </EditDialog>
  );
}

function TokenRow({ token, onRevoke }: { token: ApiTokenInfo; onRevoke: (token: ApiTokenInfo) => void }) {
  const { t, i18n } = useTranslation();
  return (
    <Table.Tr>
      <Table.Td>
        <strong>{token.name}</strong>
        <Text size="sm" c="dimmed">
          {token.token_prefix}…
        </Text>
      </Table.Td>
      <Table.Td>{token.scopes.map((s) => t(`account.tokens.scope.${s}`)).join(', ')}</Table.Td>
      <Table.Td>
        {token.state === 'active' ? (
          t('account.tokens.expiresOn', { date: formatDay(token.expires_at, i18n.language) })
        ) : (
          <Badge variant="light" color="gray">
            {t(`account.tokens.state.${token.state}`)}
          </Badge>
        )}
        <Text size="sm" c="dimmed">
          {token.last_used_at
            ? t('account.tokens.lastUsed', { date: formatDay(token.last_used_at, i18n.language) })
            : t('account.tokens.neverUsed')}
        </Text>
      </Table.Td>
      <Table.Td>
        {token.state === 'active' && (
          <Button
            size="xs"
            variant="subtle"
            color="red"
            onClick={() => onRevoke(token)}
            aria-label={t('account.tokens.revokeNamed', { name: token.name })}
          >
            {t('account.tokens.revoke')}
          </Button>
        )}
      </Table.Td>
    </Table.Tr>
  );
}

/** Your own API tokens: make one (shown once), see when it was last used, revoke it. */
export function ApiTokens() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const tokens = useQuery({ queryKey: queryKeys.apiTokens, queryFn: fetchApiTokens });
  const [making, setMaking] = useState(false);
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const [revoking, setRevoking] = useState<ApiTokenInfo | null>(null);
  const revoke = useMutation({
    mutationFn: (id: string) => revokeApiToken(id),
    onSuccess: async () => {
      setRevoking(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiTokens });
    },
  });

  return (
    <Paper withBorder component="section" aria-labelledby="api-tokens" p={{ base: 'md', sm: 'xl' }}>
      <Stack gap="md">
        <Group justify="space-between" align="start">
          <div>
            <Title order={2} id="api-tokens">
              {t('account.tokens.title')}
            </Title>
            <Text size="sm" c="dimmed" maw={560}>
              {t('account.tokens.help')}
            </Text>
          </div>
          <Button leftSection={<IconKey size={18} aria-hidden />} onClick={() => setMaking(true)}>
            {t('account.tokens.new')}
          </Button>
        </Group>
        {tokens.isError && <Alert color="red">{t('account.tokens.error')}</Alert>}
        {tokens.data && tokens.data.length === 0 && (
          <Text c="dimmed">{t('account.tokens.none')}</Text>
        )}
        {tokens.data && tokens.data.length > 0 && (
          <Table.ScrollContainer minWidth={520}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('account.tokens.name')}</Table.Th>
                  <Table.Th>{t('account.tokens.scopes')}</Table.Th>
                  <Table.Th>{t('account.tokens.status')}</Table.Th>
                  <Table.Th>
                    <span className={adminClasses.visuallyHidden}>{t('admin.users.actions')}</span>
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {tokens.data.map((token) => (
                  <TokenRow key={token.id} token={token} onRevoke={setRevoking} />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
      {making && (
        <NewTokenDialog
          onClose={() => setMaking(false)}
          onCreated={async (token) => {
            setMaking(false);
            setCreated(token);
            await queryClient.invalidateQueries({ queryKey: queryKeys.apiTokens });
          }}
        />
      )}
      {created && <Created token={created} onClose={() => setCreated(null)} />}
      {revoking && (
        <EditDialog opened title={t('account.tokens.revoke')} onClose={() => setRevoking(null)}>
          <DialogForm
            submitLabel={t('account.tokens.revoke')}
            danger
            error={revoke.isError ? errorText(t, revoke.error) : null}
            busy={revoke.isPending}
            onSubmit={(event) => {
              event.preventDefault();
              revoke.mutate(revoking.id);
            }}
            onClose={() => setRevoking(null)}
          >
            <Text>{t('account.tokens.revokeBody', { name: revoking.name })}</Text>
          </DialogForm>
        </EditDialog>
      )}
    </Paper>
  );
}
