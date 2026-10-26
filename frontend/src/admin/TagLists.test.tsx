import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { TagList, TagValue } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchTagLists: vi.fn(),
  createTagList: vi.fn(),
  updateTagList: vi.fn(),
  deleteTagList: vi.fn(),
  createTagValue: vi.fn(),
  updateTagValue: vi.fn(),
  deleteTagValue: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function value(overrides: Partial<TagValue> & Pick<TagValue, 'id' | 'label'>): TagValue {
  return {
    code: null,
    description: '',
    position: 0,
    is_active: true,
    usage_count: 0,
    ...overrides,
  };
}

function list(overrides: Partial<TagList> & Pick<TagList, 'id' | 'name'>): TagList {
  return {
    key: overrides.id,
    kind: 'custom',
    description: '',
    entity_types: ['module', 'learning_event', 'objective'],
    is_active: true,
    values: [],
    ...overrides,
  };
}

const methods = list({
  id: 'methods',
  name: 'Teaching methods',
  kind: 'teaching_method',
  description: 'How we teach.',
  values: [
    value({ id: 'pbl', label: 'PBL', code: 'pbl', usage_count: 3 }),
    value({ id: 'tbl', label: 'TBL', position: 1 }),
    value({ id: 'old', label: 'Old method', position: 2, is_active: false }),
  ],
});
const themes = list({
  id: 'themes',
  name: 'Themes',
  kind: 'theme',
  entity_types: ['objective', 'programme'],
});

