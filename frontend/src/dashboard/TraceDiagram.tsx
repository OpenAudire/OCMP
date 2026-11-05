import { useTranslation } from 'react-i18next';

import type { DashboardTrace } from '../api/types';
import classes from './Dashboard.module.css';

// The diagram is laid out on a grid: four columns, nodes of a fixed height, columns centred. The
// connecting curves are drawn behind the nodes and are decoration only: every node is text.
const NODE = 76;
const GAP = 12;
const COLUMN = 220;
const SPACE = 60;
const WIDTH = 4 * COLUMN + 3 * SPACE;

function offset(rows: number, count: number): number {
  return ((rows - count) * (NODE + GAP)) / 2;
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

/** From one programme outcome to the framework items it reaches: the module outcomes under it, the
 * session objectives under those, and the items their accepted links reach. */
export function TraceDiagram({ trace }: { trace: DashboardTrace }) {
  const { t } = useTranslation();
  const rows = Math.max(1, trace.module_outcomes.length, trace.groups.length, trace.items.length);
  const height = rows * (NODE + GAP) - GAP;
  const col = (index: number) => index * (COLUMN + SPACE);
  const centre = (count: number, i: number) => offset(rows, count) + i * (NODE + GAP) + NODE / 2;
  const outcomeY = height / 2;
  const itemIndex = new Map(trace.items.map((item, i) => [item.id, i]));
  const mainGroups = trace.groups.filter((g) => g.module_outcome_id !== null).length;

  const paths: { d: string; key: string }[] = [];
  trace.module_outcomes.forEach((_, i) => {
    paths.push({
      key: `mo${i}`,
      d: curve(col(0) + COLUMN, outcomeY, col(1), centre(trace.module_outcomes.length, i)),
    });
    paths.push({
      key: `mg${i}`,
      d: curve(
        col(1) + COLUMN,
        centre(trace.module_outcomes.length, i),
        col(2),
        centre(trace.groups.length, i)
      ),
    });
  });
  trace.groups.forEach((group, i) => {
    if (group.module_outcome_id === null) {
      paths.push({
        key: `pg${i}`,
        d: curve(col(0) + COLUMN, outcomeY, col(2), centre(trace.groups.length, i)),
      });
    }
  });
  for (const reach of trace.reaches) {
    const to = itemIndex.get(reach.item_id);
    if (to === undefined) continue;
    paths.push({
      key: `gi${reach.group}-${to}`,
      d: curve(
        col(2) + COLUMN,
        centre(trace.groups.length, reach.group),
        col(3),
        centre(trace.items.length, to)
      ),
    });
  }

  const style = (count: number, i: number) => ({
    top: offset(rows, count) + i * (NODE + GAP),
    height: NODE,
  });
  const columnStyle = (index: number) => ({ left: `${(col(index) / WIDTH) * 100}%`, width: `${(COLUMN / WIDTH) * 100}%` });

  return (
    <div className={classes.traceScroll}>
      <div className={classes.trace} style={{ height }}>
        <svg
          className={classes.traceLines}
          viewBox={`0 0 ${WIDTH} ${height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {paths.map((p) => (
            <path key={p.key} d={p.d} className={classes.traceLine} />
          ))}
        </svg>
        <ol className={classes.traceColumn} style={columnStyle(0)} aria-label={t('dashboard.trace.outcome')}>
          <li className={classes.traceNode} style={style(1, 0)}>
            <strong>{t('dashboard.trace.outcome')}</strong>
            <span title={trace.outcome?.text}>{trace.outcome?.text}</span>
          </li>
        </ol>
        <ol className={classes.traceColumn} style={columnStyle(1)} aria-label={t('dashboard.trace.moduleOutcomes')}>
          {trace.module_outcomes.map((mo, i) => (
            <li
              key={mo.id}
              className={classes.traceNode}
              style={style(trace.module_outcomes.length, i)}
            >
              <strong>{mo.module_code ?? t('dashboard.trace.moduleOutcome')}</strong>
              <span title={mo.text}>{mo.text}</span>
            </li>
          ))}
        </ol>
        <ol className={classes.traceColumn} style={columnStyle(2)} aria-label={t('dashboard.trace.sessionObjectives')}>
          {trace.groups.map((g, i) => (
            <li key={g.module_outcome_id ?? 'direct'} className={classes.traceNode} style={style(trace.groups.length, i)}>
              <strong>{t('dashboard.trace.objectives', { count: g.objectives })}</strong>
              <span>
                {t('dashboard.trace.sessions', { count: g.sessions })}
                {g.module_outcome_id === null && mainGroups > 0
                  ? ` · ${t('dashboard.trace.direct')}`
                  : ''}
              </span>
            </li>
          ))}
        </ol>
        <ol className={classes.traceColumn} style={columnStyle(3)} aria-label={t('dashboard.trace.items')}>
          {trace.items.map((item, i) => (
            <li
              key={item.id}
              className={classes.traceNode}
              data-low={item.coverage <= 1 ? 'true' : undefined}
              style={style(trace.items.length, i)}
            >
              <strong>
                {item.code} · {t('dashboard.trace.coverageOf', { n: item.coverage })}
              </strong>
              <span title={item.title}>{item.title}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
