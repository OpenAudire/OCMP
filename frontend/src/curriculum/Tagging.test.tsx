import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type {
  InheritancePreview,
  ItemTag,
  LearningEventDetail,
  ModuleDetail,
  TagList,
} from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { programmes, structure } from './testData';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchProgramme: vi.fn(),
  fetchVersionStructure: vi.fn(),
  fetchProgrammeOutcomes: vi.fn(),
  fetchModule: vi.fn(),
  fetchLearningEvent: vi.fn(),
  fetchTaxonomyScales: vi.fn(),
  fetchTagLists: vi.fn(),
  fetchTagPreview: vi.fn(),
  fetchPassOnPreview: vi.fn(),
  passTagOn: vi.fn(),
  addTag: vi.fn(),
  removeTagging: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const direct: ItemTag = {
  tag_value_id: 'pbl',
  label: 'PBL',
  list_id: 'methods',
  list_name: 'Teaching methods',
  direct_tagging_id: 't1',
  sources: [],
};

const inherited: ItemTag = {
  tag_value_id: 'ethics',
  label: 'Ethics',
  list_id: 'themes',
  list_name: 'Themes',
  direct_tagging_id: null,
  sources: [{ item_type: 'module', item_id: 'm2', name: 'HSC201 Cardiovascular system' }],
};

const lists: TagList[] = [
  {
    id: 'methods',
    key: 'methods',
    name: 'Teaching methods',
    kind: 'teaching_method',
    description: '',
    entity_types: ['module', 'learning_event', 'objective'],
    is_active: true,
    faculty_id: null,
    faculty_name: null,
    can_manage: false,
    values: [
      { id: 'pbl', label: 'PBL', code: null, description: '', position: 0, is_active: true, usage_count: 0 },
      { id: 'tbl', label: 'TBL', code: null, description: '', position: 1, is_active: true, usage_count: 0 },
      { id: 'old', label: 'Retired method', code: null, description: '', position: 2, is_active: false, usage_count: 0 },
    ],
  },
  {
    id: 'themes',
    key: 'themes',
    name: 'Themes',
    kind: 'theme',
    description: '',
    entity_types: ['objective'],
    is_active: true,
    faculty_id: null,
    faculty_name: null,
    can_manage: false,
    values: [
      { id: 'ethics', label: 'Ethics', code: null, description: '', position: 0, is_active: true, usage_count: 0 },
    ],
  },
];

const moduleDetail = (tags: ItemTag[], canTag: boolean): ModuleDetail => ({
  id: 'm2',
  version_id: 'v2027',
  phase_id: 'y2',
  code: 'HSC201',
  name: 'Cardiovascular system',
  credits: '16.0',
  nqf_level: 6,
  description: '',
  external_lms_ref: null,
  event_count: 2,
  contact_minutes: 210,
  self_study_minutes: 210,
  outcomes: [
    {
      id: 'o-m2',
      text: 'Interpret cardiac tests.',
      domain: null,
      taxonomy_level_id: null,
      status: 'draft',
      position: 0,
      parent_ids: [],
      tags: [inherited],
    },
  ],
  can_edit_objectives: false,
  can_approve_objectives: false,
  tags,
  can_edit_tags: canTag,
});

const eventDetail = (tags: ItemTag[], canTag: boolean): LearningEventDetail => ({
  id: 'e1',
  module_id: 'm2',
  title: 'Cardiac cycle',
  format: 'Lecture',
  format_value_id: 'f-lecture',
  contact_minutes: 90,
  self_study_minutes: 120,
  week: 4,
  position: 0,
  description: '',
  external_lms_ref: null,
  objectives: [
    {
      id: 'o-e1',
      text: 'Describe the cardiac cycle.',
      domain: null,
      taxonomy_level_id: null,
      status: 'draft',
      position: 0,
      parent_ids: [],
      tags: [],
    },
  ],
  can_edit_objectives: false,
  can_approve_objectives: false,
  tags,
  can_edit_tags: canTag,
});

const preview: InheritancePreview = {
  tag_value_id: 'tbl',
  label: 'TBL',
  list_name: 'Teaching methods',
  item_has_tag: false,
  items: [
    {
      item_type: 'learning_event',
      item_id: 'e1',
      name: 'Cardiac cycle',
      level: null,
      module_code: 'HSC201',
      status: 'new',
    },
    {
      item_type: 'learning_event',
      item_id: 'e2',
      name: 'ECG interpretation workshop',
      level: null,
      module_code: 'HSC201',
      status: 'has_tag',
    },
  ],
};

async function tree() {
  return screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
}

