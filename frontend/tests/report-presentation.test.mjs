import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import * as presentation from "../src/lib/report-presentation.ts";
const require = createRequire(import.meta.url);
function load(file, imports = {}) {
  const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => imports[name] ?? require(name), mod, mod.exports);
  return mod.exports;
}
const surface = ({ children, ...props }) => React.createElement("div", props, children);
const cards = { Card: surface, CardHeader: surface, CardTitle: surface, CardContent: surface };
const { CandidatePerformance } = load("../src/components/reports/candidate-performance.tsx", { "@/lib/report-presentation": presentation });
const { RecruiterReportAnalysis } = load("../src/components/reports/recruiter-report-analysis.tsx", {
  "@/lib/report-presentation": presentation, "@/components/ui/card": cards,
  "@/components/ui/progress": { Progress: ({ value }) => React.createElement("meter", { value, min: 0, max: 100 }) },
});
const performance = { interview_id: "own-interview", status: "ready", rating: 4.2, feedback: ["Your explanations were clear.", "Your examples showed practical experience.", "Add detail about the decisions you made."] };

test("candidate feedback is a strict ready-only projection without recruiter metadata", () => {
  assert.deepEqual(presentation.candidatePerformanceSummary({ ...performance, recommendation: "no_hire", analysis: { private: "internal notes" } }), { rating: 4.2, feedback: performance.feedback });
  for (const status of ["not_completed", "not_started", "generating", "failed"]) assert.equal(presentation.candidatePerformanceSummary({ ...performance, status }), null);
  for (const rating of [0, 5.1, NaN, Infinity, "4.2"]) assert.equal(presentation.candidatePerformanceSummary({ ...performance, rating }), null);
  for (const feedback of [[], ["a"], ["a", "b", ""], ["a", "b", "c", "d"], ["a", 3, "c"]]) assert.equal(presentation.candidatePerformanceSummary({ ...performance, feedback }), null);
});

test("fractional stars represent the saved value accessibly and feedback is escaped", () => {
  assert.deepEqual(presentation.starFillPercentages(4.2), [100, 100, 100, 100, 20]);
  assert.deepEqual(presentation.starFillPercentages(1), [100, 0, 0, 0, 0]);
  assert.deepEqual(presentation.starFillPercentages(5), [100, 100, 100, 100, 100]);
  assert.deepEqual(presentation.starFillPercentages(NaN), []);
  const html = renderToStaticMarkup(React.createElement(CandidatePerformance, { performance: { ...performance, recommendation: "SECRET_HIRING_DECISION", feedback: ['Clear <script>alert(1)</script> explanations.', ...performance.feedback.slice(1)] } }));
  assert.match(html, /aria-label="4.2 out of 5 stars"/);
  assert.match(html, /width:20%/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>|SECRET_HIRING_DECISION|Salary|Competency|Download|Hire/);
  assert.equal((html.match(/<p>/g) ?? []).length, 3);
});

test("only generating state polls, request errors stop polling, and regeneration is explicit", () => {
  for (const status of [undefined, "not_completed", "not_started", "ready", "failed"]) assert.equal(presentation.reportPollInterval(status), false);
  assert.equal(presentation.reportPollInterval("generating"), 3000);
  assert.equal(presentation.reportPollInterval("generating", true), false);
  assert.equal(presentation.reportGenerationAction("not_started"), "Generate Report");
  assert.equal(presentation.reportGenerationAction("failed", true), "Retry Generation");
  for (const status of ["not_completed", "generating", "ready", "failed"]) assert.equal(presentation.reportGenerationAction(status), null);
});

test("PDF links require a real safe URL and never fabricate a download endpoint", () => {
  for (const value of [null, "", "javascript:alert(1)", "data:text/html,x", "//other.example/report", "https://user:secret@example.com/report"]) assert.equal(presentation.safeReportPdfUrl(value), null);
  assert.equal(presentation.safeReportPdfUrl("https://files.example/report.pdf"), "https://files.example/report.pdf");
  assert.equal(presentation.safeReportPdfUrl("/saved/report.pdf"), "/saved/report.pdf");
});

