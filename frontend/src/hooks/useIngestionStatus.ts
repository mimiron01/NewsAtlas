import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { IngestionRunStatus } from "../api/types";

const POLL_INTERVAL_MS = 1500;

/** Polls the latest ingestion run (manual or scheduled) so a progress bar or
 * last-run message stays correct across page loads, not just while this tab is
 * watching a run it started. `onRunFinished` fires once per transition out of
 * "running", so callers can refresh whatever list the run just updated. */
export function useIngestionStatus(onRunFinished?: () => void) {
  const [ingestionStatus, setIngestionStatus] = useState<IngestionRunStatus | null>(null);
  const wasRunningRef = useRef(false);
  // Kept in a ref (rather than a poll() dependency) so a new onRunFinished identity on
  // every render doesn't tear down and restart the polling interval below.
  const onRunFinishedRef = useRef(onRunFinished);
  onRunFinishedRef.current = onRunFinished;
  const isRunning = ingestionStatus?.status === "running";

  const poll = useCallback(async () => {
    try {
      const result = await api.get<IngestionRunStatus | null>("/ingestion/status");
      setIngestionStatus(result);
      if (result?.status === "running") {
        wasRunningRef.current = true;
      } else if (wasRunningRef.current) {
        wasRunningRef.current = false;
        onRunFinishedRef.current?.();
      }
    } catch {
      // Transient poll failure — the next tick (or the next page load) will pick it back up.
    }
  }, []);

  useEffect(() => {
    poll();
  }, [poll]);

  useEffect(() => {
    if (!isRunning) return;
    const interval = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [isRunning, poll]);

  return { ingestionStatus, setIngestionStatus, isRunning };
}
