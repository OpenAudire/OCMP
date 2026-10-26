import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, Paper, Text } from '@mantine/core';
import { IconStack2 } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router';

import { isApiError } from '../api/client';
import { fetchVersionStructure, queryKeys } from '../api/endpoints';
import type { VersionStructure } from '../api/types';
import { useSession } from '../session/useSession';
import { Permission } from '../session/permissions';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { ComparePage } from './ComparePage';
import { QualityPage } from './QualityPage';
import {
  defaultVersionId,
  findVersion,
  rememberedVersion,
  rememberVersion,
  useProgrammes,
} from './currentVersion';
import type { EditResult } from './editing';
import { ItemActions } from './ItemActions';
import { ItemDetails } from './ItemDetails';
import { CURRICULUM_PATH, versionPath } from './paths';
import {
  canRearrange,
  canRearrangeAny,
  isMovable,
  placementOf,
  useMoveItem,
  type MovableItem,
} from './reorder';
import { StructureTree } from './StructureTree';
import { buildTree, findNode, hasNoModules, ROOT_ID } from './treeModel';
import { VersionBar } from './VersionBar';
import type { NoticeState } from './versions';
import { VersionSwitcher } from './VersionSwitcher';
import classes from './CurriculumPage.module.css';

/** `/curriculum`: opens the remembered or newest version the user may see. */
function CurriculumStart() {
  const { t } = useTranslation();
  const { data: session } = useSession();
  const { data: programmes, isPending, isError, refetch } = useProgrammes();

  if (isPending) {
    return (
      <Page title={t('curriculum.title')}>
        <LoadingState skeletons={3} />
      </Page>
    );
  }
  if (isError) {
    return (
      <Page title={t('curriculum.title')}>
        <ErrorState
          title={t('curriculum.errors.loadTitle')}
          body={t('curriculum.errors.loadBody')}
          actions={<Button onClick={() => void refetch()}>{t('pages.retry')}</Button>}
        />
      </Page>
    );
  }
  const versionId = defaultVersionId(programmes, rememberedVersion());
  if (versionId) return <Navigate to={versionPath(versionId)} replace />;

  const canSetUp = session?.permissions.has(Permission.SettingsManage) ?? false;
  return (
    <Page title={t('curriculum.title')}>
      <EmptyState
        icon={IconStack2}
        title={t('curriculum.empty.noProgrammesTitle', {
          programmes: t('terms.programme', { count: 2 }).toLocaleLowerCase(),
        })}
        body={t(canSetUp ? 'curriculum.empty.noProgrammesAdmin' : 'curriculum.empty.noProgrammes', {
          programme: t('terms.programme', { count: 1 }).toLocaleLowerCase(),
        })}
      />
    </Page>
  );
}

interface BuilderProps {
  structure: VersionStructure;
}

