import { useTranslation } from "react-i18next";

import HelpTooltip from "./HelpTooltip";
import TagInput from "./TagInput";

/**
 * The trusted-sources field has three genuinely different states, and the distinction is
 * invisible in a plain tag input:
 *
 *   null  — inherit the workspace's trusted sources (the default, and right for almost
 *           every company)
 *   []    — deliberately search everything, ignoring the workspace list
 *   [...] — replace the workspace list with these domains
 *
 * Without the middle state a workspace-level list could never be opted out of, which is
 * the problem the override semantics exist to fix — so it has to be reachable in the UI,
 * not just in the data model.
 */
export default function SourceAllowlistField({
  value,
  onChange,
}: {
  value: string[] | null;
  onChange: (value: string[] | null) => void;
}) {
  const { t } = useTranslation("settings");
  const mode = value === null ? "inherit" : value.length === 0 ? "all" : "custom";

  const hint =
    mode === "inherit"
      ? t("targets.allowlistInheritHint")
      : mode === "all"
        ? t("targets.allowlistAllHint")
        : t("targets.allowlistCustomHint");

  return (
    <div className="source-allowlist-field">
      <span className="field-label">
        {t("targets.sourceAllowlist")} <HelpTooltip content={hint} />
      </span>
      <div className="field-row">
        <label className="checkbox-label">
          <input
            type="radio"
            checked={mode === "inherit"}
            onChange={() => onChange(null)}
          />
          {t("targets.allowlistInherit")}
        </label>
        <label className="checkbox-label">
          <input type="radio" checked={mode === "all"} onChange={() => onChange([])} />
          {t("targets.allowlistAll")}
        </label>
        <label className="checkbox-label">
          <input
            type="radio"
            checked={mode === "custom"}
            // Switching to "custom" with nothing entered would look identical to "all"
            // until the first tag is typed, so seed it with a placeholder-free empty list
            // and let the tag input carry the meaning.
            onChange={() => onChange(value && value.length > 0 ? value : [])}
          />
          {t("targets.allowlistCustom")}
        </label>
      </div>
      {mode !== "inherit" && (
        <TagInput
          tags={value ?? []}
          onChange={(tags) => onChange(tags)}
          placeholder={t("targets.sourceAllowlistPlaceholder")}
        />
      )}
    </div>
  );
}
