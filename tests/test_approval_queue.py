"""The approval queue: integrity of what gets sent, and who can approve it.

No network and no real ledger: every test points the ledger at a temp directory
and blocks sockets, so a test that tried to reach a platform would fail instead
of posting.
"""
from __future__ import annotations

import errno
import os
import re
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

from lib import approval_queue as q
from lib import backend_selector

try:
    import requests  # noqa: F401
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

ACCT = "linkedin-abc"
POST = dict(kind="post", text="Shipped the thing.\n\nIt works.", target="https://www.linkedin.com/post/new/",
            accounts=[ACCT], scheduled_time="2026-11-03T13:00:00Z")
COMMENT = dict(kind="comment", text="Nice point.", target="https://www.linkedin.com/feed/update/urn:li:share:1/",
               accounts=[ACCT], post_urn="urn:li:share:1", reaction_type="LIKE")
REPLY = dict(kind="reply", text="Thanks!", target="https://www.linkedin.com/feed/update/urn:li:share:1/",
             accounts=[ACCT], post_urn="urn:li:share:1", parent_comment="urn:li:comment:(urn:li:share:1,9)")


def _no_network(*_a, **_k):
    raise AssertionError("a test tried to open a network connection")


class FakeTTY:
    """Stands in for /dev/tty: answers the a/r/s prompts from a script and types
    back the confirmation code it was shown (or a wrong one)."""

    def __init__(self, answers, code_ok=True, on_code=None):
        self.answers, self.code_ok, self.on_code = list(answers), code_ok, on_code
        self.out = ""

    def close(self):
        pass

    def write(self, s):
        self.out += s

    def readline(self):
        if self.out.rstrip().endswith("to confirm:"):
            if self.on_code:
                self.on_code()
            code = re.search(r"code (\w{6}) ", self.out).group(1)
            return (code if self.code_ok else "nope") + "\n"
        return self.answers.pop(0) + "\n"


def review(ids, tty):
    """Run the human review against a fake terminal (the only seam: `_open_tty`)."""
    with mock.patch.object(q, "_open_tty", return_value=tty):
        return q.review_on_tty(ids)


def human_approves(*items):
    """The human path: review on a (fake) terminal, answering 'a' for each."""
    return review([i["id"] for i in items], FakeTTY(["a"] * len(items)))


class QueueCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = Path(tmp.name) / "queue.jsonl"
        env = mock.patch.dict(os.environ, {q.ENV_PATH: str(self.ledger)})
        env.start()
        self.addCleanup(env.stop)
        for var in (q.ENV_REQUIRE, "LINKEDIN_PLATFORM_ID"):
            os.environ.pop(var, None)
        for p in (mock.patch.object(socket.socket, "connect", _no_network),
                  mock.patch.object(socket, "create_connection", _no_network)):
            p.start()
            self.addCleanup(p.stop)


class Hashing(QueueCase):
    def test_hash_is_stable_and_pinned(self):
        h = q.approval_hash(**POST)
        self.assertEqual(h, q.approval_hash(**dict(POST)))
        # Pinned: changing the canonical form silently would void every approval.
        self.assertEqual(h, "7e10984d20242a1c105d7864012cfa6bb614b0ad9d16cb1de494141eba301db0")

    def test_equivalent_times_line_endings_and_account_order_hash_alike(self):
        a = q.approval_hash(**{**POST, "accounts": ["linkedin-a", "linkedin-b"]})
        b = q.approval_hash(**{**POST, "accounts": ["linkedin-b", "linkedin-a"],
                               "scheduled_time": "2026-11-03T10:00:00-03:00",
                               "text": POST["text"].replace("\n", "\r\n")})
        self.assertEqual(a, b)

    def test_every_covered_field_changes_the_hash(self):
        for base, changes in [
            (POST, {"text": "Different.", "target": "https://x/y", "accounts": ["linkedin-zzz"],
                    "scheduled_time": "2026-11-04T13:00:00Z", "media": ["https://img/1.png"],
                    "network": "x"}),
            (COMMENT, {"post_urn": "urn:li:share:2", "reaction_type": "PRAISE", "text": "Other."}),
            (REPLY, {"parent_comment": "urn:li:comment:(urn:li:share:1,10)"}),
        ]:
            ref = q.approval_hash(**base)
            for field, value in changes.items():
                self.assertNotEqual(ref, q.approval_hash(**{**base, field: value}), field)

    def test_the_whole_account_list_is_covered(self):
        one = q.approval_hash(**{**POST, "accounts": ["linkedin-a"]})
        two = q.approval_hash(**{**POST, "accounts": ["linkedin-a", "linkedin-b"]})
        self.assertNotEqual(one, two)

    def test_fields_a_kind_does_not_deliver_are_refused_at_enqueue(self):
        with self.assertRaises(ValueError):
            q.enqueue(**{**POST, "parent_comment": "urn:li:comment:1"})
        with self.assertRaises(ValueError):
            q.enqueue(**{**REPLY, "parent_comment": ""})
        with self.assertRaises(ValueError):
            q.enqueue(**{**COMMENT, "media": ["https://img/1.png"]})

    def test_a_ledger_inside_the_repo_is_refused(self):
        with mock.patch.dict(os.environ, {q.ENV_PATH: str(q.ROOT / "docs" / "queue.jsonl")}):
            with self.assertRaises(ValueError):
                q.ledger_path()
        with mock.patch.dict(os.environ, {q.ENV_PATH: str(q.ROOT / "testing" / "q.jsonl")}):
            self.assertEqual(q.ledger_path().name, "q.jsonl")


