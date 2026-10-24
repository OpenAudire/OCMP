import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from './App';

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'app.title': 'Open Curriculum Mapping Platform',
        'app.description': 'Map your curriculum to competency frameworks with AI assistance',
      };
      return translations[key] || key;
    },
  }),
}));

describe('App', () => {
  it('renders the app title', () => {
    render(<App />);
    expect(screen.getByText('Open Curriculum Mapping Platform')).toBeInTheDocument();
  });
});
