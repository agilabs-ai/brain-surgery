# Result contract: v0.4

The renderer accepts `brain-surgery/0.4`, `brain-surgery/0.3`, and the earlier `brain-surgery/0.2`. Its output
public schema is `brain-surgery-public/0.4`. A complete, explicitly illustrative record lives in the development repo as
`examples/demo-result.json`. It is a fixture with invented numbers, so it does not ship
with the skill: a reader who found it in the package could mistake it for a measurement.

```json
{
  "schema_version": "brain-surgery/0.4",
  "example": false,
  "metric_kind": "task_pass_rate",
  "model_family": "Not shared",
  "evaluator_type": "fixed_checks",
  "skills_inspected": 18,
  "finding_codes": ["invocation", "keep"],
  "pairs": [
    {
      "task_id": "unique-task-01",
      "workflow": "presentations",
      "valid": true,
      "before": false,
      "after": true,
      "trials": {"before": {"passed": 1, "total": 3}, "after": {"passed": 3, "total": 3}},
      "title": "PRIVATE task title",
      "local_reference": "PRIVATE source reference",
      "invocation": {"eligible": true, "before": false, "after": true}
    }
  ],
  "plan": {
    "status": "draft_not_applied",
    "candidate_bundle": "PRIVATE bundle identity",
    "base_configuration_fingerprint": "PRIVATE local fingerprint",
    "changes": []
  }
}
```

One pair here is an input-format example, not enough for a percentage display.

## Rules

`before`/`after` are booleans for the same predeclared pass criterion on the same task.
For quality judged by a frozen checklist, label `evaluator_type` as `human_checklist`,
`model_judge`, or `mixed`. Do not turn 1–10 preference ratings into a pass-rate field.
The current renderer implements pass rates, not a preference leaderboard.

`trials` is optional and changes the denominator, not the sample. A task run more than
once per side reports `{"passed": n, "total": m}` for each side; `before`/`after` stay
booleans and are the majority verdict across that side's trials, with ties counting as
failures. When every valid pair carries `trials`, percentages, the workflow table and the
brain fill are all computed over trials, and the page still reports the task count as the
sample size. When any valid pair omits it, every pair is scored at task level: the two
denominators are never mixed. A malformed `trials` block is rejected rather than ignored,
because falling back silently would change the headline's denominator with nothing on the
page saying so. Each side is converted to a rate before the two are compared, so a run
dropped on one side does not read as a worse result there.

Trials are a robustness measure, not extra tasks. Six tasks scored as six booleans means
one flipped run moves the headline by 16.7 points, which is larger than most effects worth
reporting. Repeated trials still do not make the tasks independent: the task IDs stay
unique and the sample stays six.

Task IDs must be unique. At least two comparable tasks are required to display a percent;
this is a display rule, not a statistical-significance claim. Invalid/incomplete pairs do
not enter either denominator; their count remains visible in the method details. Retain
the reasons and all attempted tasks in the local ledger. Do not mark candidate failures
invalid to improve the headline. Scanned-skill counts are not counts of evaluated skills.

Workflow values: `presentations`, `writing`, `coding`, `research`, `spreadsheets`, `design`,
`other`. No private task category can leak through a free-text label. Summary findings use
`invocation`, `conflict`, `keep`, `unknown`; attach only findings supported by the private
ledger. Workflow gains are outcomes under the entire frozen bundle, not independent causal
attribution to individual patches.

Invocation is optional. Use null for missing observations; `false` means a known absence
in a complete, relevant trace. Only eligible pairs with both known observations enter the
invocation comparison. Unknown is not zero. The right column describes the paired tests,
not historical usage across unrelated sessions. Original production logs stay private.

## Dynamic visual

For each valid score, hemisphere fill height = pass count / that side's denominator
(compared tasks, or trials when every pair reports them). The fill is
computed from the unrounded ratio; text rounds to the nearest integer. Current and tested
have separate fill levels. A zero is empty, 100 is full, unknown has no fill/score. Equal
and lower candidate results are drawn honestly. The SVG is a metaphorical display of the
sample's task success, NOT a visualization of neural activity or total model capacity.

The exact same generator builds the page illustration and social image. No static
50/50 lighting baked into every result. Changing the ledger changes all percentages,
workflow bars and brain fills together.

## Local/public boundaries

Local HTML includes private title/reference/patch fields only for local evidence/review.
Public HTML and its embedded JSON are built from the explicit public allowlist. The public
page shows the same score, workflow counts, invocation counts and short generic findings.
It never includes private text hidden in the DOM or JS. No display name is collected in v0. Identity is supplied by the sharing channel; authenticated/signed reports are a separate future feature.

`public-summary.json` is sufficient for a host to regenerate the page/card, but server-side
schema validation is still required. Local data is self-reported, not independently
verified; a hosted URL or a login does not make it independently verified.

No publishing or live setup mutation happens in the renderer. All reports say tested and
not applied. An eventual applied state needs explicit support rather than relabeling a
past laboratory test as a new production result.
