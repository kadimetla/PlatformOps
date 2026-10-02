# PlatformOps web chat frontend

Vite + React + TypeScript, talking AG-UI/SSE directly to
`transports/http.py` (`@ag-ui/client`'s `HttpAgent`, no CopilotKit
Runtime) and rendering A2UI surfaces via `@a2ui/react`'s built-in
`basicCatalog`. See `docs/WEB_CHAT_APP.md` for the full design and the
verified wire shapes this code depends on.

## Node version

Requires Node **>= 20.19** (`package.json`'s `engines` field enforces
this with a warning on `npm install`/`npm run build` if violated —
plain `npm` doesn't otherwise fail loudly on an old Node). Two ways to
get a matching Node without touching your system install:

- **Volta** (what this project was built with): `package.json` already
  has `"volta": {"node": "22.23.1", "npm": "11.12.0"}` pinned. If
  [Volta](https://volta.sh) is installed and its shims are on `PATH`,
  `node`/`npm` inside this directory resolve to that version
  automatically — no extra command needed.
- **nvm**: `nvm use` picks up `.nvmrc` (`22.23.1`) in this directory.

If neither is active, `node --version` will silently run whatever your
system default is — check that first if `npm run build` fails with a
Vite/engine-version error.

## Commands

```bash
npm install
npm run dev      # Vite dev server, port 5173, proxies /runs, /info and /commands
                  # to transports/http.py on port 8000 (see vite.config.ts)
npm run build     # tsc -b && vite build -- verified clean 2026-08-07
                  # against the real installed @ag-ui/client/@a2ui/react/
                  # @a2ui/web_core packages
```

Requires a backend built with `transports.http.create_app(...)` listening
on port 8000. *Corrected 2026-10-01:* there is no module-level `app`
(`uvicorn transports.http:app` no longer works) and no `platformops login`
file session; requests carry the HttpOnly session cookie plus an in-memory
`x-csrf-proof` (`src/lib/browserSession.ts`). The frontend has no
login-confirmation page yet, so nothing calls `setCsrfProof` and browser
calls 401 until one does. See `docs/WEB_CHAT_APP.md`'s Session Handling.

Dev proxy covers `/runs`, `/info`, and `/commands`. Tests:
`node --test tests/browserSession.test.mjs` (Node >= 22.18).
