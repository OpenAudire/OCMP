import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// findBy* and waitFor wait up to 3 s (default 1 s): the first render of the whole app in a
// busy parallel run can take longer than a second on slower machines.
configure({ asyncUtilTimeout: 3000 });

// Real translations in every test, so assertions read like the UI.
import '../i18n';

// Browser APIs Mantine needs that jsdom lacks. Plain functions (not vi.fn), so
// tests that reset mocks cannot remove them.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;

window.scrollTo = () => {};

afterEach(() => {
  cleanup();
});
