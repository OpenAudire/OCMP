import type { FormEvent, ReactNode } from 'react';
import { Alert, Button, Group, Modal, Stack } from '@mantine/core';
import { useTranslation } from 'react-i18next';

interface EditDialogProps {
  opened: boolean;
  title: string;
  onClose: () => void;
  /** Mounted only while the dialog is open, so each opening starts fresh. */
  children: ReactNode;
}

/**
 * A dialog that adds, changes or deletes one curriculum item. Focus moves into the
 * dialog and back to the button that opened it; Escape and Cancel close it unsaved.
 */
export function EditDialog({ opened, title, onClose, children }: EditDialogProps) {
  const { t } = useTranslation();
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={title}
      size="lg"
      centered
      closeButtonProps={{ 'aria-label': t('curriculum.edit.close') }}
    >
      {children}
    </Modal>
  );
}

interface DialogFormProps {
  /** Text of the main button (e.g. "Add module", "Save", "Delete module"). */
  submitLabel: string;
  /** A failed save, in plain language. */
  error: string | null;
  busy: boolean;
  danger?: boolean;
  /** Without a submit handler the dialog only informs and offers Close. */
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
  children?: ReactNode;
}

/** The body of an edit dialog: an error, the fields, and Cancel and submit buttons. */
export function DialogForm({
  submitLabel,
  error,
  busy,
  danger = false,
  onSubmit,
  onClose,
  children,
}: DialogFormProps) {
  const { t } = useTranslation();
  return (
    <form noValidate onSubmit={onSubmit ?? ((event) => event.preventDefault())}>
      <Stack gap="md">
        {error && <Alert color="red">{error}</Alert>}
        {children}
        <Group justify="flex-end" gap="sm" mt="xs">
          {onSubmit ? (
            <>
              <Button variant="default" onClick={onClose} disabled={busy}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" color={danger ? 'red' : undefined} loading={busy}>
                {submitLabel}
              </Button>
            </>
          ) : (
            <Button onClick={onClose}>{t('curriculum.edit.close')}</Button>
          )}
        </Group>
      </Stack>
    </form>
  );
}
