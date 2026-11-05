import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core';
import { IconSearch, IconUserPlus } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { isApiError } from '../api/client';
import { createUser, fetchUsers, queryKeys } from '../api/endpoints';
import { EditDialog } from '../curriculum/EditDialog';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import classes from './Admin.module.css';
import { formatWhen } from './adminFormat';

const PAGE = 25;

function createUserError(t: TFunction, error: unknown): string {
  if (isApiError(error, 409)) return t('admin.users.errors.exists');
  if (isApiError(error, 422) && error.message) return error.message;
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

function AddPersonDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const add = useMutation({
    mutationFn: () => createUser({ email: email.trim(), display_name: name.trim(), password }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      onClose();
    },
  });
  const ready = email.trim() !== '' && name.trim() !== '' && password !== '';
  return (
    <EditDialog opened title={t('admin.users.add')} onClose={onClose}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) add.mutate();
        }}
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            {t('admin.users.addHelp')}
          </Text>
          {add.isError && (
            <Alert color="red" role="alert">
              {createUserError(t, add.error)}
            </Alert>
          )}
          <TextInput
            label={t('admin.users.email')}
            type="email"
            autoComplete="off"
            required
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
            data-autofocus
          />
          <TextInput
            label={t('admin.users.name')}
            autoComplete="off"
            required
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
          />
          <PasswordInput
            label={t('admin.users.password')}
            description={t('admin.users.passwordHelp')}
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={add.isPending} disabled={!ready}>
              {t('admin.users.addSubmit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </EditDialog>
  );
}

/** Admin > People: everyone with an account, with search and paging. */
export function UsersPage() {
  const { t, i18n } = useTranslation();
  const [typed, setTyped] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const users = useQuery({
    queryKey: queryKeys.adminUsers(search, offset),
    queryFn: () => fetchUsers(search, offset, PAGE),
  });
  const data = users.data;
  const last = data ? Math.min(offset + PAGE, data.total) : 0;

  return (
    <Page title={t('admin.users.title')} description={t('admin.users.description')}>
      <Group justify="space-between" align="end">
        <form
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setSearch(typed.trim());
          }}
        >
          <Group align="end" gap="xs">
            <TextInput
              label={t('admin.users.searchLabel')}
              placeholder={t('admin.users.searchPlaceholder')}
              value={typed}
              onChange={(event) => setTyped(event.currentTarget.value)}
              maxLength={200}
              w={280}
            />
            <Button type="submit" variant="default" leftSection={<IconSearch size={18} aria-hidden />}>
              {t('admin.users.search')}
            </Button>
          </Group>
        </form>
        <Button leftSection={<IconUserPlus size={18} aria-hidden />} onClick={() => setAdding(true)}>
          {t('admin.users.add')}
        </Button>
      </Group>

      {users.isPending && <LoadingState title={t('admin.users.loading')} />}
      {users.isError && (
        <ErrorState title={t('admin.users.error')} body={t('admin.users.errorBody')} />
      )}
      {data && data.items.length === 0 && (
        <EmptyState
          icon={IconSearch}
          title={t('admin.users.none.title')}
          body={t(search ? 'admin.users.none.search' : 'admin.users.none.body')}
        />
      )}
      {data && data.items.length > 0 && (
        <Paper withBorder className={classes.card}>
          <Table.ScrollContainer minWidth={560}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('admin.users.name')}</Table.Th>
                  <Table.Th>{t('admin.users.email')}</Table.Th>
                  <Table.Th>{t('admin.users.status')}</Table.Th>
                  <Table.Th>{t('admin.users.lastSignIn')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((user) => (
                  <Table.Tr key={user.id}>
                    <Table.Td>
                      <Link to={`/admin/users/${user.id}`}>{user.display_name}</Link>
                    </Table.Td>
                    <Table.Td>{user.email}</Table.Td>
                    <Table.Td>
                      <Badge variant="light" color={user.is_active ? 'teal' : 'gray'}>
                        {t(user.is_active ? 'admin.users.active' : 'admin.users.inactive')}
                      </Badge>
                      {!user.has_password && (
                        <Text span size="sm" c="dimmed" ml={8}>
                          {t('admin.users.ssoOnly')}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {user.last_login_at
                        ? formatWhen(user.last_login_at, i18n.language)
                        : t('admin.users.never')}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="space-between" mt="md">
            <Text size="sm" c="dimmed" aria-live="polite">
              {t('admin.users.range', { from: offset + 1, to: last, total: data.total })}
            </Text>
            <Group gap="xs">
              <Button
                variant="default"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                {t('admin.users.previous')}
              </Button>
              <Button
                variant="default"
                disabled={last >= data.total}
                onClick={() => setOffset(offset + PAGE)}
              >
                {t('admin.users.next')}
              </Button>
            </Group>
          </Group>
        </Paper>
      )}
      {adding && <AddPersonDialog onClose={() => setAdding(false)} />}
    </Page>
  );
}
