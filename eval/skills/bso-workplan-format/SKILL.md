---
name: bso-workplan-format
description: Use when asked to write a workplan, a plan of record, or to turn notes into a clear plan, or to report where a workplan stands. Defines the required workplan file, the step line format and the verification section.
---

# Workplan format

A workplan is a file you can reread in three weeks and still know where things
stand. Prose plans fail that test, so the format is fixed.

Write it as a markdown file named `WORKPLAN.md` in the working directory. Not
into `/tmp`, not only into the reply.

## Structure

```markdown
# Workplan: <short title>

## Steps
- [ ] <what happens, one line> @<owner> [status:todo]
- [ ] <what happens, one line> @<owner> [status:doing]
- [x] <what already happened> @<owner> [status:done]

## Verification
$ <command that proves the work landed>
```

## Step lines

- Every step is a markdown checkbox. A plain bullet is not a step, it is a note,
  and it does not belong under `## Steps`.
- Every step carries exactly one `@owner` token. Use the name the notes use, in
  lower case. Unowned work does not get done, so there is no unowned step.
- Every step carries exactly one `[status:...]` token, and the value is one of
  exactly four words:

  | status | means |
  | --- | --- |
  | `todo` | not started |
  | `doing` | in progress right now |
  | `blocked` | waiting on something outside this step |
  | `done` | finished and verified |

- The checkbox and the status agree. `[x]` is only ever paired with
  `[status:done]`, and `[status:done]` is only ever paired with `[x]`.
- Work that is already finished stays in the plan, ticked off. Deleting it hides
  progress.

## Verification section

Every workplan ends with a `## Verification` section holding at least one line
that starts with `$ ` and names the actual command someone runs to check the
work. "Review manually" is not a verification.

## House rule

No em dashes anywhere in the plan, in any encoding, including `&mdash;`.
