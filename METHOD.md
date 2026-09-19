# Method

Brain Surgery measures whether a change to a coding agent's setup, a skill, an
instruction, a configuration, actually makes the agent better at the user's own work.
It is an experiment, not a benchmark and not an opinion. This document states the design
so a skeptical reader can decide whether to trust a report, and reproduce one.

The machine-checkable contracts live alongside this file: `references/RUNTIME.md` (what
runs and under what bounds), `references/RESULT_FORMAT.md` (the scored record and how the
numbers are computed), `references/ADAPTER.md` (the request/response contract for a host's
model backend), and `references/PUBLIC_SKILL_IDENTITY.md` (how a skill's identity is
established). This file is the rationale those contracts implement.

## The problem

Most agent setups are changed on vibes. Someone installs a skill, adds a rule to a config
file, rewrites a prompt, and keeps it because the next thing they tried happened to work.
There is no counterfactual. Two things are conflated every time:

1. **Does the change help when it is used?**
2. **Does the agent actually reach the change when it should?**

A skill can be excellent and never fire. A skill can fire constantly and change nothing. A
rule can help one workflow and quietly break another. None of this is visible from a single
timeline of successes, because the timeline has no control arm. Brain Surgery builds the
control arm.

## The unit of measurement is the user's own task

The evidence is the user's real recent sessions, not a public benchmark. A benchmark tells
you how a setup does on someone else's problems; it cannot tell you whether *your* setup
fits *your* work. So the tool reads a bounded, read-only window of the local agent
transcripts and the installed skills, and it derives task episodes from them.

