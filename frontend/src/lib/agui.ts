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
// State is a Turn[] -- one entry per conversational step (matching the
// event kinds workflows/harness already define: intake started,
// clarification required, route resolved, plus client-side user/error
// turns), each carrying its own A2UI surface if it created one. This is
// the TUI-style model docs/INTERACTION_LAYER.md already justified
// ("mostly linear progress, occasionally pausing for a structured
// choice") -- one scrolling stream, not a chat log separate from a
// content panel. Owned here, not in App.tsx, as a small external store
// consumed via React's useSyncExternalStore -- both sendMessage (text
// input) and handleAction (A2UI button clicks, invoked by
// MessageProcessor's actionHandler, outside React's own event handling)
// need to share one in-flight guard, which only works if one place owns
// the flag both paths check.
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
import { browserFetch } from "./browserSession";

export { A2uiSurface };

// @a2ui/react doesn't export ReactComponentImplementation (the type
// SurfaceModel is parametrized with) directly -- derive the exact
// surface type A2uiSurface itself expects from its own prop type,
// rather than guessing at re-declaring the generic by hand.
export type A2uiSurfaceModel = ComponentProps<typeof A2uiSurface>["surface"];

export type TurnKind =
  | "user_message"
  | "clarification_required"
  | "approval_required"
  | "route_resolved"
  | "error";

export interface Turn {
  id: string;
  kind: TurnKind;
  timestamp: string;
  text: string;
  surfaceId?: string;
}

export interface PlatformOpsClientState {
  turns: Turn[];
  isSubmitting: boolean;
  surfacesById: Map<string, A2uiSurfaceModel>;
}

function surfaceIdFromMessage(message: A2uiMessage): string | undefined {
  if ("createSurface" in message) return message.createSurface.surfaceId;
  if ("updateComponents" in message) return message.updateComponents.surfaceId;
  return undefined;
}

function summarizeResult(result: unknown): string {
  if (result && typeof result === "object" && "intent" in result) {
    const r = result as Record<string, unknown>;
    return r.route
      ? `Routed to ${String(r.route)}`
      : `No route yet -- ${String(r.unsupported_reason ?? "unsupported")}`;
  }
  return "Result received";
}

