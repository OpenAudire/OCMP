import type { DepthMatch } from '../api/types';

/**
 * The coverage scale 0 to 5 and the depth choices (ADR 039). The wording is in the
 * translations under `mapping.coverage` and `mapping.depth`; the order here is the order shown.
 */
export const COVERAGE_LEVELS = [0, 1, 2, 3, 4, 5] as const;

export const DEPTH_CHOICES: readonly DepthMatch[] = ['below', 'matches', 'above', 'not_applicable'];
