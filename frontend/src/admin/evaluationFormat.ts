/** A share as a percentage, or a dash where it cannot be worked out. */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${(value * 100).toFixed(1)}%`;
}

/** A figure with two decimals (F1, kappa), or a dash. */
export function decimal(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : value.toFixed(2);
}
