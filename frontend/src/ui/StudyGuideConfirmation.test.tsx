import { fireEvent, render, screen } from '@testing-library/react';
import axe from 'axe-core';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { ThemeProvider } from '../theme/ThemeProvider';
import { StudyGuideConfirmation } from './StudyGuideConfirmation';
import {
  STUDY_GUIDE_CONFIRMATION_VERSION,
  studyGuideConfirmationPayload,
} from './studyGuidePayload';

function Harness({ error }: { error?: string }) {
  const [checked, setChecked] = useState(false);
  return (
    <ThemeProvider>
      <StudyGuideConfirmation checked={checked} onChange={setChecked} error={error} />
      <button type="button" disabled={!checked}>
        Upload
      </button>
    </ThemeProvider>
  );
}

describe('study guide confirmation', () => {
  it('is an unticked, required checkbox that names the rule in words', () => {
    render(<Harness />);

    const box = screen.getByRole('checkbox', { name: /contains no real patient information/ });
    expect(box).not.toBeChecked();
    expect(box).toBeRequired();
    expect(screen.getByText(/recorded in the audit log/)).toBeInTheDocument();
  });

  it('keeps the upload unavailable until it is ticked', () => {
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox'));

    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled();
  });

  it('shows an error as text', () => {
    render(<Harness error="Confirm this before uploading." />);
    expect(screen.getByText('Confirm this before uploading.')).toBeInTheDocument();
  });

  it('sends the confirmation with the version of the text that was shown', () => {
    expect(studyGuideConfirmationPayload(true)).toEqual({
      confirmed: true,
      text_version: STUDY_GUIDE_CONFIRMATION_VERSION,
    });
  });

  it('has no structural accessibility violations (contrast is checked on the screen that uses it)', async () => {
    const { container } = render(<Harness error="Confirm this before uploading." />);

    const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });

    expect(result.violations).toEqual([]);
  });
});