// @ag-ui/client's HttpAgent throws Error(`HTTP ${status}: ${body}`) on a
// non-2xx response, with .status and .payload (parsed JSON body, when
// the response is JSON) attached as extra properties -- verified
// directly against the installed package
// (node_modules/@ag-ui/client/dist/index.js). transports/http.py's
// HTTPExceptions always carry a clean, actionable `detail` string (e.g.
// "no session -- run 'platformops login' first"); prefer that over the
// raw stringified-JSON message so a 401 reads as guidance, not a crash.
function describeAgentError(err: unknown): string {
  if (err && typeof err === "object" && "payload" in err) {
    const payload = (err as { payload?: unknown }).payload;
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail) return detail;
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export interface ThreadClient {
  id: string;
  getState: () => PlatformOpsClientState;
  subscribe: (listener: () => void) => () => void;
  sendMessage: (text: string, scope: string) => Promise<void>;
}

function buildForwardedProps(scope: string): Record<string, unknown> {
  const trimmed = scope.trim();
  return trimmed ? { scope: trimmed } : {};
}

/** One HttpAgent + MessageProcessor + state store per thread -- threadId
 * is AG-UI's own thread identifier and harness/core.py's request_id, so
 * each ThreadClient is a fully independent conversation as far as the
 * backend is concerned (PlatformOpsHarness._pending_intake is already
 * keyed per request_id; nothing backend-side needs to change to support
 * more than one of these at once). See lib/threadManager.ts for the
 * multi-thread registry this composes into.
 */
export function createThreadClient(runsUrl: string, threadId: string): ThreadClient {
  // browserFetch adds same-origin credentials and the in-memory CSRF proof.
  const agent = new HttpAgent({ url: runsUrl, threadId, fetch: browserFetch });
  const commandsUrl = new URL("commands", new URL(runsUrl, window.location.href)).toString();
  const processor = new MessageProcessor([basicCatalog], handleAction);

  let state: PlatformOpsClientState = {
    turns: [],
    isSubmitting: false,
    surfacesById: new Map(),
  };
  const listeners = new Set<() => void>();

  function notify(): void {
    listeners.forEach((listener) => listener());
  }

  function setState(patch: Partial<PlatformOpsClientState>): void {
    state = { ...state, ...patch };
    notify();
  }

  function appendTurn(entry: Omit<Turn, "id" | "timestamp">): void {
    const turn: Turn = { id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...entry };
    setState({ turns: [...state.turns, turn] });
  }

  function syncSurfaces(): void {
    setState({ surfacesById: new Map(processor.model.surfacesMap) });
  }
  processor.onSurfaceCreated(syncSurfaces);
  processor.onSurfaceDeleted(syncSurfaces);

  function handleAction(action: A2uiClientAction): void {
    if (state.isSubmitting) {
      // Duplicate/rapid click while a prior action or message is still
      // in flight -- explicit no-op, not a silently queued retry.
      return;
    }
    if (action.name === "guest.login.submit") {
      const email = action.context?.email;
      if (typeof email !== "string" || !email.trim()) {
        appendTurn({ kind: "error", text: "Enter an email address before requesting a sign-in link." });
        return;
      }
      // This is the one public typed action. The server accepts only the
      // email through the existing registration handler; no browser session,
      // target, organization, or authority field is supplied.
      void runAndLog((s) => runCommand("/login", { email }, s));
      return;
    }
    if (action.name.startsWith("/")) {
      // A typed control-plane action (e.g. onboarding-review Approve).
      // Only the command name and the surface-reported context are sent;
      // the server derives the principal from the session cookie and
      // rejects authority-bearing fields.
      void runAndLog((s) => runCommand(action.name, action.context ?? {}, s));
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

  // POST /commands answers with the same AG-UI SSE framing as /runs, but
  // it is not an agent run (no thread state or interrupts), so it is read
  // directly: a2ui.* CUSTOM events feed the processor, RUN_FINISHED ends it.
  async function runCommand(
    command: string,
    payload: Record<string, unknown>,
    subscriber?: AgentSubscriber,
  ): Promise<void> {
    const response = await browserFetch(commandsUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        threadId,
        runId: crypto.randomUUID(),
        command,
        payload,
      }),
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string" && body.detail) detail = body.detail;
      } catch {
        // non-JSON error body -- keep the status line
      }
      throw new Error(detail);
    }
    const text = await response.text();
    for (const line of text.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const event = JSON.parse(line.slice(6)) as {
        type: string;
        name?: string;
        value?: unknown;
        result?: unknown;
      };
      if (event.type === "CUSTOM" && event.name?.startsWith("a2ui.")) {
        subscriber?.onCustomEvent?.({ event } as never);
      } else if (event.type === "RUN_FINISHED") {
        subscriber?.onRunFinishedEvent?.({ outcome: "success", result: event.result } as never);
      }
    }
  }

  async function runAndLog(run: (s: AgentSubscriber) => Promise<unknown>): Promise<void> {
    setState({ isSubmitting: true });
    // Scoped to this one call: at most one surface is created per run
    // (interaction/a2ui.py's design), so the last surfaceId observed
    // during this run is the one to attach to whichever turn its
    // RUN_FINISHED outcome produces.
    let lastSurfaceId: string | undefined;
    const subscriber: AgentSubscriber = {
      onCustomEvent: ({ event }: { event: AGUICustomEvent }) => {
        if (!event.name.startsWith("a2ui.")) return;
        const message = event.value as A2uiMessage;
        lastSurfaceId = surfaceIdFromMessage(message) ?? lastSurfaceId;
        processor.processMessages([message]);
      },
      onRunFinishedEvent: (params) => {
        if (params.outcome === "success") {
          appendTurn({
            kind: "route_resolved",
            text: summarizeResult(params.result),
            surfaceId: lastSurfaceId,
          });
          return;
        }
        const reason = params.interrupts[0]?.reason;
        appendTurn({
          kind: reason === "approval.required" ? "approval_required" : "clarification_required",
          text: "Input needed",
          surfaceId: lastSurfaceId,
        });
      },
    };
    try {
      await run(subscriber);
    } catch (err) {
      appendTurn({ kind: "error", text: describeAgentError(err) });
    } finally {
      setState({ isSubmitting: false });
    }
  }

  async function sendMessage(text: string, scope: string): Promise<void> {
    if (state.isSubmitting) return;
    appendTurn({ kind: "user_message", text });
    if (agent.pendingInterrupts.length === 1) {
      const interrupt = agent.pendingInterrupts[0];
      const resume = buildResumeArray([interrupt], {
        [interrupt.id]: { status: "resolved", payload: { value: text } },
      });
      await runAndLog((s) => agent.runAgent({ resume }, s));
      return;
    }
    if (agent.pendingInterrupts.length > 1) {
      appendTurn({
        kind: "error",
        text: "Multiple pending inputs are open. Resolve them from the cards before sending a new message.",
      });
      return;
    }
    agent.messages.push({ id: crypto.randomUUID(), role: "user", content: text });
    await runAndLog((s) => agent.runAgent({ forwardedProps: buildForwardedProps(scope) }, s));
  }

  return {
    id: threadId,
    getState: () => state,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    sendMessage,
  };
}
