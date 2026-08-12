import { useState } from "react";

interface ConfirmButtonProps {
  label: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
  className?: string;
  confirmClassName?: string;
  title?: string;
}

/** A button that arms on first click (showing confirm/cancel) instead of firing
 *  immediately — the same inline-confirm UX ThemesPage and SettingsTargets already use
 *  for delete, packaged so consequential actions elsewhere don't each reinvent it. */
export default function ConfirmButton({
  label,
  confirmLabel,
  cancelLabel,
  onConfirm,
  disabled = false,
  className,
  confirmClassName = "danger",
  title,
}: ConfirmButtonProps) {
  const [armed, setArmed] = useState(false);

  if (armed) {
    return (
      <>
        <button
          type="button"
          className={confirmClassName}
          disabled={disabled}
          onClick={() => {
            setArmed(false);
            onConfirm();
          }}
        >
          {confirmLabel}
        </button>
        <button type="button" disabled={disabled} onClick={() => setArmed(false)}>
          {cancelLabel}
        </button>
      </>
    );
  }

  return (
    <button type="button" className={className} title={title} disabled={disabled} onClick={() => setArmed(true)}>
      {label}
    </button>
  );
}
