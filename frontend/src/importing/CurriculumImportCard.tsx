import {
  applyCurriculumImport,
  curriculumImportTemplateUrl,
  previewCurriculumImport,
} from '../api/endpoints';
import { ExcelImportCard, type ExcelImportKind } from './ExcelImportCard';

const CURRICULUM: ExcelImportKind = {
  kind: 'curriculum',
  sheets: ['phases', 'modules', 'sessions', 'objectives'],
  needsVersion: true,
  templateUrl: curriculumImportTemplateUrl,
  preview: previewCurriculumImport,
  apply: (versionId, token) => applyCurriculumImport(versionId, token),
};

/** Import the structure and objectives of a draft curriculum version from the Excel template. */
export function CurriculumImportCard() {
  return <ExcelImportCard config={CURRICULUM} />;
}