class HumanOnlyApproval(QueueCase):
    """B1. Approval comes from a person at a terminal, or it does not happen."""

    def test_there_is_no_programmatic_approve(self):
        import lib
        self.assertFalse(hasattr(q, "approve"))
        self.assertNotIn("approve", dir(lib))

    def test_review_approves_what_the_human_confirms(self):
        item = q.enqueue(**POST)
        self.assertEqual(human_approves(item), {item["id"]: "approved"})
        self.assertEqual(q.get(item["id"])["status"], "approved")

    def test_the_card_and_code_go_to_the_terminal_only(self):
        item = q.enqueue(**POST)
        tty = FakeTTY(["a"])
        review([item["id"]], tty)
        self.assertIn(item["approval_hash"], tty.out)
        self.assertIn("Shipped the thing.", tty.out)
        self.assertRegex(tty.out, r"code [0-9a-f]{6} to confirm")

    def test_without_a_terminal_it_refuses(self):
        item = q.enqueue(**POST)
        real_open = open

        def no_tty(path, *a, **k):
            if path == "/dev/tty":
                raise OSError(errno.ENXIO, "Device not configured")
            return real_open(path, *a, **k)

        with mock.patch("builtins.open", no_tty):
            with self.assertRaises(q.ApprovalError):
                q.review_on_tty([item["id"]])
        self.assertEqual(q.get(item["id"])["status"], "pending")

    def test_a_wrong_code_approves_nothing(self):
        item = q.enqueue(**POST)
        out = review([item["id"]], FakeTTY(["a"], code_ok=False))
        self.assertEqual(out, {item["id"]: "not_confirmed"})
        self.assertEqual(q.get(item["id"])["status"], "pending")

    def test_skipped_and_rejected_items_are_not_approved(self):
        a, b = q.enqueue(**POST), q.enqueue(**{**POST, "text": "Second."})
        out = review(None, FakeTTY(["s", "r"]))
        self.assertEqual(out, {a["id"]: "skipped", b["id"]: "rejected"})
        self.assertEqual(q.get(a["id"])["status"], "pending")
        self.assertEqual(q.get(b["id"])["status"], "rejected")

    def test_an_edit_while_the_card_is_open_comes_back_stale(self):
        item = q.enqueue(**POST)
        tty = FakeTTY(["a"], on_code=lambda: q.edit(item["id"], text="Changed under the card."))
        self.assertEqual(review([item["id"]], tty), {item["id"]: "stale"})
        self.assertEqual(q.get(item["id"])["status"], "pending")

    def test_only_no_terminal_errnos_are_reported_as_no_terminal(self):
        real_open = open

        def failing(errno_):
            def opener(path, *a, **k):
                if path == "/dev/tty":
                    raise OSError(errno_, os.strerror(errno_))
                return real_open(path, *a, **k)
            return opener

        for e in (errno.ENXIO, errno.ENOTTY, errno.ENODEV):
            with mock.patch("builtins.open", failing(e)):
                with self.assertRaises(q.ApprovalError) as ctx:
                    q._TTY()
            self.assertIn("no controlling terminal", str(ctx.exception))
        with mock.patch("builtins.open", failing(errno.EACCES)):
            with self.assertRaises(q.ApprovalError) as ctx:
                q._TTY()
        self.assertNotIn("no controlling terminal", str(ctx.exception))
        self.assertIn("could not open", str(ctx.exception))

    def test_the_terminal_is_opened_as_two_handles_not_one_rplus(self):
        opened = []
        real_open = open

        def spy(path, mode="r", *a, **k):
            if path == "/dev/tty":
                opened.append(mode)
                return real_open(os.devnull, mode, *a, **k)
            return real_open(path, mode, *a, **k)

        with mock.patch("builtins.open", spy):
            q._TTY().close()
        self.assertEqual(sorted(opened), ["r", "w"])

    def test_review_takes_no_terminal_parameter(self):
        import inspect
        self.assertEqual(list(inspect.signature(q.review_on_tty).parameters), ["item_ids"])

    def test_an_older_schema_item_renders_and_is_marked_stale_not_a_crash(self):
        old = {"id": "old1", "kind": "post", "network": "linkedin", "account": "linkedin-abc",
               "target": "https://x/", "post_urn": "", "parent_comment": "", "text": "Old schema text.",
               "scheduled_time": None, "media": [], "status": "pending", "origin": {},
               "dedupe_key": "k", "approval_hash": "a" * 64, "remote": None}
        import json
        self.ledger.write_text(json.dumps({"ts": "2026-10-25T00:00:00Z", "event": "enqueued",
                                           "note": "", "item": old}) + "\n", encoding="utf-8")
        card = q.render_card(q.get("old1"), show_hash=True)  # no KeyError
        self.assertIn("Old schema text.", card)
        self.assertIn("STALE", card)
        tty = FakeTTY(["a"])
        self.assertEqual(review(["old1"], tty), {"old1": "stale"})
        self.assertEqual(q.get("old1")["status"], "pending")
        self.assertIn("STALE", tty.out)
        self.assertEqual(q.render_card({"id": "bare", "text": "x"}, show_hash=False).count("STALE"), 1)

    def test_a_real_pty_review_end_to_end(self):
        """The whole human path in a real pseudo-terminal: run the CLI, read the
        card, type the decision, type the code it printed, find the item approved.
        This is what a single r+ handle on /dev/tty broke."""
        try:
            import pty
            if not hasattr(os, "fork"):
                raise ImportError
        except ImportError:
            self.skipTest("no pty/fork on this platform")
        item = q.enqueue(**POST)
        try:
            pid, fd = pty.fork()
        except OSError as exc:
            self.skipTest(f"pty unavailable: {exc}")
        if pid == 0:  # child: its controlling terminal is the pty slave
            try:
                os.execv(sys.executable, [sys.executable, str(q.ROOT / "scripts" / "approval_queue.py"), "review"])
            finally:
                os._exit(127)
        seen = b""

        def read_until(marker: bytes, timeout=30.0):
            nonlocal seen
            deadline = time.time() + timeout
            while marker not in seen:
                left = deadline - time.time()
                if left <= 0 or not select.select([fd], [], [], left)[0]:
                    raise AssertionError(f"timed out waiting for {marker!r}; saw: {seen[-400:]!r}")
                try:
                    chunk = os.read(fd, 4096)
                except OSError:  # child closed the terminal
                    break
                if not chunk:
                    break
                seen += chunk

        try:
            read_until(b"kip > ")
            self.assertIn(item["approval_hash"].encode(), seen)
            os.write(fd, b"a\n")
            read_until(b"to confirm:")
            code = re.search(rb"code ([0-9a-f]{6}) to confirm", seen).group(1)
            os.write(fd, code + b"\n")
            try:
                read_until(b"\x00never", timeout=5)  # drain until the child exits
            except AssertionError:
                pass
            _, status = os.waitpid(pid, 0)
        except BaseException:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            raise
        finally:
            os.close(fd)
        self.assertTrue(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, f"status {status}; saw {seen[-400:]!r}")
        self.assertEqual(q.get(item["id"])["status"], "approved")

    def cli(self, *args):
        # A new session has no controlling terminal, like an agent's shell.
        return subprocess.run([sys.executable, str(q.ROOT / "scripts" / "approval_queue.py"), *args],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              start_new_session=True, timeout=60)

    def test_cli_review_refuses_without_a_terminal_and_nothing_changes(self):
        item = q.enqueue(**POST)
        r = self.cli("review")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(q.get(item["id"])["status"], "pending")

    def test_cli_has_no_approve_command(self):
        self.assertNotEqual(self.cli("approve", "x:y").returncode, 0)

    def test_the_hash_is_not_in_piped_output(self):
        item = q.enqueue(**POST)
        for args in (("list",), ("show", item["id"])):
            r = self.cli(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(item["approval_hash"], r.stdout)
            self.assertNotIn(item["approval_hash"][:12], r.stdout)
        self.assertIn("Shipped the thing.", self.cli("show", item["id"]).stdout)

    def test_the_card_makes_hidden_characters_visible(self):
        hostile = "Hello ‮evil‬ \x1b[2Jclear ​zero"
        item = q.enqueue(**{**POST, "text": hostile, "target": "https://x/‮y"})
        card = q.render_card(item, show_hash=False)
        for raw in ("‮", "‬", "\x1b", "​"):
            self.assertNotIn(raw, card)
        self.assertIn("\\u202e", card)
        self.assertIn("\\u001b", card)
        self.assertIn("shown as", card)
        self.assertNotIn(item["approval_hash"], card)


class Lifecycle(QueueCase):
    def test_editing_invalidates_the_approval(self):
        item = q.enqueue(**POST)
        human_approves(item)
        edited = q.edit(item["id"], text="Rewritten after approval.")
        self.assertEqual(edited["status"], "pending")
        self.assertNotEqual(edited["approval_hash"], item["approval_hash"])

    def test_a_no_op_edit_keeps_the_approval(self):
        item = q.enqueue(**POST)
        human_approves(item)
        q.edit(item["id"], text=POST["text"])
        self.assertEqual(q.get(item["id"])["status"], "approved")

    def test_dedupe_returns_the_existing_item(self):
        first = q.enqueue(**POST)
        again = q.enqueue(**POST)
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(q.list_items()), 1)

    def test_a_rejected_item_can_be_enqueued_again(self):
        first = q.enqueue(**POST)
        q.reject([first["id"]])
        self.assertNotEqual(q.enqueue(**POST)["id"], first["id"])

    def test_edit_into_a_duplicate_is_refused(self):
        q.enqueue(**POST)
        other = q.enqueue(**{**POST, "text": "Other."})
        with self.assertRaises(ValueError):
            q.edit(other["id"], text=POST["text"])

    def test_history_keeps_every_event(self):
        item = q.enqueue(**POST)
        human_approves(item)
        q.edit(item["id"], text="v2")
        self.assertEqual([e["event"] for e in q.history(item["id"])],
                         ["enqueued", "approved", "edited"])

    def test_ledger_file_is_private(self):
        q.enqueue(**POST)
        self.assertEqual(self.ledger.stat().st_mode & 0o777, 0o600)

    def test_appending_does_not_need_os_pread(self):
        """os.pread does not exist on Windows; the newline check must not use it."""
        with mock.patch.object(os, "pread", create=True, side_effect=AssertionError("pread used")):
            q.enqueue(**POST)
            with open(self.ledger, "a", encoding="utf-8") as f:
                f.write("{broken")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                q.enqueue(**{**POST, "text": "Second."})
        self.assertEqual(len(self.ledger.read_text(encoding="utf-8").splitlines()), 3)

    def test_a_truncated_line_is_skipped_with_a_warning_not_fatal(self):
        keep = q.enqueue(**POST)
        with open(self.ledger, "a", encoding="utf-8") as f:
            f.write('{"ts": "2026-11-01T00:00:00Z", "event": "enq')  # crash mid-write, no newline
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual([i["id"] for i in q.list_items()], [keep["id"]])
        self.assertTrue(any("unreadable line" in str(w.message) for w in caught))
        # the next append starts a fresh line instead of gluing onto the broken one
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            later = q.enqueue(**{**POST, "text": "After the crash."})
            self.assertEqual({i["id"] for i in q.list_items()}, {keep["id"], later["id"]})


