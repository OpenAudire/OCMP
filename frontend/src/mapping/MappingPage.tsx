import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Alert, Button, NativeSelect, Paper, Stack, Text } from '@mantine/core';
import { IconRoute } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import {
  confirmMappingRecheck,
  fetchFrameworkItem,
  fetchFrameworkLibrary,
  queryKeys,
  removeMappingLink,
  fetchMappingWorkspace,
} from '../api/endpoints';
import type { MappingWorkspace, WorkspaceLink, WorkspaceObjective } from '../api/types';
import {
  defaultVersionId,
  findVersion,
  rememberedVersion,
  rememberVersion,
  useProgrammes,
} from '../curriculum/currentVersion';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { editErrorMessage } from '../curriculum/editing';
import { VersionSwitcher } from '../curriculum/VersionSwitcher';
import { FrameworkExplorer } from '../frameworks/FrameworkBrowser';
import { ItemPanel } from '../frameworks/ItemPanel';
import { NoAccessPage } from '../pages/StatusPages';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { LinkDialog } from './LinkDialog';
import { MappingHelp } from './MappingHelp';
import { ObjectiveLinks } from './ObjectiveLinks';
import { applyFilters, NO_FILTERS, type Filters } from './filters';
import { ObjectiveList } from './ObjectiveList';
import classes from './Mapping.module.css';

export const MAPPING_PATH = '/mapping';

function mappingPath(versionId: string) {
  return `${MAPPING_PATH}/${versionId}`;
}

/** What saving a link does to its status, said in words before the person saves. */
function statusNote(t: TFunction, workspace: MappingWorkspace, objective: WorkspaceObjective) {
  if (!objective.can_review) return t('mapping.status.suggested');
  return t(workspace.four_eyes ? 'mapping.status.secondReview' : 'mapping.status.accepted');
}

interface ItemTarget {
  id: string;
  code: string;
  title: string;
}

type Dialog =
  | { kind: 'link'; item: ItemTarget; link?: WorkspaceLink }
  | { kind: 'remove'; link: WorkspaceLink };

function RemoveDialog({
  link,
  objectiveText,
  onClose,
  onRemoved,
}: {
  link: WorkspaceLink;
  objectiveText: string;
  onClose: () => void;
  onRemoved: (deleted: boolean) => void;
}) {
  const { t } = useTranslation();
  const mutation = useMutation({
    mutationFn: () => removeMappingLink(link.id),
    onSuccess: (result) => onRemoved(result.deleted),
  });
  return (
    <DialogForm
      submitLabel={t('mapping.remove.submit')}
      danger
      busy={mutation.isPending}
      error={mutation.isError ? editErrorMessage(t, mutation.error) : null}
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
      onClose={onClose}
    >
      <Text>
        {t('mapping.remove.body', { item: `${link.item_code} ${link.item_title}` })}
      </Text>
      <Text size="sm" c="dimmed">
        {objectiveText}
      </Text>
    </DialogForm>
  );
}

/** The panel for a selected framework item: link it to the selected objective. */
function ItemActions({
  workspace,
  objective,
  item,
  onLink,
  onEdit,
}: {
  workspace: MappingWorkspace;
  objective: WorkspaceObjective | null;
  item: ItemTarget | null;
  onLink: (item: ItemTarget) => void;
  onEdit: (item: ItemTarget, link: WorkspaceLink) => void;
}) {
  const { t } = useTranslation();
  if (!item) return null;
  if (!objective) return <Text size="sm">{t('mapping.item.selectObjective')}</Text>;
  const existing = objective.links.find((l) => l.item_id === item.id);
  if (existing) {
    return (
      <Stack gap="xs" align="flex-start">
        <Text size="sm">{t('mapping.item.alreadyLinked')}</Text>
        {workspace.editable && objective.can_edit && (
          <Button variant="default" onClick={() => onEdit(item, existing)}>
            {t('mapping.item.editLink')}
          </Button>
        )}
      </Stack>
    );
  }
  if (!workspace.editable) return <Text size="sm">{t('mapping.item.readOnly')}</Text>;
  if (!objective.can_edit) return <Text size="sm">{t('mapping.links.cannotEdit')}</Text>;
  return (
    <Stack gap="xs" align="flex-start">
      <Button onClick={() => onLink(item)}>{t('mapping.item.link')}</Button>
      <Text size="sm" c="dimmed">
        {t('mapping.item.linkHint')}
      </Text>
    </Stack>
  );
}

