import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

function loadClient(file) {
  const calls = [];
  const api = (...args) => { calls.push(args); return Promise.resolve({}); };
  for (const method of ["get", "post", "patch"]) api[method] = (...args) => { calls.push([method, ...args]); return Promise.resolve({}); };
  const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    assert.equal(name, "./client");
    return { apiClient: api };
  }, mod, mod.exports);
  return { calls, exports: mod.exports };
}

test("template edits send the expected version and job application uses the authorized endpoint", async () => {
  const { calls, exports: { interviewTemplatesApi: api } } = loadClient("../src/lib/api/interview-templates.ts");
  const draft = { name: "Backend interview", description: "", rounds: [] };
  await api.update("template/a", draft, 7);
  await api.applyToJob("template/a", "job-123");
  await api.list(true);
  assert.deepEqual(calls[0], ["patch", "/api/v1/interview-templates/template%2Fa", { ...draft, expected_version: 7 }]);
  assert.deepEqual(calls[1], ["post", "/api/v1/interview-templates/template%2Fa/apply-to-job", { job_id: "job-123" }]);
  assert.deepEqual(calls[2], ["get", "/api/v1/interview-templates", { params: { include_archived: true } }]);
});
test("new scheduled and instant interviews carry the selected template ID", async () => {
  const { calls, exports: api } = loadClient("../src/lib/api/scheduling.ts");
  await api.bookInterviewSlot("application-1", "slot-2", "template-3");
  await api.startInstantInterview("application-1", "template-3");
  assert.deepEqual(JSON.parse(calls[0][1].body), { slot_id: "slot-2", template_id: "template-3" });
  assert.deepEqual(JSON.parse(calls[1][1].body), { template_id: "template-3" });
});
test("rescheduling preserves saved configuration and legacy calls omit a template", async () => {
  const { calls, exports: api } = loadClient("../src/lib/api/scheduling.ts");
  await api.rescheduleInterview("application-1", "slot-2");
  await api.bookInterviewSlot("application-1", "slot-2");
  await api.startInstantInterview("application-1");
  assert.deepEqual(JSON.parse(calls[0][1].body), { slot_id: "slot-2" });
  assert.deepEqual(JSON.parse(calls[1][1].body), { slot_id: "slot-2" });
  assert.equal(calls[2][1].body, undefined);
});
