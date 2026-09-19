---
name: bsr-artifact-recall
description: Use when asked "did we already write this", "we did this before, no?", "check the history", "find the old draft", or to look through a history, archive or past-work directory before redoing something. Defines the house recall note that reports what was found, and the rule against rewriting or reproducing what already exists.
---

# Recalling past work

The ask is for a pointer, not for a new version of the thing. If it exists,
the answer is where it is.

## The one rule

Never rewrite, re-draft or re-render something that already exists, and never
paste its contents into the note. The past artifact stays exactly where it is,
byte for byte. The only file you write is the recall note itself.

## Picking between versions

When several versions of the same artifact exist, cite the newest one that is
not marked superseded. A file that says it is superseded is never the answer,
and neither is a file that merely talks about the artifact, such as a plan, a
schedule or a retro.

## The recall note

Exactly three lines, in this order, nothing else in the file:

```
FOUND: <path to the artifact, relative to where you were asked to look>
WHEN: <YYYY-MM-DD the artifact is filed under>
REUSE: yes
```

- `FOUND:` is one path. Not a list, not a description, no surrounding prose.
- `WHEN:` is an ISO date, taken from how the archive files the artifact.
- `REUSE:` is `yes` when the artifact can be used as it stands, and `no` when
  everything you found is superseded or is not the artifact that was asked for.
- No fourth line. No summary, no heading, no extract of the artifact.
- No em dashes anywhere, in any encoding.

Worked example:

```
FOUND: history/2025-11-03-pricing-page/copy-v2.md
WHEN: 2025-11-03
REUSE: yes
```
