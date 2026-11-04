import { useState } from 'react';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  FileInput,
  Group,
  NativeSelect,
  Paper,
  Progress,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconDownload, IconPlayerPlay, IconUpload } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import {
  cancelEvaluation,
  deleteGoldSet,
  fetchEvaluation,
  fetchEvaluations,
  fetchFrameworkLibrary,
  fetchGoldSets,
  fetchProgrammes,
  GOLD_TEMPLATE_URL,
  goldExportUrl,
  queryKeys,
  startEvaluation,
  uploadGoldSet,
} from '../api/endpoints';
import type { EvalRun, EvalScores, GoldPreview } from '../api/types';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import classes from './AiEvaluationPage.module.css';
import { decimal, percent } from './evaluationFormat';

const POLL_MS = 3000;
const ACTIVE = new Set(['queued', 'running']);
const MIN_COVERAGES = [1, 2, 3, 4, 5];

function errorText(t: ReturnType<typeof useTranslation>['t'], error: unknown): string {
  if (isApiError(error, 409, 422) && error.message && !error.message.startsWith('Request failed'))
    return t('admin.evaluation.errors.reason', { reason: error.message });
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

function Figures({ scores }: { scores: EvalScores | null }) {
  const { t } = useTranslation();
  if (!scores) return <Table.Td colSpan={6}>{t('admin.evaluation.results.notReady')}</Table.Td>;
  return (
    <>
      <Table.Td>{percent(scores.precision)}</Table.Td>
      <Table.Td>{percent(scores.recall)}</Table.Td>
      <Table.Td>{decimal(scores.f1)}</Table.Td>
      <Table.Td>{decimal(scores.kappa)}</Table.Td>
      <Table.Td>
        {decimal(scores.coverage_kappa)}
        {scores.coverage_kappa !== null && (
          <Text size="xs" c="dimmed">
            {t('admin.evaluation.detail.scoreKappaN', { n: scores.coverage_pairs })}
          </Text>
        )}
        {scores.coverage_kappa_weighted !== null && (
          <Text size="xs" c="dimmed">
            {t('admin.evaluation.detail.weightedKappa', {
              value: decimal(scores.coverage_kappa_weighted),
            })}
          </Text>
        )}
      </Table.Td>
      <Table.Td>{percent(scores.shortlist_recall)}</Table.Td>
    </>
  );
}

// --- Gold sets ---------------------------------------------------------------------------------

function GoldSetsCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const sets = useQuery({ queryKey: queryKeys.goldSets, queryFn: fetchGoldSets });
  const frameworks = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const [name, setName] = useState('');
  const [frameworkId, setFrameworkId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [checked, setChecked] = useState<GoldPreview | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const options = (frameworks.data?.frameworks ?? []).filter((f) => f.status !== 'draft');
  const chosen = frameworkId || options[0]?.id || '';

  const upload = useMutation({
    mutationFn: (dryRun: boolean) =>
      uploadGoldSet({ name, frameworkId: chosen, description: '', file: file as File, dryRun }),
    onSuccess: (result, dryRun) => {
      setChecked(result);
      if (!dryRun && result.saved) {
        setSaved(result.saved.name);
        setChecked(null);
        setFile(null);
        setName('');
        void queryClient.invalidateQueries({ queryKey: queryKeys.goldSets });
      }
    },
  });
  const remove = useMutation({
    mutationFn: deleteGoldSet,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.goldSets }),
  });
  const ready = name.trim() !== '' && file !== null && chosen !== '';

  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="gold-title">
      <Title order={2} id="gold-title" className={classes.sectionTitle}>
        {t('admin.evaluation.gold.title')}
      </Title>
      <Text c="dimmed">{t('admin.evaluation.gold.intro')}</Text>

      {sets.isLoading && <LoadingState />}
      {sets.isError && (
        <ErrorState
          title={t('admin.evaluation.loadErrorTitle')}
          body={t('admin.evaluation.loadErrorBody')}
        />
      )}
      {sets.data && sets.data.length === 0 && (
        <Text>{t('admin.evaluation.gold.none')}</Text>
      )}
      {sets.data && sets.data.length > 0 && (
        <Table.ScrollContainer minWidth={640}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('admin.evaluation.gold.name')}</Table.Th>
                <Table.Th>{t('admin.evaluation.gold.framework')}</Table.Th>
                <Table.Th>{t('admin.evaluation.gold.objectives')}</Table.Th>
                <Table.Th>{t('admin.evaluation.gold.mappings')}</Table.Th>
                <Table.Th>{t('admin.evaluation.gold.actions')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sets.data.map((set) => (
                <Table.Tr key={set.id}>
                  <Table.Td>
                    {set.name}{' '}
                    {set.is_demo && (
                      <Badge variant="light" color="ochre">
                        {t('admin.evaluation.gold.demo')}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{set.framework_name}</Table.Td>
                  <Table.Td>
                    {t('admin.evaluation.gold.objectiveCount', {
                      count: set.objectives,
                      none: set.without_mapping,
                    })}
                  </Table.Td>
                  <Table.Td>{set.mappings}</Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <Anchor href={goldExportUrl(set.id)} download>
                        {t('admin.evaluation.gold.export')}
                      </Anchor>
                      <Button
                        size="compact-md"
                        variant="subtle"
                        color="red"
                        loading={remove.isPending && remove.variables === set.id}
                        onClick={() => remove.mutate(set.id)}
                        aria-label={t('admin.evaluation.gold.deleteNamed', { name: set.name })}
                      >
                        {t('admin.evaluation.gold.delete')}
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {remove.isError && <Alert color="red">{errorText(t, remove.error)}</Alert>}
      {saved && (
        <SuccessNotice>{t('admin.evaluation.gold.saved', { name: saved })}</SuccessNotice>
      )}

      <Title order={3}>{t('admin.evaluation.gold.addTitle')}</Title>
      <Text size="sm" c="dimmed">
        {t('admin.evaluation.gold.addHelp')}
      </Text>
      <Anchor
        href={`${GOLD_TEMPLATE_URL}${chosen ? `?framework_id=${chosen}` : ''}`}
        download
        className={classes.download}
      >
        <IconDownload size={18} aria-hidden /> {t('admin.evaluation.gold.template')}
      </Anchor>
      <form
        className={classes.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) upload.mutate(true);
        }}
      >
        <TextInput
          label={t('admin.evaluation.gold.nameLabel')}
          value={name}
          onChange={(event) => setName(event.currentTarget.value)}
          maxLength={200}
          required
        />
        <NativeSelect
          label={t('admin.evaluation.gold.frameworkLabel')}
          value={chosen}
          onChange={(event) => {
            setFrameworkId(event.currentTarget.value);
            setChecked(null);
          }}
          data={options.map((f) => ({ value: f.id, label: `${f.name} (${f.version_label})` }))}
        />
        <FileInput
          label={t('admin.evaluation.gold.fileLabel')}
          accept=".xlsx"
          value={file}
          onChange={(value) => {
            setFile(value);
            setChecked(null);
          }}
          clearable
          clearButtonProps={{ 'aria-label': t('admin.evaluation.gold.clearFile') }}
          leftSection={<IconUpload size={18} aria-hidden />}
        />
        <Group>
          <Button type="submit" variant="default" disabled={!ready} loading={upload.isPending}>
            {t('admin.evaluation.gold.check')}
          </Button>
        </Group>
      </form>
      {upload.isError && <Alert color="red">{errorText(t, upload.error)}</Alert>}
      {checked && (
        <Stack gap="xs" role="status">
          <Text fw={600}>
            {t('admin.evaluation.gold.summary', {
              objectives: checked.objectives,
              mappings: checked.mappings,
              none: checked.without_mapping,
            })}
          </Text>
          {checked.problems.length > 0 ? (
            <Alert color="ochre" title={t('admin.evaluation.gold.problemsTitle')}>
              <ul className={classes.problems}>
                {checked.problems.map((problem, index) => (
                  <li key={index}>
                    {problem.row
                      ? t('admin.evaluation.gold.problemRow', {
                          row: problem.row,
                          message: problem.message,
                        })
                      : problem.message}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : (
            <Group>
              <Button loading={upload.isPending} onClick={() => upload.mutate(false)}>
                {t('admin.evaluation.gold.save')}
              </Button>
            </Group>
          )}
        </Stack>
      )}
    </Paper>
  );
}

// --- Running an evaluation ---------------------------------------------------------------------

function StartCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const sets = useQuery({ queryKey: queryKeys.goldSets, queryFn: fetchGoldSets });
  const programmes = useQuery({ queryKey: queryKeys.programmes, queryFn: fetchProgrammes });
  const [goldSetId, setGoldSetId] = useState('');
  const [versionId, setVersionId] = useState('');
  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({
      value: v.id,
      label: t('admin.evaluation.run.versionLabel', {
        programme: p.code,
        year: v.academic_year,
        status: t(`curriculum.versionStatus.${v.status}`),
      }),
    }))
  );
  const goldChoice = goldSetId || sets.data?.[0]?.id || '';
  const versionChoice = versionId || versions[0]?.value || '';
  const start = useMutation({
    mutationFn: () => startEvaluation({ goldSetId: goldChoice, versionId: versionChoice }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-evaluation', 'runs'] }),
  });
  const ready = goldChoice !== '' && versionChoice !== '';
  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="run-title">
      <Title order={2} id="run-title" className={classes.sectionTitle}>
        {t('admin.evaluation.run.title')}
      </Title>
      <Text c="dimmed">{t('admin.evaluation.run.intro')}</Text>
      <form
        className={classes.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) start.mutate();
        }}
      >
        <NativeSelect
          label={t('admin.evaluation.run.goldSet')}
          value={goldChoice}
          onChange={(event) => setGoldSetId(event.currentTarget.value)}
          data={(sets.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
        />
        <NativeSelect
          label={t('admin.evaluation.run.version')}
          description={t('admin.evaluation.run.versionHelp')}
          value={versionChoice}
          onChange={(event) => setVersionId(event.currentTarget.value)}
          data={versions}
        />
        <Group>
          <Button
            type="submit"
            leftSection={<IconPlayerPlay size={18} aria-hidden />}
            disabled={!ready}
            loading={start.isPending}
          >
            {t('admin.evaluation.run.start')}
          </Button>
        </Group>
      </form>
      {start.isError && <Alert color="red">{errorText(t, start.error)}</Alert>}
      {start.isSuccess && <SuccessNotice>{t('admin.evaluation.run.started')}</SuccessNotice>}
    </Paper>
  );
}

// --- Results -----------------------------------------------------------------------------------

function RunDetail({ run, minCoverage }: { run: EvalRun; minCoverage: number }) {
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: queryKeys.evalRun(run.id, minCoverage),
    queryFn: () => fetchEvaluation(run.id, minCoverage),
  });
  if (detail.isLoading) return <LoadingState />;
  if (detail.isError || !detail.data)
    return (
      <ErrorState
        title={t('admin.evaluation.loadErrorTitle')}
        body={t('admin.evaluation.loadErrorBody')}
      />
    );
  const d = detail.data;
  return (
    <Stack gap="md" aria-live="polite">
      <Title order={3}>
        {t('admin.evaluation.detail.title', { prompt: d.prompt_version, model: d.model })}
      </Title>
      <Text size="sm" c="dimmed">
        {t('admin.evaluation.detail.counts', {
          objectives: d.scores?.objectives ?? 0,
          failed: d.scores?.failed ?? 0,
          missing: d.not_found,
          shown: decimal(d.scores?.average_shortlist),
        })}
      </Text>

      <Title order={4}>{t('admin.evaluation.detail.coverageTitle')}</Title>
      <Text size="sm" c="dimmed">
        {t('admin.evaluation.detail.coverageHelp')}
      </Text>
      <Table.ScrollContainer minWidth={560}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('admin.evaluation.detail.minCoverage')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.suggestions')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.precision')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.recall')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.f1')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.kappa')}</Table.Th>
              <Table.Th title={t('admin.evaluation.results.scoreKappaTitle')}>
                {t('admin.evaluation.results.scoreKappa')}
              </Table.Th>
              <Table.Th title={t('admin.evaluation.results.weightedKappaTitle')}>
                {t('admin.evaluation.results.weightedKappa')}
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {d.by_min_coverage.map((row) => (
              <Table.Tr key={row.min_coverage} data-current={row.min_coverage === minCoverage}>
                <Table.Td>{t('admin.evaluation.detail.orMore', { n: row.min_coverage })}</Table.Td>
                <Table.Td>{row.suggestions}</Table.Td>
                <Table.Td>{percent(row.precision)}</Table.Td>
                <Table.Td>{percent(row.recall)}</Table.Td>
                <Table.Td>{decimal(row.f1)}</Table.Td>
                <Table.Td>{decimal(row.kappa)}</Table.Td>
                <Table.Td>
                  {decimal(row.coverage_kappa)}
                  {row.coverage_kappa !== null && ` (${t('admin.evaluation.detail.scoreKappaN', { n: row.coverage_pairs })})`}
                </Table.Td>
                <Table.Td>{decimal(row.coverage_kappa_weighted)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      <Text size="sm" c="dimmed">
        {t('admin.evaluation.detail.scoreKappaHelp')}
      </Text>

      <Title order={4}>{t('admin.evaluation.detail.bulkTitle', { n: minCoverage })}</Title>
      <Text size="sm" c="dimmed">
        {t('admin.evaluation.detail.bulkHelp')}
      </Text>
      <Table.ScrollContainer minWidth={560}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('admin.evaluation.detail.floor')}</Table.Th>
              <Table.Th>{t('admin.evaluation.detail.accepted')}</Table.Th>
              <Table.Th>{t('admin.evaluation.detail.wrong')}</Table.Th>
              <Table.Th>{t('admin.evaluation.results.precision')}</Table.Th>
              <Table.Th>{t('admin.evaluation.detail.left')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {d.bulk_accept.map((row) => (
              <Table.Tr key={row.floor}>
                <Table.Td>{row.floor}%</Table.Td>
                <Table.Td>{row.accepted}</Table.Td>
                <Table.Td>{row.wrong}</Table.Td>
                <Table.Td>{percent(row.precision)}</Table.Td>
                <Table.Td>{row.left_for_review}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      <Title order={4}>{t('admin.evaluation.detail.disagreeTitle')}</Title>
      {d.disagreements.length === 0 ? (
        <Text>{t('admin.evaluation.detail.noDisagreements')}</Text>
      ) : (
        <ul className={classes.problems}>
          {d.disagreements.map((item) => (
            <li key={item.case_id}>
              <Text fw={600}>{item.objective}</Text>
              <Text size="sm">
                {t('admin.evaluation.detail.onlyAi')}: {item.only_ai.join(', ') || '–'}
                {' · '}
                {t('admin.evaluation.detail.onlyGold')}: {item.only_gold.join(', ') || '–'}
                {item.not_shown.length > 0 &&
                  ` (${t('admin.evaluation.detail.notShown', { codes: item.not_shown.join(', ') })})`}
              </Text>
            </li>
          ))}
        </ul>
      )}
    </Stack>
  );
}

function ResultsCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [minCoverage, setMinCoverage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const runs = useQuery({
    queryKey: queryKeys.evalRuns(minCoverage),
    queryFn: () => fetchEvaluations(minCoverage),
    refetchInterval: (query) =>
      query.state.data?.some((r) => ACTIVE.has(r.status)) ? POLL_MS : false,
  });
  const cancel = useMutation({
    mutationFn: cancelEvaluation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-evaluation', 'runs'] }),
  });
  const chosen = runs.data?.find((r) => r.id === selected);
  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="results-title">
      <Title order={2} id="results-title" className={classes.sectionTitle}>
        {t('admin.evaluation.results.title')}
      </Title>
      <Text c="dimmed">{t('admin.evaluation.results.intro')}</Text>
      <NativeSelect
        label={t('admin.evaluation.results.minCoverage')}
        description={t('admin.evaluation.results.minCoverageHelp')}
        value={String(minCoverage)}
        onChange={(event) => setMinCoverage(Number(event.currentTarget.value))}
        data={MIN_COVERAGES.map((n) => ({
          value: String(n),
          label: t('admin.evaluation.detail.orMore', { n }),
        }))}
        className={classes.narrow}
      />
      {runs.isLoading && <LoadingState />}
      {runs.isError && (
        <ErrorState
          title={t('admin.evaluation.loadErrorTitle')}
          body={t('admin.evaluation.loadErrorBody')}
        />
      )}
      {runs.data && runs.data.length === 0 && <Text>{t('admin.evaluation.results.none')}</Text>}
      {runs.data && runs.data.length > 0 && (
        <Table.ScrollContainer minWidth={820}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('admin.evaluation.results.run')}</Table.Th>
                <Table.Th>{t('admin.evaluation.results.precision')}</Table.Th>
                <Table.Th>{t('admin.evaluation.results.recall')}</Table.Th>
                <Table.Th>{t('admin.evaluation.results.f1')}</Table.Th>
                <Table.Th>{t('admin.evaluation.results.kappa')}</Table.Th>
                <Table.Th title={t('admin.evaluation.results.scoreKappaTitle')}>
                  {t('admin.evaluation.results.scoreKappa')}
                </Table.Th>
                <Table.Th>{t('admin.evaluation.results.shown')}</Table.Th>
                <Table.Th>{t('admin.evaluation.results.cost')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {runs.data.map((run) => (
                <Table.Tr key={run.id} data-selected={run.id === selected}>
                  <Table.Td>
                    <Button
                      variant="subtle"
                      size="compact-md"
                      onClick={() => setSelected(run.id === selected ? null : run.id)}
                      aria-expanded={run.id === selected}
                    >
                      {t('admin.evaluation.results.runLabel', {
                        prompt: run.prompt_version,
                        model: run.model,
                        set: run.gold_set_name,
                      })}
                    </Button>
                    {ACTIVE.has(run.status) ? (
                      <Group gap="xs" wrap="nowrap">
                        <Progress
                          className={classes.progress}
                          value={run.total_items ? (run.done_items / run.total_items) * 100 : 0}
                          aria-label={t('admin.evaluation.results.progress', {
                            done: run.done_items,
                            total: run.total_items,
                          })}
                        />
                        <Button
                          size="compact-sm"
                          variant="default"
                          onClick={() => cancel.mutate(run.id)}
                        >
                          {t('admin.evaluation.results.cancel')}
                        </Button>
                      </Group>
                    ) : (
                      run.status !== 'succeeded' && (
                        <Text size="sm" c="dimmed">
                          {t(`admin.evaluation.status.${run.status}`)}
                          {run.error_message ? `: ${run.error_message}` : ''}
                        </Text>
                      )
                    )}
                  </Table.Td>
                  <Figures scores={run.scores} />
                  <Table.Td>${run.estimated_cost}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {chosen && chosen.scores && <RunDetail run={chosen} minCoverage={minCoverage} />}
    </Paper>
  );
}

/** `/admin/ai-evaluation`: gold sets, running the AI on one, and the figures that come out. */
export function AiEvaluationPage() {
  const { t } = useTranslation();
  return (
    <Page title={t('admin.evaluation.title')} description={t('admin.evaluation.description')}>
      <Stack gap="lg">
        <Alert color="ochre" title={t('admin.evaluation.honestTitle')}>
          {t('admin.evaluation.honest')}
        </Alert>
        <GoldSetsCard />
        <StartCard />
        <ResultsCard />
      </Stack>
    </Page>
  );
}
