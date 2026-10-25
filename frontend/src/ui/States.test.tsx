import { Button } from '@mantine/core';
import { IconStack2 } from '@tabler/icons-react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ThemeProvider } from '../theme/ThemeProvider';
import { EmptyState, ErrorState, LoadingState } from './States';

function renderInTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe('state components', () => {
  it('empty state: title, explanation and next steps', () => {
    renderInTheme(
      <EmptyState
        icon={IconStack2}
        title="No modules yet"
        body="Start by bringing in what you already have."
        actions={<Button>Import from Excel</Button>}
      />
    );

    expect(screen.getByRole('heading', { level: 2, name: 'No modules yet' })).toBeInTheDocument();
    expect(screen.getByText(/bringing in what you already have/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import from Excel' })).toBeInTheDocument();
  });

  it('loading state with progress: a labelled progress bar and a busy region', () => {
    const { container } = renderInTheme(
      <LoadingState
        title="Suggesting links for HSC201"
        progress={{ value: 41, label: '46 of 112 objectives', detail: 'about 3 minutes left' }}
        note="You can leave this page."
      />
    );

    const bar = screen.getByRole('progressbar', { name: 'Suggesting links for HSC201' });
    expect(bar).toHaveAttribute('aria-valuenow', '41');
    expect(screen.getByText('46 of 112 objectives')).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('loading state without progress announces loading', () => {
    renderInTheme(<LoadingState />);

    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
  });

  it('error state is announced and says how to carry on', () => {
    renderInTheme(
      <ErrorState
        title="Couldn't reach the AI service"
        body="Nothing else in your curriculum was changed."
        hint="Mapping by hand still works."
        actions={<Button>Try again</Button>}
      />
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent("Couldn't reach the AI service");
    expect(alert).toHaveTextContent('Mapping by hand still works.');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
