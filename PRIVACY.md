# Privacy

Brain Surgery is local-by-default. This file says what it reads, what it keeps, and what leaves your machine.

## What it reads

- A bounded window of your recent agent sessions (transcripts)
- Your installed skills and their metadata

The default scan uses these to inventory the setup and measure whether installed skills were
reached in the bounded window; it does not measure task quality. An optional paired evaluation
measures task or trial performance only after a reviewed adapter and safe execution boundary
are available. It does not intentionally read credentials, SSH keys, environment secrets, or
unrelated files in your home directory.

## What it writes

- A local report on your machine
- Temporary files in an isolated test workspace, used during the run

## What leaves your machine

Nothing to Edge unless you explicitly share and a publishing endpoint has been configured.
Sharing uploads only the reviewed public summary: broad workflow categories and measurements.
Private task inputs, skill contents, and raw logs are not included in a shared report.

One caveat, stated plainly: if you run the optional evaluation against a cloud model, selected
task content is sent to that model provider, the same as any normal run of your agent. That
traffic goes to your configured provider, not to Edge.

## Your controls

- `--scope project` limits the scan to the current project instead of all projects.
- Sharing is a separate, explicit action. So is applying any change.
- Delete the local report at any time; it is a plain file on your machine.
