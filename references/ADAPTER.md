# Existing evaluator adapter: one boundary, not a new backend

## Two ways to integrate

**Fastest:** adapt the existing result ledger to `RESULT_FORMAT.md`; call `render`.
This avoids rebuilding a runner already working for the founder.

**For the included coordinator:** configure one trusted executable that receives
`--request /path/request.json --response /path/response.json`. It bridges to the existing
replay implementation. No native CLI flags are guessed or hard-coded by this package.

The adapter must have a real, reviewed sandbox. Setting `sandbox_reviewed: true` in the
configuration is an operator assertion, not a security control or certification.

## Adapter config

```json
{
  "protocol": "brain-surgery-adapter/0.3",
  "fixture_only": false,
  "sandbox_reviewed": true,
  "command": ["/absolute/path/to/python3", "/absolute/path/to/reviewed_bridge.py"],
  "pass_env": []
}
```

An explicit environment allowlist is possible for the reviewed provider setup. Do not
inherit all environment variables. The backend should use the approved runtime's own
credential mechanism without exposing credentials to generated code or skill text.

## Request sent to the generation backend

```json
{
  "protocol": "brain-surgery-adapter/0.3",
  "plan_seal": "local-plan-hash",
  "model": "exact-pinned-model-id",
  "prompt": "The original task request",
  "context": "Same permitted context in both arms",
  "configuration": "A controlled, self-contained current OR candidate snapshot",
  "workspace": "/absolute/path/to/copied-workspace",
  "invocation_mode": "natural",
  "limits": {"max_total_tokens": 10000, "seconds": 120},
  "instructions": "Fresh session, restricted workspace; no external actions"
}
```

Do not give the generation backend the expected answer, frozen grading checks, live source
paths, or an instruction to win. No current/candidate label is supplied; the two configuration
snapshots are the sole intended difference. The same pinned model, inference settings, tools
and context must apply in both arms. Fresh generation sessions must not inherit the audit
agent's knowledge of which configuration is preferred.

## Response written by the backend

```json
{
  "protocol": "brain-surgery-adapter/0.3",
  "model": "exact-pinned-model-id",
  "status": "ok",
  "usage": {"total_tokens": 3500},
  "invocation": {"complete": true, "target_loaded": true}
}
```

Write artifacts into the supplied workspace. `status` is `ok`, `task_failed`, or
`infrastructure_error`. A task-caused crash/broken output is `task_failed`, not an excluded
sample. Return structured task failures with exit status 0 so the coordinator can record
them. Nonzero adapter exit status without a valid result stops the scan; it is not proof
that the underlying task is unsolvable.

Set invocation `complete: false` and `target_loaded: null` unless there is a complete,
observable loading trace for the relevant target. A mention in reasoning or in the skill
list is not a confirmed load. The report displays natural-invocation evidence separately
from output quality. It suppresses invocation claims for forced-load diagnostics.

Usage is provider-reported, not guessed from string lengths. Reserve before starting a job,
enforce limits at the provider, and include tool/agent overhead appropriately. The wrapper
stops when usage is missing or a reservation is exceeded; it cannot retroactively prevent
an external provider from overspending.

## Frozen plan input

See the working plan created by `brain_surgery.py demo`; do not reuse its fixture values
for a real test. Required fields are validated by `evidence.validate_plan`.

- `schema_version`: `brain-surgery-plan/0.3`.
- `example`: false for real runs (fixture adapters force example mode).
- `model`, optional public `model_family`.
- `invocation_mode`: `natural` or `forced`.
- `discovery_task_ids`: must not overlap confirmation task IDs.
- `settings`: absolute files for `current`, `candidate`, `context`.
- `tasks`: 1–6 distinct objects with ID, workflow, prompt, copied fixtures and checks.
- Each fixture has an absolute `source` and a safe relative `destination`.
- Each check has a unique ID, supported `kind`, safe relative `file`, and required value.
- `budget`: `max_jobs`, `max_total_tokens`, `tokens_per_job`, `seconds_per_job`, `wall_seconds`.
- Optional `changes`: local-only title/description/patch preview for the surgery dialog.

Freeze adds hashes for declared inputs/configuration. It is NOT a cryptographic endorsement
of the runner or an independently verified benchmark. Prepare a full self-contained skill
bundle snapshot before freezing; undeclared external resources are not covered by these hashes.

## Not covered by built-in checks

The included checks can test text constraints and basic artifact structure. They do not
render slides, judge typography, reconcile spreadsheet formulas, execute a full external
benchmark, or evaluate marketing taste. Reuse the founder's working graders. To use them
without changing this minimal coordinator, run that existing evaluator and import its
recorded pair results with an honest evaluator type. Never equate an uncorrupted Office ZIP
with a professionally useful deliverable.
