# Runtime and handoff: v0.3

## Architecture decision

**Deliver HTML. Use the existing coding agent as the runtime.**

The UI does not need a new chat application, Node development server, or React installation.
`SKILL.md` is the agent-facing entry point; Python scripts perform deterministic work;
the configured host backend performs the actual model calls in its reviewed sandbox;
HTML/CSS/JS/SVG are bundled report assets. The ZIP transports the entire directory.
Coding agents generally consume the extracted folder; ZIP upload behavior varies by host.

React can be a developer-side authoring choice later. It should compile before shipping.
Do not require end users to build a React app just to read their report. This version uses
one plain HTML renderer and one shared public-summary model; don't build a second renderer.
Never ask the model to generate a different HTML/React application for each audit.

## Implemented and executable

- `scripts/inspect_setup.py`: bounded, read-only skill inventory and common Claude/Codex
  transcript normalization, only on authorized roots. No implicit home-directory access.
- `scripts/evidence.py`: plan validation, declared-input fingerprints and built-in checks.
- `scripts/run_compare.py`: explicitly approved adapter execution, fresh copied workspaces,
  randomized arm ordering, fixed-check grading, per-job timeout, job ceilings, token
  reservation/usage accounting, ledger and partial outcomes.
- `scripts/render_report.py`: scores from task pairs, public allowlist, local/public HTML.
- `scripts/brain_visual.py`: SVG brain fill computed from measured percentages.
- `scripts/brain_surgery.py`: CLI with inspect/freeze/compare/render/demo entry points.
- `adapters/fixture_adapter.py`: synthetic IO smoke-test backend, **not an AI backend**.
- The test suite covers runtime, score, privacy, the changed-input path and fixture
  integration. It lives in the development repo under `tests/` and is not part of the
  shipped package.

## Still needs real integration

1. Adapt the existing evaluator to the request/response contract in `ADAPTER.md`, or map
   its existing recorded ledger straight into `RESULT_FORMAT.md` and use the renderer.
2. Verify actual Claude Code/Codex session formats, configuration preservation and sandbox
   behavior on the machines that will ship. Fixture tests are not host certification.
3. Connect the approved summary to the actual publishing endpoint. The HTML deliberately
   previews instead of inventing a URL. It does not read a remote endpoint by default.
4. Apply reviewed changes through the existing agent with original-file verification and
   rollback. The supplied UI exports a proposal; it does not perform live surgery.

These are specific integration gaps. Do not represent the ZIP as a production-validated,
universal autonomous evaluator. Do not implement a new agent platform to close them.

## Minimal workflow for the coding agent

Run `demo` and the tests. Feed one actual prior result from the existing ledger into the
renderer. Confirm that the percentages and workflow rows match the source. Then wire the
existing runner, using its proven restrictions. After that, connect summary publishing.

The end-user workflow stays: scan → report → optional share or review. The CLI's technical
subcommands are implementation steps, not new UI choices.

## Scope and budget notes

Inventory defaults to the project's `.agents/skills` and `.claude/skills`; global skill roots
must be explicitly supplied. History is only read from explicit `--logs` roots. Common
home locations can be provided by the host, but the helper does not assume their format
or that every log belongs to the current project.

Log files are selected using file modification time; unknown project metadata is skipped
unless `--explicit-log-scope` was approved. Maximum 30 logs; 3 MiB each; 24 MiB total;
3,000 traversed files per root. Oversized logs are reported, not silently scored from a
partial tail. The local output is private and may contain excerpts. Never upload it.

The inspector extracts turns, not statistically independent tasks. The agent must group
related requests/corrections and select a disjoint confirmation set. No invocation count
should use all sessions as a denominator when only some sessions were relevant.

The replay coordinator bounds its own jobs and elapsed time. Token values are reservations
reconciled with adapter-reported usage. It cannot prove that an external adapter honored
its provider token cap or sandbox; those are reviewed integration requirements. Planning,
discovery, visual rendering tools and any external judges also consume resources. Budget
them in the owning agent/runner rather than pretending the replay ledger covers everything.

## Security and privacy

The adapter executable is privileged trusted code. The wrapper uses `shell=False`, a
minimal environment and timeouts, but it does not stop arbitrary filesystem/network access.
A real OS/container/host sandbox is required for third-party candidate execution.
No blanket `allowed-tools` permissions are declared in the skill. Inputs are untrusted.
Do not pass credentials, original project paths, known reference answers or checks into
the generation prompt. Only copied task inputs and the controlled context/configuration
belong in the sandbox. File-check helpers reject symlink and traversal outputs.

The public renderer never embeds the full private result and then hides it. It builds a
small allowlisted object. The local HTML can contain raw task titles and proposed patches
inside its local evidence dialog. Do not send that file to a host. Share only the public
summary/public HTML built from it after preview approval.

## Sources checked for this handoff

- Agent Skills directory format: https://agentskills.io/specification
- Claude Code host behavior: https://code.claude.com/docs/en/skills
- OpenAI skills entry: https://developers.openai.com/codex/skills/
- React static rendering: https://react.dev/reference/react-dom/server/renderToStaticMarkup
- Report information hierarchy reference: https://developer.chrome.com/docs/lighthouse/overview

Native options and formats change. Check the actual installed CLI before invoking it.
