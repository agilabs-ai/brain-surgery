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

SCHEMA = "brain-surgery-scan/0.1"
PUBLIC_SCHEMA = "brain-surgery-scan-public/0.1"

# What each finding code means to the person reading it. The scan writes its own
# per-skill title and detail; this supplies the heading the codes group under, so
# five shadowed skills read as one problem rather than five separate alarms.
GROUPS = {
    "load_failed": ("Skills that failed when your agent reached for them",
                    "Your agent tried to use these and got an error back. The work continued without them."),
    "shadowed": ("Skills competing for the same trigger",
                 "More than one skill claims this work. Which one your agent picks is not something you control."),
    "inventory_gap": ("Skills loaded from outside the inventory",
                      "Your agent loaded these from somewhere this scan could not see, so their contents were never checked."),
    "dormant": ("Installed and never reached",
                "Present on the machine, not loaded once in the scanned window."),
    "no_evidence": ("No sessions were read in this window",
                    "Nothing below is a measurement of use. Widen the window or scan a "
                    "project that has transcripts to get one."),
}
ORDER = ["load_failed", "shadowed", "inventory_gap", "dormant", "no_evidence"]

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
        "evaluation_performed": bool(raw.get("evaluation_performed", False)),
        "change_status": raw.get("change_status", "not_applied"),
        "scan_complete": bool(raw.get("scan_limits", {}).get("complete", False)),
    }


CSS = """
:root{--paper:#FFFFFF;--ink:#050505;--line:#E5E5E5;--blue:#154CFF;--muted:#6B6B6B;--r:9px;
  --pad:max(20px,env(safe-area-inset-left,0px))}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:15px/1.55 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:0 var(--pad);padding-block:32px 64px}
.nav{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
  padding-bottom:20px;border-bottom:1px solid var(--line)}
.brand{font-weight:650;letter-spacing:-.02em;color:var(--ink);text-decoration:none}
.tag{font-size:12px;color:var(--muted)}
h1{font-size:clamp(28px,6vw,40px);letter-spacing:-.03em;margin:36px 0 6px;text-wrap:balance}
.sub{color:var(--muted);margin:0 0 32px}
.hero{border:1px solid var(--line);border-radius:var(--r);padding:28px 24px;margin-bottom:28px}
.big{font-size:clamp(40px,11vw,68px);line-height:1;letter-spacing:-.04em;font-weight:680}
.big small{font-size:.38em;font-weight:600;color:var(--muted);letter-spacing:-.01em}
.of{color:var(--muted);margin:10px 0 22px}
.bar{height:10px;border-radius:99px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--blue);border-radius:99px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;margin-bottom:28px}
.stat{background:var(--paper);padding:16px 18px}
.stat b{display:block;font-size:22px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat span{font-size:12px;color:var(--muted)}
h2{font-size:18px;letter-spacing:-.02em;margin:32px 0 4px}
h2 + p{margin:0 0 14px;color:var(--muted);font-size:13px}
.group{border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;margin-bottom:14px}
ul{margin:0;padding-left:18px}
li{margin:6px 0}
li small{color:var(--muted)}
.count{display:inline-block;background:var(--ink);color:var(--paper);border-radius:99px;
  padding:1px 9px;font-size:12px;font-variant-numeric:tabular-nums;margin-left:6px}
summary{cursor:pointer;color:var(--muted);font-size:13px;list-style:revert}
details ul{margin:8px 0 0}
.note{border-left:2px solid var(--blue);padding:2px 0 2px 14px;color:var(--muted);font-size:13px;margin:24px 0}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0A0A0A;--ink:#F5F5F5;--line:#242424;--muted:#9A9A9A}}
:root[data-theme="dark"]{--paper:#0A0A0A;--ink:#F5F5F5;--line:#242424;--muted:#9A9A9A}
"""


def groups_html(raw: dict[str, Any], local: bool) -> str:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for f in raw.get("findings", []):
        by_code.setdefault(f.get("code", "other"), []).append(f)
    out = []
    for code in ORDER:
        items = by_code.get(code)
        if not items:
            continue
        title, detail = GROUPS[code]
        # Count skills, not findings. One whole-setup finding carries the names of
        # every skill it covers, and badging that group "1" beside a list of 163
        # names contradicts the list directly under it.
        affected = sum(1 if f.get("skill") else len(f.get("evidence", {}).get("names", []))
                       for f in items)
        if local:
            # Names only ever reach the local page.
            rows = []
            for f in items:
                name = f.get("skill")
                if name:
                    rows.append("<li>%s<small> &middot; %s</small></li>"
                                % (html.escape(str(name)), clamp(f.get("detail", ""))))
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
        out.append('<div class="group"><h2>%s<span class="count">%d</span></h2><p>%s</p>%s</div>'
                   % (html.escape(title), affected, html.escape(detail), body))
    return "".join(out)


