# Approval flow (queue, review, publish)

The one place that says how a post, comment or reply gets from draft to the
public account. `linkedin-post-writer`, `linkedin-repurposer`,
`linkedin-comment-drafter` (comment mode) and `linkedin-reply-handler` cite this
file for everything below and keep only their own `lib.enqueue_for_review(...)`
arguments. Reshare (`lib.repost`) is outside the queue and keeps its own card.
Where this sits in the rule order: `precedence.md` §3.

## The flow

1. **Queue the draft.** `lib.enqueue_for_review(kind=..., text=..., target_url=..., ...)`
   takes the arguments `lib.publish` would have taken and sends nothing. It returns
   the item: show its `id`.
2. **The human reviews, you do not.** Tell the user to run
   `python3 scripts/approval_queue.py review` in their own terminal and to come
   back when done. Never run `review` yourself, never script it, and never treat
   a "yes" typed in the chat as approval of a queued item.
3. **The text that counts is the one `review` prints in the terminal.** The card
   in the chat is a preview. Say so, and tell the user to read the terminal text
   before confirming: if the two differ, the terminal wins.
4. **Send what was approved.** When the user says they reviewed, call
   `lib.publish_approved(<id>)`. It rebuilds the call from the stored item and
   the gate re-checks text, accounts, target, parent comment, reaction, schedule
   and media against the approved hash. On the manual tier it returns the
   copy-paste block instead: show it.

## Branches you will hit

**`enqueue_for_review` returns `duplicate: True`.** The same draft is already in
the queue. Do not queue it again; read `item["status"]`:
- `pending`: it is waiting for review. Give the id, ask the user to review.
- `approved`: reviewed already. Call `lib.publish_approved(<id>)` if they want it sent.
- `sent`: it already went out. Say so.
- `sending` or `unknown`: it may already have gone out. Do not re-queue or resend;
  see the `ApprovalError` branch below for what the user does.

**Changing a draft that is already queued.** Use
`lib.approval_queue.edit(<id>, text=<new text>)` (other editable fields: target,
reaction, schedule, media). Editing drops any approval and puts the item back to
`pending`, so the user reviews the new text. Do not queue the revision as a second
item and leave the first one pending. An item that is `sending`, `sent` or
`unknown` cannot be edited.

**`lib.publish_approved` raises `ApprovalError`.** Nothing was sent. Do not retry,
do not work around it. Read `lib.approval_queue.get(<id>)["status"]` and say what
it means:
- `pending`: not approved yet. They skipped it, or have not reviewed. Ask them to review.
- `rejected`: they rejected it. Leave it.
- `approved` (the error is a mismatch): something changed after approval. Ask them to review again.
- `sent`: it already went out.
- `sending` or `unknown`: **it may have been sent.** Do not say they skipped it. Tell
  them to check the platform (their feed, the Publora dashboard) and then record
  what they found: `python3 scripts/approval_queue.py reconcile <id> sent|failed --note "what you checked"`.
  Only after a `failed` reconcile can the same text be queued again.
- `failed`: the API refused it. Report the error; queue it again only if they ask.

**Any other exception from `publish_approved` (or from a call in a batch).** Stop.
Do not retry and do not carry on to the next item. Report which ids were sent,
which were not, and the error. The item is probably `unknown`: apply the
`sending` / `unknown` branch above.

## What this does and does not give

It guards against the text, account, target or parent comment changing between
the card and the send, against a second send of one approval, and against an
approval nobody gave. It is a guard-rail for mistakes and careless injected text,
not a security boundary: an agent that holds the Publora key can still call the
client directly. Details and the open items (approval expiry is not implemented):
`../docs/architecture/approval-queue.md`.
