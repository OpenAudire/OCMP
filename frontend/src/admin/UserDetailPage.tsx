import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Group,
  NativeSelect,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconChevronLeft, IconUserOff } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { isApiError } from '../api/client';
import {
  createAssignment,
  deleteAssignment,
  deleteUser,
  fetchRoles,
  fetchUser,
  fetchUserApiTokens,
  fetchUserAssignments,
  queryKeys,
  revokeApiToken,
  updateUser,
} from '../api/endpoints';
import type { AdminUser, ScopeType } from '../api/types';
import { useProgrammes } from '../curriculum/currentVersion';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { SuccessNotice } from '../pages/SuccessNotice';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import classes from './Admin.module.css';
import { ASSIGNABLE_SCOPES, formatDay, formatWhen, scopeLabel } from './adminFormat';

function errorText(t: TFunction, error: unknown): string {
  if (isApiError(error, 409, 422, 400) && error.message) return error.message;
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

function Details({ user }: { user: AdminUser }) {
  const { t, i18n } = useTranslation();
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState(user.display_name);
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState<'deactivate' | 'delete' | null>(null);
  const self = session?.user.id === user.id;

  const update = useMutation({
    mutationFn: (changes: { display_name?: string; is_active?: boolean }) =>
      updateUser(user.id, changes),
    onSuccess: async (updated) => {
      queryClient.setQueryData(queryKeys.adminUser(user.id), updated);
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setSaved(true);
      setConfirm(null);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteUser(user.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      void navigate('/admin/users');
    },
  });

  return (
    <Paper withBorder component="section" aria-labelledby="user-details" className={classes.card}>
      <Stack gap="md">
        <Group justify="space-between">
          <Title order={2} id="user-details" className={classes.sectionTitle}>
            {t('admin.users.details')}
          </Title>
          <Badge variant="light" color={user.is_active ? 'teal' : 'gray'}>
            {t(user.is_active ? 'admin.users.active' : 'admin.users.inactive')}
          </Badge>
        </Group>
        <dl className={classes.facts}>
          <dt>{t('admin.users.email')}</dt>
          <dd>{user.email}</dd>
          <dt>{t('admin.users.signIn')}</dt>
          <dd>{user.has_password ? t('admin.users.password') : t('admin.users.ssoOnly')}</dd>
          <dt>{t('admin.users.lastSignIn')}</dt>
          <dd>
            {user.last_login_at
              ? formatWhen(user.last_login_at, i18n.language)
              : t('admin.users.never')}
          </dd>
          <dt>{t('admin.users.created')}</dt>
          <dd>{formatDay(user.created_at, i18n.language)}</dd>
        </dl>
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            setSaved(false);
            if (name.trim()) update.mutate({ display_name: name.trim() });
          }}
        >
          <Group align="end">
            <TextInput
              label={t('admin.users.name')}
              value={name}
              maxLength={255}
              onChange={(event) => setName(event.currentTarget.value)}
              w={320}
            />
            <Button type="submit" variant="default" loading={update.isPending && confirm === null}>
              {t('admin.settings.save')}
            </Button>
          </Group>
        </form>
        {saved && <SuccessNotice>{t('admin.users.saved')}</SuccessNotice>}
        {update.isError && confirm === null && (
          <Alert color="red" role="alert">
            {errorText(t, update.error)}
          </Alert>
        )}
        <Group>
          {user.is_active ? (
            <Button
              variant="default"
              disabled={self}
              onClick={() => setConfirm('deactivate')}
              title={self ? t('admin.users.notYourself') : undefined}
            >
              {t('admin.users.deactivate')}
            </Button>
          ) : (
            <Button variant="default" onClick={() => update.mutate({ is_active: true })}>
              {t('admin.users.reactivate')}
            </Button>
          )}
          <Button
            color="red"
            variant="light"
            disabled={self}
            onClick={() => setConfirm('delete')}
            title={self ? t('admin.users.notYourself') : undefined}
          >
            {t('admin.users.delete')}
          </Button>
        </Group>
      </Stack>
      {confirm === 'deactivate' && (
        <EditDialog opened title={t('admin.users.deactivate')} onClose={() => setConfirm(null)}>
          <DialogForm
            submitLabel={t('admin.users.deactivate')}
            danger
            error={update.isError ? errorText(t, update.error) : null}
            busy={update.isPending}
            onSubmit={(event) => {
              event.preventDefault();
              update.mutate({ is_active: false });
            }}
            onClose={() => setConfirm(null)}
          >
            <Text>{t('admin.users.deactivateBody', { name: user.display_name })}</Text>
          </DialogForm>
        </EditDialog>
      )}
      {confirm === 'delete' && (
        <EditDialog opened title={t('admin.users.delete')} onClose={() => setConfirm(null)}>
          <DialogForm
            submitLabel={t('admin.users.delete')}
            danger
            error={remove.isError ? errorText(t, remove.error) : null}
            busy={remove.isPending}
            onSubmit={(event) => {
              event.preventDefault();
              remove.mutate();
            }}
            onClose={() => setConfirm(null)}
          >
            <Text>{t('admin.users.deleteBody', { name: user.display_name })}</Text>
          </DialogForm>
        </EditDialog>
      )}
    </Paper>
  );
}

