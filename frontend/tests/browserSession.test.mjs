// Run: node --test tests/browserSession.test.mjs   (Node >=22.18 strips TS types natively)
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, test } from "node:test";

import { browserFetch, clearCsrfProof, setCsrfProof } from "../src/lib/browserSession.ts";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  clearCsrfProof();
});

function captureFetch() {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ input, init });
    return new Response("");
  };
  return calls;
}

test("sends same-origin credentials and the in-memory CSRF proof", async () => {
  const calls = captureFetch();
  setCsrfProof("proof-123");

  await browserFetch("/runs", { method: "POST", headers: { "Content-Type": "application/json" } });

  const { init } = calls[0];
  assert.equal(init.credentials, "same-origin");
  assert.equal(init.headers.get("x-csrf-proof"), "proof-123");
  assert.equal(init.headers.get("content-type"), "application/json");
});

test("omits the CSRF header once the proof is cleared", async () => {
  const calls = captureFetch();
  setCsrfProof("proof-123");
  clearCsrfProof();

  await browserFetch("/runs", { method: "POST" });

  assert.equal(calls[0].init.headers.has("x-csrf-proof"), false);
});

test("a caller cannot be sent with include/omit credentials", async () => {
  const calls = captureFetch();

  await browserFetch("/runs", { credentials: "include" });

  assert.equal(calls[0].init.credentials, "same-origin");
});

test("no source file persists the CSRF proof or a JWT to browser storage", () => {
  const dir = new URL("../src/", import.meta.url).pathname;
  const files = [];
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e.name)) files.push(p);
    }
  };
  walk(dir);
  for (const file of files) {
    const src = readFileSync(file, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    const usesStorage = /(localStorage|sessionStorage|indexedDB|document\.cookie)/.test(src);
    if (usesStorage) {
      assert.doesNotMatch(src, /csrf|jwt|platformops_session/i, `${file} stores auth material`);
    }
  }
});
