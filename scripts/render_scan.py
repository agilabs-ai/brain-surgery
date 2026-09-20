#!/usr/bin/env python3
"""Render a Brain Surgery scan into the local and public report pair.

`analyze_scan.py` emits `brain-surgery-scan/0.1`. Until this existed, nothing
read it: `render_report.py` accepts only the comparison schemas and rejects the
scan outright, so the product's main path stopped one step before the user saw
anything. A scan that produces a file no one can open is not a scan.

This is a second renderer rather than a branch inside the first. The comparison
report is built end to end around two numbers and a delta, and threading a
one-sided scan through it would mean a null check on every one of those reads.
The two reports answer different questions and share a design, not a data shape.

The local and public split is by allowlist, never by stripping. The public
payload is constructed from named count fields, so a key added to the scan later
is absent from the public report until somebody chooses to put it there. Skill
names stay local: they are the names of this person's private work, and the
counts carry the finding without them.

Renderer only. No evaluation, no upload, no configuration change. Standard
library, local assets.

Usage: render_scan.py --input findings.json --out DIR
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "assets"

SCHEMA = "brain-surgery-scan/0.1"
PUBLIC_SCHEMA = "brain-surgery-scan-public/0.1"

# What each finding code means to the person reading it. The scan writes its own
# per-skill title and detail; this supplies the heading the codes group under, so
# five shadowed skills read as one problem rather than five separate alarms.
GROUPS = {
    "no_description": ("Skills nothing can trigger",
                       "A description is what your agent reads when deciding whether a skill "
                       "fits the task. Without one these load only if you name them."),
    "load_failed": ("Skills that failed when your agent reached for them",
                    "Your agent tried to use these and got an error back. The work continued without them."),
    "shadowed": ("Skills competing for the same trigger",
                 "More than one skill claims this work, and the files differ. Which one your agent picks is not something you control."),
    "duplicated": ("Stored in two places, identically",
                   "The same skill, byte for byte, in two roots. Nothing is broken: whichever loads, "
                   "you get the same thing. It matters only when you edit one and forget the other."),
    "inventory_gap": ("Loaded from somewhere this scan did not look",
                      "These ran without error. They are simply not in a root that was scanned, "
                      "usually a plugin or a host-bundled skill, so the counts above are a floor."),
    "dormant": ("Installed and never reached",
                "Present on the machine, not loaded once in the scanned window."),
    "no_evidence": ("No sessions were read in this window",
                    "Nothing below is a measurement of use. Widen the window or scan a "
                    "project that has transcripts to get one."),
}
ORDER = ["no_description", "shadowed", "load_failed", "inventory_gap", "duplicated",
         "dormant", "no_evidence"]

# What each confidence bucket means to the reader, in their words rather than ours.
# The scan emits the bucket; this is the only place it is explained.
BUCKETS = {
    "confirmed": ("Confirmed",
                  "Reproducible on your machine right now. Open the paths and see it."),
    "suspected": ("Worth checking",
                  "Evidence from your past sessions. The condition may already be gone, "
                  "so each of these needs one look before it is worth acting on."),
    "observation": ("For context",
                    "True, and not necessarily anything to fix."),
}
BUCKET_ORDER = ["confirmed", "suspected", "observation"]

# How many names a whole-setup finding lists inline before it says how many it
# withheld. The complete list is always in the embedded scan JSON.
NAME_PREVIEW = 24
# Where a per-finding detail line is cut on the page. The scan writes prose long
# enough to be worth clamping; the full text is in the embedded JSON.
DETAIL_CHARS = 160


def plural(n: int, word: str, suffix: str = "s") -> str:
    return "%d %s%s" % (n, word, "" if n == 1 else suffix)


def clamp(text: Any, limit: int = DETAIL_CHARS) -> str:
    """Escaped detail text, cut at a word boundary.

    Cut first, escape second: the other order can slice an HTML entity in half
    and emit a bare `&a` into the page. Cutting at a fixed character count alone
    ended lines mid-word ("...has been moved or removed sin"), which reads as a
    truncated render rather than a deliberate summary, so back up to the last
    space and mark the cut.
    """
    s = str(text or "").strip()
    if len(s) <= limit:
        return html.escape(s)
    head = s[:limit].rstrip()
    space = head.rfind(" ")
    if space > limit // 2:
        head = head[:space]
    return html.escape(head.rstrip(" ,.;:")) + "&hellip;"


def finding_affected_count(finding: dict[str, Any]) -> int:
    evidence = finding.get("evidence") or {}
    if type(evidence.get("dormant")) is int:
        return max(0, evidence["dormant"])
    if isinstance(evidence.get("names"), list):
        return len({str(name) for name in evidence["names"]})
    return 1


def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported schema_version: %r" % raw.get("schema_version"))
    t = raw["totals"]
    # An unmeasured scan still has findings worth showing: a name collision is on
    # disk whether or not a transcript was read. What it does not have is a
    # dormancy number, because with no sessions every skill looks dormant and the
    # most alarming possible headline would be invented out of nothing. So the
    # count is carried as null rather than zero, and the page drops the headline
    # instead of the report. Refusing outright was worse: the one machine that
    # most needs the shadowed findings is the freshly set up one with no history.
    measured = bool(t.get("measured"))
    installed, reached = int(t["installed"]), int(t["reached"])
    if installed < 0 or reached < 0 or reached > installed:
        raise ValueError("incoherent totals: reached %d of %d" % (reached, installed))
    cov = raw.get("coverage", {})
    by_code: dict[str, list[dict[str, Any]]] = {}
    for f in raw.get("findings", []):
        by_code.setdefault(f.get("code", "other"), []).append(f)
    # Public rendering receives this small, named presentation model rather
    # than the scan. It retains the diagnostic state (including confidence)
    # without carrying a skill name, path, detail, fix, or an arbitrary future
    # finding code into the shareable page.
    public_groups = {
        code: {
            "count": sum(finding_affected_count(f) for f in by_code[code]),
            "confidence": next((f.get("confidence") for f in by_code[code]
                                if f.get("confidence") in BUCKETS), None),
        }
        for code in ORDER if code in by_code
    }
    confidence_counts = {
        bucket: sum(1 for f in raw.get("findings", []) if f.get("confidence") == bucket)
        for bucket in BUCKET_ORDER
    }
    coverage = raw.get("coverage") or {}
    scope = coverage.get("scope")
    return {
        "schema_version": PUBLIC_SCHEMA,
        "measured": measured,
        "installed": installed,
        "reached": reached,
        "dormant": int(t["dormant"]) if measured else None,
        "dormant_percent": int(t["dormant_percent"]) if measured else None,
        "load_attempts": int(t.get("load_attempts", 0)),
        "confirmed_loads": int(t.get("confirmed_loads", 0)),
        "failed_loads": int(t.get("failed_loads", 0)),
        "sessions_analyzed": int(cov.get("sessions_analyzed", 0)),
        "turns_analyzed": int(cov.get("turns_analyzed", 0)),
        "window_days": int(cov.get("window_days", 0)),
        # Codes and how many skills each covers. No names: the count is the finding.
        "finding_counts": {c: len(by_code[c]) for c in ORDER if c in by_code},
        "finding_groups": public_groups,
        "finding_confidence_counts": confidence_counts,
        "resolved_loads_count": len(raw.get("resolved_since") or []),
        "scope": scope if scope in {"project", "user"} else "unknown",
        "harness_sessions_excluded": int(coverage.get("harness_sessions_excluded") or 0),
        "evaluation_performed": bool(raw.get("evaluation_performed", False)),
        "change_status": raw.get("change_status", "not_applied"),
        "scan_complete": bool(raw.get("scan_limits", {}).get("complete", False)),
    }


SCAN_CSS = """
.scan-wrap{padding-bottom:72px}.scan-head{padding:21px 0 18px}.scan-head h1{font-size:16px;font-weight:510;letter-spacing:-.35px}.scan-head .tiny{margin-top:3px}.scan-hero{position:relative;padding:38px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}.scan-hero h2{font-size:clamp(31px,4.5vw,48px);letter-spacing:-1.7px;line-height:1.1;font-weight:545;max-width:720px;margin:12px 0 15px}.scan-hero h2 span{color:var(--blue)}.scan-hero .cloud-layer{opacity:.78}.scan-hero .foreground{position:relative;z-index:1}.scan-hero .of{max-width:630px;color:var(--muted);font-size:13px;line-height:1.7;margin:0}.scan-measure{display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:32px;align-items:end;margin-top:26px}.big{font-size:92px;font-weight:550;letter-spacing:-6px;line-height:.9}.big small{font-size:.28em;font-weight:450;letter-spacing:-1px;color:var(--muted)}.bar{height:6px;background:#ececec;overflow:hidden;margin-top:22px}.bar i{display:block;height:100%;background:var(--blue)}.scan-reach{font-size:11px;color:var(--muted);line-height:1.6;margin:11px 0 0}.scan-stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:24px 0 0}.stat{padding:17px 18px;border-right:1px solid var(--line)}.stat:last-child{border-right:0}.stat b{display:block;font-size:27px;letter-spacing:-1px;font-weight:540}.stat span{font-size:10px;color:var(--muted)}.scan-section{padding:46px 0;border-top:1px solid var(--line)}.scan-section-head{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:25px}.scan-section-head h2{font-size:27px;letter-spacing:-.8px;font-weight:550}.scan-section-head p{font-size:12px;color:var(--muted);max-width:390px}.scan-group{border-top:1px solid var(--line);padding:22px 0}.scan-group:last-child{border-bottom:1px solid var(--line)}.scan-group h2{font-size:16px;font-weight:540;letter-spacing:-.3px;margin:0}.scan-group>p{font-size:12px;line-height:1.65;color:var(--muted);margin:7px 0 14px;max-width:680px}.scan-group ul{margin:0;padding-left:18px}.scan-group li{font-size:13px;margin:7px 0}.scan-group li small{color:var(--muted)}.count{display:inline-block;background:var(--ink);color:#fff;border-radius:99px;padding:1px 8px;font:10px var(--mono);margin-left:7px;vertical-align:2px}.bucket{display:inline-block;margin-left:8px;padding:2px 7px;border-radius:4px;font:9px var(--mono);letter-spacing:.07em;text-transform:uppercase;vertical-align:2px;border:1px solid var(--line);color:var(--muted)}.b-confirmed{background:var(--blue);border-color:var(--blue);color:#fff}.b-suspected{color:var(--ink)}summary{cursor:pointer;color:var(--muted);font-size:12px}details ul{margin:8px 0 0}.fix{margin:8px 0 3px;padding:9px 11px;background:#fafafa;border:1px solid var(--line);border-radius:7px;font-size:12px;line-height:1.5}.fix code{display:block;margin-top:6px;font:11px/1.5 var(--mono);color:var(--muted);overflow-wrap:anywhere}.scan-evidence{margin-top:0}.note{border-left:2px solid var(--blue);padding:3px 0 3px 14px;color:var(--muted);font-size:12px;line-height:1.65;margin:0;max-width:760px}.footer{margin-top:45px;padding:25px 0 0;border-top:1px solid var(--line);color:#777;font-size:11px;line-height:1.6}.footer a{color:inherit}@media(max-width:720px){.scan-wrap{width:min(var(--page),calc(100% - 32px))}.nav{height:65px}.nav-links{gap:12px}.scan-hero{padding:27px 23px}.scan-measure{grid-template-columns:1fr;gap:13px}.big{font-size:72px}.scan-stats{grid-template-columns:1fr 1fr}.stat:nth-child(2){border-right:0}.stat:nth-child(-n+2){border-bottom:1px solid var(--line)}.scan-section-head{display:block}.scan-section-head p{margin-top:9px}.scan-hero .cloud-layer{opacity:.52}}
"""

# The approved report shell is shared verbatim. Scan-only additions below do
# not introduce a second visual system; they only map diagnostic data into the
# same approved tokens and responsive layout.
CSS = (ASSETS / "approved-ui.css").read_text() + SCAN_CSS
CLOUD_JS = (ASSETS / "approved-cloud.js").read_text()


def groups_html(raw: dict[str, Any] | None, s: dict[str, Any], local: bool) -> str:
    """Render private findings from the scan or public findings from its allowlist.

    The public page must be reproducible from the public summary alone. Passing
    the original scan here would make a future copy change a privacy decision.
    """
    by_code: dict[str, list[dict[str, Any]]] = {}
    if raw:
        for f in raw.get("findings", []):
            by_code.setdefault(f.get("code", "other"), []).append(f)
    out = []
    for code in ORDER:
        items = by_code.get(code, [])
        public_group = (s.get("finding_groups") or {}).get(code, {})
        if not items and not public_group:
            continue
        title, detail = GROUPS[code]
        # Count skills, not findings. One whole-setup finding carries the names of
        # every skill it covers, and badging that group "1" beside a list of 163
        # names contradicts the list directly under it.
        affected = (sum(finding_affected_count(f) for f in items)
                    if local else int(public_group.get("count", 0)))
        if local:
            # Names only ever reach the local page.
            rows = []
            for f in items:
                name = f.get("skill")
                if name:
                    # The fix, on the page. A next step that only exists in the
                    # embedded JSON is a next step nobody takes, and a finding
                    # without one is homework rather than a diagnosis.
                    fix = str(f.get("fix") or "").strip()
                    fix_html = ""
                    if fix:
                        head, _, cmd = fix.partition("\n")
                        fix_html = '<div class="fix">%s%s</div>' % (
                            html.escape(head),
                            '<code>%s</code>' % html.escape(cmd.strip()) if cmd.strip() else "")
                    rows.append("<li>%s<small> &middot; %s</small>%s</li>"
                                % (html.escape(str(name)), clamp(f.get("detail", "")), fix_html))
                    continue
                # A whole-setup finding names no single skill. Rendering a
                # placeholder there produced a one-item list reading "your setup"
                # under a heading that had just counted 163 dormant skills, which
                # reads as a rendering fault rather than the summary it is. List
                # the names the finding actually carries.
                names = [str(n) for n in f.get("evidence", {}).get("names", []) if n]
                rows.append("<li>%s<small> &middot; %s</small></li>"
                            % (html.escape(str(f.get("title", ""))), clamp(f.get("detail", ""))))
                # A full 163-name list buries every other group under it. Show
                # enough to recognise the setting and say plainly how many were
                # withheld; the complete list is in the embedded JSON below.
                rows += ["<li>%s</li>" % html.escape(n) for n in names[:NAME_PREVIEW]]
                rest = names[NAME_PREVIEW:]
                if rest:
                    rows.append("<li><details><summary>and %d more</summary>"
                                "<ul>%s</ul></details></li>"
                                % (len(rest), "".join("<li>%s</li>" % html.escape(n)
                                                      for n in rest)))
            body = "<ul>%s</ul>" % "".join(rows)
        else:
            body = '<p class="sub" style="margin:0">%d skill%s affected. Names stay on the scanned machine.</p>' % (
                affected, "" if affected == 1 else "s")
        # The bucket on the group, so a reader scanning headings can tell what is
        # reproducible now from what is a lead, without reading every finding.
        bucket = (next((f.get("confidence") for f in items if f.get("confidence")), None)
                  if local else public_group.get("confidence"))
        chip = ''
        if bucket in BUCKETS:
            label, _ = BUCKETS[bucket]
            chip = '<span class="bucket b-%s">%s</span>' % (bucket, html.escape(label))
        out.append('<div class="scan-group"><h2>%s<span class="count">%d</span>%s</h2><p>%s</p>%s</div>'
                   % (html.escape(title), affected, chip, html.escape(detail), body))
    return "".join(out)


def page(s: dict[str, Any], raw: dict[str, Any] | None, local: bool) -> str:
    reach_pct = round(100.0 * s["reached"] / s["installed"]) if s["installed"] else 0
    where = "Local scan &middot; not shared" if local else "Shared scan"
    title = "Brain Surgery by Edge &middot; %s scan" % ("local" if local else "shared")
    # The headline is the count, not an adjective. A person reading their own
    # number should not have to trust our word for how bad it is.
    one = lambda n, a, b: a if n == 1 else b
    stats = [
        (s["installed"], one(s["installed"], "skill installed", "skills installed")),
        (s["reached"], "reached in this window"),
        (s["failed_loads"], one(s["failed_loads"], "load returned an error", "loads returned an error")
         + (", since resolved" if s.get("resolved_loads_count") and not s["finding_counts"].get("load_failed") else "")),
        (s["sessions_analyzed"], one(s["sessions_analyzed"], "session read", "sessions read")),
    ]
    stat_html = "".join('<div class="stat"><b>%s</b><span>%s</span></div>' % (f"{n:,}", html.escape(l))
                        for n, l in stats)
    excluded = int(s.get("harness_sessions_excluded") or 0)
    caveat = ("Counts cover the %s read in this scan, not your whole history. "
              "A skill with no recorded load was not reached in this window; that is not "
              "proof it is never used. Nothing was executed, uploaded, or changed."
              % plural(s["sessions_analyzed"], "session"))
    if s.get("scope") == "project":
        # 205 of 205 dormant from two sessions, with nothing on the page saying the
        # window was deliberately one project wide. That is the dormancy false
        # alarm again, wearing a different hat.
        caveat += (" Scope was one project, so skills you use elsewhere on this machine "
                   "show as never reached. Rerun with --scope user for the whole picture.")
    if excluded:
        caveat += (" %s excluded as evaluation runs, because a benchmark is not you using "
                   "your setup." % plural(excluded, "session"))
    evidence = ""
    if local:
        top = (raw or {}).get("most_used", [])[:8]
        if top:
            rows = "".join("<li>%s<small> &middot; %d load%s</small></li>" % (
                html.escape(str(x["skill"])), x["loads"], "" if x["loads"] == 1 else "s") for x in top)
            evidence = ('<div class="scan-group"><h2>What your agent actually reaches</h2>'
                        '<p>The skills that carried your work in this window.</p><ul>%s</ul></div>' % rows)
    # Escaped for a <script> context, not an HTML text one. Character references
    # are not decoded inside a script element, so html.escape here would leave a
    # block that reads `{&quot;installed&quot;: ...}` and JSON.parse would throw.
    # `<` and `&` as \\u escapes keep it parseable and still close no tag.
    payload = (json.dumps(raw if local else s, indent=1)
               .replace("&", "\\u0026").replace("<", "\\u003c"))
    data_id = "local-data" if local else "summary-data"

    # Counted from findings rather than from the dormancy number. Leading with
    # "163 of 203 skills were never used" told a reader their setup was 80% broken
    # when most of those skills are for work they do not do. A fresh machine with
    # five cleanly installed skills produced that finding and nothing else.
    confirmed_count = (sum(1 for f in (raw or {}).get("findings", []) if f.get("confidence") == "confirmed")
                       if local else int((s.get("finding_confidence_counts") or {}).get("confirmed", 0)))
    suspected_count = (sum(1 for f in (raw or {}).get("findings", []) if f.get("confidence") == "suspected")
                       if local else int((s.get("finding_confidence_counts") or {}).get("suspected", 0)))

    if s["measured"]:
        if not s.get("scan_complete"):
            headline = "Scan incomplete. Findings are provisional."
            lead = ("The readable evidence is shown below, but missing roots or sessions mean "
                    "this is not a clean bill of health and not a complete diagnosis.")
            big, unit, of = confirmed_count + suspected_count, "", "found so far"
        elif confirmed_count:
            headline = "%s to fix in your setup." % plural(confirmed_count, "thing")
            lead = ("Each one is reproducible on your machine right now, and each has a "
                    "path you can open.")
            big, unit, of = confirmed_count, "", "confirmed"
        elif suspected_count:
            headline = "Nothing confirmed broken. %s worth checking." % plural(
                suspected_count, "thing")
            lead = ("These come from your past sessions, so the condition may already be "
                    "gone. Each needs one look before it is worth acting on.")
            big, unit, of = suspected_count, "", "worth checking"
        else:
            # A clean scan is an honest result, not a failure to find something.
            headline = "Nothing broken in your setup."
            resolved_count = int(s.get("resolved_loads_count") or 0)
            if resolved_count:
                # Without this the page contradicted itself: the hero said "no
                # failed loads" while the strip beneath it counted four. They are
                # both true, and only saying one of them reads as a mistake.
                lead = ("Nothing to fix today. %s failed in earlier sessions and load now. "
                        "The earlier errors are resolved." % plural(resolved_count, "skill"))
            else:
                lead = ("No name collisions, no failed loads, nothing missing from disk. "
                        "That is the finding, not an absence of one.")
            big, unit, of = 0, "", "confirmed"
        coverage_line = "Read from %s turn%s across %s, last %s." % (
            f"{s['turns_analyzed']:,}", "" if s["turns_analyzed"] == 1 else "s",
            plural(s["sessions_analyzed"], "session"), plural(s["window_days"], "day"))
        # Dormancy moves into the strip below, where it reads as context. As the
        # hero number it told a reader with five clean skills that 80% of their
        # setup was dormant, which is true and is not a problem.
        hero = f"""<section class="scan-hero"><div class="cloud-layer" data-cloud="right" data-intensity=".38"></div><div class="foreground"><p class="kicker">READ-ONLY SETUP SCAN</p><h2>{html.escape(headline)}</h2><p class="of">{html.escape(lead)}</p><div class="scan-measure"><div><div class="big">{big}<small>{unit}</small></div><div class="bar"><i style="width:{reach_pct}%"></i></div><p class="scan-reach">{s['reached']} of {s['installed']} skills reached in this window &middot; {s['confirmed_loads']} loads from {s['load_attempts']} attempts</p></div></div></div></section>"""
    else:
        # No dormancy headline, no bar, no percentage. Nothing was measured, and
        # a zero here would read as a finding rather than an absence.
        headline = "%s installed. Nothing was measured." % plural(s["installed"], "skill")
        coverage_line = ("No sessions were readable in the last %s, so this scan counts what is "
                         "installed and what is misconfigured, not what gets used."
                         % plural(s["window_days"], "day"))
        hero = ('<section class="scan-hero"><div class="cloud-layer" data-cloud="right" data-intensity=".38"></div><div class="foreground"><p class="kicker">READ-ONLY SETUP SCAN</p><h2>Installed setup, <span>unmeasured usage.</span></h2><div class="big">&hellip;</div>'
                '<p class="tiny">Nothing was measured.</p>'
                '<p class="of">No usage to report. This is not a clean bill of health and it is '
                'not an alarm: the window held no sessions to read.</p></div></section>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">
<title>{title}</title>
<meta name="description" content="How much of your installed agent capability your agent actually reaches.">
<style>{CSS}</style></head><body><div class="wrap scan-wrap">
<nav class="nav" aria-label="Report header"><a class="brand" href="/" rel="noreferrer" aria-label="Edge home"><svg class="edge-logo" viewBox="0 0 102 94" aria-hidden="true"><g fill="currentColor" transform="translate(12 12)"><path d="M1 43 42 28v27L1 70V43ZM34 17 78 0v28L47 40V23l-13 5V17Z"/></g></svg>Edge<span class="brand-divider"></span><span class="brand-product">Brain Surgery</span></a>
<div class="nav-links"><span class="location">{where}</span></div></nav>
<header class="scan-head"><h1>Your brain scan</h1><p class="tiny">{html.escape(coverage_line)}</p></header>
{hero}
<div class="scan-stats">{stat_html}</div>
<section class="scan-section"><div class="scan-section-head"><div><p class="kicker">WHAT THE SCAN FOUND</p><h2>Signals from your setup.</h2></div><p>Diagnostic findings, ordered by confidence. This scan did not test a candidate or change your setup.</p></div>
{groups_html(raw, s, local)}</section>{('<section class="scan-section scan-evidence">' + evidence + '</section>') if evidence else ''}
<p class="note">{caveat}</p>
<footer class="footer"><span>Brain Surgery, by Edge.<br>Nothing here was applied. {'Private until you choose to share.' if local else 'Counts only. Private work stays on the machine.'}</span><span class="tiny">Read-only scan</span></footer>
</div><script id="{data_id}" type="application/json">{payload}</script><script>{CLOUD_JS}</script><script>window.Clouds&&window.Clouds.mountAll();</script></body></html>"""


def write_private(path: Path, text: str) -> None:
    """Create at 0600, never wider. write_text then chmod leaves a window in
    which the local report, which carries the skill names, is world readable."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)  # An existing file keeps its old mode through O_CREAT.


def render(raw: dict[str, Any], out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(out, 0o700)  # mode= only applies on creation, and umask masks it.
    s = summarize(raw)
    # Public HTML deliberately receives no raw scan. The summary is an
    # allowlist, and rendering from it proves a later display change cannot
    # accidentally publish skill names, paths, details, or fixes.
    write_private(out / "public-scan.html", page(s, None, local=False))
    write_private(out / "local-scan.html", page(s, raw, local=True))
    write_private(out / "public-scan-summary.json", json.dumps(s, indent=2))
    return s


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        s = render(json.loads(a.input.read_text()), a.out)
    except (OSError, ValueError, TypeError, KeyError) as e:
        p.exit(2, "Render failed: %s\n" % e)
    if s["measured"]:
        print("Scan report written. %d installed, %d reached, %d%% dormant. "
              "No upload or live setup changes."
              % (s["installed"], s["reached"], s["dormant_percent"]))
    else:
        print("Scan report written. %d installed, no sessions readable in the window, so "
              "usage is unmeasured. Findings that do not need transcripts are still in the "
              "report. No upload or live setup changes." % s["installed"])


if __name__ == "__main__":
    main()
