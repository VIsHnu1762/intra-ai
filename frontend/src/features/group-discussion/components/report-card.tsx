import type { IndividualReport } from "../api";
import { PolicySources } from "@/components/knowledge/policy-sources";

export function DiscussionReport({ report }: { report: IndividualReport }) {
  const strengths = report.feedback?.strengths ?? report.narrative?.strengths.map((item) => item.text) ?? [];
  const improvements = report.feedback?.improvements ?? report.narrative?.improvements.map((item) => item.text) ?? [];
  return <section className="space-y-5 rounded-xl border bg-card p-5" aria-label="Individual discussion feedback">
    <div className="flex flex-wrap items-baseline justify-between gap-3"><h3 className="text-xl font-semibold">Your discussion evidence</h3><p className="text-2xl font-semibold">{report.candidate_rating.toFixed(1)} <span className="text-sm text-muted-foreground">/ 5</span></p></div>
    <p className="text-sm text-muted-foreground">{report.performance_band}. Based on {report.evaluated_turns} evaluated contributions. {report.unevaluated_turns > 0 && `${report.unevaluated_turns} contributions could not be evaluated.`}</p>
    {report.narrative?.summary && <p>{report.narrative.summary}</p>}
    <div className="grid gap-5 sm:grid-cols-2"><div><h4 className="mb-2 font-medium">Strengths</h4><ul className="list-disc space-y-2 pl-5 text-sm">{strengths.map((text, i) => <li key={i}>{text}</li>)}</ul></div><div><h4 className="mb-2 font-medium">To develop</h4><ul className="list-disc space-y-2 pl-5 text-sm">{improvements.map((text, i) => <li key={i}>{text}</li>)}</ul></div></div>
    {report.evidence && <details><summary className="cursor-pointer font-medium">Saved source evidence</summary><div className="mt-3 space-y-3">{report.evidence.map((item) => <blockquote key={item.id} className="border-l-2 pl-3 text-sm"><p className="font-medium">{item.competency}</p><p className="whitespace-pre-wrap">{item.quote}</p><p className="mt-1 break-all text-xs text-muted-foreground">Source event: {item.event_id}</p></blockquote>)}</div></details>}
    {report.policy_contexts?.map((context, index) => <PolicySources key={index} context={context} />)}
    <p className="text-xs text-muted-foreground">Text participation is not speaking time or a measure of leadership. This feedback does not change a Standard Interview score.</p>
  </section>;
}
