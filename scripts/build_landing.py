#!/usr/bin/env python3
"""Derive a production-safe landing page from the approved UI prototype."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROMPT = (
    "Install Brain Surgery from https://github.com/agilabs-ai/brain-surgery after reviewing "
    "SKILL.md and its scripts. Scan my recent work and installed skills, then open my private "
    "report. Ask before running comparisons, changing my setup, or sharing anything."
)


def _one(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        raise ValueError(f"approved landing source is missing {pattern!r}")
    return match.group(1)


def build(source: str) -> str:
    css = _one(r"<style>(.*?)</style>", source)
    templates = json.loads(
        _one(r'<script id="page-templates" type="application/json">(.*?)</script>', source)
    )
    fragment = templates["landing"]

    mark = ('<svg class="edge-logo" viewBox="0 0 100 66.6667" aria-hidden="true">'
            '<path d="M 0 50 A 50 50 0 0 1 100 50 L 100 66.6667 L 0 66.6667 Z" '
            'fill="currentColor"/></svg>')
    fragment = re.sub(r'<svg class="edge-logo".*?</svg>Edge', mark + 'agi labs', fragment)
    fragment = fragment.replace('getedge.cc', 'github.com/agilabs-ai')
    fragment = fragment.replace('Brain Surgery, by Edge.', 'Brain Surgery, by AGI Labs.')

    # The named synthetic fixture becomes an unmistakable, non-personal example.
    fragment = fragment.replace("Federico’s", "Example").replace("FEDERICO’S", "EXAMPLE")
    fragment = fragment.replace("Federico De Ponte", "Example user")
    fragment = fragment.replace("Building Edge", "Illustrative results")
    fragment = fragment.replace("Building AGI Labs", "Illustrative results")
    fragment = fragment.replace('<span class="avatar fd">FD</span>', '<span class="avatar fd">EX</span>')
    fragment = fragment.replace('id="federico"', 'id="example"')
    fragment = fragment.replace('href="#public" data-route="public"', 'href="#example"')
    fragment = fragment.replace('href="#landing" data-route="landing"', 'href="/"')
    fragment = fragment.replace(
        'href="#example">View Example report',
        'href="/report.html">View Example report',
    )

    # Keep the landing card exactly aligned with examples/demo-result.json, which
    # is the source for the linked public report (2/6 -> 5/6 passing tasks).
    aligned_metrics = {
        '+25 <small>pts</small>': '+50 <small>pts</small>',
        '7 points above average': '32 points above average',
        'current 60 percent, tested 85 percent': 'current 33 percent, tested 83 percent',
        'data-percent="60.00000" data-side="current" x="20" y="179.200" width="195" height="202.800"':
            'data-percent="33.33333" data-side="current" x="20" y="269.333" width="195" height="112.667"',
        'data-percent="85.00000" data-side="tested" x="20" y="94.700" width="195" height="287.300"':
            'data-percent="83.33333" data-side="tested" x="20" y="100.333" width="195" height="281.667"',
        '<div class="stat-big">60<small>%</small>': '<div class="stat-big">33<small>%</small>',
        '<div class="stat-big blue">85<small>%</small>': '<div class="stat-big blue">83<small>%</small>',
        '4 tasks · Same model · 3 targeted changes': '6 tasks · Same model · 2 targeted changes',
    }
    for old, new in aligned_metrics.items():
        fragment = fragment.replace(old, new)

    # Production landing: one promise, one action, one complete example.
    fragment = fragment.replace('Find what holds your AI back.<br>Test the fixes on your work.',
                                'Find what’s holding your AI back.<br>Test a better setup on your own work.')
    fragment = fragment.replace('<code>Give my AI brain surgery.</code>',
                                f'<code>{PROMPT}</code>')
    fragment = fragment.replace('<div class="prompt-box">', '<div class="prompt-box" id="setup-prompt">', 1)
    fragment = fragment.replace('>Copy prompt<', '>Copy setup prompt<')
    fragment = fragment.replace('See Example’s scan', 'See example report')
    fragment = fragment.replace('Example’s scan', 'Example report')
    fragment = fragment.replace('See Example scan', 'See example report')
    fragment = fragment.replace('>Example scan<', '>Example report<')
    fragment = fragment.replace('href="#example" data-route="landing"', 'href="/report.html"')
    fragment = fragment.replace('href="#example"', 'href="/report.html"')
    fragment = fragment.replace('href="#example">See example report', 'href="/report.html">See example report')
    fragment = fragment.replace('How it works</a>', 'Source</a>')
    fragment = fragment.replace('href="#how" data-scroll="how"',
                                'href="https://github.com/agilabs-ai/brain-surgery" target="_blank" rel="noreferrer"')
    fragment = re.sub(r'<p class="participation">.*?</p>', '', fragment, count=1, flags=re.DOTALL)
    fragment = fragment.replace('Model usage applies. You approve changes.',
                                'For Claude Code and Codex. Changes need your approval.')
    fragment = re.sub(r'<section class="community">.*?</section>\s*', '', fragment, count=1, flags=re.DOTALL)
    fragment = re.sub(r'<section class="section" id="work">.*?</section>\s*', '', fragment, count=1, flags=re.DOTALL)
    fragment = re.sub(r'<section class="end-cta">.*?</section>\s*', '', fragment, count=1, flags=re.DOTALL)
    fragment = fragment.replace('I gave my AI brain surgery.', 'Same model. Better setup.')
    fragment = re.sub(r'<div class="case-person">.*?</div></div>', '</div>', fragment, count=1, flags=re.DOTALL)
    fragment = fragment.replace('View Example report', 'Open the complete example report')
    fragment = fragment.replace('Illustrative example only. Sample scores and outputs are not a measured personal result.',
                                'Fictional tasks and results, provided to show what the complete report contains.')

    compact_steps = '''<section class="section" id="how"><div class="section-head"><div><p class="kicker">HOW IT WORKS</p><h2>Inspect. Test. Review.</h2></div></div><div class="minimal-steps"><div><span>01</span><strong>Inspect</strong><p>Your agent reviews recent work and installed skills.</p></div><div><span>02</span><strong>Test</strong><p>Approve a bounded comparison on the same tasks.</p></div><div><span>03</span><strong>Review</strong><p>See the evidence before changing your setup.</p></div></div></section>'''
    fragment = re.sub(r'<section class="section" id="how">.*?</section>', compact_steps,
                      fragment, count=1, flags=re.DOTALL)
    faq = '''<section class="section"><div class="section-head"><div><p class="kicker">BEFORE YOU START</p><h2>Three things to know.</h2></div></div><div class="faq"><details><summary>What happens when I start?</summary><p>Your agent begins with a read-only scan and opens a private report. If the findings justify testing a change, it proposes the tasks, limits, and usage before asking you to proceed.</p></details><details><summary>What can change?</summary><p>Skills and the project instructions that activate them. You review proposed changes before anything is applied.</p></details><details><summary>What stays private?</summary><p>Your report stays local. Inputs used for an approved comparison may reach your configured model provider. Sharing a report is a separate action.</p></details></div></section>'''
    fragment = re.sub(r'<section class="section"><div class="faq"><div class="section-head"><div><p class="kicker">BEFORE YOU START</p>.*?</section>',
                      faq, fragment, count=1, flags=re.DOTALL)
    fragment = fragment.replace('<a class=""  href="#how">Method</a>',
                                '<a href="/brain-surgery.zip" download>Download ZIP</a>')

    prompt_action = f'''<div class="prompt-actions" id="setup-prompt"><button class="btn btn-dark" data-action="copy-prompt">Copy setup prompt<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M15 8V4H4v11h4"/></svg></button><details class="prompt-disclosure"><summary>Read the prompt</summary><code>{PROMPT}</code><a class="text-link" href="/brain-surgery.zip" download>Download ZIP ↓</a></details></div>'''
    fragment = re.sub(r'<div class="prompt-box" id="setup-prompt">.*?</div>', prompt_action,
                      fragment, count=1, flags=re.DOTALL)

    # Keep the approved labels as ordinary in-page links, not dead prototype
    # controls that appear to scan, apply, publish, or reveal evidence.
    destinations = {
        "community": "#example-note",
        "task": "#example-note",
        "method": "#how",
        "score": "#how",
        "scope": "#how",
        "privacy": "#privacy-note",
    }
    for action, destination in destinations.items():
        pattern = re.compile(
            rf'<button(?P<attrs>[^>]*) data-action="{action}"(?P<tail>[^>]*)>(?P<body>.*?)</button>',
            re.DOTALL,
        )
        fragment = pattern.sub(
            lambda m: f'<a{m.group("attrs")}{m.group("tail")} href="{destination}">{m.group("body")}</a>',
            fragment,
        )

    fragment = fragment.replace('data-action="copy-prompt"', 'data-copy-prompt="true"')
    fragment = re.sub(
        r'<p class="tiny" style="margin-top:12px;font-size:10px">Sample scores and outputs,[^<]*</p>',
        '<p class="tiny" id="example-note" style="margin-top:12px;font-size:10px">Fictional tasks and results, provided to show what the complete report contains.</p>',
        fragment,
        count=1,
    )
    fragment = fragment.replace(
        '<p class="note">One prompt. Your agent. Your work.</p>',
        '<p class="note">One prompt. Your agent. Your work.</p><p style="margin-top:14px"><a class="text-link under" href="/brain-surgery.zip" download>Download brain-surgery.zip</a></p>',
    )
    fragment = fragment.replace(
        '<span>Brain Surgery, by AGI Labs.</span>',
        '<span id="privacy-note">Brain Surgery, by AGI Labs. Local-first; nothing is uploaded by this page.</span>',
    )
    fragment = fragment.replace('<a class=""  href="#how">Method</a>',
                                '<a href="/brain-surgery.zip" download>Download ZIP</a>')

    if "data-action=" in fragment or "data-route=" in fragment:
        raise ValueError("unsafe prototype controls remain in production fragment")

    safe_prompt = json.dumps(PROMPT).replace("<", "\\u003c")
    production_css = '''
.minimal-steps{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.minimal-steps>div{padding:26px 24px 28px 0;border-right:1px solid var(--line)}
.minimal-steps>div+div{padding-left:24px}.minimal-steps>div:last-child{border-right:0}
.minimal-steps span{display:block;font:9px var(--mono);color:#999;margin-bottom:18px}.minimal-steps strong{font-size:16px;font-weight:550}.minimal-steps p{font-size:12px;line-height:1.65;color:#777;margin-top:8px}
.prompt-actions{width:min(565px,100%);margin:0 auto;display:flex;flex-direction:column;align-items:center;gap:9px}.prompt-actions>.btn{min-width:190px}.prompt-disclosure{width:100%;font-size:11px;color:#666}.prompt-disclosure summary{cursor:pointer;list-style:none;text-decoration:underline;text-underline-offset:3px}.prompt-disclosure summary::-webkit-details-marker{display:none}.prompt-disclosure code{display:block;text-align:left;white-space:normal;font:11px/1.65 var(--mono);padding:14px 16px;margin-top:10px;border:1px solid var(--line);border-radius:9px;background:#fff}.prompt-disclosure .text-link{justify-content:center}.landing-hero{min-height:auto;padding-bottom:72px}.case-shell{margin-top:24px}
@media(max-width:640px){.minimal-steps{grid-template-columns:1fr}.minimal-steps>div,.minimal-steps>div+div{padding:21px 0;border-right:0;border-bottom:1px solid var(--line)}.minimal-steps>div:last-child{border-bottom:0}.prompt-actions>.btn{width:100%;min-height:46px}}
'''
    return f'''<!doctype html>
<html lang="en" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer">
<title>Brain Surgery by AGI Labs</title>
<link rel="icon" href="/assets/brand/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/brand/favicon-32x32.png">
<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon.png">
<meta name="description" content="Find what holds your AI back, then test targeted fixes on your work.">
<style>{css}{production_css}</style></head><body>
{fragment}
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script src="/assets/approved-cloud.js"></script>
<script>"use strict";const prompt={safe_prompt};const toast=document.getElementById("toast");
document.querySelectorAll("[data-copy-prompt]").forEach(button=>button.addEventListener("click",async()=>{{
  try{{await navigator.clipboard.writeText(prompt);toast.textContent="Copied. Paste into your agent.";}}
  catch(error){{toast.textContent="Copy blocked. Download the skill or copy from the source repository.";}}
  toast.classList.add("show");setTimeout(()=>toast.classList.remove("show"),3000);
}}));window.Clouds?.mountAll?.();</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rendered = build(args.source.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
