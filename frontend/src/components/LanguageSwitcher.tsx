import { useTranslation } from "react-i18next";

import type { SupportedLanguage } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { GlobeIcon } from "./icons/NavIcons";

// Cycles workspace default (personal preference cleared) -> English -> German -> ...,
// mirroring useTheme's system -> light -> dark -> system cycle.
const CYCLE: (SupportedLanguage | null)[] = [null, "en", "de"];

export default function LanguageSwitcher() {
  const { t } = useTranslation("nav");
  const { user, setLanguagePreference } = useAuth();
  if (!user) return null;

  const current = user.preferred_language;
  const label =
    current === null ? t("language.workspaceDefault") : t(`language.${current}`);

  function cycleLanguage() {
    const nextIndex = (CYCLE.indexOf(current) + 1) % CYCLE.length;
    setLanguagePreference(CYCLE[nextIndex]);
  }

  return (
    <button type="button" className="language-toggle" onClick={cycleLanguage}>
      <GlobeIcon />
      {label}
    </button>
  );
}
