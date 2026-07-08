import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import deAuth from "./locales/de/auth.json";
import deCommon from "./locales/de/common.json";
import deDashboard from "./locales/de/dashboard.json";
import deErrors from "./locales/de/errors.json";
import deNav from "./locales/de/nav.json";
import deSettings from "./locales/de/settings.json";
import deSignals from "./locales/de/signals.json";
import enAuth from "./locales/en/auth.json";
import enCommon from "./locales/en/common.json";
import enDashboard from "./locales/en/dashboard.json";
import enErrors from "./locales/en/errors.json";
import enNav from "./locales/en/nav.json";
import enSettings from "./locales/en/settings.json";
import enSignals from "./locales/en/signals.json";

export const SUPPORTED_LANGUAGES = ["en", "de"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

// Mirrors useTheme.ts's localStorage-caching pattern: the effective language for an
// authenticated user (personal preference, falling back to the workspace's Main
// Language) always wins once known — see AuthContext, which calls i18n.changeLanguage()
// after /auth/me resolves. Before that (or when logged out, e.g. on the Login page),
// this detector's browser-language guess is what's shown.
const LOCALE_STORAGE_KEY = "newsatlas_locale";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
        nav: enNav,
        auth: enAuth,
        dashboard: enDashboard,
        signals: enSignals,
        settings: enSettings,
        errors: enErrors,
      },
      de: {
        common: deCommon,
        nav: deNav,
        auth: deAuth,
        dashboard: deDashboard,
        signals: deSignals,
        settings: deSettings,
        errors: deErrors,
      },
    },
    supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
    fallbackLng: "en",
    ns: ["common", "nav", "auth", "dashboard", "signals", "settings", "errors"],
    defaultNS: "common",
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: LOCALE_STORAGE_KEY,
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: true },
  });

function syncHtmlLang(language: string) {
  document.documentElement.lang = language;
}

i18n.on("languageChanged", syncHtmlLang);
if (i18n.language) syncHtmlLang(i18n.language);

export default i18n;
