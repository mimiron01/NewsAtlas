import type { SignalStatus } from "../api/types";

export const STATUS_TRANSITIONS: { value: SignalStatus; label: string }[] = [
  { value: "reviewed", label: "Mark reviewed" },
  { value: "archived", label: "Archive" },
  { value: "dismissed", label: "Dismiss" },
];
