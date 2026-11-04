import {
  applyMappingImport,
  applyTagImport,
  mappingImportTemplateUrl,
  previewMappingImport,
  previewTagImport,
  tagImportTemplateUrl,
} from '../api/endpoints';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { ExcelImportCard, type ExcelImportKind } from './ExcelImportCard';

const TAGS: ExcelImportKind = {
  kind: 'tags',
  sheets: ['tag_lists', 'tag_values'],
  needsVersion: false,
  templateUrl: () => tagImportTemplateUrl(),
  preview: (_version, file) => previewTagImport(file),
  apply: (_version, token) => applyTagImport(token),
};

/** Import tag lists and their tags from the Excel template (institution-wide lists). */
export function TagImportCard() {
  return <ExcelImportCard config={TAGS} />;
}

/** Import mapping links into a draft version: suggested for review, or (for people who may review
 * mappings) recorded as already decided. */
export function MappingImportCard() {
  const { data: session } = useSession();
  const canDecide = session?.permissions.has(Permission.MappingReview) ?? false;
  const config: ExcelImportKind = {
    kind: 'mappings',
    sheets: ['mappings'],
    needsVersion: true,
    templateUrl: mappingImportTemplateUrl,
    preview: previewMappingImport,
    apply: (versionId, token, decided) => applyMappingImport(versionId, token, decided),
    canDecide,
  };
  return <ExcelImportCard config={config} />;
}
