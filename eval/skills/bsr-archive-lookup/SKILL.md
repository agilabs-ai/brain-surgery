---
name: bsr-archive-lookup
description: Use when asked where a past build, render, clip or asset lives, which version actually went out, or to hand someone the file for something that already exists. Defines how the answer is written and which path is the answer.
---

# Pointing at an archived build

Someone needs the file. The answer is one line, and it is the build that went
out, not the newest build and not the one that looks nicest.

## Which build

- Only a build marked as published is an answer. Drafts, colour passes and
  builds that were never sent are never the answer, whatever their date.
- If more than one build is published, take the one whose subject matches what
  was asked for, then the most recent of those.
- Never rebuild, re-render or copy the file. It exists. Point at it.

## Which path

Always the archive path. A render or cache path, anything under `/tmp`, is a
working copy the renderer left behind, it disappears, and it is never handed to
anyone. Do not name it, not even as an aside.

## The line

One line, three fields, separated by a space, two colons, a space:

```
<build id> :: <build date> :: <archive path>
```

For example:

```
mf-0388 :: 2026-01-22 :: media/2026-01/all-hands-v4.mp4
```

Nothing else in the file. No heading, no explanation, no second candidate, no
em dashes in any encoding.
