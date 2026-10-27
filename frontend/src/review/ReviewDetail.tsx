import type { RefObject } from 'react';
import { Alert, Button, Paper, Radio, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { DepthMatch, ReviewDecision, ReviewLink } from '../api/types';
import { MappingHelp } from '../mapping/MappingHelp';
import { COVERAGE_LEVELS, DEPTH_CHOICES } from '../mapping/scale';
import { objectiveWhere } from './format';
import { Confidence } from './ReviewCard';
import classes from './Review.module.css';

export interface Picks {
  coverage: number | null;
  depth: DepthMatch | null;
}

/** The objective's words with the evidence quote marked, when the quote is found in them. */
function ObjectiveWords({ text, quote }: { text: string; quote: string }) {
  const at = quote ? text.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + quote.length)}</mark>
      {text.slice(at + quote.length)}
    </>
  );
}

function Key({ children }: { children: string }) {
  return (
    <span className={classes.kbd} aria-hidden="true">
      {children}
    </span>
  );
}

interface ReviewDetailProps {
  link: ReviewLink;
  picks: Picks;
  onPicks: (picks: Picks) => void;
  fourEyes: boolean;
  busy: boolean;
  problem: string | null;
  coverageRef: RefObject<HTMLDivElement | null>;
  onDecide: (decision: ReviewDecision) => void;
  onSkip: () => void;
  onRecheck: () => void;
}

/** The selected suggestion: the evidence, the reasoning, the scores to correct, the decision. */
export function ReviewDetail({
  link,
  picks,
  onPicks,
  fourEyes,
  busy,
  problem,
  coverageRef,
  onDecide,
  onSkip,
  onRecheck,
}: ReviewDetailProps) {
  const { t } = useTranslation();
  const recheck = link.stage === 'recheck';
  const quoteShown = link.evidence_quote !== '' && link.objective.text.toLowerCase().includes(
    link.evidence_quote.toLowerCase()
  );

  return (
    <Paper
      withBorder
      component="section"
      className={classes.detail}
      aria-label={t('review.detail.label')}
    >
      <div className={classes.block}>
        <span className={classes.label}>{t('review.detail.objective')}</span>
        <p className={classes.objectiveFull}>
          <ObjectiveWords text={link.objective.text} quote={link.evidence_quote} />
        </p>
        <span className={classes.hint}>{objectiveWhere(t, link)}</span>
      </div>

      <div className={classes.itemBox}>
        <span className={classes.label}>{t('review.detail.item')}</span>
        <span className={classes.hint}>
          {[link.item.framework_name, link.item.group].filter(Boolean).join(' › ')}
        </span>
        <Text fw={600} size="md">
          <span className={classes.code}>{link.item.code}</span> {link.item.title}
        </Text>
      </div>

      <div className={classes.block}>
        <span className={classes.label}>{t(`review.detail.why.${link.source}`)}</span>
        <p className={classes.why}>{link.rationale || t('review.detail.noReason')}</p>
        <div className={classes.hint}>
          <Confidence value={link.confidence} />
          {quoteShown && <div>{t('review.detail.evidence')}</div>}
          {link.evidence_quote !== '' && !quoteShown && (
            <div>{t('review.detail.evidenceQuote', { quote: link.evidence_quote })}</div>
          )}
        </div>
      </div>

      {link.stage === 'second' && link.first_decision && (
        <div className={classes.notice} role="note">
          {t(`review.detail.firstDecision.${link.first_decision}`)}
        </div>
      )}
      {link.needs_recheck && (
        <div className={classes.notice} role="note">
          <IconAlertTriangle size={16} aria-hidden="true" /> {t('review.detail.recheck')}
        </div>
      )}
      {link.needs_discussion && (
        <div className={classes.notice} role="note">
          <IconAlertTriangle size={16} aria-hidden="true" /> {t('review.detail.discussion')}
        </div>
      )}

      {!recheck && (
        <>
          <div ref={coverageRef}>
            <Radio.Group
              label={t('review.detail.coverageLegend')}
              description={t('review.detail.coverageHint')}
              value={picks.coverage === null ? '' : String(picks.coverage)}
              onChange={(value) => onPicks({ ...picks, coverage: Number(value) })}
            >
              <div className={classes.choices}>
                {COVERAGE_LEVELS.map((level) => (
                  <div
                    key={level}
                    className={classes.choice}
                    data-checked={picks.coverage === level}
                  >
                    <Radio
                      value={String(level)}
                      label={t('mapping.coverage.choice', {
                        value: level,
                        label: t(`mapping.coverage.levels.${level}`),
                      })}
                    />
                  </div>
                ))}
              </div>
            </Radio.Group>
          </div>
          <Radio.Group
            label={t('review.detail.depthLegend')}
            value={picks.depth ?? ''}
            onChange={(value) => onPicks({ ...picks, depth: value as DepthMatch })}
          >
            <div className={classes.choices}>
              {DEPTH_CHOICES.map((choice) => (
                <div key={choice} className={classes.choice} data-checked={picks.depth === choice}>
                  <Radio value={choice} label={t(`mapping.depth.names.${choice}`)} />
                </div>
              ))}
            </div>
            {picks.depth && (
              <Text size="sm" c="dimmed" mt={8}>
                {t(`mapping.depth.definitions.${picks.depth}`)}
              </Text>
            )}
          </Radio.Group>
          <MappingHelp />
        </>
      )}

      {problem && <Alert color="red">{problem}</Alert>}

      {recheck ? (
        <div className={classes.actions}>
          <Button onClick={onRecheck} loading={busy} aria-keyshortcuts="A">
            {t('review.actions.stillFits')} <Key>A</Key>
          </Button>
          <Button
            component={Link}
            variant="default"
            to={`/mapping/${link.version_id}?objective=${link.objective.id}&framework=${link.item.framework_id}&item=${link.item.id}`}
          >
            {t('review.actions.openWorkspace')}
          </Button>
          <Button variant="subtle" onClick={onSkip} aria-keyshortcuts="S">
            {t('review.actions.skip')} <Key>S</Key>
          </Button>
        </div>
      ) : (
        <>
          <div className={classes.actions}>
            <Button onClick={() => onDecide('accept')} loading={busy} aria-keyshortcuts="A">
              {t('review.actions.accept')} <Key>A</Key>
            </Button>
            {link.stage === 'first' && (
              <Button
                variant="default"
                onClick={() => onDecide('second_review')}
                disabled={busy}
                aria-keyshortcuts="2"
              >
                {t('review.actions.second')} <Key>2</Key>
              </Button>
            )}
            <Button
              variant="subtle"
              color="red"
              onClick={() => onDecide('reject')}
              disabled={busy}
              aria-keyshortcuts="R"
            >
              {t('review.actions.reject')} <Key>R</Key>
            </Button>
            <Button variant="subtle" onClick={onSkip} aria-keyshortcuts="S">
              {t('review.actions.skip')} <Key>S</Key>
            </Button>
          </div>
          <Text size="sm" c="dimmed">
            {link.stage === 'second'
              ? t('review.detail.secondNote')
              : fourEyes
                ? t('review.detail.fourEyesNote')
                : t('review.detail.acceptNote')}
          </Text>
        </>
      )}
    </Paper>
  );
}
