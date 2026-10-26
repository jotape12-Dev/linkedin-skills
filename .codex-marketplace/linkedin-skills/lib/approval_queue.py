"""Local approval queue: what the user approved is what gets sent.

An item is a draft (post, comment or reply) plus everything that decides where
it lands. `approval_hash` is a SHA-256 over those fields, so editing any of them
changes the hash and the earlier approval stops applying.

What this proves and what it does not
  - Integrity: the text, target and accounts did not change between the card the
    user saw and the call that sent it.
  - Human approval is only as strong as the terminal: `review_on_tty` reads the
    decision and a random confirmation code from /dev/tty, never from stdin or
    arguments, and there is no programmatic `approve`. That is a barrier for an
    agent running without a controlling terminal, not a proof; an agent allowed
    to allocate its own pty could still drive it. Pair it with deny/ask rules
    (docs/architecture/approval-queue.md).

Status flow
  pending -> approved -> sending -> sent | failed | unknown
  `sending` is written under a file lock BEFORE the dispatch, and only the
  caller that made that transition dispatches. An item left in `sending` or
  `unknown` blocks re-enqueue and resend until a human reconciles it.

Storage is an append-only JSONL ledger, one event per line carrying the full
item snapshot; the current state of an item is its last line. It holds
unpublished text and account ids, so it must live outside version control:
default `testing/approval-queue.jsonl` (gitignored), or `LINKEDIN_SKILLS_QUEUE_PATH`.
A path inside the repo but outside `testing/` is refused.

No network, no third-party imports: manual-tier users can import this.
"""
from __future__ import annotations

import contextlib
import contextvars
import errno
import hashlib
import json
import os
import secrets
import threading
import unicodedata
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

try:  # POSIX only
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "testing" / "approval-queue.jsonl"
ENV_PATH = "LINKEDIN_SKILLS_QUEUE_PATH"
ENV_REQUIRE = "LINKEDIN_SKILLS_REQUIRE_APPROVAL"

KINDS = ("post", "comment", "reply")
STATUSES = ("pending", "approved", "sending", "sent", "failed", "unknown", "rejected")
#: Statuses that still occupy a dedupe slot. failed and rejected may be queued
#: again; sending, unknown and sent may not (they may have gone out).
ACTIVE = ("pending", "approved", "sending", "sent", "unknown")
EDITABLE = ("network", "accounts", "target", "post_urn", "parent_comment",
            "reaction_type", "text", "scheduled_time", "media")
HASH_VERSION = "v2"

#: kwargs `lib.publish` may carry for each kind while gated. Anything else is
#: refused: a kwarg the hash does not cover could change what is delivered.
ALLOWED_KWARGS = {
    "post": {"platforms", "platform_id", "scheduled_time", "media_urls", "network"},
    "comment": {"post_urn", "platform_id", "reaction_type", "network"},
    "reply": {"post_urn", "parent_comment", "platform_id", "reaction_type", "network"},
}


class ApprovalError(Exception):
    """The call is not backed by an approved item, or approval cannot happen here."""


class ApprovalMismatch(ApprovalError):
    """The call's content differs from what was approved."""


def approval_required() -> bool:
    """True when LINKEDIN_SKILLS_REQUIRE_APPROVAL is set: `lib.publish` then
    refuses any call that carries no approved_hash."""
    return os.getenv(ENV_REQUIRE, "").strip().lower() in ("1", "true", "yes", "on")


# --- ledger, lock ------------------------------------------------------------

def ledger_path() -> Path:
    raw = os.getenv(ENV_PATH)
    path = Path(raw).expanduser() if raw else DEFAULT_LEDGER
    resolved = path.resolve()
    try:
        inside = resolved.relative_to(ROOT)
    except ValueError:
        return resolved
    if inside.parts and inside.parts[0] == "testing":
        return resolved
    raise ValueError(
        f"{resolved} is inside the repository. The approval ledger holds unpublished "
        f"text and must stay out of version control: use testing/ or set {ENV_PATH} "
        "to a path outside the repo."
    )


_tlock = threading.RLock()
_depth = 0