test("recruiter evidence keeps answer links, zero scores, N-agent ownership and coverage warnings", () => {
  const analysis = {
    overall_summary: "This interview showed mixed performance.",
    round_assessments: [{ round_id: "round-a", round_name: "API Design" }, { round_id: "round-b", round_name: "Product Decisions" }],
    competency_findings: [{ competency_id: "reliability", score: 0, evidence_ids: ["ev-a"], observations: ["No retry policy was described."], agent_ids: ["casey"], round_ids: ["round-a"] }],
    evidence: [{ id: "ev-a", signal: "No retry policy was described.", score: 0, competency: "reliability", answer_id: "answer-a", round_id: "round-a", source_agent_id: "casey" }, { id: "ev-b", signal: "Prioritized support needs.", score: 8, competency: "user_empathy", answer_id: "answer-b", round_id: "round-b", source_agent_id: "riley" }],
    answers: [{ answer_id: "answer-a", question_text: "How did you retry?", answer_text: "We did not retry <img src=x>." }, { answer_id: "answer-b", question_text: "What did users need?", answer_text: "Faster support." }],
    coverage: { warnings: ["One configured round has no scored evidence."], unobserved_rounds: [{ round_id: "round-c", round_name: "Collaboration" }] },
    handoffs: [{ from_agent_id: "casey", to_agent_id: "riley", status: "completed" }],
  };
  const html = renderToStaticMarkup(React.createElement(RecruiterReportAnalysis, { analysis }));
  assert.match(html, /0.0\/100/);
  assert.match(html, /0\/10/);
  assert.match(html, /Casey/);
  assert.match(html, /Riley/);
  assert.match(html, /Collaboration/);
  assert.match(html, /href="#report-evidence-0"/);
  const firstEvidence = /id="report-evidence-0"(.*?)<\/details>/s.exec(html)?.[1];
  assert.match(firstEvidence, /How did you retry\?/);
  assert.match(firstEvidence, /We did not retry &lt;img src=x&gt;/);
  assert.doesNotMatch(firstEvidence, /Faster support|Riley|<img/);
});

test("report reads use authenticated client calls and cannot trigger generation", async () => {
  const calls = [];
  const api = load("../src/lib/api/reports.ts", { "./client": { apiClient: (...args) => { calls.push(args); return Promise.resolve({}); } } });
  await api.getReportStatus("interview/a");
  await api.getCandidatePerformance("interview/a");
  await api.getReport("report/a");
  assert.deepEqual(calls, [["/api/v1/reports/interview%2Fa/status"], ["/api/v1/interviews/interview%2Fa/performance"], ["/api/v1/reports/report%2Fa"]]);
  await api.generateReport("interview/a");
  assert.deepEqual(calls[3], ["/api/v1/interviews/interview%2Fa/report/generate", { method: "POST" }]);
});

