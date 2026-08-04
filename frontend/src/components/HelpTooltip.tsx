import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { HelpIcon } from "./icons/NavIcons";

/**
 * Small "?" icon that reveals a field's help text on hover/focus (desktop) or tap
 * (touch — toggled via `isOpen`, since there's no hover event to rely on there),
 * instead of the text being permanently visible next to every field.
 */
export default function HelpTooltip({ content }: { content: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);
  const { t } = useTranslation("common");

  useEffect(() => {
    if (!isOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <span className={`help-tooltip${isOpen ? " open" : ""}`} ref={containerRef}>
      <button
        type="button"
        className="help-tooltip-trigger"
        aria-label={t("help")}
        aria-expanded={isOpen}
        onClick={(event) => {
          event.preventDefault();
          setIsOpen((open) => !open);
        }}
      >
        <HelpIcon />
      </button>
      <span className="help-tooltip-popover" role="tooltip">
        {content}
      </span>
    </span>
  );
}
