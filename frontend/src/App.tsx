import { useMemo, useState, useSyncExternalStore } from "react";
import { createPlatformOpsClient, A2uiSurface } from "./lib/agui";

// createPlatformOpsClient owns log/isSubmitting/surfaces as one external
// store (both text-send and A2UI button clicks need to share the same
// in-flight guard, and button clicks happen outside React's own event
// handling via MessageProcessor's actionHandler) -- useSyncExternalStore
// is the correct way to subscribe a component to state that lives
// outside React.
export default function App() {
  const client = useMemo(() => createPlatformOpsClient("/runs"), []);
  const state = useSyncExternalStore(client.subscribe, client.getState);
  const [input, setInput] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || state.isSubmitting) return;
    setInput("");
    await client.sendMessage(text);
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>PlatformOps</h1>

      <div
        style={{
          minHeight: 120,
          maxHeight: 320,
          overflowY: "auto",
          border: "1px solid #ccc",
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        {state.log.length === 0 && (
          <p style={{ color: "#888" }}>Say something to get started.</p>
        )}
        {state.log.map((entry) => (
          <p
            key={entry.id}
            style={{
              color: entry.kind === "error" ? "#c00" : entry.kind === "user" ? "#000" : "#555",
              fontStyle: entry.kind === "result" ? "italic" : "normal",
            }}
          >
            <strong>
              {entry.kind === "user" ? "you: " : entry.kind === "error" ? "error: " : "result: "}
            </strong>
            {entry.text}
          </p>
        ))}
      </div>

      <div style={{ border: "1px solid #ccc", padding: "1rem", marginBottom: "1rem" }}>
        {state.surfaces.length === 0 && (
          <p style={{ color: "#888" }}>No pending question right now.</p>
        )}
        {state.surfaces.map((surface) => (
          <A2uiSurface key={surface.id} surface={surface} />
        ))}
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder='e.g. "compliance_check: does this comply?"'
          disabled={state.isSubmitting}
          style={{ flex: 1, padding: "0.5rem" }}
        />
        <button type="submit" disabled={state.isSubmitting || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
