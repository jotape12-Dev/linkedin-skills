#!/usr/bin/env python3
"""CLI: review the local approval queue. Approval is for a human at a terminal.

Usage:
    python3 scripts/approval_queue.py list [--status pending]
    python3 scripts/approval_queue.py show <id>
    python3 scripts/approval_queue.py review [<id> ...]      # approve/reject on the terminal
    python3 scripts/approval_queue.py reject <id> [<id> ...]
    python3 scripts/approval_queue.py reconcile <id> sent|failed --note "what you checked"

`review` reads every decision and a random confirmation code from /dev/tty. With no
controlling terminal it refuses; there is no flag, argument or pipe that approves.
`list` and `show` print the approval hash only when stdout is a terminal.

`reconcile` resolves an item stuck in `sending` or `unknown` (a send whose outcome
is not known): check the platform yourself, then record sent or failed with a note.

The ledger is testing/approval-queue.jsonl unless LINKEDIN_SKILLS_QUEUE_PATH points
elsewhere (it must be outside version control). Nothing here sends anything:
publishing is `lib.publish(..., approved_hash=<hash>)`.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import approval_queue as q  # noqa: E402


def report(results: dict[str, str]) -> int:
    bad = 0
    for item_id, outcome in results.items():
        print(f"{item_id}  {outcome}")
        if outcome not in ("approved", "rejected", "skipped"):
            bad += 1
    return 1 if bad else 0


def cmd_list(args) -> int:
    items = q.list_items(args.status)
    if not items:
        print("(empty)")
        return 0
    tty = sys.stdout.isatty()
    for i in items:
        first = q.safe(i["text"].splitlines()[0][:60]) if i["text"] else ""
        digest = f"  {i['approval_hash'][:12]}" if tty else ""
        print(f"{i['id']}  {i['status']:<8} {i['kind']:<7}{digest}  {first}")
    return 0


def cmd_show(args) -> int:
    item = q.get(args.id)
    if item is None:
        print(f"no item {args.id}", file=sys.stderr)
        return 1
    print(q.render_card(item, show_hash=sys.stdout.isatty()))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--status", choices=q.STATUSES); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("review"); p.add_argument("ids", nargs="*")
    p.set_defaults(fn=lambda a: report(q.review_on_tty(a.ids or None)))
    p = sub.add_parser("reject"); p.add_argument("ids", nargs="+")
    p.set_defaults(fn=lambda a: report(q.reject(a.ids, note="rejected via cli")))
    p = sub.add_parser("reconcile"); p.add_argument("id"); p.add_argument("outcome", choices=("sent", "failed"))
    p.add_argument("--note", required=True)
    p.set_defaults(fn=lambda a: (print(f"{a.id}  {q.reconcile(a.id, a.outcome, a.note)['status']}"), 0)[1])
    args = ap.parse_args()
    warnings.simplefilter("always", RuntimeWarning)
    try:
        return args.fn(args)
    except q.ApprovalError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 3
    except (ValueError, KeyError) as e:  # e.g. ledger path inside the repo
        print(f"✗ {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
