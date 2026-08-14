import { useMemo, useState, useSyncExternalStore } from "react";
import { createThreadManager } from "./lib/threadManager";
import type { ThreadClient } from "./lib/agui";
import { STATUS_LABELS, TURN_LABELS, deriveLabel, deriveStatus } from "./lib/sessionPresentation";
import FloatingSessionPanel from "./FloatingSessionPanel";
import "./App.css";

// createThreadManager (and each ThreadClient it creates) owns state
// outside React, so every level here reads it via useSyncExternalStore
// rather than mirroring it into React state -- see lib/agui.ts's and
// lib/threadManager.ts's module docstrings for why.
//
// The grid renders unconditionally; the floating panel layers on top of
// it when a session is selected, rather than replacing it -- unlike the
// old full-page ThreadView, the grid stays visible and interactive
// (other sessions' status cards keep updating) while you work one
// session in the panel.
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

      {selectedClient && (
        <FloatingSessionPanel
          key={selectedClient.id}
          client={selectedClient}
          onClose={() => setSelectedId(null)}
        />
      )}
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
    <div
      className="thread-card"
      data-status={status}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="thread-card-header">
        <span className="thread-card-label">{label}</span>
        <button
          type="button"
          className="thread-card-close"
          onClick={(event) => {
            event.stopPropagation();
            onClose();
          }}
          aria-label="Delete session"
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
