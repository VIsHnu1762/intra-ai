import type { GroundedPolicyContext } from "@/types/company-knowledge";

export function PolicySources({ context }: { context?: GroundedPolicyContext | null }) {
  if (!context) return null;
  if (context.status !== "available") return <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">{context.message}</p>;
  return <details className="rounded-lg border bg-background p-3 text-xs"><summary className="cursor-pointer font-medium">Company-policy source snapshot ({context.excerpts.length} excerpts)</summary><p className="mt-2 text-muted-foreground">Effective-date check: {new Date(context.effective_at).toLocaleString()}. These are exact source quotations, not generated policy.</p><div className="mt-3 space-y-4">{context.excerpts.map((source) => <blockquote key={source.chunk_id} className="space-y-1 border-l-2 pl-3"><p className="font-medium">{source.title}, version {source.version}</p><p className="whitespace-pre-wrap leading-relaxed">{source.text}</p><p className="break-all text-muted-foreground">Version: {source.version_id} / Chunk: {source.chunk_id}</p></blockquote>)}</div></details>;
}