class GateCase(QueueCase):
    """Dispatch and backend mocked: a refusal is proven by the mock never being called."""

    def setUp(self):
        super().setUp()
        for p in (mock.patch.object(backend_selector, "_dispatch",
                                    return_value={"postGroupId": "pg1", "status": "scheduled"}),
                  mock.patch.object(backend_selector, "active_backend", return_value="publora")):
            m = p.start()
            self.addCleanup(p.stop)
            if p.attribute == "_dispatch":
                self.dispatch = m

    def approved(self, fields=POST):
        item = q.enqueue(**fields)
        human_approves(item)
        return item

    def post(self, h, **over):
        args = dict(draft_text=POST["text"], target_url=POST["target"],
                    platforms=[ACCT], scheduled_time=POST["scheduled_time"])
        args.update(over)
        return backend_selector.publish("post", approved_hash=h, **args)



class PublishGate(GateCase):
    """lib.publish with and without approved_hash."""

    # -- the basic gate
    def test_matching_hash_sends_and_marks_sent(self):
        item = self.approved()
        self.assertEqual(self.post(item["approval_hash"])["postGroupId"], "pg1")
        self.dispatch.assert_called_once()
        self.assertNotIn("approved_hash", self.dispatch.call_args.kwargs)
        self.assertEqual(q.get(item["id"])["status"], "sent")
        self.assertEqual(q.get(item["id"])["remote"]["postGroupId"], "pg1")

    def test_diverging_content_is_refused_and_nothing_is_sent(self):
        item = self.approved()
        for over in ({"draft_text": "Quietly changed."}, {"scheduled_time": "2026-11-09T13:00:00Z"},
                     {"platforms": ["linkedin-other"]}, {"media_urls": ["https://img/1.png"]},
                     {"target_url": "https://elsewhere/"}):
            with self.assertRaises(q.ApprovalMismatch):
                self.post(item["approval_hash"], **over)
        self.dispatch.assert_not_called()
        self.assertEqual(q.get(item["id"])["status"], "approved")

    def test_unapproved_or_edited_hash_is_refused(self):
        pending = q.enqueue(**POST)
        with self.assertRaises(q.ApprovalError):
            self.post(pending["approval_hash"])
        human_approves(pending)
        q.edit(pending["id"], text="Edited later.")
        with self.assertRaises(q.ApprovalError):
            self.post(pending["approval_hash"])
        self.dispatch.assert_not_called()

    def test_without_a_hash_publish_is_unchanged(self):
        backend_selector.publish("post", "Plain text", "https://www.linkedin.com/post/new/",
                                 platforms=[ACCT])
        self.dispatch.assert_called_once_with("post", "Plain text", "https://www.linkedin.com/post/new/",
                                              platforms=[ACCT])
        self.assertFalse(self.ledger.exists())

    def test_publish_signature_is_unchanged(self):
        import inspect
        self.assertEqual(list(inspect.signature(backend_selector.publish).parameters),
                         ["kind", "draft_text", "target_url", "kwargs"])

    # -- B2: one approval, one send
    def test_sending_is_recorded_before_the_dispatch(self):
        item = self.approved()
        seen = []
        self.dispatch.side_effect = lambda *a, **k: (seen.append(q.get(item["id"])["status"]),
                                                     {"postGroupId": "pg1"})[1]
        self.post(item["approval_hash"])
        self.assertEqual(seen, ["sending"])

    def test_the_same_hash_cannot_send_twice(self):
        item = self.approved()
        self.post(item["approval_hash"])
        with self.assertRaises(q.ApprovalError):
            self.post(item["approval_hash"])
        self.assertEqual(self.dispatch.call_count, 1)

    def test_two_concurrent_callers_dispatch_once(self):
        item = self.approved()
        self.dispatch.side_effect = lambda *a, **k: (time.sleep(0.3), {"postGroupId": "pg1"})[1]
        outcomes, gate = [], threading.Barrier(2)

        def go():
            gate.wait()
            try:
                self.post(item["approval_hash"])
                outcomes.append("sent")
            except q.ApprovalError:
                outcomes.append("refused")

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(outcomes), ["refused", "sent"])
        self.assertEqual(self.dispatch.call_count, 1)

    def test_any_baseexception_leaves_unknown_and_reraises(self):
        for exc in (KeyboardInterrupt(), SystemExit(1), TimeoutError("read timed out")):
            with self.subTest(exc=type(exc).__name__):
                item = self.approved({**POST, "text": f"post {type(exc).__name__}"})
                self.dispatch.side_effect = exc
                with self.assertRaises(type(exc)):
                    self.post(item["approval_hash"], draft_text=f"post {type(exc).__name__}")
                self.assertEqual(q.get(item["id"])["status"], "unknown")

    def test_unknown_blocks_resend_and_reenqueue_until_reconciled(self):
        item = self.approved()
        self.dispatch.side_effect = TimeoutError("read timed out")
        with self.assertRaises(TimeoutError):
            self.post(item["approval_hash"])
        self.dispatch.side_effect = None
        with self.assertRaises(q.ApprovalError) as ctx:
            self.post(item["approval_hash"])
        self.assertIn("reconcile", str(ctx.exception))
        self.assertTrue(q.enqueue(**POST)["duplicate"])
        # a human checks the platform and records the answer, with a note
        with self.assertRaises(ValueError):
            q.reconcile(item["id"], "failed", "  ")
        q.reconcile(item["id"], "failed", "checked the Publora dashboard: no such post")
        self.assertEqual(q.get(item["id"])["status"], "failed")
        self.assertNotIn("duplicate", q.enqueue(**POST))
        self.assertEqual(q.history(item["id"])[-1]["event"], "reconciled")

    def test_only_sending_or_unknown_items_are_reconciled(self):
        item = q.enqueue(**POST)
        with self.assertRaises(q.ApprovalError):
            q.reconcile(item["id"], "sent", "n/a")

    def test_manual_tier_sends_nothing_and_releases_the_claim(self):
        item = self.approved()
        self.dispatch.return_value = {"mode": "manual", "message": "paste it"}
        self.post(item["approval_hash"])
        self.assertEqual(q.get(item["id"])["status"], "approved")

    # -- B3: the hash covers what is delivered
    def test_the_whole_account_list_must_match(self):
        item = self.approved({**POST, "accounts": ["linkedin-a", "linkedin-b"]})
        for platforms in (["linkedin-a"], ["linkedin-a", "linkedin-b", "linkedin-c"]):
            with self.assertRaises(q.ApprovalMismatch):
                self.post(item["approval_hash"], platforms=platforms)
        self.dispatch.assert_not_called()
        self.post(item["approval_hash"], platforms=[{"platform": "linkedin", "platformId": "linkedin-b"},
                                                    "linkedin-a"])
        self.dispatch.assert_called_once()

    def test_a_default_account_from_the_environment_is_part_of_the_hash(self):
        with mock.patch.dict(os.environ, {"LINKEDIN_PLATFORM_ID": "linkedin-env"}):
            item = self.approved({**POST, "accounts": q.resolve_accounts("post")})
            self.assertEqual(item["accounts"], ["linkedin-env"])
            backend_selector.publish("post", POST["text"], POST["target"],
                                     approved_hash=item["approval_hash"],
                                     scheduled_time=POST["scheduled_time"])
        self.dispatch.assert_called_once()

    def test_no_resolvable_account_is_refused_on_a_real_backend(self):
        item = self.approved({**POST, "accounts": []})
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish("post", POST["text"], POST["target"],
                                     approved_hash=item["approval_hash"],
                                     scheduled_time=POST["scheduled_time"])
        self.dispatch.assert_not_called()

    def test_reaction_type_is_covered(self):
        item = self.approved(COMMENT)
        common = dict(draft_text=COMMENT["text"], target_url=COMMENT["target"], post_urn=COMMENT["post_urn"],
                      platform_id=ACCT, approved_hash=item["approval_hash"])
        for reaction in ("PRAISE", None):
            with self.assertRaises(q.ApprovalMismatch):
                backend_selector.publish("comment", reaction_type=reaction, **common)
        self.dispatch.assert_not_called()
        backend_selector.publish("comment", reaction_type="LIKE", **common)
        self.dispatch.assert_called_once()

    def test_a_kwarg_the_hash_does_not_cover_is_refused(self):
        item = self.approved()
        for extra in ({"visibility": "CONNECTIONS"}, {"parent": "urn:li:share:9"}, {"anything": 1}):
            with self.assertRaises(q.ApprovalError) as ctx:
                self.post(item["approval_hash"], **extra)
            self.assertIn("not covered", str(ctx.exception))
        self.dispatch.assert_not_called()
        self.post(item["approval_hash"], reaction_type=None)  # None carries nothing
        self.dispatch.assert_called_once()

    def test_a_network_with_no_adapter_is_refused(self):
        item = self.approved({**POST, "network": "x"})
        with self.assertRaises(q.ApprovalError):
            self.post(item["approval_hash"], network="x")
        self.dispatch.assert_not_called()

    # -- M1: parent_comment is the same on both sides
    def test_reply_binds_its_parent_comment_both_ways(self):
        c = self.approved(REPLY)
        common = dict(draft_text=REPLY["text"], target_url=REPLY["target"], post_urn=REPLY["post_urn"],
                      platform_id=ACCT, approved_hash=c["approval_hash"])
        with self.assertRaises(q.ApprovalMismatch):  # wrong parent
            backend_selector.publish("reply", parent_comment="urn:li:comment:(urn:li:share:1,10)", **common)
        with self.assertRaises(q.ApprovalMismatch):  # parent dropped: would become a top-level comment
            backend_selector.publish("reply", **common)
        self.dispatch.assert_not_called()
        backend_selector.publish("reply", parent_comment=REPLY["parent_comment"], **common)
        self.dispatch.assert_called_once()

    def test_a_comment_cannot_smuggle_a_parent_comment(self):
        c = self.approved(COMMENT)
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish("comment", COMMENT["text"], COMMENT["target"], post_urn=COMMENT["post_urn"],
                                     platform_id=ACCT, reaction_type="LIKE",
                                     parent_comment="urn:li:comment:1", approved_hash=c["approval_hash"])
        self.dispatch.assert_not_called()

    # -- I2: require approval; reshare
    def test_require_approval_refuses_a_publish_without_a_hash(self):
        with mock.patch.dict(os.environ, {q.ENV_REQUIRE: "1"}):
            with self.assertRaises(q.ApprovalError) as ctx:
                backend_selector.publish("post", "No hash", POST["target"], platforms=[ACCT])
            self.assertIn(q.ENV_REQUIRE, str(ctx.exception))
        self.dispatch.assert_not_called()

    def test_reshare_and_repost_are_outside_v1_with_a_clear_error(self):
        with mock.patch.dict(os.environ, {q.ENV_REQUIRE: "1"}):
            with self.assertRaises(q.ApprovalError) as ctx:
                backend_selector.publish("reshare", "", "https://www.linkedin.com/feed/update/x/",
                                         parent="urn:li:share:1")
            self.assertIn("reshare", str(ctx.exception))
            with self.assertRaises(q.ApprovalError):
                backend_selector.repost("https://www.linkedin.com/feed/update/x/", parent="urn:li:share:1")
        with self.assertRaises(q.ApprovalError):  # also when a hash is passed
            backend_selector.publish("reshare", "", "u", parent="p", approved_hash="0" * 64)
        self.dispatch.assert_not_called()

    def test_reshare_without_the_switch_still_works(self):
        backend_selector.publish("reshare", "", "u", parent="urn:li:share:1")
        self.dispatch.assert_called_once()


