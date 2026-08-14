import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { A2uiSurface, type A2uiSurfaceModel, type Turn, type ThreadClient } from "./lib/agui";
import { useDraggable } from "./lib/useDraggable";
import { TURN_LABELS, deriveLabel, formatTime } from "./lib/sessionPresentation";
import { readStoredJSON, writeStoredJSON } from "./lib/storage";

const PANEL_WIDTH = 400;
const PANEL_HEIGHT = 560;
const EDGE_MARGIN = 24;
const POSITION_STORAGE_KEY = "platformops.floatingChatPosition";
const PINNED_STORAGE_KEY = "platformops.floatingChatPinned";

function defaultPosition() {
  // Bottom-right corner -- the common floating-chat-widget convention
  // (Intercom etc.), adjustable from there via drag.
  return {
    x: Math.max(window.innerWidth - PANEL_WIDTH - EDGE_MARGIN, 0),
    y: Math.max(window.innerHeight - PANEL_HEIGHT - EDGE_MARGIN, 0),
  };
}

function loadPinned(): boolean {
  return readStoredJSON<unknown>(PINNED_STORAGE_KEY, false) === true;
}

function savePinned(pinned: boolean): void {
  writeStoredJSON(PINNED_STORAGE_KEY, pinned);
}

// The grid (App.tsx) stays visible and interactive behind this panel --
// unlike the old full-page ThreadView, there's no "back to grid" state
// to navigate out of, so the only exit affordance is Close.
export default function FloatingSessionPanel({
  client,
  onClose,
}: {
  client: ThreadClient;
  onClose: () => void;
}) {
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const [input, setInput] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [pinned, setPinned] = useState(loadPinned);
  const streamRef = useRef<HTMLDivElement>(null);
  const { position, isDragging, onDragHandleMouseDown } = useDraggable({
    storageKey: POSITION_STORAGE_KEY,
    defaultPosition,
    size: { width: PANEL_WIDTH, height: PANEL_HEIGHT },
  });

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

  function togglePinned() {
    setPinned((current) => {
      const next = !current;
      savePinned(next);
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
    <div
      className="floating-panel"
      data-pinned={pinned || undefined}
      data-dragging={isDragging || undefined}
      style={{ left: position.x, top: position.y }}
    >
      <div className="floating-panel-header">
        <button
          type="button"
          className="floating-panel-drag-handle"
          onMouseDown={pinned ? undefined : onDragHandleMouseDown}
          aria-label={pinned ? "Chat panel is pinned" : "Move chat panel"}
          title={pinned ? "Pinned" : "Drag to move"}
        >
          <span className="floating-panel-grip" aria-hidden="true" />
        </button>
        <span className="floating-panel-label">{deriveLabel(state.turns)}</span>
        <button
          type="button"
          className="floating-panel-action"
          onClick={togglePinned}
          aria-pressed={pinned}
          title={pinned ? "Unpin chat panel" : "Pin chat panel"}
        >
          {pinned ? "Unpin" : "Pin"}
        </button>
        <button type="button" className="floating-panel-close" onClick={onClose} aria-label="Hide panel" title="Hide panel">
          ×
        </button>
      </div>

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
