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

    expect(screen.getByRole('link', { name: /Review queue.*79 suggestions waiting/ })).toBeInTheDocument();
    expect(screen.getByText('79')).toBeInTheDocument();
  });

  it('says "1 suggestion waiting" for one', () => {
    renderSidebar('/dashboard', { review: 1 });

    expect(screen.getByRole('link', { name: /Review queue.*1 suggestion waiting/ })).toBeInTheDocument();
  });

  it('shows 99 as it is and 100 or more as 99+ with a matching accessible name', () => {
    const { unmount } = renderSidebar('/dashboard', { review: 99 });
    expect(screen.getByText('99')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /99 suggestions waiting/ })).toBeInTheDocument();
    unmount();

    renderSidebar('/dashboard', { review: 100 });
    expect(screen.getByText('99+')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Review queue.*more than 99 suggestions waiting/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText('100')).not.toBeInTheDocument();
  });

  it('shows no count when nothing is waiting', () => {
    renderSidebar('/dashboard', { review: 0 });

    expect(screen.getByRole('link', { name: 'Review queue' })).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
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
