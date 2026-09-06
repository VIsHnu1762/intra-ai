import test from "node:test";
import assert from "node:assert/strict";
import { copyTemplateRounds, formatTemplateFocusAreas, parseTemplateFocusAreas, templateDuration, validateTemplateRounds, newTemplateRound } from "../src/lib/interview-templates.ts";

const round = { type: "technical", duration_minutes: 20, enabled: true, focus_areas: [" debugging ", "communication"], agent_ids: ["alex", "jordan", "casey", "casey"], agent_id: "alex", order_index: 7 };
test("applying or duplicating templates retains N interviewers and isolates future editor changes", () => {
  const copy = copyTemplateRounds([round]);
  assert.deepEqual(copy[0].agent_ids, ["alex", "jordan", "casey"]);
  assert.deepEqual(copy[0].focus_areas, ["debugging", "communication"]);
  assert.equal(copy[0].order_index, 1);
  copy[0].agent_ids.push("devon"); copy[0].focus_areas.push("another_topic");
  assert.equal(round.agent_ids.includes("devon"), false);
  assert.equal(round.focus_areas.includes("another_topic"), false);
});
test("template budgets count enabled rounds only and reject missing interviewers or focus", () => {
  assert.equal(templateDuration([round, { ...round, enabled: false }]), 20);
  assert.equal(validateTemplateRounds([round, { ...round, duration_minutes: 41 }]), "Keep the total interview duration at 60 minutes or less.");
  assert.match(validateTemplateRounds([{ ...round, agent_ids: [], agent_id: undefined }]), /choose at least one interviewer/);
  assert.match(validateTemplateRounds([{ ...round, focus_areas: [" "] }]), /add at least one focus/);
  assert.match(validateTemplateRounds([{ ...round, enabled: false }]), /at least one active/);
  assert.match(validateTemplateRounds([{ ...round, duration_minutes: NaN }]), /duration between/);
  assert.equal(validateTemplateRounds(copyTemplateRounds([round])), null);
});
test("template editor uses the available catalog instead of forcing Alex or Jordan", () => {
  assert.deepEqual(newTemplateRound(2, [{ agent_id: "casey", name: "Casey", role: "Interviewer" }]).agent_ids, ["casey"]);
  assert.deepEqual(newTemplateRound(1, []).agent_ids, []);
});
test("readable default focus retains its canonical value when adding or editing custom topics", () => {
  const original = newTemplateRound(1, []).focus_areas;
  const displayed = formatTemplateFocusAreas(original);
  assert.equal(displayed, "Coding & Problem Solving");
  assert.deepEqual(parseTemplateFocusAreas(displayed), original);
  assert.deepEqual(parseTemplateFocusAreas(`${displayed}, API design`), ["coding_problem_solving", " API design"]);
  assert.deepEqual(parseTemplateFocusAreas("Coding fundamentals, project_delivery"), ["Coding fundamentals", " project_delivery"]);
});
test("template focus limits cannot smuggle internal metadata into a saved round", () => {
  assert.match(validateTemplateRounds([{ ...round, focus_areas: ["__intra_agent_ids:forged"] }]), /plain topic names/);
  assert.match(validateTemplateRounds([{ ...round, focus_areas: ["x".repeat(161)] }]), /plain topic names/);
  assert.match(validateTemplateRounds([{ ...round, focus_areas: Array(25).fill("debugging") }]), /24 focus/);
});
