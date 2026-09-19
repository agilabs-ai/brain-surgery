# How to author a benchmark task

A task is three things: a prompt, a seeded workspace, and a deterministic verifier.
`run_grid.py` runs the prompt under four arms and hands the finished workspace to the
verifier. The verifier never learns which arm produced the workspace.

```
eval/tasks/<task-id>/task.json        required
eval/tasks/<task-id>/check.py         required
eval/tasks/<task-id>/workspace/       optional, copied verbatim into every run
eval/skills/<skill-name>/SKILL.md     the candidate skill the task is testing
```

## task.json

```json
{
  "id": "<task-id>",
  "workflow": "writing|coding|research|design|presentations|spreadsheets|other",
  "skill": "<skill-name under eval/skills/>",
  "prompt": "<the exact text piped to the agent, as a user would type it>",
  "seed": {"notes.md": "inline file contents, an alternative to workspace/"}
}
```

## Scope of this document

**This spec governs the legacy discovery corpus in `eval/tasks/` only. It is not the
specification for generated customer cases, and its central rule below must not be
carried into one.** See `references/DECISION_PLAN.md` for the rules a generated
performance case has to satisfy.

The distinction matters because the two ask different questions. This corpus asks
"does the agent find and apply a convention nobody told it about", which requires
withholding the convention. A customer performance case asks "does the proposed
change make the agent better at the customer's own work", which requires the
opposite: the request and its permitted context must establish what success needs,
and the candidate changes how the agent gets there, not what the grader secretly
wants.

## The rule this corpus is built on, and its cost

**In this corpus the prompt never mentions the convention the verifier checks, and
never hints that a skill exists.** It is written exactly as the user would type it on
a normal day. If the prompt says "keep it under 170 words", the task measures
instruction-following, which every arm passes, and the result is noise.

The with-skill arms therefore measure discovery and use together. That is the
intended measurement here. Say it out loud rather than engineering around it.

**What it costs, stated because it was not stated before.** A task built this way
cannot be passed without the skill, by construction. So the gap it measures is
convention discovery and compliance, not general capability, and reporting it as the
latter is how this corpus produced +72.2pp against SkillsBench's +16.2pp average.
Classify every check `outcome` or `convention` (see `checklib.py`) and report the two
apart, so the headline cannot be read as capability when it is mostly compliance.

**Not every convention is an exclusion.** A format the user actually required is a
legitimate success criterion and belongs in `outcome`. The line is *user-required
outcome* against *evidence that our mechanism activated*, not outcome against
formatting. A check that only proves the skill fired is an invocation indicator and
is reported beside the score, never inside it.

## What makes a good verifier

- **Deterministic.** Same workspace in, same exit code out, every time. No model
  calls, no network, no clock, no randomness. Standard library only.
- **Exit 0 to pass, non-zero to fail.** Print one line saying why on failure. That
  line is stored in the record and shown in the report, so make it specific:
  `'em dash at line 14: "shipped it, — and then"'` beats `'formatting wrong'`.
- **Checks the artifact, not the transcript.** Look at files on disk in the
  workspace. Never grep the agent's reasoning.
- **Tolerant where a human would be, strict where the convention is.** Accept
  `status.md` or `STATUS.md` if the prompt did not pin the name. Do not accept
  an em dash because it "reads fine".
- **Fails for the right reason.** If the file is missing, say the file is missing.
  Do not let a missing file fall through into a format error.

## Calibration: the task must be losable and winnable

Before you ship a task, satisfy yourself that:

1. A competent agent that has never seen the skill **can plausibly fail it**, because
   the convention is arbitrary and unguessable. If the "right" answer is what any
   model would produce by default, the task measures nothing.
2. A competent agent that **has read the skill can pass it**, using only what the
   SKILL.md states. If the skill is ambiguous about the thing the verifier checks,
   the task is broken, not hard.
3. It is **not a trick**. No hidden second file, no parsing gotcha, no requirement
   stated only in the verifier's source.

A task where all four arms pass, or all four fail, contributes nothing to any
contrast. Aim for the middle.

## The skill

One `SKILL.md` with YAML frontmatter:

```yaml
---
name: <skill-name>
description: Use when <the trigger>. <what it defines>.
---
```

The `description` is what the agent sees when deciding whether to open the skill, so
it must name the trigger situation in the words the prompt would use. A description
that only describes the contents is how a good skill never gets reached, which is a
real finding but not the one this task is for.

Body: state the convention, the rules as a list, and one worked example. Keep it
short. A skill that needs three screens to state a format is testing reading stamina.

## Provenance

Every task is derived from a shape that actually appears in the user's session logs,
with the session count recorded. Record it in a `# provenance:` comment at the top of
`check.py`: the shape name and the number of sessions it was seen in. A task nobody
does is a task nobody should be scored on.
