import { Route, Routes } from 'react-router';

import { NotFoundPage } from '../pages/StatusPages';
import { ExplorerHome } from './ExplorerHome';
import { ExplorerModulePage } from './ExplorerModulePage';

/** The explorer: this week's sessions, the modules of a published version, one module. */
export function ExplorerSection() {
  return (
    <Routes>
      <Route index element={<ExplorerHome />} />
      <Route path="modules/:moduleId" element={<ExplorerModulePage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