@unittest.skipUnless(HAVE_REQUESTS, "needs requests for the real PubloraError")
class ErrorClassification(GateCase):
    """I1. Failed only when certain; decided by HTTP status, not by names."""

    def real_error(self, status):
        from lib.publora_client import PubloraClient
        r = mock.Mock(status_code=status)
        r.json.return_value = {"error": "x"}
        try:
            PubloraClient._handle(r)
        except Exception as exc:  # the real PubloraError, built by the real code
            return exc
        raise AssertionError("no error raised")

    def test_status_decides(self):
        for status, want in [(400, "failed"), (401, "failed"), (403, "failed"), (404, "failed"),
                             (409, "failed"), (422, "failed"), (408, "unknown"), (429, "unknown"),
                             (500, "unknown"), (502, "unknown"), (503, "unknown"), (504, "unknown")]:
            self.assertEqual(q.classify_error(self.real_error(status)), want, status)

    def test_nothing_is_decided_by_name_or_message(self):
        self.assertEqual(q.classify_error(RuntimeError("HTTP 400: bad request")), "unknown")
        fake = type("PubloraError", (RuntimeError,), {})("HTTP 400")
        self.assertEqual(q.classify_error(fake), "unknown")
        for exc in (TimeoutError(), ConnectionError(), KeyboardInterrupt(), ValueError("x")):
            self.assertEqual(q.classify_error(exc), "unknown")

    def test_an_error_raised_before_any_request_is_failed(self):
        from lib.publora_client import PubloraClient, PubloraError
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PubloraError) as ctx:
                PubloraClient(api_key="")
        self.assertEqual(q.classify_error(ctx.exception), "failed")

    def test_end_to_end_a_400_is_failed_and_a_503_is_unknown(self):
        for status, want in ((400, "failed"), (503, "unknown")):
            item = self.approved({**POST, "text": f"status {status}"})
            self.dispatch.side_effect = self.real_error(status)
            with self.assertRaises(Exception):
                self.post(item["approval_hash"], draft_text=f"status {status}")
            self.assertEqual(q.get(item["id"])["status"], want, status)


