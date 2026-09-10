export interface RequestTicket { fingerprint: string; request_id: string }

/** Retain the same idempotency key after a lost response, until intent changes. */
export function requestTicket(payload: unknown, previous: RequestTicket | null, createId = () => crypto.randomUUID()): RequestTicket {
  const fingerprint = JSON.stringify(payload);
  return previous?.fingerprint === fingerprint ? previous : { fingerprint, request_id: createId() };
}

export interface PendingInvitation { session: string; token: string; request_id: string; received_at: number }
export const invitationStorageKey = "intra.gd.pending-invitation";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const token = /^[A-Za-z0-9_-]{43}$/;
export function invitationFromFragment(fragment: string, now: number, createId = () => crypto.randomUUID()): PendingInvitation | null {
  const params = new URLSearchParams(fragment.replace(/^#/, ""));
  const session = params.get("session") || "";
  const value = params.get("token") || "";
  if (!uuid.test(session) || !token.test(value)) return null;
  return { session, token: value, request_id: createId(), received_at: now };
}
export function storedInvitation(value: string | null, now: number): PendingInvitation | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<PendingInvitation>;
    if (typeof parsed.session !== "string" || !uuid.test(parsed.session) || typeof parsed.token !== "string" || !token.test(parsed.token)
      || typeof parsed.request_id !== "string" || !uuid.test(parsed.request_id) || typeof parsed.received_at !== "number"
      || !Number.isFinite(parsed.received_at) || parsed.received_at > now || now - parsed.received_at > 30 * 60 * 1000) return null;
    return parsed as PendingInvitation;
  } catch { return null; }
}
