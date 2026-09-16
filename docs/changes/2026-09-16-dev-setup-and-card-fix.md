# Changes: dev setup + clarification card layout fix

**Date:** 2026-09-16
**Branch:** fix/card-inline-layout
**PR:** #2
**Issue:** #1

---

## Status

All changes in this document are real and committed. None are design-only.

---

## What changed and why

### 1. `.env.example` — added `PLATFORMOPS_MODEL`

**File:** `.env.example`

`PLATFORMOPS_MODEL` was missing from `.env.example` entirely. The variable exists in
`transports/http.py` and controls which LLM the server uses at startup, but anyone
copying `.env.example` to get started had no idea it existed.

Additionally, `gemini/gemini-2.5-flash` (the value that was in the real `.env`)
returned HTTP 404 from Google's API — that model is deprecated. Same for
`gemini/gemini-2.0-flash`. The working model as of 2026-09-16 is `gemini/gemini-3.6-flash`.

**Added:**
```
PLATFORMOPS_MODEL=gemini/gemini-3.6-flash
```

With a comment explaining the Gemini and OpenAI options.

---

### 2. `frontend/src/FloatingSessionPanel.tsx` — card moved inline

**File:** `frontend/src/FloatingSessionPanel.tsx`

**Problem:** When the backend returns a clarification question, `ActiveSurfaceSlot`
was rendered *outside* the `.turn-stream` scroll container as a sibling element.
Combined with the CSS below, it became a floating overlay covering all previous turns.
The active attention turn was also filtered *out* of the stream while the card was
showing, so the user's own message disappeared.

**Fix:** Move `ActiveSurfaceSlot` inside the `.turn-stream` div, wrapped in
`.inline-surface-slot`. Remove the filter that hid the active turn.

Before:
```tsx
<div className="turn-stream">
  {turns.filter(t => t.id !== activeAttentionTurn?.id).map(...)}
</div>
{activeSurface && <ActiveSurfaceSlot surface={activeSurface} />}
```

After:
```tsx
<div className="turn-stream">
  {turns.map(...)}
  {activeSurface && (
    <div className="inline-surface-slot">
      <ActiveSurfaceSlot surface={activeSurface} />
    </div>
  )}
</div>
```

---

### 3. `frontend/src/App.css` — removed absolute overlay styling

**File:** `frontend/src/App.css`

**Problem:** `.active-surface-slot` used `position: absolute; inset: 0.75rem; z-index: 2`
which made it fill the entire `conversation-region` (which is `position: relative`),
covering the turn stream behind it. `pointer-events: none` on the slot with
`pointer-events: auto` on the inner surface was needed to let clicks through —
a sign the overlay approach was working against the layout.

**Fix:** Replace with plain block layout. Add `.inline-surface-slot` with padding
so the card sits naturally in the turn stream flow.

Before:
```css
.active-surface-slot {
  position: absolute;
  inset: 0.75rem;
  display: grid;
  place-items: center;
  padding: 0.75rem;
  pointer-events: none;
  z-index: 2;
}
.active-surface-slot .a2ui-surface {
  width: min(34rem, 100%);
  max-height: 100%;
  overflow-y: auto;
  pointer-events: auto;
}
```

After:
```css
.inline-surface-slot {
  padding: 0.5rem 0;
}
.active-surface-slot {
  width: 100%;
}
.active-surface-slot .a2ui-surface {
  width: 100%;
}
```

---

## Not committed (gitignored)

### `.platformops/session.json` — dev session bypass

Created for local development. The FastAPI server (`transports/http.py`) reads a
session file on every request. Without it every request returns 401.

For local dev without running Authentik, create this file at
`.platformops/session.json`:

```json
{
  "session_id": "dev-session-001",
  "actor": {
    "user_id": "dev-user",
    "email": "dev@example.com",
    "execution_grants": [
      {
        "scope": {"org": "aiq", "bu": "it", "project": "invoices", "workspace": "dev"},
        "provider": "aws",
        "capability": "apply_limited"
      }
    ],
    "approval_grants": [],
    "resolved_at": "2026-09-16T00:00:00Z"
  },
  "groups": [],
  "created_at": "2026-09-16T00:00:00Z",
  "expires_at": "2027-09-16T00:00:00Z"
}
```

The `execution_grants` entry is what allows the provision flow to pass the scope
and tenant policy checks. Without it:
- Missing `scope_hint.tenant.org_bu` → "tenant not authorized for this route"
- Scope present but no matching grant → "target not found or not accessible"

This file is gitignored (`.platformops/` in `.gitignore`). Do not commit it.

---

## How to run locally after these changes

```bash
# 1. Copy env and fill in your Google API key
cp .env.example .env
# edit .env: set GOOGLE_API_KEY=your_key

# 2. Create dev session
mkdir -p .platformops
# paste the session JSON above into .platformops/session.json

# 3. Start backend
uv run --env-file .env uvicorn transports.http:app --port 8000

# 4. Start frontend (separate terminal)
cd frontend && npm run dev

# 5. Open http://localhost:5173
# Set Target to: aiq:it/invoices/dev
# Send: I want to deploy my static site to AWS
```