test("recruiter report renders explicit generation states and never fills missing measurements", () => {
  let status = { interview_id: "interview-1", status: "not_started", retryable: false };
  let mutationCalls = 0;
  const emptyReport = { id: "report-1", interview_id: "interview-1", overall_score: 0, recommendation: "maybe", created_at: "2026-09-06T00:00:00Z", strengths: [], improvements: [], round_assessments: [], pdf_url: null, proctoring_summary: null };
  const { default: ReportPage } = load("../src/app/admin/reports/[id]/page.tsx", {
    "next/link": { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) },
    "next/navigation": { useParams: () => ({ id: "interview-1" }) },
    "@/components/ui/button": { Button: ({ children, loading, asChild, ...props }) => React.createElement("button", props, children) },
    "@/components/ui/card": cards,
    "@/components/ui/score-badge": { ScoreBadge: ({ score }) => React.createElement("span", null, score) },
    "@/components/reports/recruiter-report-analysis": { RecruiterReportAnalysis },
    "@/lib/report-presentation": presentation,
    "@/lib/utils": { cn: (...classes) => classes.filter(Boolean).join(" "), formatDate: value => value, getRecommendationLabel: value => value, getScoreBg: () => "" },
    "@/hooks/queries/useReports": {
      useReportStatus: () => ({ data: status, isLoading: false, error: null }),
      useReport: () => ({ data: emptyReport, isLoading: false, error: null }),
      useGenerateReport: () => ({ mutate: () => { mutationCalls++; }, isPending: false }),
    },
  });
  let html = renderToStaticMarkup(React.createElement(ReportPage));
  assert.match(html, />Generate Report</);
  assert.equal(mutationCalls, 0);
  status = { ...status, status: "generating" };
  html = renderToStaticMarkup(React.createElement(ReportPage));
  assert.match(html, /being prepared/);
  assert.doesNotMatch(html, />Generate Report<|>Retry Generation<|>Check Again</);
  status = { ...status, status: "failed", retryable: true };
  assert.match(renderToStaticMarkup(React.createElement(ReportPage)), />Retry Generation</);
  status = { ...status, retryable: false };
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(ReportPage)), />Retry Generation</);
  status = { ...status, status: "ready" };
  html = renderToStaticMarkup(React.createElement(ReportPage));
  assert.match(html, /No proctoring measurements were recorded/);
  assert.match(html, /No strengths were recorded/);
  assert.doesNotMatch(html, /99%|98%|Download PDF|Clear technical articulation|Continue sharpening/);
  assert.equal(mutationCalls, 0);
});

test("completed interview remains discoverable when the recruiter has no published reports", () => {
  let status = { status: "failed", retryable: true };
  const links = { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) };
  const utils = { cn: (...classes) => classes.filter(Boolean).join(" "), formatDate: value => value, getRecommendationLabel: value => value };
  const { CompletedInterviewReport } = load("../src/components/reports/completed-interview-report.tsx", {
    "next/link": links, "@/lib/utils": utils,
    "@/hooks/queries/useReports": { useReportStatus: () => ({ data: status }) },
  });
  const { default: ReportsPage } = load("../src/app/admin/reports/page.tsx", {
    "next/link": links, "@/lib/utils": utils, "@/lib/report-presentation": presentation,
    "@/components/ui/card": cards,
    "@/components/ui/button": { Button: ({ children, asChild, ...props }) => React.createElement("button", props, children) },
    "@/components/ui/score-badge": { ScoreBadge: () => null },
    "@/components/ui/avatar": { Avatar: () => null },
    "@/components/ui/skeleton": { Skeleton: () => null },
    "@/components/ui/empty-state": { EmptyState: () => React.createElement("p", null, "No published reports") },
    "@/components/reports/completed-interview-report": { CompletedInterviewReport },
    "@/hooks/queries/useReports": { useReports: () => ({ data: { reports: [] }, isLoading: false }) },
    "@/hooks/queries/useScheduling": { useInterviews: params => {
      assert.equal(params.status, "completed");
      return { data: { interviews: [{ id: "completed-without-report", scheduled_at: "2026-09-06", candidate: { name: "Sriram" }, job: { title: "Software Developer Intern" } }] } };
    } },
  });
  let html = renderToStaticMarkup(React.createElement(ReportsPage));
  assert.match(html, /Sriram/);
  assert.match(html, /Software Developer Intern/);
  assert.match(html, /href="\/admin\/reports\/completed-without-report"/);
  assert.match(html, /Review &amp; Retry/);
  assert.match(html, /No published reports/);
  status = { status: "failed", retryable: false };
  html = renderToStaticMarkup(React.createElement(ReportsPage));
  assert.doesNotMatch(html, /retry available|Review &amp; Retry/);
  assert.match(html, /review details/);
});