class AgentHelpers(GateCase):
    """lib.enqueue_for_review / lib.publish_approved: what the skills call."""

    def test_enqueue_sends_nothing_and_resolves_the_account(self):
        with mock.patch.dict(os.environ, {"LINKEDIN_PLATFORM_ID": "linkedin-env"}):
            item = backend_selector.enqueue_for_review("post", "Hello.", POST["target"])
        self.assertEqual((item["status"], item["accounts"]), ("pending", ["linkedin-env"]))
        self.dispatch.assert_not_called()

    def test_a_pending_item_is_not_published(self):
        item = backend_selector.enqueue_for_review("post", "Hello.", POST["target"], platforms=[ACCT])
        with self.assertRaises(q.ApprovalError) as ctx:
            backend_selector.publish_approved(item["id"])
        self.assertIn("approval_queue.py review", str(ctx.exception))
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish_approved("nope")
        self.dispatch.assert_not_called()

    def test_each_kind_round_trips_through_the_gate(self):
        cases = [
            ("post", "Hello.", POST["target"], dict(platforms=[ACCT], scheduled_time="2026-11-03T13:00:00Z",
                                                    media_urls=["https://img/1.png"])),
            ("comment", "Nice.", COMMENT["target"], dict(post_urn="urn:li:share:1", platform_id=ACCT,
                                                         reaction_type="LIKE")),
            ("reply", "Thanks!", REPLY["target"], dict(post_urn="urn:li:share:1", platform_id=ACCT,
                                                       parent_comment=REPLY["parent_comment"],
                                                       reaction_type="INTEREST")),
        ]
        for kind, text, target, kw in cases:
            with self.subTest(kind=kind):
                self.dispatch.reset_mock()
                item = backend_selector.enqueue_for_review(kind, text, target, **kw)
                human_approves(item)
                backend_selector.publish_approved(item["id"])
                self.dispatch.assert_called_once()
                args, sent = self.dispatch.call_args
                self.assertEqual((args[0], args[1], args[2]), (kind, text, target))
                self.assertEqual(q.get(item["id"])["status"], "sent")

    def test_an_edit_after_approval_blocks_publish_approved(self):
        item = backend_selector.enqueue_for_review("post", "Hello.", POST["target"], platforms=[ACCT])
        human_approves(item)
        q.edit(item["id"], text="Changed after approval.")
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish_approved(item["id"])
        self.dispatch.assert_not_called()

    def test_the_same_draft_is_not_queued_twice_and_cannot_send_twice(self):
        a = backend_selector.enqueue_for_review("post", "Hello.", POST["target"], platforms=[ACCT])
        b = backend_selector.enqueue_for_review("post", "Hello.", POST["target"], platforms=[ACCT])
        self.assertTrue(b["duplicate"])
        human_approves(a)
        backend_selector.publish_approved(a["id"])
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish_approved(a["id"])
        self.assertEqual(self.dispatch.call_count, 1)

    def test_diy_and_manual_tiers_take_an_empty_account_list(self):
        """No account configured is a normal state for these tiers. Only publora
        needs the destination known before it sends."""
        for tier in ("diy", "manual"):
            with self.subTest(tier=tier), mock.patch.object(backend_selector, "active_backend",
                                                            return_value=tier):
                self.dispatch.reset_mock()
                for kind, kw in (("post", {}), ("comment", {"post_urn": "urn:li:share:1"})):
                    item = backend_selector.enqueue_for_review(kind, f"Text {tier} {kind}.", "https://t/", **kw)
                    self.assertEqual(item["accounts"], [])
                    human_approves(item)
                    backend_selector.publish_approved(item["id"])
                self.assertEqual(self.dispatch.call_count, 2)

    def test_publora_still_refuses_an_empty_account_list(self):
        item = backend_selector.enqueue_for_review("post", "No account.", "https://t/")
        human_approves(item)
        with self.assertRaises(q.ApprovalError):
            backend_selector.publish_approved(item["id"])
        self.dispatch.assert_not_called()

    def test_reshare_is_outside_the_queue(self):
        with self.assertRaises(q.ApprovalError):
            backend_selector.enqueue_for_review("reshare", "", "https://www.linkedin.com/feed/update/x/")


