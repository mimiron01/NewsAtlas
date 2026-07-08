import { useCallback } from "react";
import { useTranslation } from "react-i18next";

export function useLocaleFormat() {
  const { i18n } = useTranslation();

  const formatDate = useCallback(
    (value: string | Date, options?: Intl.DateTimeFormatOptions) =>
      new Intl.DateTimeFormat(i18n.language, options).format(new Date(value)),
    [i18n.language]
  );

  const formatNumber = useCallback(
    (value: number, options?: Intl.NumberFormatOptions) =>
      new Intl.NumberFormat(i18n.language, options).format(value),
    [i18n.language]
  );

  return { formatDate, formatNumber };
}
