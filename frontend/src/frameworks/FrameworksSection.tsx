import { Route, Routes } from 'react-router';

import { FrameworkBrowser } from './FrameworkBrowser';
import { LibraryPage } from './LibraryPage';

/** `/frameworks`: the library, and `/frameworks/:frameworkId`: one framework's tree. */
export function FrameworksSection() {
  return (
    <Routes>
      <Route index element={<LibraryPage />} />
      <Route path=":frameworkId" element={<FrameworkBrowser />} />
    </Routes>
  );
}
