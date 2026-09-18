#!/usr/bin/env python3
"""Write a skill routing block into a CLAUDE.md, reversibly.

The scan says which installed capability the agent never reaches. This is the
one step that changes something about that, and it is the step where the product
can do real damage: a CLAUDE.md is hand-written work. So everything here is built
around two properties, in this order: the user's own bytes survive, and the row
we write is one the agent can actually test itself against.

Why the second property is a property and not a detail. Our own eval ran an arm
that wrote a routing table listing each skill under its own frontmatter
description. Discovery moved 33% -> 56%, and two of six tasks recorded zero
discovery across three trials each. The transcripts show the agent read the table
and the rows did not match: a skill advertising itself as "use when writing any
in-session reply to Federico" describes the author's working context, and an
agent cannot test itself against a description of somebody else's day. The next
arm rewrote each trigger into "the task is to draft a LinkedIn post", a condition
about the task in front of the agent. Listing a skill is not routing to it. So
this script does not copy descriptions into a table. It derives a trigger, and
where it cannot derive one honestly it emits no row and says so.

Local only. Standard library, no network, no subprocess, no evaluation. The only
file this writes is the target you name and its backup.

Usage:
  apply_surgery.py --input findings.json --target ./CLAUDE.md            # dry run
  apply_surgery.py --input findings.json --target ./CLAUDE.md --confirm
  apply_surgery.py --target ./CLAUDE.md --rollback
  apply_surgery.py --list-targets
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Path discovery is inspect_setup's job and it already knows where skills live on
# both hosts. Re-deriving it here would give the surgery a different idea of the
# machine than the scan it is acting on, which is how a tool ends up routing to a
# skill the scan never saw.
from inspect_setup import default_skill_roots, inventory  # noqa: E402

SCHEMA = "brain-surgery-scan/0.1"
BEGIN = b"<!-- brain-surgery:begin -->"
END = b"<!-- brain-surgery:end -->"
# A CLAUDE.md is prose. Anything this size is not one, and splicing into it blind
# is a worse outcome than stopping.
MAX_TARGET_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# Trigger derivation
# ---------------------------------------------------------------------------

# Most descriptions in the wild are "<what it does>. Use when <condition>." The
# clause after "Use when" is the author's own routing condition, already written
# as a condition. Lifting it is extraction, not invention, which is why it is the
# preferred tier: the only thing that changes is the frame around it.
USE_WHEN = re.compile(
    r"\bUse\s+(?:this\s+skill\s+)?(?:when(?:ever)?|if)\b\s*[:,]?\s+(.+)", re.I | re.S)

# The head of a lifted clause is usually addressed to the agent or the author
# ("the user wants to X", "you need to X"). Dropping the head leaves the task
# itself. These substitutions are structural: each one deletes a framing phrase,
# and none of them adds a word about what the task is.
HEADS = (
    (re.compile(r"^(?:the\s+)?user\s+(?:wants|needs|asks)\s+(?:you\s+)?(?:to\s+)?", re.I), "to "),
    (re.compile(r"^(?:the\s+)?user\s+(?:says|requests)\b.*", re.I), ""),  # quoted phrases, not a task
    (re.compile(r"^you\s+(?:need|want|have)\s+to\s+", re.I), "to "),
    (re.compile(r"^you\s+are\s+", re.I), ""),
    (re.compile(r"^(?:asked|told)\s+to\s+", re.I), "to "),
    (re.compile(r"^(?:someone|anyone)\s+(?:wants|needs|asks)\s+(?:to\s+)?", re.I), "to "),
    (re.compile(r"^working\s+(?:on|with)\s+", re.I), "about "),
)

# Tier two, for a description that never states a condition. A closed list, not a
# part-of-speech tagger: a fixed set of verbs is predictable and its failures are
# visible, where a guessed one would silently turn "Master the uv package
# manager" into a routing condition about mastery. Its known failure is a word
# that is both verb and adjective: "Clean editorial-style interfaces" becomes
# "the task is to clean editorial-style interfaces", which routes on the right
# subject with the wrong verb. Tier two rows sort below tier one for that reason.
IMPERATIVES = {
    "analyse", "analyze", "audit", "build", "check", "clean", "compress", "convert",
    "create", "debug", "deploy", "design", "detect", "diagnose", "draft", "edit",
    "extract", "find", "fix", "generate", "handle", "inspect", "install", "manage",
    "optimise", "optimize", "plan", "prepare", "process", "publish", "read", "render",
    "repair", "review", "rewrite", "run", "schedule", "score", "search", "send",
    "summarise", "summarize", "test", "track", "transform", "turn", "update",
    "validate", "verify", "write",
}

# Author voice. This is the arm F failure in pattern form: text that describes the
# author's situation rather than the task. First person is unambiguous, and so is
# the machine owner's own name, which is exactly what skill authors write into
# their own descriptions ("Federico's mailbox", "read my telegram").
FIRST_PERSON = re.compile(
    r"\b(?:my|mine|me|myself|our|ours|ourselves|we|us|his|her|hers|i'm|i've|i'd|i'll)\b", re.I)
FIRST_PERSON_I = re.compile(r"\bI\b")

# A condition that carries its own finite verb is a sentence about a situation
# ("banner PNGs are needed", "a product artifact needs positioning"), and pasting
# one behind "the task is" produces a row that is not a sentence. The first
# version of this script emitted exactly that, and a row an agent has to squint
# at is the arm F failure again in a different costume. Closed list, whole word.
FINITE = {
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "do", "does",
    "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "need", "needs", "want", "wants", "say", "says", "said", "show", "shows", "exist",
    "exists", "require", "requires", "fail", "fails", "gets", "seems", "looks",
}
FINITE_RE = re.compile(r"\b(?:%s)\b" % "|".join(sorted(FINITE)), re.I)
# "to how", "to the", "to it" are the wreckage of a head substitution that removed
# a verb along with the frame. Only a verb may follow "to" in a task condition.
BAD_AFTER_TO = {"how", "what", "when", "where", "why", "whether", "which", "the", "a",
                "an", "it", "this", "that", "there", "their", "its"}
DETERMINERS = {"a", "an", "any", "the"}

MIN_TRIGGER = 16
MAX_TRIGGER = 140


def owner_tokens(extra: list[str]) -> set[str]:
    """Names that mean 'the person whose machine this is'.

    Taken from the account, not from a list we ship, because the name that shows
    up in descriptions is whoever wrote them.
    """
    blob = " ".join([Path.home().name, os.environ.get("USER", "")] + extra).lower()
    return {t for t in re.split(r"[^a-z]+", blob) if len(t) >= 5}


def names_owner(text: str, owners: set[str]) -> bool:
    # Substring both ways: a home directory reads "janedoe" and the description
    # reads "Jane". Five characters minimum keeps an ordinary English word from
    # colliding with a chunk of somebody's login.
    for word in re.findall(r"[A-Za-z]{5,}", text.lower()):
        if any(word in owner or owner in word for owner in owners):
            return True
    return False


def first_sentence(text: str, limit: int) -> str:
    """One clause. A row that runs past the edge of the table is not scanned."""
    text = " ".join(text.split())
    for stop in (". ", "; ", " — ", " -- "):
        if stop in text:
            text = text.split(stop)[0]
    return text.rstrip(" .;,").strip()[:limit]


def derive_trigger(description: str, owners: set[str]) -> tuple[str | None, str, str]:
    """Return (trigger, tier, reason).

    Two things happen here and only one of them is a rewrite. The frame around a
    condition ("Use when the user wants to ...") is rewritten, because the frame
    carries no meaning about the task and dropping it cannot change which tasks
    match. The condition itself is never rewritten: there is no mechanical way to
    turn "any in-session reply to Federico" into a task condition without
    guessing what the author meant, and a guessed trigger that looks right is
    worse than a missing row, because a missing row tells the user to write one
    and a wrong row tells nobody anything. So author-voice conditions are
    refused, by name, with the reason printed.

    The limit, stated plainly: this catches first person and the owner's own
    name. A description naming a third party — "send it to Arian", "the Cakewalk
    board" — reads as ordinary task text here and will produce a row an agent in
    another context cannot test itself against. That hole is real and unfixed.
    """
    desc = " ".join((description or "").split())
    if not desc:
        return None, "none", "no description in the skill's frontmatter"

    tier, body = "", ""
    m = USE_WHEN.search(desc)
    if m:
        tier, body = "condition", first_sentence(m.group(1), MAX_TRIGGER + 40)
    else:
        lead = first_sentence(desc, MAX_TRIGGER + 40)
        head = lead.split(" ", 1)[0].lower().strip(",")
        if head in IMPERATIVES and " " in lead:
            tier = "imperative"
            body = "to " + lead[0].lower() + lead[1:]
        else:
            return None, "none", "description states what the skill is, not when to load it"

    for pattern, repl in HEADS:
        new = pattern.sub(repl, body, count=1)
        if new != body:
            body = new.strip()
            break

    body = " ".join(body.strip(" .,;:").split())
    if not body:
        return None, tier, "condition was only a framing phrase"
    if FIRST_PERSON.search(body) or FIRST_PERSON_I.search(body):
        return None, tier, "author voice: first person, which no agent can test itself against"
    if names_owner(body, owners):
        return None, tier, "author voice: names the machine owner, not the task"
    if FINITE_RE.search(body):
        return None, tier, "condition is a sentence about a situation, not a task shape"
    if re.match(r"^(?:the\s+)?(?:user|someone|they)\b", body, re.I):
        # HEADS only knows a handful of verbs. Anything else ("the user pastes a
        # figma.com link") is still a sentence about a person, and guessing the
        # verb out of it would be inventing the condition.
        return None, tier, "condition still describes what a person does, not what the task is"

    # Three shapes fit behind "the task is" and read as English: an infinitive, a
    # gerund, and a bare noun phrase. Anything else is refused rather than bent,
    # because bending it is where a mechanical rewrite starts inventing.
    words = body.split()
    head = words[0].lower()
    if head == "to":
        if len(words) < 3 or words[1].lower() in BAD_AFTER_TO:
            return None, tier, "rewrite left 'to' without a verb after it"
    elif not (head.endswith("ing") and len(head) >= 5) and head not in DETERMINERS:
        return None, tier, "condition is not an infinitive, gerund, or noun phrase"

    trigger = "the task is " + body[0].lower() + body[1:]
    trigger = " ".join(trigger.split())
    if len(trigger) < MIN_TRIGGER:
        return None, tier, "condition too short to match anything"
    if len(trigger) > MAX_TRIGGER:
        # Truncating a condition changes it. Hand it back instead.
        return None, tier, "condition too long for a row; shorten it yourself"
    return trigger, tier, ""


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

# Which skills get a row, and why this rule and not "all of them":
#
#   * Only skills the scan found dormant. A skill the agent already reaches does
#     not need routing, and every row it does not need makes the rows it does
#     need harder to find. The measured gap is the dormant set, so that is the
#     set the surgery acts on.
#   * Never a shadowed skill. Two directories claim that name and which one wins
#     is decided by load order, not by this table. A row pointing at a name that
#     resolves to a file the user did not choose is routing to a coin flip, so
#     shadowed skills are reported and left alone.
#   * Never a skill that failed to load. It is broken; the fix is repair, and a
#     row would spend a turn discovering that.
#   * Never a skill loaded from outside the inventory. Its SKILL.md is not on a
#     path this scan read, so there is no description to derive a trigger from.
#   * Then capped. Arm F's table listed six skills and the agent still failed to
#     match two of them. A hundred and sixty-seven rows is not a routing table,
#     it is a directory. The cap is visible in the output and in the block.
SELECTION_RULE = ("dormant skills only, minus shadowed, failed and uninventoried ones, "
                  "minus any whose description yields no testable trigger")

# What the Skill tool can actually load.
SLUG = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")


def read_findings(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA:
        raise SystemExit(
            "Refusing: --input is %r, not %s. This writes into a file you wrote by hand; it "
            "acts only on a scan whose shape it knows." % (raw.get("schema_version"), SCHEMA))
    totals = raw.get("totals", {})
    if not totals.get("measured"):
        # render_scan.py renders an unmeasured scan on purpose: a name collision is
        # on disk whether or not a transcript was read. Routing is the opposite
        # case. Every skill on a machine with no readable history looks dormant, so
        # the candidate list here would be the whole install and the ranking behind
        # it would be nothing at all. Reporting that is honest; editing a config on
        # the strength of it is not.
        raise SystemExit(
            "Refusing: this scan measured no usage (totals.measured is false), so every "
            "installed skill looks dormant and none of them looks dormant for a reason. "
            "Routing a machine with no usage history is guesswork, and this writes into "
            "your CLAUDE.md. Re-scan with a window that holds sessions "
            "(inspect_setup.py --scope user --days 30) and run this again.")
    return raw


def by_code(raw: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [f for f in raw.get("findings", []) if f.get("code") == code]


def candidates(raw: dict[str, Any]) -> tuple[list[str], dict[str, list[str]], list[str], list[str]]:
    dormant: list[str] = []
    for f in by_code(raw, "dormant"):
        dormant.extend(f.get("evidence", {}).get("names", []))
    shadowed = {f["skill"]: f.get("evidence", {}).get("paths", []) for f in by_code(raw, "shadowed")
                if f.get("skill")}
    failed = [f["skill"] for f in by_code(raw, "load_failed") if f.get("skill")]
    outside = [f["skill"] for f in by_code(raw, "inventory_gap") if f.get("skill")]
    blocked = set(shadowed) | set(failed) | set(outside)
    return sorted({n for n in dormant if n and n not in blocked}), shadowed, failed, outside


def descriptions(roots: list[Path]) -> dict[str, str]:
    """Name -> frontmatter description, read off disk.

    The scan carries names and counts, not descriptions, and it is right not to:
    those go in a report that can be shared. The trigger has to come from the
    skill itself, so this reads the same roots the scan walked.
    """
    out: dict[str, str] = {}
    for s in inventory(roots)["skills"]:
        name = s.get("name")
        # Keep a name with an empty description rather than dropping it, so
        # "this skill says nothing about itself" is not reported as "this skill
        # is not on disk". Those are different problems with different fixes.
        if name and (name not in out or not out[name]):
            out[name] = s.get("description") or ""
    return out


def plan(raw: dict[str, Any], roots: list[Path], max_rows: int, only: list[str],
         owners: set[str]) -> dict[str, Any]:
    names, shadowed, failed, outside = candidates(raw)
    if only:
        # An explicit pick overrides the dormancy filter but nothing else: the
        # user may know a skill matters, and cannot know which SKILL.md a
        # shadowed name resolves to any better than we can.
        blocked = set(shadowed) | set(failed) | set(outside)
        names = [n for n in only if n not in blocked]
    descs = descriptions(roots)

    rows: list[dict[str, str]] = []
    refused: list[dict[str, str]] = []
    for name in names:
        if name not in descs:
            refused.append({"skill": name, "reason": "no SKILL.md found under the scanned roots"})
            continue
        if not SLUG.match(name):
            # The row has to name something the Skill tool can load. The scan
            # reports a skill's frontmatter `name`, and some authors put a
            # display title there ("Floom Job Scout") while the tool resolves the
            # directory. Routing to a name that will not resolve spends a turn
            # and teaches the agent the table is unreliable.
            refused.append({"skill": name,
                            "reason": "frontmatter name is a display title, not a loadable id"})
            continue
        trigger, tier, reason = derive_trigger(descs[name], owners)
        (rows if trigger else refused).append(
            {"skill": name, "trigger": trigger, "tier": tier} if trigger
            else {"skill": name, "reason": reason})

    # Lifted conditions before reshaped imperatives: the author wrote the first
    # kind as a condition, so it is the kind more likely to match a real task.
    # Within a tier, by name — the scan cannot rank dormant skills by value,
    # because a skill with no usage has nothing to rank on. The output says so.
    rows.sort(key=lambda r: (r["tier"] != "condition", r["skill"]))
    eligible = len(rows)
    return {"rows": rows[:max_rows], "eligible": eligible, "dropped": max(0, eligible - max_rows),
            "refused": refused, "shadowed": shadowed, "failed": failed, "outside": outside,
            "unrouted_only": [n for n in only if n not in names] if only else []}


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------

def render_block(p: dict[str, Any], raw: dict[str, Any]) -> str:
    t = raw.get("totals", {})
    cov = raw.get("coverage", {})
    lines = [
        BEGIN.decode(),
        "## Skill routing",
        "",
        "These skills are installed on this machine and were not loaded once in the scanned",
        "window. Each row states a condition about the task in front of you. When one matches,",
        "load that skill with the Skill tool before you start, not after you have written the",
        "answer. If no row matches, carry on without a skill.",
        "",
        "| skill | load it when |",
        "| --- | --- |",
    ]
    for row in p["rows"]:
        lines.append("| `%s` | %s |" % (row["skill"], row["trigger"]))
    lines += [
        "",
        "<!-- %d of %d eligible rows, %s. Scan: %d installed, %d reached, %d sessions over %s days. "
        "Everything between these two markers is regenerated by scripts/apply_surgery.py. "
        "Put your own rows outside them. -->"
        % (len(p["rows"]), p["eligible"], SELECTION_RULE, t.get("installed", 0),
           t.get("reached", 0), cov.get("sessions_analyzed", 0), cov.get("window_days", "?")),
        END.decode(),
        "",
    ]
    return "\n".join(lines)


def splice(original: bytes, block: str) -> bytes:
    """Replace the block between the markers, or append one. Nothing else moves.

    Byte level on purpose. Decoding to text and re-encoding round-trips almost
    always, and 'almost' is not the standard for somebody's own file: a lone
    surrogate or an unusual normalization would come back changed and the diff
    would not show it. Splicing bytes makes preservation a property of the
    operation rather than a property of the encoder.
    """
    starts, ends = original.count(BEGIN), original.count(END)
    if starts > 1 or ends > 1:
        raise ValueError("found %d begin and %d end markers; refusing to guess which block is "
                         "ours. Delete the extra markers by hand." % (starts, ends))
    if starts != ends:
        raise ValueError("found %d begin and %d end markers. An unpaired marker means the block "
                         "was edited by hand; refusing to splice." % (starts, ends))
    payload = block.encode("utf-8")
    if starts == 1:
        i, j = original.index(BEGIN), original.index(END) + len(END)
        if j < i:
            raise ValueError("end marker precedes the begin marker; refusing to splice.")
        tail = original[j:]
        # The block already ends in a newline. Do not eat the one after the old
        # end marker, or repeated runs would walk the following text upwards.
        if tail.startswith(b"\n"):
            tail = tail[1:]
        return original[:i] + payload + tail
    if not original:
        return payload
    pad = b"" if original.endswith(b"\n\n") else (b"\n" if original.endswith(b"\n") else b"\n\n")
    return original + pad + payload


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

BACKUP_FMT = "%s.brain-surgery-%s.bak"
PRE_ROLLBACK_FMT = "%s.brain-surgery-prerollback-%s.bak"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_target(path: Path) -> bytes:
    if path.is_symlink():
        raise SystemExit("Refusing a symlink: %s. Point --target at the real file." % path)
    if not path.exists():
        return b""
    if not path.is_file():
        raise SystemExit("Not a regular file: %s" % path)
    size = path.stat().st_size
    if size > MAX_TARGET_BYTES:
        raise SystemExit("Refusing: %s is %d bytes. That is not a CLAUDE.md." % (path, size))
    data = path.read_bytes()
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SystemExit("Refusing: %s is not valid UTF-8 (%s)." % (path, e))
    return data


def write_preserving(path: Path, data: bytes) -> None:
    """Replace the file's contents atomically, keeping its permissions.

    A new file is created owner-only, the house default. An existing file keeps
    the mode the user gave it: this is their config, and quietly tightening it to
    0600 is still changing something they did not ask to change.
    """
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(prefix=".brain-surgery-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def backup(path: Path, fmt: str = BACKUP_FMT) -> Path:
    dest = path.parent / (fmt % (path.name, stamp()))
    n = 0
    # Two runs inside one second must not overwrite each other, and the suffix is
    # zero padded because the newest backup is found by sorting names.
    while dest.exists():
        n += 1
        dest = path.parent / (fmt % (path.name, "%s-%02d" % (stamp(), n)))
    shutil.copy2(path, dest)
    return dest


def backup_stack(path: Path) -> list[Path]:
    """Backups next to the file, newest first."""
    return sorted((p for p in path.parent.glob(path.name + ".brain-surgery-2*.bak*")
                   if p.is_file() and not p.is_symlink()),
                  key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def pick_backup(stack: list[Path], current: bytes) -> tuple[Path | None, list[Path]]:
    """The newest backup that is not already what is on disk, and the ones above it.

    Two applies in a row leave a backup holding a state the file is already in.
    Restoring that one is a no-op, and a rollback that reports success while
    changing nothing would leave the user believing they had undone something.
    Those get skipped, and the caller retires them along with the one it used:
    a state already reached is not somewhere to roll back to, and leaving it on
    the stack made the next --rollback walk forward into the change just undone.
    """
    skipped: list[Path] = []
    for candidate in stack:
        if candidate.read_bytes() != current:
            return candidate, skipped
        skipped.append(candidate)
    return None, skipped


def rollback(path: Path, source: Path | None, confirm: bool) -> int:
    have = read_target(path)
    skipped: list[Path] = []
    src = source
    if src is None:
        src, skipped = pick_backup(backup_stack(path), have)
    if src is None:
        print("No brain-surgery backup holding a different state was found next to %s. "
              "Nothing to roll back." % path)
        return 1
    if not src.is_file() or src.is_symlink():
        raise SystemExit("Backup is not a regular file: %s" % src)
    want = src.read_bytes()
    print("Rollback\n  target: %s\n  backup: %s (%d bytes)" % (path, src, len(want)))
    if want == have:
        print("  target already matches the backup byte for byte. Nothing to do.")
        return 0
    print(diff_text(have, want, str(path), "restored from backup"))
    if not confirm:
        print("Dry run. Nothing was written. Re-run with --confirm to restore.")
        return 0
    keep = backup(path, PRE_ROLLBACK_FMT) if path.exists() else None
    write_preserving(path, want)
    # A rollback that does not read the file back has not rolled anything back;
    # it has only issued a write and assumed. Compare the bytes on disk now.
    after = path.read_bytes()
    if after != want:
        raise SystemExit("ROLLBACK FAILED: %s does not match %s after the restore. The backup is "
                         "untouched; restore it by hand." % (path, src))
    print("  restored and verified: %d bytes, identical to the backup." % len(after))
    if keep:
        print("  the pre-rollback state was kept at %s" % keep)
    if source is None:
        # Retire the backup this consumed, so a second --rollback reaches the
        # state before it instead of walking forward into the one just undone.
        # Renamed, never deleted: it is a copy of the user's file. An explicitly
        # named backup is left alone, because naming it is a deliberate choice to
        # restore that exact state and possibly to do it again.
        for used in [src] + skipped:
            retired = used.parent / ("%s.brain-surgery-restored-%s.bak" % (path.name, stamp()))
            n = 0
            while retired.exists():
                n += 1
                retired = used.parent / ("%s.brain-surgery-restored-%s-%02d.bak"
                                         % (path.name, stamp(), n))
            used.rename(retired)
        print("  %d backup%s retired (renamed, not deleted) so the next rollback goes further "
              "back, not forward." % (1 + len(skipped), "" if not skipped else "s"))
    return 0


def diff_text(old: bytes, new: bytes, name: str, label: str) -> str:
    d = list(difflib.unified_diff(
        old.decode("utf-8", "replace").splitlines(True),
        new.decode("utf-8", "replace").splitlines(True),
        fromfile=name, tofile=name + "  (" + label + ")", n=3))
    return "".join(d) if d else "(no change)\n"


def claude_md_candidates(project: Path, home: Path) -> list[Path]:
    """Where a CLAUDE.md lives, project first then user, mirroring the order
    inspect_setup.default_skill_roots uses for skills. Nothing is chosen for you:
    --target is explicit so that no invocation can write to a file you did not
    name."""
    return [project / "CLAUDE.md", project / ".claude" / "CLAUDE.md",
            home / ".claude" / "CLAUDE.md", home / "CLAUDE.md"]


# ---------------------------------------------------------------------------

def report(p: dict[str, Any]) -> None:
    print("\nSelection: %s." % SELECTION_RULE)
    print("  %d row%s written, %d eligible." % (len(p["rows"]), "" if len(p["rows"]) == 1 else "s",
                                                p["eligible"]))
    if p["dropped"]:
        print("  %d eligible skill%s left out by --max-rows. This cut is arbitrary: a dormant "
              "skill has no usage to rank on, so the scan cannot tell you which ones matter. "
              "Choose them with --only, or raise --max-rows and accept a longer table."
              % (p["dropped"], "" if p["dropped"] == 1 else "s"))
    if p["shadowed"]:
        print("\nReported, not routed - %d name%s declared in more than one place:"
              % (len(p["shadowed"]), "" if len(p["shadowed"]) == 1 else "s"))
        for name, paths in sorted(p["shadowed"].items()):
            print("  %s" % name)
            for path in paths:
                print("      %s" % path)
        print("  Which of these loads is decided by load order, not by a table. Delete or rename "
              "one before routing to that name.")
    if p["failed"]:
        print("\nReported, not routed - failed to load when the agent reached for them: %s"
              % ", ".join(sorted(p["failed"])))
    if p["outside"]:
        print("\nReported, not routed - loaded from outside the scanned skill roots: %s"
              % ", ".join(sorted(p["outside"])))
    if p["unrouted_only"]:
        print("\n--only named skills that are not dormant candidates and were skipped: %s"
              % ", ".join(p["unrouted_only"]))
    if p["refused"]:
        print("\nNo row written for %d skill%s. Their descriptions do not yield a trigger an "
              "agent can test itself against, and a guessed one that looks right is worse than "
              "none. Write these by hand, OUTSIDE the markers:"
              % (len(p["refused"]), "" if len(p["refused"]) == 1 else "s"))
        for item in p["refused"][:15]:
            print("  %-34s %s" % (item["skill"], item["reason"]))
        if len(p["refused"]) > 15:
            print("  ... and %d more (--show-refused for all)" % (len(p["refused"]) - 15))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, help="scan findings JSON from analyze_scan.py")
    ap.add_argument("--target", type=Path, help="the CLAUDE.md to write into")
    ap.add_argument("--project", type=Path, default=Path.cwd(),
                    help="project whose skill roots to read (default: cwd)")
    ap.add_argument("--skill-root", type=Path, action="append", default=[])
    ap.add_argument("--max-rows", type=int, default=12)
    ap.add_argument("--only", default="", help="comma-separated skill names to route, instead of "
                                               "the scan's dormant set")
    ap.add_argument("--owner-name", action="append", default=[],
                    help="extra name meaning 'the person whose machine this is', for author-voice "
                         "detection")
    ap.add_argument("--show-refused", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="the default without --confirm; print the diff and write nothing. "
                         "Passed together with --confirm, this one wins.")
    ap.add_argument("--confirm", action="store_true", help="actually write")
    ap.add_argument("--rollback", nargs="?", const="", metavar="BACKUP",
                    help="restore --target from a backup (default: the newest one beside it)")
    ap.add_argument("--list-targets", action="store_true")
    a = ap.parse_args()

    home = Path.home()
    if a.list_targets:
        for c in claude_md_candidates(a.project.resolve(), home):
            print("%-8s %s" % ("exists" if c.is_file() else "-", c))
        print("\nPass one of these as --target. Nothing is picked for you.")
        return 0

    # Writing is opt in, and --dry-run beats --confirm when both are given. A flag
    # combination that could go either way should go the way that changes nothing.
    write = a.confirm and not a.dry_run

    if a.rollback is not None:
        if not a.target:
            ap.error("--rollback needs --target")
        return rollback(a.target, Path(a.rollback) if a.rollback else None, write)

    if not a.input or not a.target:
        ap.error("--input and --target are both required")
    if not 1 <= a.max_rows <= 200:
        ap.error("--max-rows must be between 1 and 200")

    raw = read_findings(a.input)
    roots = a.skill_root or default_skill_roots(a.project.resolve(), home)
    owners = owner_tokens(a.owner_name)
    p = plan(raw, roots, a.max_rows, [s.strip() for s in a.only.split(",") if s.strip()], owners)

    original = read_target(a.target)
    if not p["rows"]:
        print("No routable skill found. Nothing to write.")
        report(p)
        return 1
    try:
        updated = splice(original, render_block(p, raw))
    except ValueError as e:
        raise SystemExit("Refusing to touch %s: %s" % (a.target, e))

    existing = BEGIN in original
    print("Target: %s (%d bytes%s)"
          % (a.target, len(original), ", existing block will be replaced" if existing
             else ", no block yet" if original else ", new file"))
    print("\n" + diff_text(original, updated, str(a.target), "after surgery"))
    report(p)
    if a.show_refused and len(p["refused"]) > 15:
        for item in p["refused"][15:]:
            print("  %-34s %s" % (item["skill"], item["reason"]))

    if not write:
        print("\nDry run. Nothing was written. Re-run with --confirm to apply."
              + (" (--dry-run was passed alongside --confirm.)" if a.confirm else ""))
        return 0

    saved = backup(a.target) if a.target.exists() else None
    write_preserving(a.target, updated)
    after = a.target.read_bytes()
    if after != updated:
        raise SystemExit("Write verification failed for %s. %s"
                         % (a.target, "Restore from %s." % saved if saved else "File was new."))
    outside_ok = (original == b"" or after.startswith(original.split(BEGIN)[0]))
    print("\nApplied. %d bytes -> %d bytes, %d row%s."
          % (len(original), len(after), len(p["rows"]), "" if len(p["rows"]) == 1 else "s"))
    if saved:
        print("Backup: %s\nRoll back with: %s --target %s --rollback --confirm"
              % (saved, Path(__file__).name, a.target))
    print("Text before the block is unchanged: %s" % ("yes" if outside_ok else "NO - check the diff"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
