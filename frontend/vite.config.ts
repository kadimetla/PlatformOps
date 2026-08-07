import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend is transports/http.py (FastAPI), default dev port 8000 -- see
// docs/WEB_CHAT_APP.md. Proxy /runs and /info so the browser can call
// same-origin paths without a CORS setup for this first slice.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/runs": "http://localhost:8000",
      "/info": "http://localhost:8000",
    },
  },
});
