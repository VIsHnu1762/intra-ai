import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

function load(fetch) {
  const source = readFileSync(new URL("../src/lib/api/client.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
  } }).outputText;
  const mod = { exports: {} };
  let cleared = false;
  new Function("require", "module", "exports", "fetch", compiled)(name => {
    if (name === "@/lib/auth/token-storage") return {
      getAuthToken: () => "test-session-token", clearAuthToken: () => { cleared = true; },
    };
    if (name === "@/lib/env") return { env: { apiUrl: "http://api.test" } };
    throw new Error(name);
  }, mod, mod.exports, fetch);
  return { ...mod.exports, wasCleared: () => cleared };
}

test("private CV uses the bearer session and retains binary bytes", async () => {
  const bytes = new Uint8Array([37, 80, 68, 70, 255, 0, 128]);
  const calls = [];
  const { apiClient } = load(async (url, options) => {
    calls.push({ url, options });
    return new Response(bytes, { headers: { "Content-Type": "application/pdf" } });
  });
  const blob = await apiClient("/api/v1/applications/owned/resume/pdf", { responseType: "blob" });
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
  assert.equal(calls[0].options.headers.Authorization, "Bearer test-session-token");
  assert.equal(calls[0].url, "http://api.test/api/v1/applications/owned/resume/pdf");
  assert.equal(calls[0].options.responseType, undefined);
});

test("an expired session is handled instead of downloading an error as a PDF", async () => {
  const client = load(async () => Response.json({ detail: "Session expired" }, { status: 401 }));
  await assert.rejects(client.apiClient("/api/v1/applications/owned/resume/pdf", { responseType: "blob" }),
    error => error.status === 401 && error.message === "Session expired");
  assert.equal(client.wasCleared(), true);
});