/** The loaded version: structure tree and the selected item's details. */
function Builder({ structure }: BuilderProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const root = useMemo(() => buildTree(structure), [structure]);
  const found = findNode(root, searchParams.get('item') ?? ROOT_ID) ?? findNode(root, ROOT_ID)!;
  const selectedId = found.node.id;
  // Open the root and its groups (so every module shows), and the way down to an item
  // named in the address.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () =>
      new Set([root.id, ...root.children.map((node) => node.id), ...found.ancestors, selectedId])
  );
  const versionId = structure.version.id;
  useEffect(() => rememberVersion(versionId), [versionId]);
  const { data: session } = useSession();
  const { data: programmes } = useProgrammes();
  const programme = programmes ? (findVersion(programmes, versionId)?.programme ?? null) : null;
  // What the last change did; announced, and focused when the selection moved. A copy
  // forward or a deleted draft brings its notice along from the previous version.
  const location = useLocation();
  const navigate = useNavigate();
  const carried = (location.state as NoticeState | null)?.notice;
  const [notice, setNotice] = useState<{ key: number; message: string; focus: boolean } | null>(
    () => (carried ? { key: Date.now(), message: carried, focus: true } : null)
  );
  useEffect(() => {
    // Shown once: not again after a reload.
    if (carried) {
      navigate({ pathname: location.pathname, search: location.search }, { replace: true });
    }
  }, [carried, navigate, location.pathname, location.search]);
  const noticeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice?.focus) noticeRef.current?.focus();
  }, [notice]);

  // Moving (Move up and down buttons, or drag and drop in the tree) keeps the selection.
  const focusAfterMove = useRef(false);
  const mover = useMoveItem(versionId, (message) => {
    setNotice({ key: Date.now(), message, focus: focusAfterMove.current });
  });
  const moveItem = (item: MovableItem, position: number, count: number, focusNotice: boolean) => {
    focusAfterMove.current = focusNotice;
    setNotice(null);
    mover.move({ item, position, count });
  };
  const placement = placementOf(root, selectedId);
  // Only items with siblings to move among.
  const canDrag = (id: string) => {
    const item = findNode(root, id)?.node.item;
    const count = placementOf(root, id)?.count ?? 0;
    return item !== undefined && count > 1 && canRearrange(item, structure);
  };
  const drop = (id: string, position: number) => {
    const item = findNode(root, id)?.node.item;
    const at = placementOf(root, id);
    if (item && isMovable(item) && at && position !== at.index) {
      moveItem(item, position, at.count, false);
    }
  };

  const select = (id: string) => {
    setNotice(null);
    mover.reset();
    setSearchParams(id === ROOT_ID ? {} : { item: id }, { replace: true });
  };
  const saved = (result: EditResult) => {
    const moves = result.select !== undefined && result.select !== selectedId;
    if (result.select !== undefined) select(result.select);
    if (result.reveal?.length) {
      setExpanded((current) => new Set([...current, ...(result.reveal ?? [])]));
    }
    setNotice({ key: Date.now(), message: result.message, focus: moves || !!result.focus });
  };
  const toggle = (id: string, open: boolean) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (open) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const terms = {
    modules: t('terms.module', { count: 2 }).toLocaleLowerCase(),
    sessions: t('terms.learning_event', { count: 2 }).toLocaleLowerCase(),
  };

  const versionBar = (
    <VersionBar
      structure={structure}
      programme={programme}
      canCheckObjectives={session?.permissions.has(Permission.ObjectivesEdit) ?? false}
      onNotice={(message) => setNotice({ key: Date.now(), message, focus: true })}
    />
  );
  const noticeBox = notice && (
    <div key={notice.key} ref={noticeRef} tabIndex={-1} className={classes.notice}>
      <SuccessNotice>{notice.message}</SuccessNotice>
    </div>
  );

  // People who may add modules get the builder, with its "Add" buttons, instead.
  if (hasNoModules(structure) && !structure.can_edit) {
    return (
      <>
        {versionBar}
        {noticeBox}
        <EmptyState
          icon={IconStack2}
          title={t('curriculum.empty.noModulesTitle', { modules: terms.modules })}
          body={t('curriculum.empty.noModules', terms)}
        />
      </>
    );
  }

  return (
    <>
      {versionBar}
      <div className={classes.layout}>
        <Paper
          withBorder
          component="section"
          aria-labelledby="structure-title"
          className={classes.tree}
        >
          <Text id="structure-title" className={classes.label}>
            {t('curriculum.tree.title')}
          </Text>
          {canRearrangeAny(structure) && (
            <Text size="sm" c="dimmed" className={classes.partial}>
              {t('curriculum.reorder.hint')}
            </Text>
          )}
          {structure.partial && (
            <Text size="sm" c="dimmed" className={classes.partial}>
              {t('curriculum.tree.partial', terms)}
            </Text>
          )}
          <StructureTree
            root={root}
            label={t('curriculum.tree.label', {
              programme: structure.programme.name,
            })}
            selectedId={selectedId}
            expanded={expanded}
            onSelect={select}
            onToggle={toggle}
            canDrag={canDrag}
            onDrop={drop}
          />
        </Paper>
        <section aria-label={t('curriculum.details.label')} className={classes.details}>
          {noticeBox}
          {mover.error && <Alert color="red">{mover.error}</Alert>}
          <ItemActions
            key={`actions-${selectedId}`}
            item={found.node.item}
            structure={structure}
            onSaved={saved}
            placement={placement}
            moving={mover.busy}
            onMove={(position, focusNotice) => {
              const item = found.node.item;
              if (isMovable(item) && placement) {
                moveItem(item, position, placement.count, focusNotice);
              }
            }}
          />
          <ItemDetails
            key={selectedId}
            item={found.node.item}
            structure={structure}
            onSaved={saved}
          />
        </section>
      </div>
    </>
  );
}

/** `/curriculum/versions/:versionId`: the read-only builder for one version. */
function VersionPage() {
  const { t } = useTranslation();
  const { versionId = '' } = useParams();
  const structure = useQuery({
    queryKey: queryKeys.versionStructure(versionId),
    queryFn: () => fetchVersionStructure(versionId),
  });
  const notFound = isApiError(structure.error, 404);
  const data = structure.data;

  let content;
  if (structure.isPending) {
    content = <LoadingState skeletons={3} />;
  } else if (notFound) {
    content = (
      <ErrorState
        title={t('curriculum.errors.notFoundTitle')}
        body={t('curriculum.errors.notFoundBody')}
        actions={
          <Button component={Link} to={CURRICULUM_PATH}>
            {t('curriculum.errors.openDefault')}
          </Button>
        }
      />
    );
  } else if (structure.isError || !data) {
    content = (
      <ErrorState
        title={t('curriculum.errors.loadTitle')}
        body={t('curriculum.errors.loadBody')}
        actions={<Button onClick={() => void structure.refetch()}>{t('pages.retry')}</Button>}
      />
    );
  } else {
    content = <Builder key={versionId} structure={data} />;
  }

  return (
    <Page title={t('curriculum.title')}>
      {/* On phones the switcher sits here; wider screens have it in the header. */}
      <Box hiddenFrom="sm">
        <VersionSwitcher versionId={versionId} />
      </Box>
      {content}
    </Page>
  );
}

/** The curriculum section: start page and the builder for one version. */
export function CurriculumSection() {
  return (
    <Routes>
      <Route index element={<CurriculumStart />} />
      <Route path="versions/:versionId" element={<VersionPage />} />
      <Route path="versions/:versionId/compare" element={<ComparePage />} />
      <Route path="versions/:versionId/quality" element={<QualityPage />} />
      <Route path="*" element={<Navigate to={CURRICULUM_PATH} replace />} />
    </Routes>
  );
}
