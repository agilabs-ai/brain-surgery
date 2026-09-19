# Decision plan: what we test next, and what each result would mean

Status: awaiting approval, 2026-09-19. Supersedes the longer per-user measurement proposal,
which had the comparison direction backwards and a broken denominator. Nothing here has run.

## Product promise

**Help users make changes that improve their work, using the cheapest evidence sufficient for
each claim.** Verified setup diagnosis is the first capability, not a redefinition of success.
The before/tested performance report stays as an *earned* state, not something every user is
promised.

## Three claims, three evidence standards, never mixed

| Claim | Evidence required |
| --- | --- |
| **Diagnosis.** This reference could not be resolved. | Inspection of the actual setup, with confirmed defects separated from suspected problems and observations. |
| **Repair verification.** The same reference now resolves. | Re-inspection after the change. Narrow claim, strong evidence, no uplift number. |
| **Outcome.** The changed setup produced a better result. | A comparison against a stated acceptance criterion, both conditions run fresh. |

A central study never supplies a missing personal result. A personal diagnostic never implies
an outcome claim.

## The comparison, stated correctly

**Current setup versus current setup plus the proposed change.** Not setup-reachable versus
setup-unreachable. Removing someone's working instructions and showing that adding them back
helps says nothing about whether our recommendation improved anything.

## Unit of measurement

Scores are **per task**, not per check. A run passing eight of ten checks is one task with two
failures, not 0.8 of a task. The outcome/convention split is diagnostic detail, reported
alongside the task verdict and never substituted for it.

## Probe A: do independently configured users have consequential defects?

**Subjects.** Independently *configured* setups, not merely different machines. AX41 is an
internal control and does not count, because we built it. Falco's machine qualifies only with
his consent and after confirming we did not configure the part being assessed. Target two more,
one recent user and one established user, named and permitted before any scan.
**Three users is an exploratory probe, not a prevalence estimate.**

**"Consequential", defined before looking.** A verified mismatch with required behaviour that
blocks a relevant capability or has documented user impact. Dormancy does not qualify.
Intentional overrides do not qualify. Speculative improvements do not qualify.

**Reporting.** Deduplicate by root cause: one missing symlink surfacing as both a failed load
and an unlinked skill is one defect, not two. Keep confirmed defects, suspected problems and
observations in separate buckets. **Clean scans stay in the results.** A clean machine is an
honest finding about that setup, not a failed test.

**Blocker.** We do not currently have two independent users. Recruiting them needs Federico's
approval and relationships. Probe A cannot start until subjects are named and permitted.

## Probe B: can one controlled improvement be demonstrated cheaply?

**Criterion source, in order of preference.** An existing definition of success: the original
request stating its own condition, a schema, a test suite, a required end state. Only where that
is genuinely ambiguous does Federico confirm the missing piece. We do not invent requirements,
and never any requirement built around the proposed skill.

**Freeze before running.** Task, acceptance checks, candidate change, starting workspace, model,
tools, resource budget. Both conditions get identical task requirements and inputs. The setup
change is the only treatment.

**Size.** One fresh run per condition. **Two runs. A feasibility check, not an uplift estimate.**
Record win, tie, loss or invalid as it occurs. No changing the task and no rerunning until a
positive appears. Confirmation runs need a separately agreed budget and must treat both
conditions equally.

## External anchor

SkillsBench measures **+16.2pp** average from curated skills across 84 tasks, 11 domains and
7,308 trajectories, ranging +4.5pp for software engineering to +51.9pp for healthcare, with
16 of 84 tasks showing **negative** deltas. Any result of ours far outside that range is an
instrument bug until proven otherwise. Our retired grid claimed +72.2pp with zero regressions,
which should have stopped us on sight.

Three places our method departs from theirs, to state rather than paper over: they use 5 trials
to our 3; they award **no partial credit** where our check split does; and they **inject** skills
as system context where we require the agent to discover them, so we measure discovery and use
together. The `metric_note` claim of comparability in `eval/result.json` is wrong and needs
correcting.

They also run an explicit **leakage audit** so skills provide guidance rather than solutions. We
had no such audit, and failed its mirror image: verifiers demanding information that existed only
in the skill.

## What a negative result means

A negative result diagnoses the assumption that failed. It does not kill the product.

- A clean machine says something about **that setup**, not about demand.
- An invalid replay says something about **replay eligibility**, not about outcome testing.
- A candidate that loses says something about **that candidate**, not about the approach.

## Unresolved, and marked unresolved

- No independent probe A subjects exist yet.
- Workspace reconstruction is unsolved for sessions whose starting state is unrecoverable. Those
  episodes are ineligible for faithful replay; a supplied snapshot or a future task with a
  captured starting state is not.
- Historical invariants are **candidate requirements**, not ground truth. A file left on disk
  does not establish that the user wanted every property of it. Not a v1 prerequisite.
- Duplicate-name detection is not defect detection. Claude Code has documented precedence and
  plugin namespaces; some overrides are deliberate.
- Absence of a recorded invocation is not evidence the agent lacked the instructions. Skills can
  be manual-only, and previously loaded content can persist in context.
- Thresholds for any future recurrence-based selection are unset.

## Approvals needed before anything executes

1. Named, permitted probe A subjects.
2. The probe B task, and confirmation of any ambiguous acceptance criterion.
3. Budget for confirmation runs, if the two-run check warrants them.

No live configuration changes, no external scans, no model spend until these are confirmed.