@contextlib.contextmanager
def _locked():
    """Exclusive lock for read-modify-write: a thread lock plus flock on a
    sidecar file (so other processes wait too). Re-entrant within a thread."""
    global _depth
    with _tlock:
        if _depth:
            _depth += 1
            try:
                yield
            finally:
                _depth -= 1
            return
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_EX)
            _depth = 1
            try:
                yield
            finally:
                _depth = 0
        finally:
            os.close(fd)  # closing releases the flock


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(event: str, item: dict, note: str = "") -> None:
    line = json.dumps({"ts": _now(), "event": event, "note": note, "item": item},
                      ensure_ascii=False, sort_keys=True) + "\n"
    with _locked():
        path = ledger_path()
        # A crash can leave a last line with no newline; start a fresh line so
        # the next event is not glued onto the broken one. seek/read, not
        # os.pread, which does not exist on Windows.
        if path.exists() and path.stat().st_size:
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    line = "\n" + line
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)


def _events() -> list[dict]:
    """Every readable event. A truncated or corrupt line is skipped with a
    warning instead of taking the whole queue down."""
    path = ledger_path()
    if not path.exists():
        return []
    out = []
    for n, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            ev = json.loads(raw)
            ev["item"]["id"], ev["item"]["status"], ev["event"]  # shape check
        except (ValueError, KeyError, TypeError):
            warnings.warn(f"approval ledger {path.name}: ignoring unreadable line {n}",
                          RuntimeWarning, stacklevel=2)
            continue
        out.append(ev)
    return out


def _state() -> dict[str, dict]:
    """item_id -> latest snapshot, in first-seen order."""
    items: dict[str, dict] = {}
    for ev in _events():
        items[ev["item"]["id"]] = ev["item"]
    return items


# --- hashing -----------------------------------------------------------------

def _norm_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _norm_time(value: Optional[str]) -> Optional[str]:
    """Same instant, same string: aware times become UTC `...Z`. A naive or
    unparseable value is kept as given rather than guessed at."""
    if not value:
        return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        return s
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _account_ids(platforms: Optional[Iterable]) -> list[str]:
    out = []
    for p in platforms or []:
        got = p if isinstance(p, str) else (p.get("platformId") or p.get("platform"))
        if got:
            out.append(str(got))
    return out


def resolve_accounts(kind: str, *, platform_id: Optional[str] = None,
                     platforms: Optional[list] = None) -> list[str]:
    """The accounts a `lib.publish` call will really deliver to, resolved with
    no network lookup and mirroring `backend_selector._dispatch`: a post goes to
    `platforms` if given, else to `[platform_id or LINKEDIN_PLATFORM_ID]`; a
    comment or reply goes to `platform_id or LINKEDIN_PLATFORM_ID`. Empty when
    nothing is configured. Call this to fill `accounts=` when enqueueing."""
    single = platform_id or os.getenv("LINKEDIN_PLATFORM_ID") or ""
    if kind == "post" and platforms:
        return _account_ids(platforms)
    return [single] if single else []


def _fields(*, kind, network, accounts, target, post_urn, parent_comment,
            reaction_type, text, scheduled_time, media) -> dict[str, Any]:
    if kind not in KINDS:
        raise ApprovalError(f"kind must be one of {KINDS}, got {kind!r}; "
                            "other kinds (reshare) are outside approval v1")
    if not _norm_text(text or "").strip():
        raise ValueError("text is empty")
    media = list(media or [])
    if kind == "post":
        extra = {"post_urn": post_urn, "parent_comment": parent_comment,
                 "reaction_type": reaction_type}
    else:
        extra = {"scheduled_time": scheduled_time, "media": media}
        if kind == "comment":
            extra["parent_comment"] = parent_comment
        if not post_urn:
            raise ValueError(f"a {kind} needs post_urn")
        if kind == "reply" and not parent_comment:
            raise ValueError("a reply needs parent_comment")
    stray = [k for k, v in extra.items() if v]
    if stray:
        raise ValueError(f"a {kind} does not deliver {stray}; leave them empty")
    accts = sorted({str(a) for a in (accounts or []) if a})
    return {
        "kind": kind,
        "network": network or "linkedin",
        "accounts": accts,
        "target": target or "",
        "post_urn": post_urn or "",
        "parent_comment": parent_comment or "",
        "reaction_type": reaction_type or "",
        "text": _norm_text(text),
        "scheduled_time": _norm_time(scheduled_time),
        "media": media,
    }


_FIELD_NAMES = ("kind", "network", "accounts", "target", "post_urn", "parent_comment",
                "reaction_type", "text", "scheduled_time", "media")


