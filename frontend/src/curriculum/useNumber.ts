import { useTranslation } from 'react-i18next';

/** Formats numbers (also numeric strings from the API) in the interface language. */
export function useNumber() {
  const { i18n } = useTranslation();
  return (value: number | string, digits = 1) =>
    new Intl.NumberFormat(i18n.language, {
      maximumFractionDigits: digits,
    }).format(Number(value));
}
