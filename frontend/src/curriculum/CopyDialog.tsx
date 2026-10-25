import { Fieldset, NativeSelect, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { copyLearningEvent, copyModule, copyPhase } from '../api/endpoints';
import type { VersionStructure } from '../api/types';
import { DialogForm, EditDialog } from './EditDialog';
import {
  editErrorMessage,
  moduleAncestors,
  nounsFor,
  useRefreshCurriculum,
  type EditResult,
} from './editing';
import { itemName, type MovableItem } from './reorder';
import { ROOT_ID } from './treeModel';

interface CopyDialogProps {
  opened: boolean;
  structure: VersionStructure;
  item: MovableItem;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

interface Values {
  /** Name of a phase or module, title of a session. */
  name: string;
  code: string;
  /** Module copies: the phase id, or '' for across phases. */
  phase: string;
  /** Phase copies: a new code per module id. */
  codes: Record<string, string>;
}

type FormProps = Omit<CopyDialogProps, 'opened'>;

/** Makes the copy; returns what the builder shows and selects next. */
async function copy(
  item: MovableItem,
  values: Values,
  copied: (name: string) => string
): Promise<EditResult> {
  const name = values.name.trim();
  switch (item.kind) {
    case 'phase': {
      const saved = await copyPhase(item.phase.id, {
        name,
        module_codes: Object.fromEntries(
          Object.entries(values.codes).map(([id, code]) => [id, code.trim()])
        ),
      });
      return {
        message: copied(saved.name),
        select: `phase:${saved.id}`,
        reveal: [ROOT_ID, `phase:${saved.id}`],
      };
    }
    case 'module': {
      const saved = await copyModule(item.module.id, {
        code: values.code.trim(),
        name,
        phase_id: values.phase || null,
      });
      return {
        message: copied(`${saved.code} ${saved.name}`),
        select: `module:${saved.id}`,
        reveal: moduleAncestors(saved.phase_id),
      };
    }
    case 'event': {
      const saved = await copyLearningEvent(item.event.id, name);
      return {
        message: copied(saved.title),
        select: `event:${saved.id}`,
        reveal: [...moduleAncestors(item.phase?.id ?? null), `module:${item.module.id}`],
      };
    }
  }
}

function CopyForm({ structure, item, onClose, onSaved }: FormProps) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const refresh = useRefreshCurriculum(structure.version.id);
  const modules = item.kind === 'phase' ? item.phase.modules : [];
  const sourceName = item.kind === 'module' ? item.module.name : itemName(item);
  const form = useForm<Values>({
    initialValues: {
      name: t('curriculum.copy.defaultName', { name: sourceName }),
      code: '',
      phase: item.kind === 'module' ? (item.phase?.id ?? '') : '',
      codes: Object.fromEntries(modules.map((module) => [module.id, ''])),
    },
    validate: (values) => {
      const errors: Record<string, string | null> = {};
      if (!values.name.trim()) errors.name = t('curriculum.edit.required');
      if (item.kind === 'module' && !values.code.trim()) {
        errors.code = t('curriculum.edit.required');
      }
      const seen = new Set<string>();
      for (const module of modules) {
        const code = values.codes[module.id].trim();
        if (!code) errors[`codes.${module.id}`] = t('curriculum.edit.required');
        else if (seen.has(code.toLocaleLowerCase())) {
          errors[`codes.${module.id}`] = t('curriculum.copy.errors.sameCode');
        }
        seen.add(code.toLocaleLowerCase());
      }
      return errors;
    },
  });
  const run = useMutation({
    mutationFn: (values: Values) =>
      copy(item, values, (name) => t('curriculum.copy.copied', { name })),
    onSuccess: async (result) => {
      await refresh();
      onSaved(result);
    },
  });

  const conflict =
    item.kind === 'event'
      ? undefined
      : item.kind === 'module'
        ? t('curriculum.edit.errors.codeTaken', nouns)
        : t('curriculum.copy.errors.codesTaken', nouns);
  const error = run.isError ? editErrorMessage(t, run.error, conflict) : null;

  const term = item.kind === 'event' ? 'learning_event' : item.kind;
  let includes: string;
  if (item.kind === 'phase') {
    includes = t('curriculum.copy.includesPhase', nouns);
  } else if (item.kind === 'module') {
    includes = t('curriculum.copy.includesModule', nouns);
  } else {
    includes = t('curriculum.copy.includesEvent', nouns);
  }

  return (
    <DialogForm
      submitLabel={t('curriculum.copy.submit', { noun: nouns.noun(term) })}
      error={error}
      busy={run.isPending}
      onSubmit={form.onSubmit((values) => run.mutate(values))}
      onClose={onClose}
    >
      <Stack gap={4}>
        <Text>{includes}</Text>
        <Text size="sm" c="dimmed">
          {t('curriculum.copy.notIncluded')}
        </Text>
      </Stack>
      {item.kind === 'module' && (
        <TextInput
          label={t('curriculum.edit.fields.code')}
          description={t('curriculum.copy.codeHint', { code: item.module.code })}
          required
          maxLength={32}
          data-autofocus
          {...form.getInputProps('code')}
        />
      )}
      <TextInput
        label={t(
          item.kind === 'event' ? 'curriculum.edit.fields.title' : 'curriculum.edit.fields.name'
        )}
        required
        maxLength={255}
        data-autofocus={item.kind === 'module' ? undefined : true}
        {...form.getInputProps('name')}
      />
      {item.kind === 'module' && (
        <NativeSelect
          label={t('terms.phase', { count: 1 })}
          data={[
            ...structure.phases.map((phase) => ({ value: phase.id, label: phase.name })),
            { value: '', label: t('curriculum.edit.fields.acrossPhases') },
          ]}
          {...form.getInputProps('phase')}
        />
      )}
      {modules.length > 0 && (
        <Fieldset legend={t('curriculum.copy.newCodes', nouns)} variant="unstyled">
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              {t('curriculum.copy.newCodesHint', nouns)}
            </Text>
            {modules.map((module) => (
              <TextInput
                key={module.id}
                label={t('curriculum.copy.codeFor', { name: `${module.code} ${module.name}` })}
                required
                maxLength={32}
                {...form.getInputProps(`codes.${module.id}`)}
              />
            ))}
          </Stack>
        </Fieldset>
      )}
    </DialogForm>
  );
}

/** Copy a phase, module or session with what it holds, right after it. */
export function CopyDialog({ opened, item, ...props }: CopyDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('curriculum.copy.title', { name: itemName(item) })}
    >
      <CopyForm item={item} {...props} />
    </EditDialog>
  );
}
