import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as workflows from "../src/lib/morgan-workflows.ts";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/components/voice/morgan-action-cards.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 } }).outputText;
const mod = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "@/lib/morgan-workflows" ? workflows : require(name), mod, mod.exports);

test("bulk confirmation shows named candidates, skipped reasons, actual slot and no internal IDs", () => {
  const html = renderToStaticMarkup(React.createElement(mod.exports.MorganBulkReview, { action: { tool: "bulk_schedule_interviews", confirmation_id: "opaque-confirmation-secret", details: { timezone: "Asia/Kolkata", template: { name: "Engineering <review>", template_id: "internal-template-id", duration_minutes: 30 }, items: [
    { candidate: { id: "internal-candidate-id", name: "Sam <script>" }, application: { id: "internal-application-id" }, job: { title: "Engineer" }, eligible: true, scheduled_at: "2026-09-10T04:30:00Z", duration_minutes: 30 },
    { candidate: { name: "Avery" }, eligible: false, skip_reason: "Already scheduled" },
  ] } } }));
  assert.match(html, /1 ready · 1 will be skipped/);
  assert.match(html, /Sam &lt;script&gt;/);
  assert.match(html, /Already scheduled/);
  assert.match(html, /Engineering &lt;review&gt;/);
  assert.match(html, /Asia\/Kolkata/);
  assert.doesNotMatch(html, /internal-|opaque-confirmation|<script>/);
  assert.match(html, /Only candidates marked Ready will be changed after you confirm/);
});
test("partial results preserve failed and skipped outcomes rather than presenting blanket success", () => {
  const result = { status: "partial", result: { succeeded: 1, failed: 1, skipped: 1, items: [
    { application_id: "hidden-a", candidate: { name: "Sam" }, status: "succeeded", message: "Interview scheduled." },
    { candidate: { name: "Avery" }, status: "failed", message: "That slot is no longer available." },
    { candidate: { name: "Morgan" }, status: "skipped", message: "Already shortlisted." },
  ] } };
  const html = renderToStaticMarkup(React.createElement(mod.exports.MorganBulkResult, { result }));
  assert.match(html, /1 completed · 1 skipped · 1 failed/);
  assert.match(html, /That slot is no longer available/);
  assert.match(html, /Already shortlisted/);
  assert.doesNotMatch(html, /hidden-a/);
});
test("admin data refreshes after writes or uncertain outcomes, never during submission", () => {
  assert.equal(workflows.morganChangedQueryKeys("succeeded").length, 5);
  assert.equal(workflows.morganChangedQueryKeys("partial").length, 5);
  assert.equal(workflows.morganChangedQueryKeys("failed").length, 5);
  assert.equal(workflows.morganChangedQueryKeys("error", true).length, 5);
  for (const status of [undefined, "confirmation_required", "executing", "submitting", "declined", "error"]) assert.deepEqual(workflows.morganChangedQueryKeys(status), []);
  assert.equal(workflows.morganBulkResults({ result: { items: [{ name: "a read-only candidate list" }] } }), null);
});
test("review timestamps require an explicit offset and safely reject invalid timezones", () => {
  assert.equal(workflows.reviewDate("2026-09-10T10:00:00", "Asia/Kolkata"), "2026-09-10T10:00:00");
  assert.equal(workflows.reviewDate("2026-09-10T04:30:00Z", "invalid/timezone"), "2026-09-10T04:30:00Z");
  assert.match(workflows.reviewDate("2026-09-10T04:30:00Z", "Asia/Kolkata"), /10:00/);
});

test("accepted confirmations cannot reappear and stale polling cannot replace the running action", () => {
  const submitted = new Set(["confirmed-1"]);
  const current = { confirmation_id: "confirmed-1", status: "executing" };
  const stale = { confirmation_id: "older-result", status: "succeeded" };
  const next = workflows.reconcileMorganActionSnapshot(current, stale, { confirmation_id: "confirmed-1", tool: "send_candidate_email" }, submitted);
  assert.equal(next.pending, null);
  assert.equal(next.result, current);
  const done = { confirmation_id: "confirmed-1", status: "partial", result: { succeeded: 1, failed: 1 } };
  assert.equal(workflows.reconcileMorganActionSnapshot(current, done, null, submitted).result, done);
  assert.equal(workflows.reconcileMorganActionSnapshot(done, current, null, submitted).result, done);
});

