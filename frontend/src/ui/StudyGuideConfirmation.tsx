import { Checkbox } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { STUDY_GUIDE_CONFIRMATION_VERSION } from './studyGuidePayload';

interface StudyGuideConfirmationProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Shown under the box, e.g. "Confirm this before uploading" after a refused submit. */
  error?: string;
  disabled?: boolean;
}

/**
 * "This study guide contains no real patient information." Every study-guide upload (Slice
 * 1.18) must show this, keep its upload button disabled until it is ticked, and send
 * `studyGuideConfirmationPayload(true)`. The server refuses an upload without it and records
 * the confirmation in the audit log.
 */
export function StudyGuideConfirmation({
  checked,
  onChange,
  error,
  disabled,
}: StudyGuideConfirmationProps) {
  const { t } = useTranslation();
  return (
    <Checkbox
      checked={checked}
      onChange={(event) => onChange(event.currentTarget.checked)}
      disabled={disabled}
      error={error}
      required
      label={t(`studyGuideConfirmation.v${STUDY_GUIDE_CONFIRMATION_VERSION}.text`)}
      description={t('studyGuideConfirmation.help')}
    />
  );
}
