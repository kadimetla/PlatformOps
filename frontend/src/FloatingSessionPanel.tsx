import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { A2uiSurface, type A2uiSurfaceModel, type Turn, type ThreadClient } from "./lib/agui";
import { TURN_LABELS, deriveLabel, formatTime } from "./lib/sessionPresentation";
import { readStoredJSON, writeStoredJSON } from "./lib/storage";

const TARGET_SCOPE_STORAGE_KEY = "platformops.targetScope";
const DEFAULT_TARGET_SCOPE = "aiq:it/invoices/dev";

function loadTargetScope(): string {
  const stored = readStoredJSON<unknown>(TARGET_SCOPE_STORAGE_KEY, DEFAULT_TARGET_SCOPE);
  return typeof stored === "string" && stored ? stored : DEFAULT_TARGET_SCOPE;
}

function isAttentionTurn(turn: Turn): boolean {
  return turn.kind === "clarification_required" || turn.kind === "approval_required";
}

// Docked chat/control panel for the selected session. Generated workflow
// UI is rendered in the workspace by App.tsx, not inside this transcript.
export default function FloatingSessionPanel({
  client,
  onClose,
}: {
  client: ThreadClient;
  onClose: () => void;
}) {
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const [input, setInput] = useState("");
  const [targetScope, setTargetScope] = useState(loadTargetScope);
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

  function updateTargetScope(value: string) {
    setTargetScope(value);
    writeStoredJSON(TARGET_SCOPE_STORAGE_KEY, value);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || state.isSubmitting) return;
    setInput("");
    await client.sendMessage(text, targetScope);
  }

  return (
    <div className="session-chat-panel">
      <div className="session-chat-header">
        <span className="session-chat-label">{deriveLabel(state.turns)}</span>
        <button type="button" className="session-chat-close" onClick={onClose} aria-label="Hide chat" title="Hide chat">
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

      <label className="scope-bar">
        <span>Target</span>
        <input
          value={targetScope}
          onChange={(event) => updateTargetScope(event.target.value)}
          placeholder="org:bu/project/workspace"
          disabled={state.isSubmitting}
        />
      </label>

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
          {surface && !isAttentionTurn(turn) && (
            <div className="turn-surface">
              <A2uiSurface surface={surface} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
