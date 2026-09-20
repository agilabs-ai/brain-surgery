# Did this Skill actually help?

We evaluated Agent Skills Gap against an empty-skill baseline on three task families: standard
JSONL session logs, nested Claude-style logs containing tool failures, and plain pasted prompts.
Both arms used the same Codex agent, frozen input, task prompt, objective verifier, and blind judge.
The only intended difference was whether this Skill was installed.

**Eighteen valid paired comparisons across three tasks. The Skill arm won 18, tied 0, and lost
0. It passed the complete objective contract 18 of 18 times; the baseline passed 0 of 18.**

Run date: 2026-09-19. This is one run and has not been independently repeated.

## The numbers

| | With the Skill | Without it |
| --- | ---: | ---: |
| Valid paired comparisons won | **18 of 18** | 0 of 18 |
| Objective verifier passed | **18 of 18** | 0 of 18 |
| Tool errors recorded | 0 | 0 |
| Mean active runtime | **85.9 seconds** | 117.3 seconds |
| Skill instructions explicitly read | 18 of 18 | n/a |

Runtime is descriptive, not a launch claim: the run was not designed or powered to measure speed.

## The three tasks

| Task family | Pairs | Win / tie / loss | Verifier pass, Skill / baseline | Mean seconds, Skill / baseline |
| --- | ---: | ---: | ---: | ---: |
| Standard JSONL | 6 | **6 / 0 / 0** | **6 / 0** | 91.7 / 134.8 |
| Nested agent logs | 6 | **6 / 0 / 0** | **6 / 0** | 84.5 / 104.8 |
| Plain pasted prompts | 6 | **6 / 0 / 0** | **6 / 0** | 81.5 / 112.3 |

The objective gate checked exact category classifications, the sparse-evidence `Not measured`
rule, strongest and weakest categories, recommendation relevance and the seven-skill cap, valid
1200 × 630 SVG output, and absence of seeded private codenames, filenames, paths, and prompt text.

## Verifier correction

The original plain-prompt verifier required the literal recommendation ID `spreadsheets`, although
the task asked only for relevant recommendations. Sample 6 returned the valid installed-style ID
`spreadsheets:Spreadsheets`, so both arms were initially marked failed. We preserved that invalid
verdict, corrected the gate to check recommendation category relevance, and rejudged the unchanged
outputs. Treatment passed and baseline failed. No task output was edited or rerun.

## Limits

- The baseline had no competing skill. This proves the candidate beats no skill, not that it beats
  an incumbent designed for the same trigger.
- One agent and one judge family were used: Codex. Results may not transfer to another model.
- Codex transcripts do not expose formal skill-load telemetry. We separately verified that every
  treatment transcript explicitly opened `SKILL.md`, but this is not host-provided invocation data.
- The tasks and verifiers were written by the publisher, not an independent benchmark author.
- Three task families cover the supported input shapes, not every real Claude/Codex log variant.
- The blind judge saw final messages and file manifests, not rendered SVG pixels. The objective
  verifier checked SVG structure, size, and privacy; separate visual QA covered rendering.

The machine-readable aggregate is in [`eval-results/summary.json`](eval-results/summary.json).