function Assignments({ user }: { user: AdminUser }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const programmes = useProgrammes();
  const roles = useQuery({ queryKey: queryKeys.roles, queryFn: fetchRoles });
  const assignments = useQuery({
    queryKey: queryKeys.adminUserAssignments(user.id),
    queryFn: () => fetchUserAssignments(user.id),
  });
  const [roleKey, setRoleKey] = useState('');
  const [scopeType, setScopeType] = useState<ScopeType>('instance');
  const [scopeId, setScopeId] = useState('');
  const [expires, setExpires] = useState('');
  const [removing, setRemoving] = useState<string | null>(null);

  const role = roles.data?.find((r) => r.key === roleKey);
  const scopes = ASSIGNABLE_SCOPES.filter((s) => !role || role.scope_types.includes(s));
  const effectiveScope = scopes.includes(scopeType) ? scopeType : (scopes[0] ?? 'instance');
  const faculties = [
    ...new Map((programmes.data ?? []).map((p) => [p.faculty_id, p.faculty_name])).entries(),
  ];
  const targets =
    effectiveScope === 'faculty'
      ? faculties.map(([id, name]) => ({ value: id, label: name }))
      : effectiveScope === 'programme'
        ? (programmes.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))
        : [];
  const target = scopeId || targets[0]?.value || '';
  const ready =
    !!roleKey &&
    (effectiveScope === 'instance' || !!target) &&
    (!role?.requires_expiry || !!expires);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.adminUserAssignments(user.id) });
  const add = useMutation({
    mutationFn: () =>
      createAssignment({
        user_id: user.id,
        role_key: roleKey,
        scope_type: effectiveScope,
        scope_id: effectiveScope === 'instance' ? null : target,
        expires_at: expires ? `${expires}T23:59:59Z` : null,
      }),
    onSuccess: async () => {
      setRoleKey('');
      setExpires('');
      await refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deleteAssignment(id),
    onSuccess: async () => {
      setRemoving(null);
      await refresh();
    },
  });

  return (
    <Paper withBorder component="section" aria-labelledby="user-roles" className={classes.card}>
      <Stack gap="md">
        <div>
          <Title order={2} id="user-roles" className={classes.sectionTitle}>
            {t('admin.users.roles')}
          </Title>
          <Text size="sm" c="dimmed">
            {t('admin.users.rolesHelp')}
          </Text>
        </div>
        {assignments.isPending && <LoadingState title={t('admin.users.loading')} skeletons={1} />}
        {assignments.isError && (
          <ErrorState title={t('admin.users.error')} body={t('admin.users.errorBody')} />
        )}
        {assignments.data && assignments.data.length === 0 && (
          <Text c="dimmed">{t('admin.users.noRoles')}</Text>
        )}
        {assignments.data && assignments.data.length > 0 && (
          <Table.ScrollContainer minWidth={520}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('admin.roles.role')}</Table.Th>
                  <Table.Th>{t('admin.users.where')}</Table.Th>
                  <Table.Th>{t('admin.users.expires')}</Table.Th>
                  <Table.Th>
                    <span className={classes.visuallyHidden}>{t('admin.users.actions')}</span>
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {assignments.data.map((a) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>{a.role.name}</Table.Td>
                    <Table.Td>{scopeLabel(t, a, programmes.data ?? [])}</Table.Td>
                    <Table.Td>
                      {a.expires_at ? formatDay(a.expires_at, i18n.language) : t('admin.users.noExpiry')}
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        onClick={() => setRemoving(a.id)}
                        aria-label={t('admin.users.removeRole', { role: a.role.name })}
                      >
                        {t('admin.users.remove')}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}

        <form
          noValidate
          aria-label={t('admin.users.giveRole')}
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) add.mutate();
          }}
        >
          <Stack gap="sm">
            <Title order={3} className={classes.subTitle}>
              {t('admin.users.giveRole')}
            </Title>
            <div className={classes.formRow}>
              <NativeSelect
                label={t('admin.roles.role')}
                value={roleKey}
                onChange={(event) => setRoleKey(event.currentTarget.value)}
                data={[
                  { value: '', label: t('admin.users.chooseRole') },
                  ...(roles.data ?? []).map((r) => ({ value: r.key, label: r.name })),
                ]}
              />
              <NativeSelect
                label={t('admin.users.where')}
                value={effectiveScope}
                onChange={(event) => {
                  setScopeType(event.currentTarget.value as ScopeType);
                  setScopeId('');
                }}
                data={scopes.map((s) => ({ value: s, label: t(`admin.scope.type.${s}`) }))}
              />
              {effectiveScope !== 'instance' && (
                <NativeSelect
                  label={t(`admin.scope.type.${effectiveScope}`)}
                  value={target}
                  onChange={(event) => setScopeId(event.currentTarget.value)}
                  data={targets}
                />
              )}
              <TextInput
                label={t(role?.requires_expiry ? 'admin.users.expiresRequired' : 'admin.users.expiresOptional')}
                type="date"
                value={expires}
                onChange={(event) => setExpires(event.currentTarget.value)}
              />
            </div>
            {add.isError && (
              <Alert color="red" role="alert">
                {errorText(t, add.error)}
              </Alert>
            )}
            <Button type="submit" w="fit-content" loading={add.isPending} disabled={!ready}>
              {t('admin.users.assign')}
            </Button>
          </Stack>
        </form>
      </Stack>
      {removing && (
        <EditDialog opened title={t('admin.users.remove')} onClose={() => setRemoving(null)}>
          <DialogForm
            submitLabel={t('admin.users.remove')}
            danger
            error={revoke.isError ? errorText(t, revoke.error) : null}
            busy={revoke.isPending}
            onSubmit={(event) => {
              event.preventDefault();
              revoke.mutate(removing);
            }}
            onClose={() => setRemoving(null)}
          >
            <Text>{t('admin.users.removeBody', { name: user.display_name })}</Text>
          </DialogForm>
        </EditDialog>
      )}
    </Paper>
  );
}