class DiyRoundTrip(QueueCase):
    """The real diy dispatch, with a harmless poster script, end to end."""

    def test_enqueue_review_publish_through_a_custom_poster(self):
        poster = Path(self.ledger.parent) / "poster.py"
        out = Path(self.ledger.parent) / "got.json"
        poster.write_text("import sys\nopen(sys.argv[0] + '.out', 'w', encoding='utf-8')"
                          ".write(sys.stdin.read())\n", encoding='utf-8')
        env = {"LINKEDIN_SKILLS_CUSTOM_POSTER": f"{sys.executable} {poster}"}
        with mock.patch.dict(os.environ, env):
            for var in ("PUBLORA_API_KEY", "LINKEDIN_PLATFORM_ID"):
                os.environ.pop(var, None)
            self.assertEqual(backend_selector.active_backend(), "diy")
            item = backend_selector.enqueue_for_review("post", "Sent through my own poster.",
                                                       "https://www.linkedin.com/post/new/")
            self.assertEqual(item["accounts"], [])
            with self.assertRaises(q.ApprovalError):  # not reviewed yet
                backend_selector.publish_approved(item["id"])
            human_approves(item)
            result = backend_selector.publish_approved(item["id"])
        self.assertEqual((result["mode"], result["returncode"]), ("diy", 0))
        self.assertEqual(q.get(item["id"])["status"], "sent")
        import json
        got = json.loads(Path(str(poster) + ".out").read_text(encoding="utf-8"))
        self.assertEqual(got["draft_text"], "Sent through my own poster.")
        self.assertNotIn("approved_hash", got)


