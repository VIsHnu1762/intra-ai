"use client";

import type { BackendReportAnalysis } from "@/types/api";
import { reportLabel } from "@/lib/report-presentation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

function Timestamp({ value }: { value?: string | null }) {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime()) ? <time dateTime={value!}>{date.toLocaleString()}</time> : null;
}

export function RecruiterReportAnalysis({ analysis }: { analysis?: BackendReportAnalysis | null }) {
  if (!analysis) return null;
  const evidence = analysis.evidence ?? [];
  const answerLookup = new Map((analysis.answers ?? []).map(answer => [answer.answer_id, answer]));
  const roundLookup = new Map((analysis.round_assessments ?? []).map(round => [round.round_id, round]));
  const roundName = (id?: string | null) => {
    const round = id ? roundLookup.get(id) : null;
    return reportLabel(round?.round_name || round?.round_type || id, "Unresolved round");
  };
  const evidenceLinks = (ids: string[] = []) => ids.flatMap(id => {
    const index = evidence.findIndex(item => item.id === id);
    return index < 0 ? [] : [<a key={id} href={`#report-evidence-${index}`} className="text-xs text-brand underline underline-offset-2">Evidence {index + 1}</a>];
  });
  return (
    <>
      {analysis.overall_summary && <Card><CardHeader><CardTitle>Overall Assessment</CardTitle></CardHeader><CardContent><p className="text-sm leading-relaxed text-text-primary">{analysis.overall_summary}</p></CardContent></Card>}
      {(analysis.coverage?.warnings?.length || analysis.coverage?.unobserved_rounds?.length) ? (
        <Card className="border-warning/30 bg-warning-light"><CardContent className="p-5">
          <h2 className="font-semibold text-warning">Assessment Coverage</h2>
          <ul className="mt-2 space-y-2 text-sm text-text-primary">{analysis.coverage?.warnings?.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
          {!!analysis.coverage?.unobserved_rounds?.length && <p className="mt-2 text-sm text-text-muted">Rounds without scored evidence: {analysis.coverage.unobserved_rounds.map(round => reportLabel(round.round_name || round.round_type, "Unresolved round")).join(", ")}. These rounds are not shown as completed scores.</p>}
        </CardContent></Card>
      ) : null}
      {!!analysis.competency_findings?.length && <Card><CardHeader><CardTitle>Competency Findings</CardTitle></CardHeader><CardContent className="space-y-5">
        {analysis.competency_findings.map((finding, index) => (
          <div key={`${finding.competency_id}-${index}`}>
            <div className="flex items-center justify-between gap-3 text-sm"><h3 className="font-semibold text-text-primary">{reportLabel(finding.competency_id)}</h3><span className="text-text-muted">{typeof finding.score === "number" && Number.isFinite(finding.score) ? `${finding.score.toFixed(1)}/100` : "Not scored"}</span></div>
            {typeof finding.score === "number" && Number.isFinite(finding.score) && <Progress className="mt-2" value={finding.score} />}
            {!!finding.agent_ids?.length && <p className="mt-2 text-xs text-text-muted">Interviewers: {finding.agent_ids.map(id => reportLabel(id, "Interviewer")).join(", ")}</p>}
            <ul className="mt-2 space-y-1 text-sm text-text-muted">{finding.observations?.map((text, i) => <li key={i}>{text}</li>)}</ul>
            <div className="mt-2 flex flex-wrap gap-3">{evidenceLinks(finding.evidence_ids)}</div>
          </div>
        ))}
      </CardContent></Card>}
      {(analysis.narrative_evidence?.strengths?.length || analysis.narrative_evidence?.improvements?.length) ? <Card><CardHeader><CardTitle>Evidence Behind the Assessment</CardTitle></CardHeader><CardContent className="space-y-4">
        {([['Strengths', analysis.narrative_evidence?.strengths], ['Areas for improvement', analysis.narrative_evidence?.improvements]] as const).map(([label, rows]) => rows?.length ? <div key={label}><h3 className="text-sm font-semibold text-text-primary">{label}</h3>{rows.map((row, index) => <div key={index} className="mt-2"><p className="text-sm text-text-muted">{row.text}</p><div className="mt-1 flex flex-wrap gap-3">{evidenceLinks(row.evidence_ids)}</div></div>)}</div> : null)}
      </CardContent></Card> : null}
      {!!evidence.length && <Card><CardHeader><CardTitle>Interview Evidence</CardTitle></CardHeader><CardContent className="space-y-3">
        {evidence.map((item, index) => {
          const answer = item.answer_id ? answerLookup.get(item.answer_id) : null;
          return <details key={item.id} id={`report-evidence-${index}`} className="scroll-mt-24 rounded-lg border border-border p-4">
            <summary className="cursor-pointer text-sm font-medium text-text-primary">Evidence {index + 1}: {item.signal}</summary>
            <div className="mt-3 space-y-3 text-sm">
              <p className="text-xs text-text-muted">{reportLabel(item.source_agent_id, "Interviewer not recorded")} · {roundName(item.round_id)} · {reportLabel(item.competency)}{typeof item.score === "number" && Number.isFinite(item.score) ? ` · ${item.score}/10` : " · Not scored"}</p>
              {answer?.question_text && <div><h4 className="font-semibold text-text-primary">Question</h4><p className="mt-1 text-text-muted">{answer.question_text}</p></div>}
              {answer?.answer_text || answer?.transcript ? <div><h4 className="font-semibold text-text-primary">Candidate’s Answer</h4><blockquote className="mt-1 whitespace-pre-wrap border-l-2 border-brand pl-3 text-text-muted">{answer.answer_text || answer.transcript}</blockquote></div> : <p className="text-text-muted">The answer transcript for this evidence is unavailable.</p>}
              <p className="text-xs text-text-muted"><Timestamp value={item.timestamp} /></p>
            </div>
          </details>;
        })}
      </CardContent></Card>}
      {!!analysis.handoffs?.length && <Card><CardHeader><CardTitle>Interviewer Handoffs</CardTitle></CardHeader><CardContent><ol className="space-y-3 text-sm text-text-primary">{analysis.handoffs.map((handoff, index) => <li key={index}>
        {reportLabel(handoff.from_agent_id || handoff.source_agent_id, "Interviewer not recorded")} → {reportLabel(handoff.to_agent_id || handoff.target_agent_id, "Interviewer not recorded")}
        {handoff.status && <span className="ml-2 text-xs text-text-muted">{reportLabel(handoff.status)}</span>}
        {handoff.round_id && <span className="ml-2 text-xs text-text-muted">{roundName(handoff.round_id)}</span>}
        <div className="text-xs text-text-muted"><Timestamp value={handoff.timestamp} /></div>
      </li>)}</ol></CardContent></Card>}
      {!!analysis.transcripts?.length && <Card><CardContent className="p-5"><details><summary className="cursor-pointer font-semibold text-text-primary">Interview Transcript</summary><ol className="mt-4 space-y-4">{analysis.transcripts.map((entry, index) => <li key={entry.id || index} className="text-sm"><p className="font-semibold text-text-primary">{reportLabel(entry.agent_id || entry.speaker, "Speaker not recorded")}</p><p className="mt-1 whitespace-pre-wrap text-text-muted">{entry.text}</p><p className="mt-1 text-xs text-text-muted"><Timestamp value={entry.timestamp} /></p></li>)}</ol></details></CardContent></Card>}
    </>
  );
}
