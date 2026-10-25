import { useEffect, useMemo, useState } from 'react';
import { Box, Button, Paper, Text } from '@mantine/core';
import { IconStack2 } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, Route, Routes, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchVersionStructure, queryKeys } from '../api/endpoints';
import type { VersionStructure } from '../api/types';
import { useSession } from '../session/useSession';
import { Permission } from '../session/permissions';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import {
  defaultVersionId,
  rememberedVersion,
  rememberVersion,
  useProgrammes,
} from './currentVersion';
import { ItemDetails } from './ItemDetails';
import { CURRICULUM_PATH, versionPath } from './paths';
import { StructureTree } from './StructureTree';
import { buildTree, findNode, hasNoModules, ROOT_ID } from './treeModel';
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

  const select = (id: string) => {
    setSearchParams(id === ROOT_ID ? {} : { item: id }, { replace: true });
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

  if (hasNoModules(structure)) {
    return (
      <EmptyState
        icon={IconStack2}
        title={t('curriculum.empty.noModulesTitle', { modules: terms.modules })}
        body={t('curriculum.empty.noModules', terms)}
      />
    );
  }

  return (
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
        />
      </Paper>
      <section aria-label={t('curriculum.details.label')} className={classes.details}>
        <ItemDetails key={selectedId} item={found.node.item} />
      </section>
    </div>
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
      <Route path="*" element={<Navigate to={CURRICULUM_PATH} replace />} />
    </Routes>
  );
}
