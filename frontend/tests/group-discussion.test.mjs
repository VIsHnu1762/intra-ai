import test from "node:test";
import assert from "node:assert/strict";
import { requestTicket, invitationFromFragment, storedInvitation } from "../src/features/group-discussion/state.ts";

const id = "12000000-0000-4000-8000-000000000001";
const token = "A".repeat(43);
test("GD request retries preserve the key, changed intent creates a new key", () => {
  const first = requestTicket({ text: "A proposal" }, null, () => "first");
  assert.equal(requestTicket({ text: "A proposal" }, first, () => "second"), first);
  assert.equal(requestTicket({ text: "Another proposal" }, first, () => "second").request_id, "second");
});
test("Invitation fragments are bounded and never accept arbitrary redirects", () => {
  const value = invitationFromFragment(`#session=${id}&token=${token}&redirect=https://attacker.example`, 100, () => id);
  assert.deepEqual(value, { session: id, token, request_id: id, received_at: 100 });
  assert.equal(invitationFromFragment(`#session=../../admin&token=${token}`, 100), null);
  assert.equal(invitationFromFragment(`#session=${id}&token=bad`, 100), null);
});
test("Stored invitation expires, rejects corruption and future timestamps", () => {
  const value = invitationFromFragment(`#session=${id}&token=${token}`, 100, () => id);
  assert.deepEqual(storedInvitation(JSON.stringify(value), 101), value);
  assert.equal(storedInvitation(JSON.stringify(value), 100 + 30 * 60 * 1000 + 1), null);
  assert.equal(storedInvitation(JSON.stringify(value), 99), null);
  assert.equal(storedInvitation("not JSON", 100), null);
  assert.equal(storedInvitation('{"received_at":null}', 100), null);
});
