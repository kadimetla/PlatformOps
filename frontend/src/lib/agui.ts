// Thin wrapper around @ag-ui/client's HttpAgent + @a2ui/web_core's
// MessageProcessor, catalog and component implementations coming from
// @a2ui/react's own basicCatalog export (per @a2ui/react's own README
// quickstart: MessageProcessor is instantiated with @a2ui/react/v0_9's
// basicCatalog, not a separate web_core one -- the React package's
// catalog is what binds basicCatalog's schemas to real React
// components).
//
// Both libraries already implement the protocol-state rules
// transports/remote_tui.py's RemoteTUIState/observe_agui_event
// hand-built for a future client: HttpAgent tracks
// agent.pendingInterrupts itself (populated on a RUN_FINISHED interrupt
// outcome, cleared on the next successful run), so there is no second
// interrupt-tracking layer to write here.
//
// interaction/a2ui.py sets each A2UI surface's id to the HITLEvent's
// event_id, which is also the AG-UI Interrupt's id (interaction/agui.py's
// hitl_event_to_interrupt sets "id": event.event_id) -- so a Button's
// action name (set to that same surface_id in interaction/a2ui.py) is
// always exactly the interrupt id to resume. That equality is what lets
// handleAction below look the interrupt up directly, with no separate
// id-mapping table.
//
// State (log/isSubmitting/surfaces) is owned here, not in App.tsx, as a
// small external store consumed via React's useSyncExternalStore --
// both sendMessage (text input) and handleAction (A2UI button clicks,
// invoked by MessageProcessor's actionHandler, outside React's own event
// handling) need to share one in-flight guard, which only works if one
// place owns the flag both paths check.
import {
  HttpAgent,
  buildResumeArray,
  type AgentSubscriber,
  type CustomEvent as AGUICustomEvent,
} from "@ag-ui/client";
import type { ComponentProps } from "react";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import type { A2uiClientAction, A2uiMessage } from "@a2ui/web_core/v0_9";
import { basicCatalog, A2uiSurface } from "@a2ui/react/v0_9";

export { A2uiSurface };

// @a2ui/react doesn't export ReactComponentImplementation (the type
// SurfaceModel is parametrized with) directly -- derive the exact
// surface type A2uiSurface itself expects from its own prop type,
// rather than guessing at re-declaring the generic by hand.
type A2uiSurfaceModel = ComponentProps<typeof A2uiSurface>["surface"];

export interface LogEntry {
  id: string;
  kind: "user" | "result" | "error";
  text: string;
}

export interface PlatformOpsClientState {
  log: LogEntry[];
  isSubmitting: boolean;
  surfaces: A2uiSurfaceModel[];
}

export function createPlatformOpsClient(runsUrl: string) {
  const agent = new HttpAgent({ url: runsUrl });
  const processor = new MessageProcessor([basicCatalog], handleAction);

  let state: PlatformOpsClientState = { log: [], isSubmitting: false, surfaces: [] };
  const listeners = new Set<() => void>();

  function notify(): void {
    listeners.forEach((listener) => listener());
  }

  function setState(patch: Partial<PlatformOpsClientState>): void {
    state = { ...state, ...patch };
    notify();
  }

  function appendLog(entry: Omit<LogEntry, "id">): void {
    setState({ log: [...state.log, { id: crypto.randomUUID(), ...entry }] });
  }

  function syncSurfaces(): void {
    setState({ surfaces: Array.from(processor.model.surfacesMap.values()) });
  }
  processor.onSurfaceCreated(syncSurfaces);
  processor.onSurfaceDeleted(syncSurfaces);

  function handleCustomEvent({ event }: { event: AGUICustomEvent }): void {
    if (!event.name.startsWith("a2ui.")) return;
    processor.processMessages([event.value as A2uiMessage]);
  }

  function subscriber(): AgentSubscriber {
    return {
      onCustomEvent: handleCustomEvent,
      onRunFinishedEvent: (params) => {
        if (params.outcome === "success") {
          appendLog({ kind: "result", text: JSON.stringify(params.result ?? {}) });
        }
        // interrupt outcome: the A2UI surface already renders the
        // question/choices -- no separate transcript line needed.
      },
    };
  }

  async function runAndLog(run: (s: AgentSubscriber) => Promise<unknown>): Promise<void> {
    setState({ isSubmitting: true });
    try {
      await run(subscriber());
    } catch (err) {
      appendLog({ kind: "error", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setState({ isSubmitting: false });
    }
  }

  function handleAction(action: A2uiClientAction): void {
    if (state.isSubmitting) {
      // Duplicate/rapid click while a prior action or message is still
      // in flight -- explicit no-op, not a silently queued retry.
      return;
    }
    const interruptId = action.name;
    const interrupt = agent.pendingInterrupts.find((i) => i.id === interruptId);
    if (!interrupt) {
      // Not a resumable action (or already resumed) -- ignore, matching
      // AG-UI's own "every open interrupt must be addressed" rule: a
      // stale click after resume has nothing left to resume.
      return;
    }
    const resume = buildResumeArray([interrupt], {
      [interruptId]: { status: "resolved", payload: action.context },
    });
    void runAndLog((s) => agent.runAgent({ resume }, s));
  }

  async function sendMessage(text: string): Promise<void> {
    if (state.isSubmitting) return;
    appendLog({ kind: "user", text });
    agent.messages.push({ id: crypto.randomUUID(), role: "user", content: text });
    await runAndLog((s) => agent.runAgent({}, s));
  }

  return {
    getState: () => state,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    sendMessage,
  };
}
