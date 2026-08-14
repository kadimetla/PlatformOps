// Presentation helpers shared between the session grid (App.tsx's
// ThreadCard) and the floating session panel (FloatingSessionPanel.tsx)
// -- kept in one place so both render the same label/status vocabulary
// rather than drifting.
import type { PlatformOpsClientState, Turn, TurnKind } from "./agui";

export const TURN_LABELS: Record<TurnKind, string> = {
  user_message: "You",
  clarification_required: "Question",
  approval_required: "Approval",
  route_resolved: "Result",
  error: "Error",
};

// Ops-flavored session states, not generic chat states -- each session
// is a bounded unit of work (a compliance check, a provision request),
// so status reads like a work item's status, not "is someone typing."
// Distinguishing needs_input (a classification question) from
// awaiting_approval (a mutating action waiting on a human sign-off)
// matters here specifically because those are different HITLEventKinds
// backend-side (interaction/events.py) with different stakes -- worth
// keeping visually distinct even though neither is resumable through
// approval yet (see interaction/a2ui.py's message-only approval
// rendering).
export type SessionStatus =
  | "new"
  | "working"
  | "needs_input"
  | "awaiting_approval"
  | "done"
  | "error";

export const STATUS_LABELS: Record<SessionStatus, string> = {
  new: "New",
  working: "Working…",
  needs_input: "Needs input",
  awaiting_approval: "Awaiting approval",
  done: "Done",
  error: "Error",
};

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function deriveLabel(turns: Turn[]): string {
  const firstMessage = turns.find((t) => t.kind === "user_message");
  if (!firstMessage) return "New session";
  return firstMessage.text.length > 40 ? `${firstMessage.text.slice(0, 40)}…` : firstMessage.text;
}

export function deriveStatus(state: PlatformOpsClientState): SessionStatus {
  if (state.isSubmitting) return "working";
  const last = state.turns[state.turns.length - 1];
  if (!last) return "new";
  if (last.kind === "clarification_required") return "needs_input";
  if (last.kind === "approval_required") return "awaiting_approval";
  if (last.kind === "error") return "error";
  return "done"; // route_resolved
}