function Tokens({ user }: { user: AdminUser }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const tokens = useQuery({
    queryKey: queryKeys.adminUserTokens(user.id),
    queryFn: () => fetchUserApiTokens(user.id),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => revokeApiToken(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.adminUserTokens(user.id) }),
  });
  const active = (tokens.data ?? []).filter((x) => x.state === 'active');
  return (
    <Paper withBorder component="section" aria-labelledby="user-tokens" className={classes.card}>
      <Stack gap="sm">
        <Title order={2} id="user-tokens" className={classes.sectionTitle}>
          {t('admin.users.tokens')}
        </Title>
        <Text size="sm" c="dimmed">
          {t('admin.users.tokensHelp')}
        </Text>
        {tokens.isError && <Text c="red">{t('admin.users.error')}</Text>}
        {tokens.data && active.length === 0 && <Text c="dimmed">{t('admin.users.noTokens')}</Text>}
        {active.length > 0 && (
          <Table.ScrollContainer minWidth={520}>
            <Table>
              <Table.Tbody>
                {active.map((token) => (
                  <Table.Tr key={token.id}>
                    <Table.Td>
                      <strong>{token.name}</strong> <Text span c="dimmed">{token.token_prefix}…</Text>
                    </Table.Td>
                    <Table.Td>{token.scopes.map((s) => t(`account.tokens.scope.${s}`)).join(', ')}</Table.Td>
                    <Table.Td>
                      {t('account.tokens.expiresOn', { date: formatDay(token.expires_at, i18n.language) })}
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        loading={revoke.isPending}
                        onClick={() => revoke.mutate(token.id)}
                        aria-label={t('account.tokens.revokeNamed', { name: token.name })}
                      >
                        {t('account.tokens.revoke')}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
    </Paper>
  );
}

/** Admin > People > one person: details, roles by place, and their API tokens. */
export function UserDetailPage() {
  const { t } = useTranslation();
  const { userId = '' } = useParams();
  const user = useQuery({
    queryKey: queryKeys.adminUser(userId),
    queryFn: () => fetchUser(userId),
    retry: (count, error) => !isApiError(error, 404) && count < 1,
  });
  if (user.isPending) {
    return (
      <Page title={t('admin.users.title')}>
        <LoadingState title={t('admin.users.loading')} />
      </Page>
    );
  }
  if (user.isError) {
    return (
      <Page title={t('admin.users.title')}>
        {isApiError(user.error, 404) ? (
          <EmptyState
            icon={IconUserOff}
            title={t('admin.users.missing.title')}
            body={t('admin.users.missing.body')}
            actions={<Link to="/admin/users">{t('admin.users.back')}</Link>}
          />
        ) : (
          <ErrorState title={t('admin.users.error')} body={t('admin.users.errorBody')} />
        )}
      </Page>
    );
  }
  return (
    <Page title={user.data.display_name} description={user.data.email}>
      <Link to="/admin/users" className={classes.back}>
        <IconChevronLeft size={16} aria-hidden /> {t('admin.users.back')}
      </Link>
      <Details user={user.data} />
      <Assignments user={user.data} />
      <Tokens user={user.data} />
    </Page>
  );
}
