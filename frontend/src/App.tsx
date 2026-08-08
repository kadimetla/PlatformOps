import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { A2uiSurface, type A2uiSurfaceModel, type Turn, type TurnKind } from "./lib/agui";
import { createThreadManager } from "./lib/threadManager";
import type { ThreadClient, PlatformOpsClientState } from "./lib/agui";
import "./App.css";

const TURN_LABELS: Record<TurnKind, string> = {
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
type SessionStatus = "new" | "working" | "needs_input" | "awaiting_approval" | "done" | "error";

const STATUS_LABELS: Record<SessionStatus, string> = {
  new: "New",
  working: "Working…",
  needs_input: "Needs input",
  awaiting_approval: "Awaiting approval",
  done: "Done",
  error: "Error",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function deriveLabel(turns: Turn[]): string {
  const firstMessage = turns.find((t) => t.kind === "user_message");
  if (!firstMessage) return "New session";
  return firstMessage.text.length > 40 ? `${firstMessage.text.slice(0, 40)}…` : firstMessage.text;
}

function deriveStatus(state: PlatformOpsClientState): SessionStatus {
  if (state.isSubmitting) return "working";
  const last = state.turns[state.turns.length - 1];
  if (!last) return "new";
  if (last.kind === "clarification_required") return "needs_input";
  if (last.kind === "approval_required") return "awaiting_approval";
  if (last.kind === "error") return "error";
  return "done"; // route_resolved
}

// createThreadManager (and each ThreadClient it creates) owns state
// outside React, so every level here reads it via useSyncExternalStore
// rather than mirroring it into React state -- see lib/agui.ts's and
// lib/threadManager.ts's module docstrings for why.
export default function App() {
  const manager = useMemo(() => createThreadManager("/runs"), []);
  const threadIds = useSyncExternalStore(manager.subscribe, manager.getThreadIds);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedClient = selectedId ? manager.getThread(selectedId) : undefined;

  function openNewThread() {
    setSelectedId(manager.createThread());
  }

  function closeThread(id: string) {
    manager.closeThread(id);
    if (selectedId === id) setSelectedId(null);
  }

  if (selectedClient) {
    return (
      <ThreadView
        client={selectedClient}
        onBack={() => setSelectedId(null)}
        onClose={() => closeThread(selectedClient.id)}
      />
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>PlatformOps</h1>
        <button type="button" className="new-thread-button" onClick={openNewThread}>
          + New session
        </button>
      </header>
      <div className="thread-grid">
        {threadIds.length === 0 && (
          <p className="turn-stream-empty">No sessions yet -- start one to get going.</p>
        )}
        {threadIds.map((id) => {
          const client = manager.getThread(id);
          return client ? (
            <ThreadCard
              key={id}
              client={client}
              onOpen={() => setSelectedId(id)}
              onClose={() => closeThread(id)}
            />
          ) : null;
        })}
      </div>
    </div>
  );
}

function ThreadCard({
  client,
  onOpen,
  onClose,
}: {
  client: ThreadClient;
  onOpen: () => void;
  onClose: () => void;
}) {
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const label = deriveLabel(state.turns);
  const status = deriveStatus(state);
  const lastTurn = state.turns[state.turns.length - 1];

  return (
    <div className="thread-card" data-status={status} onClick={onOpen}>
      <div className="thread-card-header">
        <span className="thread-card-label">{label}</span>
        <button
          type="button"
          className="thread-card-close"
          onClick={(event) => {
            event.stopPropagation();
            onClose();
          }}
          aria-label="Close session"
        >
          ×
        </button>
      </div>
      <p className="thread-card-preview">
        {lastTurn ? `${TURN_LABELS[lastTurn.kind]}: ${lastTurn.text}` : "No messages yet"}
      </p>
      <span className="thread-card-status">
        {status === "working" && <span className="status-dot" />}
        {STATUS_LABELS[status]}
      </span>
    </div>
  );
}

function ThreadView({
  client,
  onBack,
  onClose,
}: {
  client: ThreadClient;
  onBack: () => void;
  onClose: () => void;
}) {
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const [input, setInput] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [state.turns.length]);

  function toggleCollapsed(turnId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) {
        next.delete(turnId);
      } else {
        next.add(turnId);
      }
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || state.isSubmitting) return;
    setInput("");
    await client.sendMessage(text);
  }

  return (
    <div className="app-shell">
      <header className="app-header thread-view-header">
        <button type="button" className="back-button" onClick={onBack}>
          ← All sessions
        </button>
        <h1>{deriveLabel(state.turns)}</h1>
        <button type="button" className="close-thread-button" onClick={onClose}>
          Close session
        </button>
      </header>

      <div className="turn-stream" ref={streamRef}>
        {state.turns.length === 0 && (
          <p className="turn-stream-empty">Say something to get started.</p>
        )}
        {state.turns.map((turn) => (
          <TurnBlock
            key={turn.id}
            turn={turn}
            surface={turn.surfaceId ? state.surfacesById.get(turn.surfaceId) : undefined}
            isCollapsed={collapsed.has(turn.id)}
            onToggle={() => toggleCollapsed(turn.id)}
          />
        ))}
      </div>

      <form className="input-bar" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder='e.g. "compliance_check: does this comply?"'
          disabled={state.isSubmitting}
        />
        <button type="submit" disabled={state.isSubmitting || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

function TurnBlock({
  turn,
  surface,
  isCollapsed,
  onToggle,
}: {
  turn: Turn;
  surface: A2uiSurfaceModel | undefined;
  isCollapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <section className="turn-block" data-kind={turn.kind}>
      <button type="button" className="turn-header" onClick={onToggle}>
        <span className="turn-kind">{TURN_LABELS[turn.kind]}</span>
        <span className="turn-timestamp">{formatTime(turn.timestamp)}</span>
        <span className="turn-collapse-indicator">{isCollapsed ? "+" : "-"}</span>
      </button>
      {!isCollapsed && (
        <div className="turn-body">
          <p className="turn-text">{turn.text}</p>
          {surface && (
            <div className="turn-surface">
              <A2uiSurface surface={surface} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