function FrameworkColumn({
  children,
  frameworkId,
  onFramework,
}: {
  children: (frameworkId: string, name: string) => ReactNode;
  frameworkId: string | null;
  onFramework: (id: string) => void;
}) {
  const { t } = useTranslation();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const frameworks = library.data?.frameworks ?? [];
  const current = frameworks.find((f) => f.id === frameworkId) ?? frameworks[0];

  return (
    <Paper withBorder className={classes.pane} component="section" aria-labelledby="framework-title">
      <h2 id="framework-title" className={classes.paneHeading}>
        {t('mapping.framework.title')}
      </h2>
      {library.isPending && (
        <Text role="status" size="sm" c="dimmed">
          {t('frameworks.browser.loadingItems')}
        </Text>
      )}
      {library.isError && (
        <Alert color="red">
          <Stack gap="xs" align="flex-start">
            {t('mapping.framework.loadFailed')}
            <Button variant="default" size="sm" onClick={() => void library.refetch()}>
              {t('pages.retry')}
            </Button>
          </Stack>
        </Alert>
      )}
      {library.data && frameworks.length === 0 && (
        <Text>{t('mapping.framework.none')}</Text>
      )}
      {current && (
        <>
          <NativeSelect
            label={t('mapping.framework.choose')}
            value={current.id}
            onChange={(event) => onFramework(event.currentTarget.value)}
            data={frameworks.map((f) => ({
              value: f.id,
              label: t('mapping.framework.option', { name: f.name, version: f.version_label }),
            }))}
          />
          {children(current.id, current.name)}
        </>
      )}
    </Paper>
  );
}

