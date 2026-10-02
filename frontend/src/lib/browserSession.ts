// Browser-session transport for the same-origin AG-UI backend
// (transports/http.py). The session itself is an HttpOnly cookie the
// browser attaches; script never sees it. The CSRF proof is the only
// secret script holds, and it lives in this module variable ONLY --
// never localStorage/sessionStorage/IndexedDB/cookies/URL -- so a page
// reload drops it and the user must re-establish the session. Do not
// add persistence here (openspec: unify-browser-agui-control-plane,
// design "CSRF proof ... only in browser memory").

const CSRF_HEADER = "x-csrf-proof";

let csrfProof: string | null = null;

export function setCsrfProof(proof: string): void {
  csrfProof = proof;
}

export function clearCsrfProof(): void {
  csrfProof = null;
}

export function hasCsrfProof(): boolean {
  return csrfProof !== null;
}

/** fetch with same-origin credentials and the in-memory CSRF proof.
 * Read at call time, so a proof set after an agent is constructed still
 * applies. The browser adds Origin itself. */
export function browserFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (csrfProof !== null) headers.set(CSRF_HEADER, csrfProof);
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}
