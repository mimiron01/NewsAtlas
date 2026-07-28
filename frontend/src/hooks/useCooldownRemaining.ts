import { useEffect, useState } from "react";

/** Seconds still remaining on a cooldown that started at `lastRunAt`, ticking down once a
 *  second and settling at 0.
 *
 *  Lets a button be visibly disabled with a live countdown instead of staying enabled and
 *  failing the click with a 429 — the user can see exactly when it will work again rather
 *  than guessing. Returns 0 (never blocked) when `lastRunAt` is null, so a control that has
 *  never been used is immediately available.
 *
 *  The interval only runs while there is actually time left, so an idle page isn't holding
 *  a timer per row.
 */
export function useCooldownRemaining(lastRunAt: string | null, cooldownSeconds: number): number {
  const [remaining, setRemaining] = useState(() => computeRemaining(lastRunAt, cooldownSeconds));

  useEffect(() => {
    const next = computeRemaining(lastRunAt, cooldownSeconds);
    setRemaining(next);
    if (next <= 0) return;

    const interval = window.setInterval(() => {
      const value = computeRemaining(lastRunAt, cooldownSeconds);
      setRemaining(value);
      if (value <= 0) window.clearInterval(interval);
    }, 1000);
    return () => window.clearInterval(interval);
  }, [lastRunAt, cooldownSeconds]);

  return remaining;
}

function computeRemaining(lastRunAt: string | null, cooldownSeconds: number): number {
  if (!lastRunAt) return 0;
  const elapsedMs = Date.now() - new Date(lastRunAt).getTime();
  // A negative elapsed time means the client clock is behind the server's; treat it as
  // "cooldown just started" rather than letting it read as a wildly long wait.
  if (Number.isNaN(elapsedMs)) return 0;
  const remaining = Math.ceil(cooldownSeconds - Math.max(0, elapsedMs) / 1000);
  return Math.max(0, remaining);
}