A task episode is not a single turn. A request and the corrections that followed it are one
episode, because the thing being judged is whether the work got done, not whether the first
message happened to land. The inspector extracts turns; the analysis groups them and selects
a disjoint confirmation set. An invocation rate is never computed with every session as its
denominator when only some sessions were relevant. (See `references/RUNTIME.md`, "Scope and
budget notes".)

## Two arms, same model, same tasks

The experiment holds everything fixed except the one variable under test.

- **Current arm:** the user's setup as it is today.
- **Tested arm:** the setup with one small, frozen candidate change applied.

Both arms run the *same* task inputs against the *same* model. The only difference between
them is the setup. That is what isolates the setup as the cause of any measured difference.
The candidate is frozen before any task runs (`brain_surgery.py freeze`), so the change
cannot be edited mid-experiment to chase a better score.

Gains are reported as outcomes under the entire frozen bundle. Brain Surgery does not claim
independent causal attribution to an individual patch inside the bundle; that is a stronger
claim than a paired setup comparison can support, and the report says so.

## Controls against the ways this normally goes wrong

Every choice below exists because the naive version of this measurement lies in a specific,
known way.

- **Fresh copied workspaces, no secrets.** Each arm runs in an isolated, freshly copied
  workspace without the user's credentials. Task inputs and the controlled configuration are
  the only things that enter the sandbox. Credentials, original project paths, and known
  reference answers are never placed in the generation prompt. Inputs are treated as
  untrusted. (A real OS or container sandbox is required for third-party candidate code;
  the wrapper's `shell=False`, minimal environment, and timeouts are not a substitute.)

- **Randomized arm ordering.** The arms are run in randomized order so that ordering effects,
  caches, warm-ups, drift, cannot systematically favor "current" or "tested".

- **Fixed-check grading.** Each task is graded against a pass criterion that is declared
  before the run, by a deterministic check, not by a judge asked after the fact whether the
  output looks good. `before` and `after` are booleans for the *same* predeclared criterion
  on the same task. Where a frozen checklist or a model judge is used instead, the record
  labels it (`human_checklist`, `model_judge`, `mixed`) rather than passing it off as a
  deterministic check.

- **Ties count as failures.** When a side is run for multiple trials, its verdict is the
  majority across trials and a tie counts as a failure, so noise never rounds up into a win.

- **Trials change the denominator, not the sample.** Running a task more than once is a
  robustness measure. It does not turn one task into several: task IDs stay unique and the
  sample size stays the number of tasks. The page reports the task count as the sample even
  when percentages are computed over trials.

- **A display floor, not a significance claim.** At least two comparable tasks are required
  before any percentage is shown. This is an honesty floor on the display, explicitly not a
  claim of statistical significance. Small samples are small; the report does not dress them
  up.

## A pass is two questions, and they are scored apart

A task's checks do not all ask the same kind of thing. Some ask whether the job was done:
did the agent produce the right answer, keep the data intact, leave the thing working. Others
ask whether the output matches a local rule that exists only in the setup: an exact filename,
a fixed field name, a required artifact the request never mentions.

Scoring those together as one pass/fail bit makes the measurement useless, and it did.

The `disk-reclaim-report` task asks for a scratch directory to be cleaned without touching
what is queued for the archive. Its verifier checks four things. The archive survived and
real space came back: both are in the prompt, in those words. A file named exactly
`reclaim-report.md` exists, and it accounts for every candidate with its size and a
`keep`/`remove` verdict: neither is anywhere in the prompt. An agent that cleaned the
directory correctly, preserved the archive, and did not invent a document nobody asked for
scored **zero**, the same as an agent that deleted the only copy of the archive.

Repeated across the corpus, that is why a no-skill arm measured near zero, and why a naive
reading of the gap credited the setup with capability it did not supply.

So every check now carries a class:

- **outcome** — passable by a competent agent that has never seen the setup, using only the
  request and the workspace. The request asked for it, or it is plain correctness or safety.
- **convention** — knowable only from the setup. A house filename, a field vocabulary, a
  required section, a format string.

Each arm reports a rate for each class, as a task-macro average over the tasks that carry
checks of that class. A task asserting no convention contributes nothing to the convention
rate rather than scoring zero on it, because a check nobody wrote is not a check an arm
failed. Where no task has been graded for a class, the rate is `null`, never `0`.

Both numbers are real and both are reported. The outcome rate is the fair fight and is the
only one that supports a claim about capability. The convention rate is where a setup
legitimately dominates, and it is worth measuring precisely because convention misses are
real rework for the user. What is not allowed is multiplying them into a single number and
describing the result as what the setup is worth.

The classification is a judgment, it is made by us, and it is visible: every check names its
class in the verifier source, with a comment giving the reason. A reader who disagrees with
a call can find it and argue with it. That is the point of writing it down rather than
leaving it implicit in a threshold.

## Invocation is measured separately from quality

Whether the agent *reached* a skill is a different question from whether the skill *helped*,
and the two are never merged. Invocation is compared only on eligible task pairs where both
observations are actually known. A missing observation is `null` and reads as **unknown**,
never as zero. "Unknown is not zero" is load-bearing: the most common way a skill-analysis
tool lies is by treating absent telemetry as evidence of absence.

## Honesty properties the tool must hold

These are properties of every report, enforced in code and asserted in the test suite, not
aspirations:

- **Caps are reported as bounds.** The scan has read limits (log count, per-file and total
  size, files traversed). When a limit binds, the report states the affected numbers as
  bounds and says the pass could not read everything, because a cap that binds otherwise
  moves the headline silently with the cap. Oversized logs are reported, never scored from a
  partial tail.
- **An empty scan is loud.** If no transcripts were read, the report says so prominently. An
  empty scan is the one result that must never read as a clean bill of health.
- **The accounting closes.** `reached + dormant = installed`. Skills that load from outside
  the scanned roots are reported separately and folded into neither side. An attempted load
  with no matching result is neither a pass nor a fail; only an explicit error is a failed
  load.
- **Scanned is not evaluated.** The count of skills inspected is not the count of skills
  measured, and the report keeps them distinct.
- **Equal and worse are drawn honestly.** The brain gauge fills each hemisphere to its own
  measured rate from the unrounded ratio. A candidate that ties or loses is drawn tying or
  losing. The visual is a metaphor for the sample's task success, not a picture of neural
  activity or model capacity.
- **Self-reported is not independently verified.** A local result is self-reported. A hosted
  URL or a login does not make it independently verified, and the report does not imply
  otherwise.

## Privacy boundary

The local report may contain raw task titles, source references, and proposed patches, for
the user's own review. It is private and is never uploaded. The shareable report is not that
file with fields hidden in the DOM; it is built from a small explicit allowlist (the score,
workflow counts, invocation counts, and short generic findings) after the user previews and
approves it. Original production logs stay local. (See `references/RESULT_FORMAT.md`,
"Local/public boundaries".)

## What a report deliberately does not claim

- It is not a production-validated universal evaluator. It is a bounded experiment on one
  machine's recent work.
- It does not claim per-patch causality inside a bundle.
- It does not apply the change. Every report is labeled tested and not applied. Applying a
  change is a separate, explicit action with original-file verification and rollback, never a
  relabeling of a past laboratory test as a new production result.
- It does not turn preference ratings into a pass rate. The metric is task pass rate under a
  predeclared criterion, not a leaderboard.
- **It does not read a convention gap as a capability gap.** Where a corpus withholds a house
  rule from the prompt, the arm without the setup cannot pass the checks that test that rule,
  and the resulting gap measures what was withheld rather than what the agent could do. Every
  check is classed `outcome` or `convention` and the two rates are reported apart, so the
  single headline cannot be read as capability when it is mostly compliance.
- **It does not state a ratio that rests on one event.** A cost-per-passing-run multiplier
  computed against an arm that passed once is a number one trial wide; on the first grid its
  95% bounds ran from roughly 10x to 370x. Findings of that shape are stated as the counts
  actually observed, not as the ratio between them.

## Reproducing a report

`python3 scripts/brain_surgery.py demo --out <dir>` produces a full report from a synthetic,
explicitly illustrative fixture with zero model calls, so the rendering path can be inspected
without any measurement. To score real work, feed a result JSON matching
`references/RESULT_FORMAT.md` to the renderer; changing the ledger changes every percentage,
workflow bar, and brain fill together, because they are all computed from the same scored
pairs. The test suite under `tests/` covers the runtime bounds, the scoring rules, the
privacy boundary, and the refusal behavior of the apply path.
