"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import type { GroundedPolicyContext as PolicyAnswer } from "@/types/company-knowledge";

export function PolicyAnswerPage() {
  const [question, setQuestion] = useState("");
  const answer = useMutation({ mutationFn: () => apiClient.post<PolicyAnswer>("/api/v1/company-knowledge/answer", { question: question.trim() }) });
  return <main className="mx-auto max-w-4xl space-y-6 p-4 sm:p-8">
    <header className="space-y-2"><p className="text-sm text-muted-foreground">Company knowledge</p><h1 className="text-3xl font-semibold">Answers anchored to policy</h1><p className="max-w-2xl text-muted-foreground">AICredits selects relevant, candidate-visible excerpts from your authorized documents. Answers contain exact quotations, not generated policy.</p></header>
    <form className="space-y-3 rounded-xl border bg-card p-5" onSubmit={(event) => { event.preventDefault(); answer.mutate(); }}><label htmlFor="policy-question" className="block text-sm font-medium">What do you need to clarify?</label><textarea id="policy-question" className="w-full rounded-lg border bg-background p-3" rows={3} value={question} onChange={(event) => { setQuestion(event.target.value); answer.reset(); }} minLength={3} maxLength={500} required disabled={answer.isPending} /><button className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={answer.isPending || question.trim().length < 3}>{answer.isPending ? "Checking authorized sources..." : "Find grounded excerpts"}</button></form>
    {answer.error && <p role="alert" className="text-sm text-destructive">{answer.error.message}</p>}
    {answer.data && <section aria-live="polite" className="space-y-4"><p className="rounded-lg border p-4 text-sm">{answer.data.message}</p><p className="text-xs text-muted-foreground">Policy effective-date check: {new Date(answer.data.effective_at).toLocaleString()}</p>{answer.data.status === "available" && answer.data.excerpts.map((excerpt) => <article key={excerpt.chunk_id} className="space-y-3 rounded-xl border bg-card p-5"><div className="flex flex-wrap items-baseline justify-between gap-2"><h2 className="font-semibold">{excerpt.title}</h2><span className="text-xs text-muted-foreground">Version {excerpt.version}</span></div><blockquote className="whitespace-pre-wrap border-l-2 border-primary pl-4 text-sm leading-relaxed">{excerpt.text}</blockquote><p className="text-xs text-muted-foreground">Effective from {new Date(excerpt.effective_from).toLocaleDateString()}{excerpt.effective_until && ` until ${new Date(excerpt.effective_until).toLocaleDateString()}`}</p><details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Source provenance</summary><p className="mt-2 break-all">Document {excerpt.document_id}<br />Version {excerpt.version_id}<br />Chunk {excerpt.chunk_id}</p></details></article>)}</section>}
  </main>;
}
