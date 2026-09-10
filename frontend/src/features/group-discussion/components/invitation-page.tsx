"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { getAuthToken } from "@/lib/auth/token-storage";
import { discussions } from "../api";
import { invitationFromFragment, invitationStorageKey, storedInvitation, type PendingInvitation } from "../state";

export function DiscussionInvitationPage() {
  const router = useRouter();
  const [pending, setPending] = useState<PendingInvitation | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const now = Date.now();
    const incoming = invitationFromFragment(window.location.hash, now);
    let retained: PendingInvitation | null = null;
    try {
      retained = storedInvitation(sessionStorage.getItem(invitationStorageKey), now);
      const value = incoming && retained?.session === incoming.session && retained.token === incoming.token ? retained : incoming || retained;
      if (value) sessionStorage.setItem(invitationStorageKey, JSON.stringify(value));
      else sessionStorage.removeItem(invitationStorageKey);
      retained = value;
    } catch { retained = incoming; }
    // Bearer invitation credentials never go into query parameters or server logs.
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
    queueMicrotask(() => { setPending(retained); setAuthenticated(Boolean(getAuthToken())); setLoaded(true); });
  }, []);
  const join = useMutation({ mutationFn: () => discussions.join(pending!.session, pending!.token, pending!.request_id), onSuccess: (session) => {
    try { sessionStorage.removeItem(invitationStorageKey); } catch { /* Private browsing may disable storage. */ }
    setPending(null);
    router.replace(`/group-discussions/${session.id}`);
  } });
  return <main className="mx-auto flex min-h-[70vh] max-w-xl items-center p-6"><section className="w-full space-y-5 rounded-2xl border bg-card p-6 sm:p-8"><p className="text-xs uppercase tracking-wider text-muted-foreground">Intra AI / Group discussion</p><h1 className="text-3xl font-semibold">Your seat at the table</h1><p className="text-sm text-muted-foreground">Sign in with the candidate account that received this invitation. Accepting joins a shared, text-only discussion; participants will see your display name and contributions.</p>{!loaded ? <p role="status">Reading invitation...</p> : !pending ? <p role="alert">This link is missing or the locally retained invitation expired. Reopen the original invitation link or ask the recruiter for a new one.</p> : authenticated ? <button className="w-full rounded-lg bg-primary px-4 py-3 font-medium text-primary-foreground disabled:opacity-50" disabled={join.isPending} onClick={() => join.mutate()}>{join.isPending ? "Joining securely..." : "Accept and join discussion"}</button> : <div className="space-y-3"><Link className="block rounded-lg bg-primary px-4 py-3 text-center font-medium text-primary-foreground" href="/login?redirect=/discussion-invite">Sign in to accept</Link><p className="text-xs text-muted-foreground">If sign-in opens your dashboard, return to this page in the same tab. The invitation is retained for 30 minutes in this tab only.</p></div>}{join.error && <p role="alert" className="text-sm text-destructive">{join.error.message}</p>}<p className="text-xs text-muted-foreground">This is not a Standard Interview. No microphone or Agora voice session will start.</p></section></main>;
}
