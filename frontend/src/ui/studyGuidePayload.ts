/**
 * The version of the confirmation text. It must match `CONFIRMATION_VERSION` in
 * `backend/app/services/study_guide_confirmation.py`; the text is the i18n key
 * `studyGuideConfirmation.v<version>.text`. The server refuses a stale version.
 */
export const STUDY_GUIDE_CONFIRMATION_VERSION = '1';

/** What a study-guide upload sends with the file (a required part of the request). */
export function studyGuideConfirmationPayload(confirmed: boolean) {
  return { confirmed, text_version: STUDY_GUIDE_CONFIRMATION_VERSION };
}
