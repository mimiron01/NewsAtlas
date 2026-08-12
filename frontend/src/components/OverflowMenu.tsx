import { ReactNode, useEffect, useRef, useState } from "react";

import { KebabIcon } from "./icons/NavIcons";

/** Generic "⋮" row-actions menu — collapses a long list of secondary actions
 *  behind a single trigger instead of lining every button up in the row. */
export default function OverflowMenu({
  label,
  disabled = false,
  children,
}: {
  label: string;
  disabled?: boolean;
  children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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
    <div className="overflow-menu" ref={containerRef}>
      <button
        type="button"
        className="overflow-menu-trigger"
        aria-haspopup="true"
        aria-expanded={isOpen}
        aria-label={label}
        disabled={disabled}
        onClick={() => setIsOpen((open) => !open)}
      >
        <KebabIcon />
      </button>
      {isOpen && (
        <div className="overflow-menu-popover" role="menu" onClick={() => setIsOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}
