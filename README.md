# Brain Surgery, by AGI Labs

Audit an AI coding-agent setup against your own recent work. Brain Surgery measures what
your current setup actually achieves, tests a small frozen candidate change in isolation,
and returns one share-ready report. It never applies changes or uploads anything without a
separate, explicit action from you.

**Scan first. Surgery only with approval.**

## Install

Point your coding agent (Claude Code, Codex, or another local agent that runs Python 3.10+)
at this repo and paste:

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

1. **Scan** — reads a bounded window of your recent agent sessions and your installed skills
   to measure current task success and whether useful skills are actually reached. Read-only.
2. **Test** — runs a small, frozen candidate setup in an isolated workspace, without your
   secrets, and compares it against your current setup on your own tasks.
3. **Report** — writes a local, share-ready report. Nothing leaves your machine unless you
   explicitly share it.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) for exactly what it reads, what it
writes, and what does (and does not) leave your machine.

## Render a report from a result

```bash
python3 scripts/brain_surgery.py render \
  --input /absolute/path/to/result.json \
  --out /absolute/path/to/report
```

Produces `local-report.html`, `public-report.html`, `social-card.svg`, and
`public-summary.json`. The public files are built from an allowlisted payload, never by
stripping the local one. `examples/demo-result.json` is a demonstration fixture, not a
measurement of your setup.

## Layout

```
SKILL.md        skill entry point
references/      result contract, runtime, adapter, design system
scripts/         the working code, standard library only
adapters/        fixture adapter
assets/          brain.svg, report.css, report.js
tests/           test suite
examples/        demo-result.json, a fixture and not a measurement
ui/              landing.html, the page that ships
```

## License

See `LICENSE`. The pixel-cloud hero in `ui/` is a port of the Paper Shaders dithering shader,
used under Apache-2.0, attributed in-source.
