---
name: bsr-handoff-note
description: Use when handing a thread, session or piece of work to someone else or to another machine, picking one up cold, or writing a note so the next person is not starting from zero. Defines the house handoff note.
---

# House handoff note

A handoff is read by someone who was not there. It is four blocks, always the
same four, always in this order.

```
HANDOFF <thread id>
## STATE
<one line, at most 25 words, where the work actually is right now>
## DONE
- <item>
- <item>
## OPEN
- <item>
- <item>
## RESUME
`<the command that continues the thread>`
```

Rules:

- Line 1 is `HANDOFF <thread id>`, the id exactly as it was given to you. It is
  not a markdown heading, so no `#` on that line.
- Exactly four sections, `## STATE`, `## DONE`, `## OPEN`, `## RESUME`, in that
  order. No extra sections, no section left out, nothing after RESUME.
- STATE is one line and at most 25 words. Not a paragraph.
- DONE and OPEN are `- ` bullets, one line each, no wrapping. OPEN carries
  everything unfinished, undecided or unverified. An empty OPEN block means you
  did not read the thread carefully enough.
- RESUME is one line: the resume command, copied from the thread, wrapped in
  backticks. Nothing else in that section.
- Every path you name is a durable path. A scratch or cache path, anything
  under `/tmp`, is never handed to the next person, even to warn them about it.
  Name the durable copy instead.
- No em dashes anywhere, in any encoding.

Worked example:

```
HANDOFF 7c10aa
## STATE
Export job runs end to end on dev, nothing has been pointed at production data.
## DONE
- CSV schema frozen and reviewed
- nightly job scheduled and green for four nights
## OPEN
- production credentials have never been used
- no alerting if the job silently exports zero rows
## RESUME
`bsr-resume 7c10aa --from step-4`
```
