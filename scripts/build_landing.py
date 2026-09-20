#!/usr/bin/env python3
"""Derive a production-safe landing page from the approved UI prototype."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROMPT = (
    "Run Brain Surgery using https://github.com/agilabs-ai/brain-surgery. "
    "Read SKILL.md first, then run the default read-only scan of my permitted recent "
    "work and installed skills and show me the private report. Only if those findings "
    "justify a bounded comparison, propose its frozen changes, tasks, criteria, time, "
    "and usage plan and wait for my approval before running it. "
    "Keep my live setup unchanged and my report private until I explicitly approve otherwise."
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
    fragment = fragment.replace(
        '<span>Paste into your agent.</span>',
        '<span>Paste into your agent.</span><a class="text-link" href="/brain-surgery.zip" download>Download skill ↓</a>',
        1,
    )
    fragment = re.sub(
        r'<p class="tiny" style="margin-top:12px;font-size:10px">Sample scores and outputs,[^<]*</p>',
        '<p class="tiny" id="example-note" style="margin-top:12px;font-size:10px">Illustrative example only. Sample scores and outputs are not a measured personal result.</p>',
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

    if "data-action=" in fragment or "data-route=" in fragment:
        raise ValueError("unsafe prototype controls remain in production fragment")

    safe_prompt = json.dumps(PROMPT).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="en" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer">
<title>Brain Surgery by AGI Labs</title>
<link rel="icon" href="/assets/brand/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/brand/favicon-32x32.png">
<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon.png">
<meta name="description" content="Find what holds your AI back, then test targeted fixes on your work.">
<style>{css}</style></head><body>
<div class="preview-ribbon" role="note">DESIGN PREVIEW · ILLUSTRATIVE EXAMPLE · SAMPLE RESULTS · NO SCAN RUNS ON THIS PAGE</div>
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