class SkillWiring(unittest.TestCase):
    """The writing skills use the queue and tell the human to review. A skill is
    a prompt, so reading its text is the only enforcement there is for the
    sentence 'never run review yourself'."""

    SKILLS = {"linkedin-post-writer": "post", "linkedin-repurposer": "post",
              "linkedin-comment-drafter": "comment", "linkedin-reply-handler": "reply"}
    CITATION = "../../references/approval-flow.md"
    #: any call written as `publish(`, with or without `lib.` and whatever the
    #: spacing. `unpublish(` and `publish_approved(` do not match.
    PUBLISH_CALL = re.compile(r"(?<![\w])(?:lib\.)?publish\s*\(([^\n]{0,160})")

    @classmethod
    def around_the_queue(cls, text):
        """publish( calls in a document that skip the queue. Allowed: a reshare,
        and a mention of the opt-in `approved_hash` gate itself."""
        bad = []
        for m in cls.PUBLISH_CALL.finditer(text):
            args = m.group(1)
            if re.search(r"""["']reshare["']""", args) or "approved_hash" in args:
                continue
            bad.append(m.group(0))
        return bad

    #: wording that would hand approval to the agent or the chat.
    FORBIDDEN = ("lib.approval_queue.review_on_tty", "approval_queue.py approve",
                 "approved_hash=<", "On approval. Call `lib.publish",
                 "On approval.** Publish via `lib.publish")

    def documents(self):
        """Every skill document, the root SKILL.md and the shared references,
        except the one that owns the flow."""
        docs = sorted((q.ROOT / "skills").rglob("*.md")) + [q.ROOT / "SKILL.md"]
        docs += [p for p in sorted((q.ROOT / "references").glob("*.md")) if p.name != "approval-flow.md"]
        return [(p, p.read_text(encoding="utf-8")) for p in docs]

    def text(self, name):
        return (q.ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def test_each_queue_skill_queues_cites_the_flow_and_publishes_approved(self):
        for name, kind in self.SKILLS.items():
            body = self.text(name)
            self.assertIn(f'lib.enqueue_for_review(kind="{kind}"', body, name)
            self.assertIn("lib.publish_approved(", body, name)
            self.assertIn(self.CITATION, body, name)
            self.assertRegex(body, r"never run `review` yourself", name)

    def test_the_publish_pattern_catches_the_variants_and_spares_the_rest(self):
        for text in ('lib.publish("post", t, u)', "publish('comment', t, u)", 'lib.publish (kind="reply", x)',
                     'publish ("post", draft_text, target_url, media_urls=urls)', "lib.publish(kind, t, u)"):
            self.assertTrue(self.around_the_queue(text), text)
        for text in ('lib.unpublish(post_group_id=1)', "lib.publish_approved(7)", 'lib.publish("reshare", "", u)',
                     "lib.publish(..., approved_hash=...)", "the publish step", "unpublish (x)"):
            self.assertFalse(self.around_the_queue(text), text)

    def test_no_markdown_calls_publish_around_the_queue(self):
        """Skills, sub-skills, the root SKILL.md and shared references. A reshare
        and the opt-in approved_hash gate are the documented exceptions."""
        for path, body in self.documents():
            self.assertEqual(self.around_the_queue(body), [], str(path))

    def test_no_skill_uses_wording_that_hands_approval_to_the_agent(self):
        for path, body in self.documents():
            for phrase in self.FORBIDDEN:
                self.assertNotIn(phrase, body, f"{path}: {phrase}")

    def test_the_flow_is_written_once(self):
        """The prose lives in the reference; a skill that repeats it drifts."""
        flow = (q.ROOT / "references" / "approval-flow.md").read_text(encoding="utf-8")
        for needle in ("duplicate", "ApprovalError", "reconcile", "terminal wins",
                       "edit(", "may have been sent", "Stop."):
            self.assertIn(needle, flow, needle)
        for name in self.SKILLS:
            self.assertNotIn("terminal wins", self.text(name), name)

    def test_reshare_keeps_working_outside_the_queue(self):
        self.assertIn("lib.repost(", self.text("linkedin-comment-drafter"))

    def test_precedence_lists_the_queue_rules(self):
        body = (q.ROOT / "references" / "precedence.md").read_text(encoding="utf-8")
        flat = " ".join(body.split())
        self.assertIn("enqueue_for_review", flat)
        self.assertIn("never runs `review`", flat)
        self.assertIn("approval-flow.md", flat)

    def test_agents_md_carries_the_precedence_paragraph(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            body = " ".join((q.ROOT / name).read_text(encoding="utf-8").split())
            self.assertIn("references/precedence.md` is the resolution order", body, name)
            self.assertIn("references/approval-flow.md` is the one copy", body, name)

    def test_approval_queue_is_importable_from_lib_in_a_fresh_process(self):
        """`lib.approval_queue.get` / `.edit` are cited in the skills; a fresh
        interpreter must find them without anyone importing the module first."""
        code = ("import sys; import lib; "
                "assert 'requests' not in sys.modules, 'pulled in a third-party dependency'; "
                "lib.approval_queue.get; lib.approval_queue.edit; print('ok')")
        r = subprocess.run([sys.executable, "-c", code], cwd=q.ROOT, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "ok"), r.stderr)

    def test_the_approval_flow_example_calls_exist(self):
        import lib
        flow = (q.ROOT / "references" / "approval-flow.md").read_text(encoding="utf-8")
        for fn in re.findall(r"lib\.([a-z_]+)\(", flow):
            self.assertTrue(hasattr(lib, fn), fn)
        self.assertTrue(hasattr(q, "edit") and hasattr(q, "get"))


@unittest.skipUnless(HAVE_REQUESTS, "needs requests")
class SingleAttemptRetry(QueueCase):
    """Behind the gate a POST is never repeated unless it certainly was not
    processed. Without the gate the retry is exactly what it was."""

    def setUp(self):
        super().setUp()
        import requests as rq
        from lib import publora_client as pc
        self.rq, self.pc = rq, pc
        sleep = mock.patch.object(pc.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.client = pc.PubloraClient(api_key="k")

    def reply(self, status, body=None):
        r = mock.Mock(status_code=status)
        r.json.return_value = body if body is not None else {"success": True, "postGroupId": "pg"}
        return r

    def run_post(self, effects, gated):
        self.client._session = mock.Mock()
        self.client._session.post.side_effect = effects
        try:
            if gated:
                with q.single_attempt():
                    return self.client._post("/create-post", {"content": "x"}), self.client._session.post.call_count
            return self.client._post("/create-post", {"content": "x"}), self.client._session.post.call_count
        except BaseException as exc:
            return exc, self.client._session.post.call_count

    def test_gated_5xx_is_not_repeated(self):
        for status in (500, 502, 503, 504, 408):
            exc, calls = self.run_post([self.reply(status), self.reply(200)], gated=True)
            self.assertIsInstance(exc, self.pc.PubloraError, status)
            self.assertEqual(calls, 1, status)

    def test_gated_timeout_and_dropped_connection_are_not_repeated(self):
        for err in (self.rq.ReadTimeout("slow"), self.rq.ConnectionError("reset by peer")):
            exc, calls = self.run_post([err, self.reply(200)], gated=True)
            self.assertIs(exc, err)
            self.assertEqual(calls, 1)

    def test_gated_429_is_repeated(self):
        out, calls = self.run_post([self.reply(429), self.reply(200)], gated=True)
        self.assertEqual(out["postGroupId"], "pg")
        self.assertEqual(calls, 2)

    def test_gated_error_before_connecting_is_repeated(self):
        from urllib3.exceptions import MaxRetryError, NewConnectionError
        refused = self.rq.ConnectionError(MaxRetryError(None, "/", NewConnectionError(None, "refused")))
        for first in (self.rq.ConnectTimeout("connect timed out"), refused):
            out, calls = self.run_post([first, self.reply(200)], gated=True)
            self.assertEqual(calls, 2, type(first).__name__)
            self.assertEqual(out["postGroupId"], "pg")

    def test_without_the_gate_the_retry_is_unchanged(self):
        out, calls = self.run_post([self.reply(503), self.reply(503), self.reply(200)], gated=False)
        self.assertEqual((out["postGroupId"], calls), ("pg", 3))
        out, calls = self.run_post([self.rq.ReadTimeout("slow"), self.reply(200)], gated=False)
        self.assertEqual((out["postGroupId"], calls), ("pg", 2))
        exc, calls = self.run_post([self.reply(400), self.reply(200)], gated=False)
        self.assertEqual(calls, 1)  # 4xx was never retried

    def test_end_to_end_through_publish_a_503_posts_once_and_is_unknown(self):
        env = {"PUBLORA_API_KEY": "k", "LINKEDIN_PLATFORM_ID": ACCT}
        with mock.patch.dict(os.environ, env):
            item = q.enqueue(**POST)
            human_approves(item)
            with mock.patch.object(self.rq.Session, "post",
                                   side_effect=[self.reply(503), self.reply(200)]) as post:
                with self.assertRaises(self.pc.PubloraError):
                    backend_selector.publish("post", POST["text"], POST["target"],
                                             approved_hash=item["approval_hash"], platforms=[ACCT],
                                             scheduled_time=POST["scheduled_time"])
            self.assertEqual(post.call_count, 1)
        self.assertEqual(q.get(item["id"])["status"], "unknown")
        self.assertFalse(q.single_attempt_active())  # the switch is off again afterwards

    def test_no_idempotency_key_is_sent(self):
        self.client._session = mock.Mock()
        self.client._session.post.return_value = self.reply(200)
        self.client.create_post(content="x", platforms=[ACCT])
        sent = self.client._session.post.call_args.kwargs["json"]
        self.assertFalse([k for k in sent if "idempot" in k.lower()])
        self.assertFalse([k for k in self.client._session.post.call_args.kwargs.get("headers", {})
                          if "idempot" in k.lower()])


if __name__ == "__main__":
    unittest.main()
