---
name: bso-readonly-inspect
description: Use when asked to look at a browser session or tab snapshot and report what is open, whether an account is signed in, or what a page says, without changing anything. Defines the read-only inspection report format.
---

# Read-only session inspection

An inspection answers the question and proves it. It never changes the thing it
is looking at, and it never hands back a paragraph of prose.

## Rules

- **Change nothing.** No clicking, typing, submitting, closing, reopening, and
  no editing of the snapshot files. Not even whitespace.
- **No preamble.** The first character of the report is the count. No "Sure",
  no "I looked at", no heading.
- **Titles verbatim.** Tab titles are copied exactly as the snapshot records
  them, in the snapshot's order, including anything in brackets. A title that
  says `(signed out)` says it for a reason, so do not tidy it away.
- **Evidence, not inference.** The conclusion gets one line, and the line of
  text you read it off gets its own line, quoted exactly. If two tabs look like
  the same site, the evidence line is what tells them apart.

## Report shape

Write it to the file you were asked for, in exactly this order:

```
tabs: <count>
1. <first tab title>
2. <second tab title>
...
answer: <one line, the direct answer>
evidence: <the exact text from the page that shows it>
mutations: none
```

Worked example, a three tab snapshot where the question was whether the billing
console is signed in:

```
tabs: 3
1. Billing console
2. Billing console (logged out)
3. Weekly report
answer: yes, signed in on tab 1 as Harbour Logistics
evidence: Account: Harbour Logistics (org id hl-04)
mutations: none
```

`mutations: none` is the last line of every read-only inspection. It is the
explicit statement that nothing in the session was touched. If something was
changed, the inspection was not read-only and you say what changed instead.