function Workspace({ workspace, versionId }: { workspace: MappingWorkspace; versionId: string }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

  const selectedId = params.get('objective');
  const selected = workspace.objectives.find((o) => o.id === selectedId) ?? null;
  const shown = useMemo(
    () => applyFilters(workspace.objectives, filters),
    [workspace.objectives, filters]
  );

  const setParam = (key: string, value: string | null) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value === null) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true }
    );

  const refresh = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.mappingWorkspace(versionId) }),
      client.invalidateQueries({ queryKey: queryKeys.frameworks }),
      // A new suggestion, or a re-check that is now confirmed, changes the review queue.
      client.invalidateQueries({ queryKey: ['review-queue'] }),
    ]);

  const recheck = useMutation({
    mutationFn: (link: WorkspaceLink) => confirmMappingRecheck(link.id),
    onSuccess: async (link) => {
      setProblem(null);
      await refresh();
      setNotice(t('mapping.notice.rechecked', { item: `${link.item_code} ${link.item_title}` }));
    },
    onError: (error) => setProblem(editErrorMessage(t, error, t('mapping.errors.conflict'))),
  });

  const frameworkParam = params.get('framework');
  const closeDialog = () => setDialog(null);

  return (
    <>
      {!workspace.editable && (
        <Alert color="yellow" role="status">
          {t('mapping.readOnly', {
            status: t(`curriculum.versionStatus.${workspace.version_status}`).toLocaleLowerCase(),
          })}
        </Alert>
      )}
      {workspace.four_eyes && workspace.editable && (
        <Alert color="blue" role="status">
          {t('mapping.fourEyes')}
        </Alert>
      )}
      {notice && (
        <div ref={noticeRef} tabIndex={-1}>
          <SuccessNotice>{notice}</SuccessNotice>
        </div>
      )}
      {problem && <Alert color="red">{problem}</Alert>}
      <MappingHelpRow />
      {workspace.objectives.length === 0 ? (
        <EmptyState
          icon={IconRoute}
          title={t('mapping.empty.title', {
            objectives: t('terms.objective', { count: 2 }).toLocaleLowerCase(),
          })}
          body={t('mapping.empty.body')}
        />
      ) : (
        <div className={classes.workspace}>
          <div className={`${classes.column} ${classes.objectives}`}>
            <ObjectiveList
              all={workspace.objectives}
              shown={shown}
              filters={filters}
              onFilters={setFilters}
              selectedId={selected?.id ?? null}
              onSelect={(id) => {
                setNotice(null);
                setParam('objective', id);
              }}
            />
          </div>
          <div className={`${classes.column} ${classes.links}`}>
            <ObjectiveLinks
              objective={selected}
              editable={workspace.editable}
              onEdit={(link) =>
                setDialog({
                  kind: 'link',
                  link,
                  item: { id: link.item_id, code: link.item_code, title: link.item_title },
                })
              }
              onRemove={(link) => setDialog({ kind: 'remove', link })}
              onRecheck={(link) => {
                setNotice(null);
                recheck.mutate(link);
              }}
              onShowItem={(link) =>
                setParams(
                  (previous) => {
                    const next = new URLSearchParams(previous);
                    next.set('framework', link.framework_id);
                    next.set('item', link.item_id);
                    return next;
                  },
                  { replace: true }
                )
              }
            />
          </div>
          <div className={`${classes.column} ${classes.framework}`}>
            <FrameworkColumn
              frameworkId={frameworkParam}
              onFramework={(id) =>
                setParams(
                  (previous) => {
                    const next = new URLSearchParams(previous);
                    next.set('framework', id);
                    next.delete('item');
                    return next;
                  },
                  { replace: true }
                )
              }
            >
              {(frameworkId, name) => (
                <FrameworkExplorer
                  key={frameworkId}
                  frameworkId={frameworkId}
                  name={name}
                  stacked
                  renderItem={(itemId, onShowInTree) => (
                    <ItemPanel
                      key={itemId}
                      frameworkId={frameworkId}
                      itemId={itemId}
                      onShowInTree={onShowInTree}
                      actions={
                        <ItemFromQuery
                          frameworkId={frameworkId}
                          itemId={itemId}
                          render={(item) => (
                            <ItemActions
                              workspace={workspace}
                              objective={selected}
                              item={item}
                              onLink={(target) => setDialog({ kind: 'link', item: target })}
                              onEdit={(target, link) =>
                                setDialog({ kind: 'link', item: target, link })
                              }
                            />
                          )}
                        />
                      }
                    />
                  )}
                />
              )}
            </FrameworkColumn>
          </div>
        </div>
      )}

      {dialog?.kind === 'link' && selected && (
        <LinkDialog
          opened
          objectiveId={selected.id}
          objectiveText={selected.text}
          item={dialog.item}
          link={dialog.link}
          statusNote={statusNote(t, workspace, selected)}
          onClose={closeDialog}
          onSaved={async (link, wasNew) => {
            closeDialog();
            setProblem(null);
            await refresh();
            setNotice(
              t(wasNew ? 'mapping.notice.added' : 'mapping.notice.saved', {
                item: `${link.item_code} ${link.item_title}`,
                status: t(`frameworks.item.linkStatus.${link.status}`).toLocaleLowerCase(),
              })
            );
          }}
        />
      )}
      {dialog?.kind === 'remove' && selected && (
        <EditDialog opened title={t('mapping.remove.title')} onClose={closeDialog}>
          <RemoveDialog
            link={dialog.link}
            objectiveText={selected.text}
            onClose={closeDialog}
            onRemoved={async (deleted) => {
              const removed = dialog.link;
              closeDialog();
              setProblem(null);
              await refresh();
              setNotice(
                t(deleted ? 'mapping.notice.removed' : 'mapping.notice.rejected', {
                  item: `${removed.item_code} ${removed.item_title}`,
                })
              );
            }}
          />
        </EditDialog>
      )}
    </>
  );
}