test("lost confirmation response can recover its saved result without any action replay", () => {
  const lost = { confirmation_id: "confirmed-1", status: "failed", outcome_unknown: true };
  const executing = { confirmation_id: "confirmed-1", status: "executing" };
  const final = { confirmation_id: "confirmed-1", status: "failed", outcome_unknown: true, message: "Execution interrupted" };
  assert.equal(workflows.reconcileMorganActionSnapshot(lost, executing, null, new Set()).result, executing);
  assert.equal(workflows.reconcileMorganActionSnapshot(executing, final, null, new Set()).result, final);
});

const reviewSource = readFileSync(new URL("../src/components/voice/morgan-external-review.tsx", import.meta.url), "utf8");
const reviewCompiled = ts.transpileModule(reviewSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 } }).outputText;
const reviewMod = { exports: {} };
new Function("require", "module", "exports", reviewCompiled)(name => name === "@/lib/morgan-workflows" ? workflows : require(name), reviewMod, reviewMod.exports);
const renderReview = action => renderToStaticMarkup(React.createElement(reviewMod.exports.MorganExternalReview, { action }));

test("Slack approval exposes the exact channel and escaped message, including line breaks", () => {
  const action = { tool: "post_recruiting_update_to_slack", details: { channel: { id: "hidden-channel-id", name: "hiring-updates" }, job: { title: "Engineer" }, message: 'Review Jane\n<script>not executable</script>' } };
  const html = renderReview(action);
  assert.match(html, /#hiring-updates/);
  assert.match(html, /Review Jane\n&lt;script&gt;not executable&lt;\/script&gt;/);
  assert.doesNotMatch(html, /hidden-channel-id|<script>/);
  assert.equal(workflows.morganExternalReviewReady(action), true);
  assert.equal(workflows.morganConfirmLabel(action), "Post to Slack");
});

test("email approval distinguishes saving a draft from sending the exact recipient, subject and body", () => {
  const details = { email: { to: "candidate@example.test", subject: "Your interview <details>", body: "Hi Sam,\nYour interview is tomorrow.", mode: "draft_only" } };
  const action = { tool: "create_candidate_email_draft", details };
  const html = renderReview(action);
  assert.match(html, /candidate@example.test/);
  assert.match(html, /Your interview &lt;details&gt;/);
  assert.match(html, /No email will be sent/);
  assert.match(html, /Hi Sam,\nYour interview is tomorrow\./);
  assert.equal(workflows.morganConfirmLabel(action), "Save Email Draft");
  const send = { tool: "send_candidate_email", details: { email: { ...details.email, mode: "send" } } };
  assert.match(renderReview(send), /Send this email to the candidate/);
  assert.equal(workflows.morganConfirmLabel(send), "Send This Email");
});

test("calendar approval shows the selected calendar, event times, attendees and invitation policy", () => {
  const action = { tool: "add_interview_to_calendar", details: { calendar: { id: "team@example.test", summary: "Recruiting Calendar" }, event: { summary: "Interview: Engineer — Sam", start_datetime: "2026-09-10T04:30:00Z", end_datetime: "2026-09-10T05:00:00Z", attendees: ["candidate@example.test"], send_updates: "none" } } };
  const html = renderReview(action);
  assert.match(html, /Recruiting Calendar\nteam@example.test/);
  assert.match(html, /candidate@example.test/);
  assert.match(html, /Starts/); assert.match(html, /Ends/);
  assert.match(html, /No invitation email will be sent/);
  assert.equal(workflows.morganExternalReviewReady(action), true);
  assert.equal(workflows.morganConfirmLabel(action), "Add to Calendar");
  action.details.event.send_updates = "all";
  assert.match(renderReview(action), /An invitation email will be sent/);
  assert.equal(workflows.morganConfirmLabel(action), "Add & Notify Candidate");
});

test("external confirmations fail closed when the exact destination or notification mode is absent", () => {
  assert.equal(workflows.morganExternalReviewReady({ tool: "post_recruiting_update_to_slack", details: { message: "hello", channel: { id: "C123" } } }), false);
  assert.equal(workflows.morganExternalReviewReady({ tool: "send_candidate_email", details: { email: { to: "candidate@example.test", subject: "subject", body: "message" } } }), false);
  assert.equal(workflows.morganExternalReviewReady({ tool: "add_interview_to_calendar", details: { calendar: { summary: "Team" }, event: { summary: "Interview", start_datetime: "2026-09-10T04:30:00Z", end_datetime: "2026-09-10T05:00:00Z", attendees: ["candidate@example.test"] } } }), false);
});
