import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import type { SupportedLanguage } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { GlobeIcon } from "./icons/NavIcons";

const WORKSPACE_DEFAULT_VALUE = "default";

export default function LanguageSwitcher() {
  const { t } = useTranslation("nav");
  const { user, setLanguagePreference } = useAuth();
  if (!user) return null;

  const value = user.preferred_language ?? WORKSPACE_DEFAULT_VALUE;

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value;
    setLanguagePreference(next === WORKSPACE_DEFAULT_VALUE ? null : (next as SupportedLanguage));
  }

  return (
    <label className="language-select">
      <GlobeIcon />
      <select value={value} onChange={handleChange} aria-label={t("language.label")}>
        <option value={WORKSPACE_DEFAULT_VALUE}>{t("language.workspaceDefault")}</option>
        <option value="en">{t("language.en")}</option>
        <option value="de">{t("language.de")}</option>
      </select>
    </label>
  );
}
