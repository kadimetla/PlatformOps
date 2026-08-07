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
npm run dev      # Vite dev server, port 5173, proxies /runs and /info
                  # to transports/http.py on port 8000 (see vite.config.ts)
npm run build     # tsc -b && vite build -- verified clean 2026-08-07
                  # against the real installed @ag-ui/client/@a2ui/react/
                  # @a2ui/web_core packages
```

Requires `transports/http.py` running separately (`uvicorn
transports.http:app`) and a session from `platformops login` — this
milestone has no browser-based login, see `docs/WEB_CHAT_APP.md`'s
Session Handling section.
