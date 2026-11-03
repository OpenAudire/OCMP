import { Alert, Button, Group, Stack, Text, VisuallyHidden } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { suggestForObjective } from '../api/endpoints';
import type { AiObjectiveResult, ObjectiveDomain } from '../api/types';
import { aiPathFor, type ObjectiveOwner } from './editing';
import { wordDiff } from './wordDiff';
import classes from './AiObjectiveHelp.module.css';

interface AiObjectiveHelpProps {
  owner: ObjectiveOwner;
  versionId: string;
  /** The wording as it stands in the form. */
  text: string;
  domain: ObjectiveDomain | null;
  taxonomyLevelId: string | null;
  hasLinks: boolean | null;
  onUseText: (text: string) => void;
  onUseClassification: (values: { domain: ObjectiveDomain | null; taxonomyLevelId: string | null }) => void;
}

function Comparison({ before, after }: { before: string; after: string }) {
  const { t } = useTranslation();
  const parts = wordDiff(before, after);
  return (
    <p className={classes.diff}>
      {parts.map((part, index) => {
        const space = index > 0 ? ' ' : '';
        if (part.kind === 'removed')
          return (
            <span key={index}>
              {space}
              <del className={classes.removed}>
                <VisuallyHidden>{t('curriculum.ai.removed')} </VisuallyHidden>
                {part.text}
              </del>
            </span>
          );
        if (part.kind === 'added')
          return (
            <span key={index}>
              {space}
              <ins className={classes.added}>
                <VisuallyHidden>{t('curriculum.ai.added')} </VisuallyHidden>
                {part.text}
              </ins>
            </span>
          );
        return <span key={index}>{`${space}${part.text}`}</span>;
      })}
    </p>
  );
}

function errorText(t: ReturnType<typeof useTranslation>['t'], error: unknown): string {
  if (isApiError(error, 409)) return t('curriculum.ai.errors.refused', { reason: error.message });
  if (isApiError(error, 403)) return t('curriculum.ai.errors.forbidden');
  if (isApiError(error, 429)) return t('curriculum.ai.errors.tooMany');
  if (isApiError(error, 502)) return t('curriculum.ai.errors.failed');
  return t('curriculum.ai.errors.generic');
}

/**
 * Two optional helpers under the wording field: a measurable rewrite shown as a word-by-word
 * comparison, and a suggested domain and taxonomy level. Nothing is changed until the person
 * presses the button that uses a suggestion, and nothing is saved until they save the objective.
 */
export function AiObjectiveHelp({
  owner,
  versionId,
  text,
  domain,
  taxonomyLevelId,
  hasLinks,
  onUseText,
  onUseClassification,
}: AiObjectiveHelpProps) {
  const { t } = useTranslation();
  const path = aiPathFor(owner, versionId);
  const ask = useMutation({
    mutationFn: (task: 'rewrite' | 'classify') =>
      suggestForObjective(path, {
        task,
        text: text.trim(),
        domain,
        taxonomy_level_id: taxonomyLevelId,
        has_parent_links: hasLinks,
      }),
  });
  const empty = text.trim() === '';
  const result: AiObjectiveResult | undefined = ask.data;
  const rewrite = result?.task === 'rewrite' ? result.rewrite : null;
  const found = result?.task === 'classify' ? result.classification : null;

  return (
    <Stack gap="xs" role="group" aria-label={t('curriculum.ai.title')} className={classes.box}>
      <Text fw={600} size="sm">
        <IconSparkles size={16} aria-hidden="true" className={classes.icon} />
        {t('curriculum.ai.title')}
      </Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.ai.intro')}
      </Text>
      <Group gap="sm">
        <Button
          variant="default"
          disabled={empty || ask.isPending}
          onClick={() => ask.mutate('rewrite')}
        >
          {t('curriculum.ai.rewrite')}
        </Button>
        <Button
          variant="default"
          disabled={empty || ask.isPending}
          onClick={() => ask.mutate('classify')}
        >
          {t('curriculum.ai.classify')}
        </Button>
      </Group>
      <div role="status" aria-live="polite">
        {ask.isPending && <Text size="sm">{t('curriculum.ai.working')}</Text>}
      </div>
      {ask.isError && (
        <Alert color="red" role="alert">
          {errorText(t, ask.error)}
        </Alert>
      )}
      {rewrite && !ask.isPending && (
        <Stack gap="xs" className={classes.result}>
          <Text fw={600} size="sm">
            {t('curriculum.ai.rewriteTitle')}
          </Text>
          {rewrite.unchanged ? (
            <Text size="sm">{t('curriculum.ai.unchanged')}</Text>
          ) : (
            <>
              <Comparison before={text} after={rewrite.text} />
              <Text size="sm" c="dimmed">
                {t('curriculum.ai.diffHint')}
              </Text>
            </>
          )}
          <Text size="sm">{t('curriculum.ai.reason', { reason: rewrite.rationale })}</Text>
          <Group gap="sm">
            {!rewrite.unchanged && (
              <Button
                onClick={() => {
                  onUseText(rewrite.text);
                  ask.reset();
                }}
              >
                {t('curriculum.ai.useRewrite')}
              </Button>
            )}
            <Button variant="default" onClick={() => ask.reset()}>
              {t('curriculum.ai.dismiss')}
            </Button>
          </Group>
        </Stack>
      )}
      {found && !ask.isPending && (
        <Stack gap="xs" className={classes.result}>
          <Text fw={600} size="sm">
            {t('curriculum.ai.classifyTitle')}
          </Text>
          <Text size="sm">
            {t('curriculum.ai.domainIs', {
              domain: found.domain
                ? t(`curriculum.domain.${found.domain}`)
                : t('curriculum.ai.notSure'),
            })}
          </Text>
          <Text size="sm">
            {t('curriculum.ai.levelIs', {
              level: found.taxonomy_level_name
                ? `${found.taxonomy_level_name} (${found.scale_name})`
                : t('curriculum.ai.notSure'),
            })}
          </Text>
          <Text size="sm">
            {t('curriculum.ai.confidence', { percent: Math.round(Number(found.confidence) * 100) })}
          </Text>
          <Text size="sm">{t('curriculum.ai.reason', { reason: found.rationale })}</Text>
          <Group gap="sm">
            {(found.domain || found.taxonomy_level_id) && (
              <Button
                onClick={() => {
                  onUseClassification({
                    domain: found.domain,
                    taxonomyLevelId: found.taxonomy_level_id,
                  });
                  ask.reset();
                }}
              >
                {t('curriculum.ai.useClassification')}
              </Button>
            )}
            <Button variant="default" onClick={() => ask.reset()}>
              {t('curriculum.ai.dismiss')}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
