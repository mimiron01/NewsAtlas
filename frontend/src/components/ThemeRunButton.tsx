import { useTranslation } from "react-i18next";

import type { ThemeWatch } from "../api/types";
import { useCooldownRemaining } from "../hooks/useCooldownRemaining";

interface ThemeRunButtonProps {
  theme: ThemeWatch;
  cooldownSeconds: number;
  /** A run (this theme's, another's, or a full one) is already in flight — the backend
   *  hands back that run rather than starting a second, so the button reflects that. */
  isRunning: boolean;
  /** Google News RSS is switched off workspace-wide, so no topic can fetch anything. */
  googleNewsDisabled: boolean;
  isPending: boolean;
  onRun: (theme: ThemeWatch) => void;
}

/** "Fetch now" for a single topic, disabled with a visible reason rather than silently:
 *  paused, source disabled, a run already going, or a cooldown still ticking down. */
export default function ThemeRunButton({
  theme,
  cooldownSeconds,
  isRunning,
  googleNewsDisabled,
  isPending,
  onRun,
}: ThemeRunButtonProps) {
  const { t } = useTranslation("themes");
  const remaining = useCooldownRemaining(theme.last_manual_run_at, cooldownSeconds);

  const blockedReason = googleNewsDisabled
    ? t("run.blockedSourceDisabled")
    : !theme.is_active
      ? t("run.blockedPaused")
      : isRunning
        ? t("run.blockedRunning")
        : remaining > 0
          ? t("run.blockedCooldown", { seconds: remaining })
          : null;

  return (
    <button
      type="button"
      className="secondary"
      disabled={isPending || blockedReason !== null}
      // The reason is on the button itself, so a disabled control never leaves the user
      // guessing why it won't respond.
      title={blockedReason ?? t("run.button")}
      onClick={() => onRun(theme)}
    >
      {remaining > 0 && !googleNewsDisabled && theme.is_active && !isRunning
        ? t("run.buttonCooldown", { seconds: remaining })
        : t("run.button")}
    </button>
  );
}
