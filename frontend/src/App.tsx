import { useMemo, useState, useSyncExternalStore } from "react";
import ActiveSurfaceSlot from "./components/a2ui/ActiveSurfaceSlot";
import { createThreadManager } from "./lib/threadManager";
import type { PlatformOpsClientState, ThreadClient } from "./lib/agui";
import { STATUS_LABELS, TURN_LABELS, deriveLabel, deriveStatus } from "./lib/sessionPresentation";
import FloatingSessionPanel from "./FloatingSessionPanel";
import "./App.css";

// createThreadManager (and each ThreadClient it creates) owns state
// outside React, so every level here reads it via useSyncExternalStore
// rather than mirroring it into React state -- see lib/agui.ts's and
// lib/threadManager.ts's module docstrings for why.
//
// The app is split into three stable regions: sessions on the side,
// generated A2UI/work results in the middle, and the selected session's
// chat docked at the bottom. Workflow-specific UI belongs in generated
// A2UI surfaces, not in React components here.
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
      </header>
      <div className="app-body">
        <aside className="session-sidebar">
          <div className="session-sidebar-header">
            <span>Sessions</span>
            <button type="button" className="new-thread-button" onClick={openNewThread}>
              + New
            </button>
          </div>
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
                  isSelected={selectedId === id}
                  onOpen={() => setSelectedId(id)}
                  onClose={() => closeThread(id)}
                />
              ) : null;
            })}
          </div>
        </aside>

        <main className="workspace-shell">
          <div className="workspace-content">
            {selectedClient ? (
              <WorkspaceActiveSurface client={selectedClient} />
            ) : (
              <div className="workspace-empty">
                <h2>Select or start a session</h2>
                <p>Generated workflow UI and results will appear here.</p>
              </div>
            )}
          </div>

          {selectedClient && (
            <FloatingSessionPanel
              key={selectedClient.id}
              client={selectedClient}
              onClose={() => setSelectedId(null)}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function activeSurfaceFromState(state: PlatformOpsClientState) {
  const latestTurn = state.turns[state.turns.length - 1];
  if (!latestTurn || !latestTurn.surfaceId) {
    return undefined;
  }
  return state.surfacesById.get(latestTurn.surfaceId);
}

function WorkspaceActiveSurface({ client }: { client: ThreadClient }) {
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const surface = activeSurfaceFromState(state);

  if (!surface) return null;

  return <ActiveSurfaceSlot surface={surface} />;
}

function ThreadCard({
  client,
  isSelected,
  onOpen,
  onClose,
}: {
  client: ThreadClient;
  isSelected: boolean;
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
      data-selected={isSelected || undefined}
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
