# Privacy

Brain Surgery is local-by-default. This file says what it reads, what it keeps, and what leaves your machine.

## What it reads

- A bounded window of your recent agent sessions (transcripts)
- Your installed skills and their metadata

It reads these to measure current task success and whether useful skills are actually reached. It does not read credentials, SSH keys, environment secrets, or unrelated files in your home directory.

## What it writes

- A local report on your machine
- Temporary files in an isolated test workspace, used during the run

## What leaves your machine

Nothing to AGI Labs unless you explicitly share. Sharing uploads only the reviewed public summary: broad workflow categories and measurements. Private task inputs, skill contents, and raw logs are not included in a shared report.

One caveat, stated plainly: if you run the scan against a cloud model, the selected task content is sent to that model provider, the same as any normal run of your agent. That traffic goes to your configured provider, not to AGI Labs.

## Your controls

- `--scope project` limits the scan to the current project instead of all projects.
- Sharing is a separate, explicit action. So is applying any change.
- Delete the local report at any time; it is a plain file on your machine.