function MappingHelpRow() {
  const { t } = useTranslation();
  return (
    <div className={classes.coverageRow}>
      <Text size="sm" c="dimmed">
        {t('mapping.helpPrompt')}
      </Text>
      <MappingHelp />
    </div>
  );
}

/** Reads the code and title of the item shown in the panel, for the dialog headings. */
function ItemFromQuery({
  frameworkId,
  itemId,
  render,
}: {
  frameworkId: string;
  itemId: string;
  render: (item: ItemTarget | null) => ReactNode;
}) {
  const item = useQuery({
    queryKey: queryKeys.frameworkItem(frameworkId, itemId),
    queryFn: () => fetchFrameworkItem(frameworkId, itemId),
  });
  return (
    <>
      {render(item.data ? { id: item.data.id, code: item.data.code, title: item.data.title } : null)}
    </>
  );
}

function VersionMapping() {
  const { t } = useTranslation();
  const { versionId } = useParams();
  const { data: programmes } = useProgrammes();
  const workspace = useQuery({
    queryKey: queryKeys.mappingWorkspace(versionId ?? ''),
    queryFn: () => fetchMappingWorkspace(versionId!),
    enabled: !!versionId,
  });

  useEffect(() => {
    if (versionId) rememberVersion(versionId);
  }, [versionId]);

  if (!versionId) return null;
  const title = t('nav.mapping');
  if (workspace.isPending) {
    return (
      <Page title={title}>
        <LoadingState skeletons={3} />
      </Page>
    );
  }
  if (workspace.isError) {
    if (isApiError(workspace.error, 404)) return <NoAccessPage />;
    return (
      <Page title={title}>
        <ErrorState
          title={t('mapping.errors.loadTitle')}
          body={t('mapping.errors.loadBody')}
          actions={<Button onClick={() => void workspace.refetch()}>{t('pages.retry')}</Button>}
        />
      </Page>
    );
  }
  const found = programmes ? findVersion(programmes, versionId) : null;
  return (
    <Page
      title={title}
      description={t('mapping.intro', {
        objectives: t('terms.objective', { count: 2 }).toLocaleLowerCase(),
      })}
    >
      <div>
        <VersionSwitcher versionId={versionId} pathFor={mappingPath} />
        {!found && (
          <Text span size="sm" c="dimmed">
            {t('curriculum.switcher.current', {
              programme: workspace.data.programme_name,
              version: t('curriculum.versionLabel', {
                year: workspace.data.academic_year,
                status: t(`curriculum.versionStatus.${workspace.data.version_status}`),
              }),
            })}
          </Text>
        )}
      </div>
      <Workspace workspace={workspace.data} versionId={versionId} />
    </Page>
  );
}

/** `/mapping`: opens the remembered or newest version the user may see. */
function MappingStart() {
  const { t } = useTranslation();
  const { data: programmes, isPending, isError, refetch } = useProgrammes();
  if (isPending) {
    return (
      <Page title={t('nav.mapping')}>
        <LoadingState skeletons={3} />
      </Page>
    );
  }
  if (isError) {
    return (
      <Page title={t('nav.mapping')}>
        <ErrorState
          title={t('mapping.errors.loadTitle')}
          body={t('mapping.errors.loadBody')}
          actions={<Button onClick={() => void refetch()}>{t('pages.retry')}</Button>}
        />
      </Page>
    );
  }
  const versionId = defaultVersionId(programmes, rememberedVersion());
  if (versionId) return <Navigate to={mappingPath(versionId)} replace />;
  return (
    <Page title={t('nav.mapping')}>
      <EmptyState
        icon={IconRoute}
        title={t('mapping.start.emptyTitle')}
        body={t('mapping.start.emptyBody')}
      />
    </Page>
  );
}

/** `/mapping`: the mapping workspace of one curriculum version. */
export function MappingSection() {
  return (
    <Routes>
      <Route index element={<MappingStart />} />
      <Route path=":versionId" element={<VersionMapping />} />
      <Route path="*" element={<Navigate to={MAPPING_PATH} replace />} />
    </Routes>
  );
}
