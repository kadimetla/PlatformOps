// Minimal hand-rolled drag mechanics (position only, no resize) for the
// floating session panel -- no react-rnd or similar dependency, since
// "reposition one panel" doesn't need a full windowing library. Same
// preference for the smaller dependency-free option already used
// elsewhere in this app (@ag-ui/client directly instead of CopilotKit's
// Runtime).
//
// Position is a UI display preference, not domain data -- persisted to
// localStorage, not the backend. Uses an isDragging + effect pattern
// (not raw addEventListener calls inside the mousedown handler) so the
// listener added and the listener removed are always the same closure
// -- the classic stale-closure bug with hand-rolled drag code.
import { useCallback, useEffect, useRef, useState } from "react";
import { readStoredJSON, writeStoredJSON } from "./storage";

export interface Position {
  x: number;
  y: number;
}

interface UseDraggableOptions {
  storageKey: string;
  defaultPosition: () => Position;
  size: { width: number; height: number };
}

function loadPosition(storageKey: string): Position | null {
  const parsed = readStoredJSON<unknown>(storageKey, null);
  if (typeof parsed !== "object" || parsed === null) return null;

  const record = parsed as Record<string, unknown>;
  if (typeof record.x === "number" && typeof record.y === "number") {
    return { x: record.x, y: record.y };
  }
  return null;
}

function savePosition(storageKey: string, position: Position): void {
  writeStoredJSON(storageKey, position);
}

export function useDraggable({ storageKey, defaultPosition, size }: UseDraggableOptions) {
  const [position, setPosition] = useState<Position>(
    () => loadPosition(storageKey) ?? defaultPosition()
  );
  const [isDragging, setIsDragging] = useState(false);
  const dragOrigin = useRef<{ mouse: Position; panel: Position } | null>(null);

  const clamp = useCallback(
    (pos: Position): Position => {
      const maxX = Math.max(window.innerWidth - size.width, 0);
      const maxY = Math.max(window.innerHeight - size.height, 0);
      return { x: Math.min(Math.max(pos.x, 0), maxX), y: Math.min(Math.max(pos.y, 0), maxY) };
    },
    [size.width, size.height]
  );

  const onDragHandleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      dragOrigin.current = { mouse: { x: event.clientX, y: event.clientY }, panel: position };
      setIsDragging(true);
    },
    [position]
  );

  useEffect(() => {
    if (!isDragging) return;

    function onMouseMove(event: MouseEvent) {
      if (!dragOrigin.current) return;
      const dx = event.clientX - dragOrigin.current.mouse.x;
      const dy = event.clientY - dragOrigin.current.mouse.y;
      setPosition(clamp({ x: dragOrigin.current.panel.x + dx, y: dragOrigin.current.panel.y + dy }));
    }

    function onMouseUp() {
      setIsDragging(false);
      dragOrigin.current = null;
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [isDragging, clamp]);

  useEffect(() => {
    function reclampPosition() {
      setPosition((current) => clamp(current));
    }

    reclampPosition();
    window.addEventListener("resize", reclampPosition);
    return () => window.removeEventListener("resize", reclampPosition);
  }, [clamp]);

  // Persist once a drag ends (isDragging flips back to false), not on
  // every intermediate mousemove.
  useEffect(() => {
    if (!isDragging) savePosition(storageKey, position);
  }, [isDragging, storageKey, position]);

  return { position, isDragging, onDragHandleMouseDown };
}