def approval_hash(**fields: Any) -> str:
    """Deterministic over every field in `_FIELD_NAMES`. `accounts` is the whole
    effective list (order-insensitive); `media` order matters."""
    f = _fields(**{k: fields.get(k) for k in _FIELD_NAMES})
    blob = json.dumps({"v": HASH_VERSION, **f}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _dedupe_key(f: dict) -> str:
    text_hash = hashlib.sha256(f["text"].encode("utf-8")).hexdigest()
    parts = (f["kind"], f["network"], ",".join(f["accounts"]), f["target"], f["post_urn"],
             f["parent_comment"], text_hash)
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _hash_of(item: dict) -> str:
    return approval_hash(**{k: item.get(k) for k in _FIELD_NAMES})


# --- card (what the human reads) ----------------------------------------------

def safe(value: Any) -> str:
    """Make hostile text visible: control, bidi, zero-width and unassigned
    characters are shown as \\uXXXX so a card cannot hide or reorder what it
    says. Newline and tab stay."""
    out = []
    for ch in str(value):
        if ch in "\n\t":
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def render_card(item: dict, *, show_hash: bool) -> str:
    """The exact item for review. The hash appears only when `show_hash`, which
    callers set for a terminal and never for piped output. Tolerates items from
    an older schema (missing fields show as empty; they cannot be approved)."""
    g = item.get
    raw_text = g("text") or ""
    text = safe(raw_text)
    accounts = g("accounts") or ([g("account")] if g("account") else [])
    lines = [
        f"id:       {g('id', '?')}",
        f"kind:     {safe(g('kind', '?'))}   network: {safe(g('network', '?'))}   status: {g('status', '?')}",
        f"accounts: {safe(', '.join(map(str, accounts))) or '(none)'}",
        f"target:   {safe(g('target', '')) or '(none)'}",
    ]
    if g("post_urn"):
        lines.append(f"post urn: {safe(g('post_urn'))}")
    if g("parent_comment"):
        lines.append(f"reply to: {safe(g('parent_comment'))}")
    if g("reaction_type"):
        lines.append(f"reaction: {safe(g('reaction_type'))}")
    media = g("media") or []
    lines += [
        f"when:     {safe(g('scheduled_time')) if g('scheduled_time') else 'as soon as released'}",
        f"media:    {safe(', '.join(map(str, media))) if media else '(none)'}",
    ]
    if show_hash:
        lines.append(f"hash:     {g('approval_hash', '(missing)')}")
    lines.append(f"chars:    {len(raw_text)}")
    if not _stored_hash_ok(item):
        lines.append("STALE:    fields do not match the stored hash (older schema or hand-edited); "
                     "it cannot be approved")
    if text != raw_text:
        lines.append("note:     hidden/control characters in the text are shown as \\uXXXX")
    lines += ["text (exact):", "-" * 60, text, "-" * 60]
    return "\n".join(lines)


# --- queue operations -----------------------------------------------------------

def enqueue(*, kind: str, text: str, target: str = "", accounts: Optional[Iterable[str]] = None,
            account: str = "", network: str = "linkedin", post_urn: str = "",
            parent_comment: str = "", reaction_type: str = "",
            scheduled_time: Optional[str] = None, media: Optional[Iterable[str]] = None,
            origin: Optional[dict] = None) -> dict:
    """Add a pending item. `accounts` is the full effective list the publish call
    will deliver to (see `resolve_accounts`); `account` is shorthand for one.
    If an active item with the same kind, network, accounts, target, parent and
    text exists, it is returned unchanged with `duplicate: True`."""
    accts = list(accounts or ([account] if account else []))
    f = _fields(kind=kind, network=network, accounts=accts, target=target,
                post_urn=post_urn, parent_comment=parent_comment,
                reaction_type=reaction_type, text=text,
                scheduled_time=scheduled_time, media=list(media or []))
    key = _dedupe_key(f)
    with _locked():
        for existing in _state().values():
            if existing.get("dedupe_key") == key and existing["status"] in ACTIVE:
                return {**existing, "duplicate": True}
        item = {"id": uuid.uuid4().hex, **f, "status": "pending", "origin": origin or {},
                "dedupe_key": key, "approval_hash": approval_hash(**f), "remote": None}
        _append("enqueued", item)
    return item


def get(item_id: str) -> Optional[dict]:
    return _state().get(item_id)


def list_items(status: Optional[str] = None) -> list[dict]:
    return [i for i in _state().values() if status is None or i["status"] == status]


def history(item_id: str) -> list[dict]:
    """Every readable ledger event for one item, oldest first."""
    return [ev for ev in _events() if ev["item"]["id"] == item_id]


def edit(item_id: str, **changes: Any) -> dict:
    """Change fields of a pending or approved item. A change that alters the
    hash drops any approval: the item goes back to pending."""
    bad = set(changes) - set(EDITABLE)
    if bad:
        raise ValueError(f"cannot edit {sorted(bad)}; editable: {EDITABLE}")
    with _locked():
        state = _state()
        item = state.get(item_id)
        if item is None:
            raise KeyError(item_id)
        if item["status"] not in ("pending", "approved"):
            raise ApprovalError(f"item is {item['status']}; only pending or approved items can be edited")
        new = {**item, **changes}
        f = _fields(**{k: new.get(k) for k in _FIELD_NAMES})
        new.update(f)
        new["approval_hash"] = approval_hash(**f)
        new["dedupe_key"] = _dedupe_key(f)
        if new["approval_hash"] == item.get("approval_hash"):
            return item
        for other in state.values():
            if (other["id"] != item_id and other.get("dedupe_key") == new["dedupe_key"]
                    and other["status"] in ACTIVE):
                raise ValueError(f"edit would duplicate active item {other['id']}")
        was = item["status"]
        new["status"] = "pending"
        _append("edited", new, note=f"hash changed; was {was}"
                + ("; approval invalidated" if was == "approved" else ""))
    return new


def reject(item_ids: Iterable[str], note: str = "") -> dict[str, str]:
    """Reject pending or approved items. Rejecting never sends anything."""
    results: dict[str, str] = {}
    with _locked():
        state = _state()
        for item_id in item_ids:
            item = state.get(item_id)
            if item is None:
                results[item_id] = "unknown_id"
            elif item["status"] not in ("pending", "approved"):
                results[item_id] = "not_pending"
            else:
                _append("rejected", {**item, "status": "rejected"}, note=note)
                results[item_id] = "rejected"
    return results


# --- human approval: terminal only ------------------------------------------------

#: errno values that mean "this process has no controlling terminal".
_NO_TERMINAL = (errno.ENXIO, errno.ENOTTY, errno.ENODEV)


class _TTY:
    """The controlling terminal, opened directly (not stdin, not stdout) as two
    handles, one to read and one to write: a single "r+" text file fails on a
    real pty with UnsupportedOperation."""

    def __init__(self):
        self._r = self._w = None
        try:
            self._r = open("/dev/tty", "r", encoding="utf-8", errors="replace")
            self._w = open("/dev/tty", "w", encoding="utf-8", errors="replace")
        except OSError as exc:
            self.close()
            if exc.errno in _NO_TERMINAL:
                raise ApprovalError(
                    "approval needs a human at a terminal: this process has no controlling "
                    f"terminal ({exc}). Run `python3 scripts/approval_queue.py review` yourself "
                    "in a terminal."
                ) from None
            raise ApprovalError(f"could not open /dev/tty ({exc}); approval needs a working "
                                "terminal") from None

    def write(self, s: str) -> None:
        self._w.write(s)
        self._w.flush()

    def readline(self) -> str:
        return self._r.readline()

    def close(self) -> None:
        for f in (self._r, self._w):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass


def _open_tty():
    return _TTY()


def _stored_hash_ok(item: dict) -> bool:
    """True when the item's fields still produce its stored hash. An item from an
    older schema, or a hand-edited line, fails this and cannot be approved."""
    try:
        return _hash_of(item) == item.get("approval_hash")
    except (ValueError, KeyError, TypeError, ApprovalError):
        return False


def review_on_tty(item_ids: Optional[Iterable[str]] = None) -> dict[str, str]:
    """Walk pending items on the controlling terminal; approve or reject each.

    Decisions and a random confirmation code are read from /dev/tty only. The
    code is printed to that terminal and nowhere else, so a process that cannot
    see the terminal cannot confirm. Approvals are bound to the hash shown on
    the card: an item edited while the card was open comes back `stale`.
    Returns id -> approved | rejected | skipped | stale | not_confirmed.
    There is deliberately no non-interactive `approve`.
    """
    tty = _open_tty()
    try:
        wanted = set(item_ids) if item_ids is not None else None
        pending = [i for i in list_items("pending") if wanted is None or i["id"] in wanted]
        if not pending:
            tty.write("Nothing pending.\n")
            return {}
        decisions: dict[str, tuple[str, str]] = {}
        results: dict[str, str] = {}
        for n, item in enumerate(pending, 1):
            tty.write(f"\n[{n}/{len(pending)}]\n{render_card(item, show_hash=True)}\n")
            if not _stored_hash_ok(item):
                tty.write("STALE: this item's fields no longer produce its stored hash "
                          "(older schema or edited by hand). It cannot be approved; re-enqueue it.\n")
                results[item["id"]] = "stale"
                continue
            while True:
                tty.write("(a)pprove / (r)eject / (s)kip > ")
                ans = tty.readline().strip().lower()
                if ans in ("a", "r", "s"):
                    break
            decisions[item["id"]] = (ans, item["approval_hash"])
        approvals = [i for i, (a, _) in decisions.items() if a == "a"]
        rejections = [i for i, (a, _) in decisions.items() if a == "r"]
        results.update({i: "skipped" for i, (a, _) in decisions.items() if a == "s"})
        if not approvals and not rejections:
            return results
        code = secrets.token_hex(3)
        tty.write(f"\nApprove {len(approvals)}, reject {len(rejections)}. "
                  f"Type the code {code} to confirm: ")
        if tty.readline().strip() != code:
            tty.write("Code did not match. Nothing changed.\n")
            return {**results, **{i: "not_confirmed" for i in approvals + rejections}}
        with _locked():
            state = _state()
            for item_id in approvals:
                item = state.get(item_id)
                shown = decisions[item_id][1]
                if (item is None or item["status"] != "pending"
                        or item["approval_hash"] != shown or _hash_of(item) != shown):
                    results[item_id] = "stale"
                    continue
                _append("approved", {**item, "status": "approved"}, note="confirmed on tty")
                results[item_id] = "approved"
            results.update(reject(rejections, note="rejected on tty"))
        return results
    finally:
        tty.close()


# --- sending: one transition, one dispatch ------------------------------------------

_single_attempt = contextvars.ContextVar("approval_single_attempt", default=False)


@contextlib.contextmanager
def single_attempt():
    """While active, the Publora client must not repeat a POST that may have been
    processed (5xx, 408, timeouts, dropped connections). `lib.publish` enters it
    around a gated dispatch; it exists here, with no third-party imports, so the
    client can read it without this module knowing about HTTP."""
    token = _single_attempt.set(True)
    try:
        yield
    finally:
        _single_attempt.reset(token)


def single_attempt_active() -> bool:
    return _single_attempt.get()


def _set_status(item_id: str, status: str, event: str, note: str = "", remote: Any = None) -> dict:
    with _locked():
        item = _state().get(item_id)
        if item is None:
            raise KeyError(item_id)
        updated = {**item, "status": status}
        if remote is not None:
            updated["remote"] = remote
        _append(event, updated, note=note)
    return updated


def _call_hash(kind: str, draft_text: str, target_url: str, kwargs: dict) -> tuple[str, list[str]]:
    """Recompute the hash from the publish call itself. Raises ApprovalError for
    kinds and kwargs the hash does not cover."""
    if kind not in KINDS:
        raise ApprovalError(f"kind {kind!r} is outside approval v1 (post, comment, reply only); "
                            "publish it without approved_hash, and unset "
                            f"{ENV_REQUIRE} if it is set")
    given = {k: v for k, v in kwargs.items() if v is not None}
    stray = sorted(set(given) - ALLOWED_KWARGS[kind])
    if stray:
        raise ApprovalError(f"kwarg(s) {stray} are not covered by the approval hash for a {kind}; "
                            "nothing was sent")
    network = given.get("network") or "linkedin"
    if network != "linkedin":
        raise ApprovalError(f"network {network!r} has no publishing adapter yet; nothing was sent")
    accounts = resolve_accounts(kind, platform_id=given.get("platform_id"),
                                platforms=given.get("platforms"))
    h = approval_hash(
        kind=kind, network=network, accounts=accounts, target=target_url,
        post_urn=given.get("post_urn"),
        parent_comment=given.get("parent_comment"),
        reaction_type=given.get("reaction_type"),
        text=draft_text, scheduled_time=given.get("scheduled_time"),
        media=given.get("media_urls"),
    )
    return h, accounts


def claim_for_send(approved_hash: str, *, kind: str, draft_text: str, target_url: str = "",
                   require_account: bool = True, **kwargs: Any) -> dict:
    """Verify the call matches an approved item, then mark it `sending` under
    the ledger lock. Returns the item; the caller that gets it back, and only
    that caller, may dispatch. Everyone else gets ApprovalError.

    Raises ApprovalMismatch if the call's content differs from what was approved
    (changed text, target, accounts, schedule, media, parent, reaction), and
    ApprovalError if the hash is not approved, was edited, or already went out.
    """
    try:
        recomputed, accounts = _call_hash(kind, draft_text, target_url, kwargs)
    except ValueError as exc:  # e.g. a reply with no parent_comment
        raise ApprovalMismatch(f"this call cannot match any approved item: {exc}") from None
    if require_account and not accounts:
        raise ApprovalError("no destination account resolved (pass platform_id/platforms or set "
                            "LINKEDIN_PLATFORM_ID): the approval cannot cover an unknown account")
    if recomputed != approved_hash:
        raise ApprovalMismatch(
            "the content of this call differs from what was approved "
            f"(approved {approved_hash[:12]}, this call {recomputed[:12]}); nothing was sent")
    with _locked():
        match = [i for i in _state().values() if i.get("approval_hash") == approved_hash]
        for item in match:
            if item["status"] == "approved":
                _append("sending", {**item, "status": "sending"})
                return {**item, "status": "sending"}
        if match:
            raise ApprovalError(
                f"item {match[-1]['id']} is {match[-1]['status']}, not approved; nothing was sent"
                + (" (outcome unknown: reconcile it by hand before trying again)"
                   if match[-1]["status"] in ("sending", "unknown") else ""))
    raise ApprovalError(f"no approved item with hash {approved_hash[:12]} (never approved, or "
                        "edited since); nothing was sent")


def classify_error(exc: BaseException) -> str:
    """`failed` only when it is certain nothing went out; otherwise `unknown`.

    Decided from the HTTP status the API returned, never from a class name or
    message text: 4xx (except 408 and 429) means the API refused and nothing was
    created; 5xx, 408, 429, timeouts and dropped connections may have been
    processed. An error raised before any request left this machine is `failed`.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return "failed" if 400 <= status < 500 and status not in (408, 429) else "unknown"
    if getattr(exc, "request_sent", True) is False:
        return "failed"
    return "unknown"


def record_outcome(item_id: str, *, result: Any = None, error: Optional[BaseException] = None) -> None:
    """Write what happened after a gated dispatch. Any BaseException (including
    KeyboardInterrupt) is classified; the default is `unknown`."""
    if error is not None:
        verdict = classify_error(error)
        text = f"{type(error).__name__}: {error}"
        (mark_failed if verdict == "failed" else mark_unknown)(item_id, text)
        return
    if isinstance(result, dict):
        mode = result.get("mode")
        if mode == "manual":
            # Nothing was sent; the user pastes it by hand. Release the claim.
            _set_status(item_id, "approved", "released", note="manual tier: nothing sent")
            return
        if mode == "diy":
            if result.get("returncode") == 0:
                mark_sent(item_id, remote={"mode": "diy"})
            else:
                mark_unknown(item_id, f"custom poster exited {result.get('returncode')}")
            return
        remote = {k: result[k] for k in ("postGroupId", "id", "commentId", "status") if k in result}
        mark_sent(item_id, remote=remote or None)
        return
    mark_unknown(item_id, "backend returned no result")


def mark_sent(item_id: str, remote: Any = None) -> dict:
    return _set_status(item_id, "sent", "sent", remote=remote)


def mark_failed(item_id: str, error: str) -> dict:
    """A definite failure: nothing went out."""
    return _set_status(item_id, "failed", "failed", note=error[:500])


def mark_unknown(item_id: str, note: str) -> dict:
    """The outcome is not known. Reconcile against the platform by hand."""
    return _set_status(item_id, "unknown", "unknown", note=note[:500])


def reconcile(item_id: str, outcome: str, note: str) -> dict:
    """Human resolution of an item stuck in `sending` or `unknown`: after
    checking the platform, record that it was `sent` or `failed`. A note saying
    what was checked is required."""
    if outcome not in ("sent", "failed"):
        raise ValueError("outcome must be 'sent' or 'failed'")
    if not (note or "").strip():
        raise ValueError("a note saying what you checked is required")
    item = get(item_id)
    if item is None:
        raise KeyError(item_id)
    if item["status"] not in ("sending", "unknown"):
        raise ApprovalError(f"item is {item['status']}; only sending or unknown items are reconciled")
    return _set_status(item_id, outcome, "reconciled", note=f"manual: {note.strip()}"[:500])