def page(s: dict[str, Any], raw: dict[str, Any], local: bool) -> str:
    reach_pct = round(100.0 * s["reached"] / s["installed"]) if s["installed"] else 0
    where = "Local scan &middot; not shared" if local else "Shared scan"
    title = "Brain Surgery by AGI Labs &middot; %s scan" % ("local" if local else "shared")
    # The headline is the count, not an adjective. A person reading their own
    # number should not have to trust our word for how bad it is.
    one = lambda n, a, b: a if n == 1 else b
    stats = [
        (s["installed"], one(s["installed"], "skill installed", "skills installed")),
        (s["reached"], "reached in this window"),
        (s["failed_loads"], one(s["failed_loads"], "load returned an error", "loads returned an error")),
        (s["sessions_analyzed"], one(s["sessions_analyzed"], "session read", "sessions read")),
    ]
    stat_html = "".join('<div class="stat"><b>%s</b><span>%s</span></div>' % (f"{n:,}", html.escape(l))
                        for n, l in stats)
    caveat = ("Counts cover the %s read in this scan, not your whole history. "
              "A skill with no recorded load was not reached in this window; that is not "
              "proof it is never used. Nothing was executed, uploaded, or changed."
              % plural(s["sessions_analyzed"], "session"))
    evidence = ""
    if local:
        top = raw.get("most_used", [])[:8]
        if top:
            rows = "".join("<li>%s<small> &middot; %d load%s</small></li>" % (
                html.escape(str(x["skill"])), x["loads"], "" if x["loads"] == 1 else "s") for x in top)
            evidence = ('<div class="group"><h2>What your agent actually reaches</h2>'
                        '<p>The skills that carried your work in this window.</p><ul>%s</ul></div>' % rows)
    # Escaped for a <script> context, not an HTML text one. Character references
    # are not decoded inside a script element, so html.escape here would leave a
    # block that reads `{&quot;installed&quot;: ...}` and JSON.parse would throw.
    # `<` and `&` as \\u escapes keep it parseable and still close no tag.
    payload = (json.dumps(raw if local else s, indent=1)
               .replace("&", "\\u0026").replace("<", "\\u003c"))
    data_id = "local-data" if local else "summary-data"

    if s["measured"]:
        headline = "%s installed. Your agent reached %d." % (
            plural(s["installed"], "skill"), s["reached"])
        coverage_line = "Read from %s turn%s across %s, last %s." % (
            f"{s['turns_analyzed']:,}", "" if s["turns_analyzed"] == 1 else "s",
            plural(s["sessions_analyzed"], "session"), plural(s["window_days"], "day"))
        hero = f"""<section class="hero"><div class="big">{s['dormant_percent']}<small>%</small></div>
<p class="of">of installed capability was never loaded in this window.</p>
<div class="bar"><i style="width:{reach_pct}%"></i></div>
<p class="of" style="margin:10px 0 0;font-size:13px">{reach_pct}% reached &middot; {s['confirmed_loads']} confirmed loads from {s['load_attempts']} attempts</p></section>"""
    else:
        # No dormancy headline, no bar, no percentage. Nothing was measured, and
        # a zero here would read as a finding rather than an absence.
        headline = "%s installed. Nothing was measured." % plural(s["installed"], "skill")
        coverage_line = ("No sessions were readable in the last %s, so this scan counts what is "
                         "installed and what is misconfigured, not what gets used."
                         % plural(s["window_days"], "day"))
        hero = ('<section class="hero"><div class="big">&hellip;</div>'
                '<p class="of">No usage to report. This is not a clean bill of health and it is '
                'not an alarm: the window held no sessions to read.</p></section>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">
<title>{title}</title>
<meta name="description" content="How much of your installed agent capability your agent actually reaches.">
<style>{CSS}</style></head><body><div class="wrap">
<nav class="nav"><a class="brand" href="/" rel="noreferrer">agi labs</a>
<span class="tag">{where}</span></nav>
<h1>{html.escape(headline)}</h1>
<p class="sub">{html.escape(coverage_line)}</p>
{hero}
<div class="stats">{stat_html}</div>
{groups_html(raw, local)}{evidence}
<p class="note">{caveat}</p>
<footer>Brain Surgery, by AGI Labs. Nothing here was applied. {'Private until you choose to share.' if local else 'Counts only. Private work stays on the machine.'}</footer>
</div><script id="{data_id}" type="application/json">{payload}</script></body></html>"""


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
    write_private(out / "public-scan.html", page(s, raw, local=False))
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
