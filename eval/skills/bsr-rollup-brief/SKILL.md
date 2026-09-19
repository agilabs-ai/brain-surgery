---
name: bsr-rollup-brief
description: Use when someone who has lost the thread asks where a piece of work stands, wants a tldr, a state of play, a catch-up or a 0-100 read on a project, and wants it written into a file. Defines the house rollup format.
---

# House rollup format

A rollup is read on a phone between two other things. It is a fixed skeleton,
never prose, and never longer than 20 lines.

```
# ROLLUP <slug>
SCORE: <0-100>
DONE
- <item>
- <item>
OPEN
- <item>
- <item>
NEXT: <the one action that happens next>
```

Rules:

- Line 1 is `# ROLLUP <slug>`. The slug is the subject in lowercase with
  hyphens, for example `ingest-rewrite`. Nothing else on that line.
- Line 2 is `SCORE: <n>`, one integer from 0 to 100, being your honest read of
  how finished the work is. No percent sign, no range, no decimals, no words.
- Then the bare word `DONE` on its own line, then 1 to 6 bullets. Each bullet
  starts with `- `, is one line, and never wraps onto a second line.
- Then the bare word `OPEN` on its own line, then 1 to 6 bullets in the same
  shape. Open means not finished, blocked, or unknown.
- The last line is `NEXT: <action>`. Exactly one action, one line, the one you
  would start with tomorrow morning.
- `DONE` and `OPEN` are bare words, not markdown headings. No `##`.
- No prose paragraphs, no code fences, no tables, no closing summary.
- No em dashes anywhere, in any encoding. Use a comma or a full stop.

Worked example, a rollup of a billing migration:

```
# ROLLUP billing-migration
SCORE: 70
DONE
- invoices table migrated on dev and the down path is tested
- the importer reads both the old and the new column names
OPEN
- nightly reconciliation job has never been run against real volume
- nobody has signed off on the cutover window
NEXT: run reconciliation against a copy of production data
```