describe('tagging curriculum items', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([
      role('programme_director', ['curriculum.view', 'tagging.edit']),
    ]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchProgramme.mockRejectedValue(new ApiError(500, 'not needed'));
    mocked.fetchVersionStructure.mockResolvedValue({ ...structure, can_edit_outcome_tags: true });
    mocked.fetchProgrammeOutcomes.mockResolvedValue([]);
    mocked.fetchModule.mockResolvedValue(moduleDetail([direct], true));
    mocked.fetchLearningEvent.mockResolvedValue(eventDetail([inherited], true));
    mocked.fetchTaxonomyScales.mockResolvedValue([]);
    mocked.fetchTagLists.mockResolvedValue(lists);
    mocked.fetchTagPreview.mockResolvedValue(preview);
  });

  it('shows direct tags and, for inherited ones, where they came from', async () => {
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    const group = await screen.findByRole('group', { name: 'Tags of HSC201 Cardiovascular system' });
    expect(within(group).getByText('PBL')).toBeInTheDocument();
    expect(within(group).getByText('Teaching methods')).toBeInTheDocument();
    // The outcome carries an inherited tag, with its source in words.
    const outcome = (await screen.findByText('Interpret cardiac tests.')).closest('li')!;
    expect(
      within(outcome).getByText(/Inherited from course HSC201 Cardiovascular system/)
    ).toBeInTheDocument();
    // Inherited tags have no Remove button; direct tags do.
    expect(within(outcome).queryByRole('button', { name: /Remove tag/ })).not.toBeInTheDocument();
    expect(
      within(group).getByRole('button', { name: 'Remove tag PBL from HSC201 Cardiovascular system' })
    ).toBeInTheDocument();
  });

  it('offers to pass a tag on to newer items, after a preview', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail([{ ...direct, not_reached: 2 }], true));
    mocked.fetchPassOnPreview.mockResolvedValue({
      ...preview,
      tag_value_id: 'pbl',
      label: 'PBL',
      item_has_tag: true,
    });
    mocked.passTagOn.mockResolvedValue({ tags: [direct], inherited_count: 1 });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    const group = await screen.findByRole('group', { name: 'Tags of HSC201 Cardiovascular system' });
    expect(
      within(group).getByText(/PBL has not reached 2 newer items below/)
    ).toBeInTheDocument();
    fireEvent.click(
      within(group).getByRole('button', {
        name: 'Pass it on: tag PBL of HSC201 Cardiovascular system to newer items',
      })
    );

    const form = await screen.findByRole('dialog', {
      name: 'Pass PBL on from HSC201 Cardiovascular system',
    });
    expect(await within(form).findByText('Cardiac cycle')).toBeInTheDocument();
    expect(mocked.fetchPassOnPreview).toHaveBeenCalledWith('t1');
    expect(within(form).getByText('Will get the tag')).toBeInTheDocument();
    expect(mocked.passTagOn).not.toHaveBeenCalled();

    fireEvent.click(within(form).getByRole('button', { name: 'Pass on to 1 item' }));

    expect(
      await screen.findByText('Tag PBL passed on from HSC201 Cardiovascular system to 1 item.')
    ).toBeInTheDocument();
    expect(mocked.passTagOn).toHaveBeenCalledWith('t1');
  });

  it('shows no pass-on notice when nothing is missing or the person cannot tag', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail([{ ...direct, not_reached: 0 }], true));
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();
    await screen.findByText('PBL');
    expect(screen.queryByText(/has not reached/)).not.toBeInTheDocument();
  });

  it('hides the pass-on notice from people who may not tag', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail([{ ...direct, not_reached: 3 }], false));
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();
    await screen.findByText('PBL');
    expect(screen.queryByText(/has not reached/)).not.toBeInTheDocument();
  });

  it('shows no tag buttons to people who may not tag', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail([direct], false));
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    await screen.findByText('PBL');
    expect(screen.queryByRole('button', { name: /Add tag/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove tag/ })).not.toBeInTheDocument();
  });

  it('tags a module after showing every session the tag would reach', async () => {
    mocked.addTag.mockResolvedValue({ tags: [direct], inherited_count: 1 });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to HSC201 Cardiovascular system' }));
    const form = await screen.findByRole('dialog', { name: 'Add a tag to HSC201 Cardiovascular system' });
    const select = await within(form).findByRole('combobox', { name: /Tag/ });
    // Only active tags of lists that apply to modules; PBL is already set here.
    const options = within(select).getAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual(['Choose a tag', 'TBL']);

    fireEvent.change(select, { target: { value: 'tbl' } });
    expect(await within(form).findByText('Cardiac cycle')).toBeInTheDocument();
    expect(mocked.fetchTagPreview).toHaveBeenCalledWith('module', 'm2', 'tbl');
    expect(within(form).getByText('Will get the tag')).toBeInTheDocument();
    expect(within(form).getByText('Already has this tag')).toBeInTheDocument();
    const inherit = within(form).getByRole('checkbox', {
      name: /Also give this tag to the 1 item below/,
    });
    expect(inherit).toBeChecked();

    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(
      await screen.findByText(
        'Tag TBL added to HSC201 Cardiovascular system and passed on to 1 other item.'
      )
    ).toBeInTheDocument();
    expect(mocked.addTag).toHaveBeenCalledWith('module', 'm2', 'tbl', true);
  });

  it('tags only the module when the person clears the box', async () => {
    mocked.addTag.mockResolvedValue({ tags: [direct], inherited_count: 0 });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to HSC201 Cardiovascular system' }));
    const form = await screen.findByRole('dialog');
    fireEvent.change(await within(form).findByRole('combobox', { name: /Tag/ }), {
      target: { value: 'tbl' },
    });
    fireEvent.click(await within(form).findByRole('checkbox', { name: /Also give this tag/ }));
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(
      await screen.findByText('Tag TBL added to HSC201 Cardiovascular system.')
    ).toBeInTheDocument();
    expect(mocked.addTag).toHaveBeenCalledWith('module', 'm2', 'tbl', false);
  });

  it('asks for a tag before saving', async () => {
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to HSC201 Cardiovascular system' }));
    const form = await screen.findByRole('dialog');
    await within(form).findByRole('combobox', { name: /Tag/ });
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(await within(form).findByText('Fill in this field.')).toBeInTheDocument();
    expect(mocked.addTag).not.toHaveBeenCalled();
  });

  it('says when a module has no sessions to pass the tag to', async () => {
    mocked.fetchTagPreview.mockResolvedValue({ ...preview, items: [] });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to HSC201 Cardiovascular system' }));
    const form = await screen.findByRole('dialog');
    fireEvent.change(await within(form).findByRole('combobox', { name: /Tag/ }), {
      target: { value: 'tbl' },
    });

    expect(await within(form).findByText(/has no sessions yet/)).toBeInTheDocument();
    expect(within(form).queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('tags a session without a preview, and offers themes only on objectives', async () => {
    mocked.addTag.mockResolvedValue({ tags: [inherited], inherited_count: 0 });
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to Cardiac cycle' }));
    const form = await screen.findByRole('dialog', { name: 'Add a tag to Cardiac cycle' });
    const select = await within(form).findByRole('combobox', { name: /Tag/ });
    expect(within(select).queryByRole('option', { name: 'Ethics' })).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'pbl' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(await screen.findByText('Tag PBL added to Cardiac cycle.')).toBeInTheDocument();
    expect(mocked.addTag).toHaveBeenCalledWith('learning_event', 'e1', 'pbl', false);
    expect(mocked.fetchTagPreview).not.toHaveBeenCalled();
  });

  it('tags an objective', async () => {
    mocked.addTag.mockResolvedValue({ tags: [inherited], inherited_count: 0 });
    mocked.fetchTagPreview.mockResolvedValue({ ...preview, items: [] });
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add tag to Describe the cardiac cycle.' })
    );
    const form = await screen.findByRole('dialog');
    const select = await within(form).findByRole('combobox', { name: /Tag/ });
    expect(within(select).getByRole('option', { name: 'Ethics' })).toBeInTheDocument();
    fireEvent.change(select, { target: { value: 'ethics' } });
    expect(await within(form).findByText(/No objectives are linked below/)).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    await screen.findByText(/Tag Ethics added to Describe the cardiac cycle/);
    expect(mocked.addTag).toHaveBeenCalledWith('objective', 'o-e1', 'ethics', false);
  });

  it('explains when no tag can be added', async () => {
    mocked.fetchTagLists.mockResolvedValue([]);
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to HSC201 Cardiovascular system' }));
    const form = await screen.findByRole('dialog');

    expect(await within(form).findByText(/There is no tag you can add here/)).toBeInTheDocument();
  });

  it('reports a failed save in plain words', async () => {
    mocked.addTag.mockRejectedValue(new ApiError(409, 'conflict'));
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add tag to Cardiac cycle' }));
    const form = await screen.findByRole('dialog');
    fireEvent.change(await within(form).findByRole('combobox', { name: /Tag/ }), {
      target: { value: 'pbl' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add tag' }));

    expect(await within(form).findByRole('alert')).toBeInTheDocument();
  });

  it('removes a tag that was set directly', async () => {
    mocked.removeTagging.mockResolvedValue(undefined);
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Remove tag PBL from HSC201 Cardiovascular system' })
    );

    expect(
      await screen.findByText('Tag PBL removed from HSC201 Cardiovascular system.')
    ).toBeInTheDocument();
    expect(mocked.removeTagging).toHaveBeenCalledWith('t1');
  });

  it('keeps the tag and says so when removing fails', async () => {
    mocked.removeTagging.mockRejectedValue(new ApiError(409, 'conflict'));
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Remove tag PBL from HSC201 Cardiovascular system' })
    );

    expect(await screen.findAllByRole('alert')).not.toHaveLength(0);
    expect(screen.getByText('PBL')).toBeInTheDocument();
  });

  it('shows a tag set here and also inherited', async () => {
    mocked.fetchModule.mockResolvedValue(
      moduleDetail([{ ...direct, sources: inherited.sources }], true)
    );
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    expect(
      await screen.findByText(/Set here and inherited from course HSC201/)
    ).toBeInTheDocument();
  });

  it('lets people who tag programme outcomes do so', async () => {
    mocked.fetchProgrammeOutcomes.mockResolvedValue([
      {
        id: 'p1',
        text: 'Practise safely.',
        domain: null,
        taxonomy_level_id: null,
        status: 'draft',
        position: 0,
        parent_ids: [],
        tags: [],
      },
    ]);
    renderAt('/curriculum/versions/v2027');
    await tree();

    expect(
      await screen.findByRole('button', { name: 'Add tag to Practise safely.' })
    ).toBeInTheDocument();
  });
});