describe('tag lists screen', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['taglists.manage'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchTagLists.mockResolvedValue([methods, themes]);
  });

  it('shows the lists with their tags, usage and state', async () => {
    renderAt('/admin/tag-lists');

    expect(await screen.findByRole('heading', { level: 1, name: 'Tag lists' })).toBeInTheDocument();
    const card = await screen.findByRole('region', { name: 'Teaching methods' });
    expect(within(card).getByRole('heading', { level: 2, name: 'Teaching methods' })).toBeInTheDocument();
    expect(within(card).getByText('How we teach.')).toBeInTheDocument();
    expect(within(card).getByText('Used on courses, sessions, objectives.')).toBeInTheDocument();
    expect(within(card).getByText('Used 3 times')).toBeInTheDocument();
    expect(within(card).getByText('Inactive')).toBeInTheDocument();
    // A tag in use cannot be deleted; nor can its list.
    expect(within(card).getByRole('button', { name: 'Delete tag PBL' })).toBeDisabled();
    expect(within(card).getByRole('button', { name: 'Delete list Teaching methods' })).toBeDisabled();
    expect(within(card).getByRole('button', { name: 'Delete tag TBL' })).toBeEnabled();
    expect(
      within(screen.getByRole('region', { name: 'Themes' })).getByRole('button', {
        name: 'Delete list Themes',
      })
    ).toBeEnabled();
  });

  it('is reached from the admin page and refused without the permission', async () => {
    renderAt('/admin');
    expect(await screen.findByRole('link', { name: 'Tag lists' })).toHaveAttribute(
      'href',
      '/admin/tag-lists'
    );
  });

  it('refuses people without the permission', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('settings', ['settings.manage'])]);
    renderAt('/admin/tag-lists');

    expect(await screen.findByRole('heading', { name: 'No access' })).toBeInTheDocument();
    expect(mocked.fetchTagLists).not.toHaveBeenCalled();
  });

  it('says what to do when there are no lists', async () => {
    mocked.fetchTagLists.mockResolvedValue([]);
    renderAt('/admin/tag-lists');

    expect(await screen.findByText('No tag lists yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New tag list' })).toBeInTheDocument();
  });

  it('offers a retry when the lists cannot be loaded', async () => {
    mocked.fetchTagLists.mockRejectedValueOnce(new ApiError(500, 'down'));
    renderAt('/admin/tag-lists');

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the tag lists");
    mocked.fetchTagLists.mockResolvedValue([methods]);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('region', { name: 'Teaching methods' })).toBeInTheDocument();
  });

  it('adds a tag list', async () => {
    mocked.createTagList.mockResolvedValue(list({ id: 'threads', name: 'Threads' }));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'New tag list' }));
    const form = await screen.findByRole('dialog', { name: 'New tag list' });
    fireEvent.click(within(form).getByRole('button', { name: 'New tag list' }));
    expect(await within(form).findAllByText('Fill in this field.')).toHaveLength(1);
    expect(mocked.createTagList).not.toHaveBeenCalled();

    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: ' Threads ' },
    });
    fireEvent.change(within(form).getByRole('textbox', { name: /Key/ }), {
      target: { value: 'Not valid' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'New tag list' }));
    expect(
      await within(form).findByText('Use lower-case letters, digits, hyphens and underscores only.')
    ).toBeInTheDocument();

    fireEvent.change(within(form).getByRole('textbox', { name: /Key/ }), {
      target: { value: 'threads' },
    });
    fireEvent.change(within(form).getByRole('combobox', { name: 'Kind' }), {
      target: { value: 'thread' },
    });
    fireEvent.click(within(form).getByRole('checkbox', { name: 'Sessions' }));
    fireEvent.click(within(form).getByRole('button', { name: 'New tag list' }));

    expect(await screen.findByText('Tag list Threads added.')).toBeInTheDocument();
    expect(mocked.createTagList).toHaveBeenCalledWith({
      key: 'threads',
      name: 'Threads',
      kind: 'thread',
      description: '',
      entity_types: ['module', 'objective'],
    });
  });

  it('says when the key is taken', async () => {
    mocked.createTagList.mockRejectedValue(new ApiError(409, 'taken'));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'New tag list' }));
    const form = await screen.findByRole('dialog', { name: 'New tag list' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: 'Themes' },
    });
    fireEvent.change(within(form).getByRole('textbox', { name: /Key/ }), {
      target: { value: 'themes' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'New tag list' }));

    expect(
      await within(form).findByText('Another tag list already uses this key.')
    ).toBeInTheDocument();
  });

  it('changes a list and keeps a programme in its item types', async () => {
    mocked.updateTagList.mockResolvedValue(themes);
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Edit list Themes' }));
    const form = await screen.findByRole('dialog', { name: 'Edit Themes' });
    expect(within(form).getByText(/Key themes, kind Themes/)).toBeInTheDocument();
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: 'Cross-cutting themes' },
    });
    fireEvent.click(within(form).getByRole('checkbox', { name: 'Courses' }));
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Changes to Themes saved.')).toBeInTheDocument();
    expect(mocked.updateTagList).toHaveBeenCalledWith('themes', {
      name: 'Cross-cutting themes',
      description: '',
      entity_types: ['objective', 'module', 'programme'],
    });
  });

  it('adds a tag with an optional code', async () => {
    mocked.createTagValue.mockResolvedValue(value({ id: 'sgl', label: 'Small group' }));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to Teaching methods' }));
    const form = await screen.findByRole('dialog', { name: 'Add a tag to Teaching methods' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Label/ }), {
      target: { value: ' Small group ' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(await screen.findByText('Tag Small group added to Teaching methods.')).toBeInTheDocument();
    expect(mocked.createTagValue).toHaveBeenCalledWith('methods', {
      label: 'Small group',
      code: null,
      description: '',
    });
  });

  it('changes a tag, clearing its code', async () => {
    mocked.updateTagValue.mockResolvedValue(value({ id: 'pbl', label: 'Problem-based learning' }));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Edit tag PBL' }));
    const form = await screen.findByRole('dialog', { name: 'Edit PBL' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Label/ }), {
      target: { value: 'Problem-based learning' },
    });
    fireEvent.change(within(form).getByRole('textbox', { name: /Code/ }), { target: { value: '' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Changes to Problem-based learning saved.')).toBeInTheDocument();
    expect(mocked.updateTagValue).toHaveBeenCalledWith('pbl', {
      label: 'Problem-based learning',
      code: null,
      description: '',
    });
  });

  it('makes a tag inactive and a list active again', async () => {
    mocked.updateTagValue.mockResolvedValue(value({ id: 'tbl', label: 'TBL' }));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Make inactive: tag TBL' }));
    expect(await screen.findByText(/TBL is inactive/)).toBeInTheDocument();
    expect(mocked.updateTagValue).toHaveBeenCalledWith('tbl', { is_active: false });

    fireEvent.click(screen.getByRole('button', { name: 'Make active: tag Old method' }));
    expect(await screen.findByText('Old method is active again.')).toBeInTheDocument();
    expect(mocked.updateTagValue).toHaveBeenCalledWith('old', { is_active: true });

    mocked.updateTagList.mockResolvedValue(themes);
    fireEvent.click(screen.getByRole('button', { name: 'Make inactive: list Themes' }));
    expect(await screen.findByText(/Themes is inactive/)).toBeInTheDocument();
    expect(mocked.updateTagList).toHaveBeenCalledWith('themes', { is_active: false });
  });

  it('shows a failed change in plain words', async () => {
    mocked.updateTagValue.mockRejectedValue(new ApiError(403, 'no'));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Make inactive: tag TBL' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('deletes a tag nothing uses after confirming', async () => {
    mocked.deleteTagValue.mockResolvedValue(undefined);
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Delete tag TBL' }));
    const form = await screen.findByRole('dialog', { name: 'Delete TBL?' });
    fireEvent.click(within(form).getByRole('button', { name: 'Delete TBL' }));

    expect(await screen.findByText('Tag TBL deleted.')).toBeInTheDocument();
    expect(mocked.deleteTagValue).toHaveBeenCalledWith('tbl');
  });

  it('deletes an unused list, and explains a refusal', async () => {
    mocked.deleteTagList.mockRejectedValueOnce(new ApiError(409, 'in use'));
    renderAt('/admin/tag-lists');

    fireEvent.click(await screen.findByRole('button', { name: 'Delete list Themes' }));
    const form = await screen.findByRole('dialog', { name: 'Delete Themes?' });
    fireEvent.click(within(form).getByRole('button', { name: 'Delete Themes' }));
    expect(await within(form).findByText(/This is in use/)).toBeInTheDocument();

    mocked.deleteTagList.mockResolvedValue(undefined);
    fireEvent.click(within(form).getByRole('button', { name: 'Delete Themes' }));
    expect(await screen.findByText('Tag list Themes deleted.')).toBeInTheDocument();
    expect(mocked.deleteTagList).toHaveBeenCalledWith('themes');
  });
});
