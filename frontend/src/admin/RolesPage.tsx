import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Paper,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { IconShieldPlus } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import {
  createRole,
  deleteRole,
  fetchPermissions,
  fetchRoles,
  queryKeys,
  updateRole,
} from '../api/endpoints';
import type { PermissionInfo, RoleInfo, RoleInput, ScopeType } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import classes from './Admin.module.css';

const SCOPE_TYPES: ScopeType[] = ['instance', 'faculty', 'programme', 'module', 'learning_event'];

function errorText(t: TFunction, error: unknown): string {
  if (isApiError(error, 409, 422, 400) && error.message) return error.message;
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

/** The permissions a role gets, with those they imply shown beside them. */
function PermissionPicker({
  permissions,
  chosen,
  onChange,
  readOnly,
}: {
  permissions: PermissionInfo[];
  chosen: string[];
  onChange: (next: string[]) => void;
  readOnly: boolean;
}) {
  const { t } = useTranslation();
  const set = new Set(chosen);
  return (
    <fieldset className={classes.fieldset}>
      <legend>{t('admin.roles.permissions')}</legend>
      <Stack gap={6}>
        {permissions.map((p) => (
          <Checkbox
            key={p.key}
            label={<code>{p.key}</code>}
            description={p.implies.length ? t('admin.roles.implies', { list: p.implies.join(', ') }) : undefined}
            checked={set.has(p.key)}
            disabled={readOnly}
            onChange={(event) =>
              onChange(
                event.currentTarget.checked ? [...chosen, p.key] : chosen.filter((k) => k !== p.key)
              )
            }
          />
        ))}
      </Stack>
    </fieldset>
  );
}

function RoleDialog({
  role,
  permissions,
  onClose,
}: {
  role: RoleInfo | null;
  permissions: PermissionInfo[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const readOnly = role?.is_system ?? false;
  const [key, setKey] = useState(role?.key ?? '');
  const [name, setName] = useState(role?.name ?? '');
  const [description, setDescription] = useState(role?.description ?? '');
  const [chosen, setChosen] = useState<string[]>(role?.permissions ?? []);
  const [scopes, setScopes] = useState<ScopeType[]>(role?.scope_types ?? ['instance']);
  const [expiry, setExpiry] = useState(role?.requires_expiry ?? false);

  const save = useMutation({
    mutationFn: () => {
      const body: Omit<RoleInput, 'key'> = {
        name: name.trim(),
        description: description.trim(),
        permissions: chosen,
        scope_types: scopes,
        requires_expiry: expiry,
      };
      return role ? updateRole(role.key, body) : createRole({ key: key.trim(), ...body });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles });
      onClose();
    },
  });
  const ready = (role !== null || key.trim().length >= 2) && name.trim() !== '' && chosen.length > 0 && scopes.length > 0;

  return (
    <EditDialog
      opened
      title={role ? (readOnly ? role.name : t('admin.roles.edit')) : t('admin.roles.create')}
      onClose={onClose}
    >
      <DialogForm
        submitLabel={role ? t('admin.settings.save') : t('admin.roles.create')}
        error={save.isError ? errorText(t, save.error) : null}
        busy={save.isPending}
        onSubmit={
          readOnly
            ? undefined
            : (event) => {
                event.preventDefault();
                if (ready) save.mutate();
              }
        }
        onClose={onClose}
      >
        <Stack gap="md">
          {readOnly && <Alert color="gray">{t('admin.roles.systemNote')}</Alert>}
          {!role && (
            <TextInput
              label={t('admin.roles.key')}
              description={t('admin.roles.keyHelp')}
              value={key}
              maxLength={64}
              required
              onChange={(event) => setKey(event.currentTarget.value)}
              data-autofocus
            />
          )}
          <TextInput
            label={t('admin.roles.name')}
            value={name}
            maxLength={255}
            required
            readOnly={readOnly}
            onChange={(event) => setName(event.currentTarget.value)}
          />
          <Textarea
            label={t('admin.roles.fieldDescription')}
            value={description}
            maxLength={2000}
            rows={3}
            readOnly={readOnly}
            onChange={(event) => setDescription(event.currentTarget.value)}
          />
          <fieldset className={classes.fieldset}>
            <legend>{t('admin.roles.heldAt')}</legend>
            <Group gap="md">
              {SCOPE_TYPES.map((s) => (
                <Checkbox
                  key={s}
                  label={t(`admin.scope.type.${s}`)}
                  checked={scopes.includes(s)}
                  disabled={readOnly}
                  onChange={(event) =>
                    setScopes(
                      event.currentTarget.checked ? [...scopes, s] : scopes.filter((x) => x !== s)
                    )
                  }
                />
              ))}
            </Group>
          </fieldset>
          <Switch
            label={t('admin.roles.requiresExpiry')}
            description={t('admin.roles.requiresExpiryHelp')}
            checked={expiry}
            disabled={readOnly}
            onChange={(event) => setExpiry(event.currentTarget.checked)}
          />
          <PermissionPicker
            permissions={permissions}
            chosen={chosen}
            onChange={setChosen}
            readOnly={readOnly}
          />
        </Stack>
      </DialogForm>
    </EditDialog>
  );
}

/** Admin > Roles: the built-in roles (read only) and the institution's own. */
export function RolesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const roles = useQuery({ queryKey: queryKeys.roles, queryFn: fetchRoles });
  const permissions = useQuery({ queryKey: queryKeys.permissions, queryFn: fetchPermissions });
  const [open, setOpen] = useState<{ role: RoleInfo | null } | null>(null);
  const [deleting, setDeleting] = useState<RoleInfo | null>(null);
  const remove = useMutation({
    mutationFn: (key: string) => deleteRole(key),
    onSuccess: async () => {
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles });
    },
  });

  return (
    <Page title={t('admin.roles.title')} description={t('admin.roles.description')}>
      <Group justify="flex-end">
        <Button leftSection={<IconShieldPlus size={18} aria-hidden />} onClick={() => setOpen({ role: null })}>
          {t('admin.roles.create')}
        </Button>
      </Group>
      {(roles.isPending || permissions.isPending) && <LoadingState title={t('admin.roles.loading')} />}
      {(roles.isError || permissions.isError) && (
        <ErrorState title={t('admin.roles.error')} body={t('admin.users.errorBody')} />
      )}
      {roles.data && permissions.data && (
        <Paper withBorder className={classes.card}>
          <Table.ScrollContainer minWidth={600}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('admin.roles.role')}</Table.Th>
                  <Table.Th>{t('admin.roles.heldAt')}</Table.Th>
                  <Table.Th>{t('admin.roles.permissions')}</Table.Th>
                  <Table.Th>
                    <span className={classes.visuallyHidden}>{t('admin.users.actions')}</span>
                  </Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {roles.data.map((role) => (
                  <Table.Tr key={role.id}>
                    <Table.Td>
                      <strong>{role.name}</strong>{' '}
                      <Badge variant="light" color={role.is_system ? 'gray' : 'teal'}>
                        {t(role.is_system ? 'admin.roles.system' : 'admin.roles.custom')}
                      </Badge>
                      <Text size="sm" c="dimmed">
                        {role.description}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {role.scope_types.map((s) => t(`admin.scope.type.${s}`)).join(', ')}
                    </Table.Td>
                    <Table.Td>{t('admin.roles.permissionCount', { count: role.permissions.length })}</Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Button
                          size="xs"
                          variant="subtle"
                          onClick={() => setOpen({ role })}
                          aria-label={t(role.is_system ? 'admin.roles.viewNamed' : 'admin.roles.editNamed', { name: role.name })}
                        >
                          {t(role.is_system ? 'admin.roles.view' : 'admin.roles.editShort')}
                        </Button>
                        {!role.is_system && (
                          <Button
                            size="xs"
                            variant="subtle"
                            color="red"
                            onClick={() => setDeleting(role)}
                            aria-label={t('admin.roles.deleteNamed', { name: role.name })}
                          >
                            {t('admin.roles.delete')}
                          </Button>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      {open && permissions.data && (
        <RoleDialog role={open.role} permissions={permissions.data} onClose={() => setOpen(null)} />
      )}
      {deleting && (
        <EditDialog opened title={t('admin.roles.delete')} onClose={() => setDeleting(null)}>
          <DialogForm
            submitLabel={t('admin.roles.delete')}
            danger
            error={remove.isError ? errorText(t, remove.error) : null}
            busy={remove.isPending}
            onSubmit={(event) => {
              event.preventDefault();
              remove.mutate(deleting.key);
            }}
            onClose={() => setDeleting(null)}
          >
            <Text>{t('admin.roles.deleteBody', { name: deleting.name })}</Text>
          </DialogForm>
        </EditDialog>
      )}
    </Page>
  );
}
