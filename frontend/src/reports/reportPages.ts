/** The reports built on the server as tables (shown by `ReportPage`) and whether they need a
 * framework. Coverage and gaps have their own pages. */
export const REPORT_PAGES: Record<string, { framework: 'required' | 'optional' | 'none' }> = {
  redundancy: { framework: 'required' },
  traceability: { framework: 'optional' },
  formats: { framework: 'none' },
  relationship: { framework: 'none' },
  'role-balance': { framework: 'required' },
  assessments: { framework: 'none' },
};

/** Every report on the reports page, in order. */
export const ALL_REPORTS = [
  'coverage',
  'gaps',
  'redundancy',
  'traceability',
  'formats',
  'relationship',
  'role-balance',
  'assessments',
];

export function reportPath(key: string): string {
  return `/reports/${key}`;
}
