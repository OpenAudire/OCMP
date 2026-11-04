/** A share (0 to 1) as a whole percentage. */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** The shade of a heatmap cell: 0 for nothing, then three steps. Every cell also prints its
 * percentage, so the shade is never the only carrier. */
export function shadeOf(value: number): 0 | 1 | 2 | 3 {
  if (value <= 0) return 0;
  if (value < 0.4) return 1;
  if (value < 0.7) return 2;
  return 3;
}

/** "4 November 2026, 11:42": when a report was made, in the reader's time. */
export function formatMade(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeStyle: 'short' }).format(date);
}
