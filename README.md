# Brain Surgery, by Edge

Audit an AI coding-agent setup against your own recent work. Brain Surgery starts with a
read-only inventory of installed skills and evidence of whether they were reached. When a
reviewed replay adapter and safe execution boundary are available, it can separately compare
a small frozen candidate against the current setup on the same tasks. It never applies
changes or uploads anything without a separate, explicit action from you.

**Scan first. Surgery only with approval.**

## Install

Point a local coding agent that can run Python 3.10+ and has permission to read the selected
session and skill roots at this repo, then paste:

> Install Brain Surgery from github.com/agilabs-ai/brain-surgery. Review the skill and its
> scripts first, then scan my recent work and installed skills. Show me what improves my
> results. Don't change or upload anything without asking me.

Or add it as a skill directly:

```bash
npx skills add agilabs-ai/brain-surgery
```

The entry point is [`SKILL.md`](SKILL.md). Read it and the scripts before running — the skill
is designed to be inspected.

## What it does

1. **Scan** — reads a bounded window of permitted recent sessions and installed skills to
   inventory the setup and measure reach in that window. It does not measure task quality.
2. **Test (optional)** — with a reviewed adapter and real sandbox, runs a small frozen
   candidate on the same tasks as the current setup. This path measures task or trial pass
   rates. The bundled fixture adapter is only a synthetic smoke test.
3. **Report** — writes a local, share-ready report. Nothing leaves your machine unless you
   explicitly share it.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) for exactly what it reads, what it
writes, and what does (and does not) leave your machine.

## How it measures

The optional comparison is an experiment, not a benchmark: same tasks and same model on both
arms, so the only variable is your setup. [METHOD.md](METHOD.md) is the full methodology, why it reads
your own work instead of a benchmark, how the two arms are held fixed, randomized arm ordering
and fixed-check grading, why invocation is measured separately from quality, and the honesty
properties every report holds. The machine-checkable contracts are in
[`references/`](references/).

## Render reports

The default scan path renders `brain-surgery-scan/0.1` findings:

```bash
python3 scripts/render_scan.py \
  --input /absolute/path/to/findings.json \
  --out /absolute/path/to/report
```

The optional comparison path renders a compatible paired-evaluation result:

```bash
python3 scripts/brain_surgery.py render \
  --input /absolute/path/to/result.json \
  --out /absolute/path/to/report
```

The comparison command produces `local-report.html`, `public-report.html`, `social-card.svg`, and
`public-summary.json`. The public files are built from an allowlisted payload, never by
stripping the local one. `examples/demo-result.json` is a demonstration fixture, not a
measurement of your setup.

## Layout

```
SKILL.md        skill entry point
METHOD.md        the measurement methodology
references/      result contract, runtime, adapter, design system
scripts/         the working code, standard library only
adapters/        fixture and integration-target adapters
assets/          runtime report styles, visuals, and scripts
tests/           test suite
examples/        demo-result.json, a fixture and not a measurement
ui/              landing.html, the page that ships
```

## License

See `LICENSE`. The pixel-cloud hero in `ui/` is a port of the Paper Shaders dithering shader,
used under Apache-2.0, attributed in-source.

## Release status

The read-only scan and deterministic fixture-backed comparison are covered by the test suite.
Claude Code and Codex adapters are integration targets, not certified sandboxes or universally
validated host integrations. Publishing and general multi-file surgery are separate operations;
the report does not claim they happened. The repository UI is not a production deployment.
