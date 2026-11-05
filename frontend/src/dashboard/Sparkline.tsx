import type { DashboardKpi } from '../api/types';

const WIDTH = 120;
const HEIGHT = 36;
const PAD = 3;

/** A small trend line. It is a picture of numbers that are also written out (the figure, and the
 * label says where the line starts and ends), so it never carries the meaning alone. */
export function Sparkline({ points, label }: { points: DashboardKpi['series']; label: string }) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const x = (i: number) => PAD + (i * (WIDTH - 2 * PAD)) / (points.length - 1);
  const y = (v: number) => HEIGHT - PAD - ((v - low) * (HEIGHT - 2 * PAD)) / span;
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const last = points[points.length - 1];
  return (
    <svg
      role="img"
      aria-label={label}
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      style={{ flexShrink: 0 }}
    >
      <polyline
        points={line}
        fill="none"
        stroke="var(--cic-brand)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r="3" fill="var(--cic-brand)" />
    </svg>
  );
}
