import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as practice from "../src/lib/taylor-practice.ts";

// Compile the real TSX presentation component for Node's server renderer.
// Only the unrelated shared button is stubbed; feedback text and HTML are real.
const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/components/voice/taylor-practice-feedback.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
}).outputText;
const componentModule = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "@/lib/taylor-practice") return practice;
  if (name === "@/components/ui/button") return { Button: ({ children }) => React.createElement("button", null, children) };
  return require(name);
}, componentModule, componentModule.exports);
const { TaylorPracticeFeedbackPanel } = componentModule.exports;
const render = (answer, extra = {}) => renderToStaticMarkup(React.createElement(TaylorPracticeFeedbackPanel, {
  feedback: { status: "ready", better_answers: [answer], ...extra }, onRetry: () => {},
}));

test("feedback template stays separate from the actual source answer and escapes both", () => {
  const html = render({
    question: "How did you validate the form?",
    answer_excerpt: 'I checked input <img src=x onerror="alert(1)"> & showed errors.',
    example_kind: "template",
    example: 'I checked input. [Add a real validation example <script>alert(1)</script>].',
    explanation: "Use a specific example from your own project.",
  });
  const sourceAnswer = /<blockquote[^>]*>(.*?)<\/blockquote>/s.exec(html)?.[1];
  assert.ok(sourceAnswer);
  assert.match(sourceAnswer, /From your answer:/);
  assert.match(sourceAnswer, /&lt;img/);
  assert.doesNotMatch(sourceAnswer, /Add a real validation example/);
  assert.match(html, /Answer template/);
  assert.match(html, /Fill in brackets with details that are true of your own experience\./);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script|<img/);
});

test("legacy feedback without example_kind remains readable as a suggested answer", () => {
  const html = render({ question: "What did you build?", example: "I built a task tracker.", explanation: "Start with the project's purpose." });
  assert.match(html, /Suggested answer/);
  assert.match(html, /I built a task tracker\./);
  assert.doesNotMatch(html, /Answer template|Fill in brackets|From your answer:/);
});

test("explicit source-grounded suggestions use the suggestion label without template instructions", () => {
  const html = render({ question: "What did you build?", example: "I built a task tracker.", example_kind: "suggested_answer", answer_excerpt: "I built a task tracker." }, { answered_questions: 12, reviewed_answers: 6, indicative_score: 78 });
  assert.match(html, /Suggested answer/);
  assert.match(html, /Feedback based on 6 of 12 practice answers/);
  assert.match(html, /Indicative practice score/);
  assert.doesNotMatch(html, /Fill in brackets/);
});
