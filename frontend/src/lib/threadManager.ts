// Registry of ThreadClient instances -- the multi-thread layer on top
// of lib/agui.ts's per-thread client. Purely a frontend concept: the
// backend needs no changes to support more than one concurrent thread
// (see createThreadClient's docstring). Threads are in-memory only for
// this iteration -- closing a thread or reloading the page loses it,
// same "local-dev, not persisted" scope as everything else in
// docs/WEB_CHAT_APP.md.
import { createThreadClient, type ThreadClient } from "./agui";

export interface ThreadManager {
  createThread: () => string;
  closeThread: (id: string) => void;
  getThread: (id: string) => ThreadClient | undefined;
  getThreadIds: () => string[];
  subscribe: (listener: () => void) => () => void;
}

export function createThreadManager(runsUrl: string): ThreadManager {
  const clients = new Map<string, ThreadClient>();
  // Newest first -- a freshly created thread should appear at the top
  // of the grid without the user having to scroll for it.
  let order: string[] = [];
  const listeners = new Set<() => void>();

  function notify(): void {
    listeners.forEach((listener) => listener());
  }

  function createThread(): string {
    const id = crypto.randomUUID();
    clients.set(id, createThreadClient(runsUrl, id));
    order = [id, ...order];
    notify();
    return id;
  }

  function closeThread(id: string): void {
    clients.delete(id);
    order = order.filter((threadId) => threadId !== id);
    notify();
  }

  return {
    createThread,
    closeThread,
    getThread: (id: string) => clients.get(id),
    getThreadIds: () => order,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
