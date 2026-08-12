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
  subject = "company",
}: {
  value: string[] | null;
  onChange: (value: string[] | null) => void;
  // This field is shared between the target-company form and the topic form; the copy
  // talks about "this company" vs. "this topic" accordingly instead of always saying
  // "company" regardless of where it's rendered.
  subject?: "company" | "topic";
}) {
  const { t } = useTranslation(["settings", "themes"]);
  const ns = subject === "topic" ? "themes" : "settings";
  const prefix = subject === "topic" ? "addTheme" : "targets";
  const tf = (key: string) => t(`${ns}:${prefix}.${key}`);
  const mode = value === null ? "inherit" : value.length === 0 ? "all" : "custom";

  const hint =
    mode === "inherit"
      ? tf("allowlistInheritHint")
      : mode === "all"
        ? tf("allowlistAllHint")
        : tf("allowlistCustomHint");

  return (
    <div className="source-allowlist-field">
      <span className="field-label">
        {tf("sourceAllowlist")} <HelpTooltip content={hint} />
      </span>
      <div className="field-row field-row--wide">
        <label className="checkbox-label">
          <input
            type="radio"
            checked={mode === "inherit"}
            onChange={() => onChange(null)}
          />
          {tf("allowlistInherit")}
        </label>
        <label className="checkbox-label">
          <input type="radio" checked={mode === "all"} onChange={() => onChange([])} />
          {tf("allowlistAll")}
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
          {tf("allowlistCustom")}
        </label>
      </div>
      {mode !== "inherit" && (
        <TagInput
          tags={value ?? []}
          onChange={(tags) => onChange(tags)}
          placeholder={tf("sourceAllowlistPlaceholder")}
        />
      )}
    </div>
  );
}
