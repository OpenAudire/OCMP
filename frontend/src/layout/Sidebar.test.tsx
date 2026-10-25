import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { collectPermissions, Permission } from '../session/permissions';
import { ThemeProvider } from '../theme/ThemeProvider';
import { initials } from './initials';
import { visibleNavItems } from './navigation';
import { Sidebar } from './Sidebar';

function renderSidebar(pathname: string, counts?: Partial<Record<string, number>>) {
  const items = visibleNavItems(
    collectPermissions([Permission.CurriculumView, Permission.MappingReview])
  );
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <Sidebar items={items} pathname={pathname} counts={counts} institutionName="Demo University" />
      </MemoryRouter>
    </ThemeProvider>
  );
}

describe('sidebar', () => {
  it('names the product and the institution', () => {
    renderSidebar('/dashboard');

    expect(screen.getByRole('img', { name: 'Curriculum in Context' })).toBeInTheDocument();
    expect(screen.getByText('Demo University')).toBeInTheDocument();
  });

  it('marks only the most specific item as the current page', () => {
    renderSidebar('/mapping/review');

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const current = within(nav)
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page');
    expect(current.map((link) => link.textContent)).toEqual(['Review queue']);
  });

  it('shows a waiting count with a text label, not a bare number', () => {
    renderSidebar('/dashboard', { review: 79 });

    expect(screen.getByRole('link', { name: /Review queue.*79 waiting/ })).toBeInTheDocument();
  });

  it('shows no count when nothing is waiting', () => {
    renderSidebar('/dashboard', { review: 0 });

    expect(screen.getByRole('link', { name: 'Review queue' })).toBeInTheDocument();
  });
});

describe('initials', () => {
  it('takes the first and last names', () => {
    expect(initials('Thandi Nkosi')).toBe('TN');
    expect(initials('  Anna  van der Merwe ')).toBe('AM');
    expect(initials('Sipho')).toBe('S');
    expect(initials('')).toBe('');
  });
});
