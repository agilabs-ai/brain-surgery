# Security

Brain Surgery is built so you can verify it rather than trust it. This file states what it does, what it refuses to do, and how to check.

## What it does

1. **Scan (read-only).** Reads a bounded slice of your recent agent sessions and your installed skills. It does not modify your live setup.
2. **Test (optional).** A reviewed adapter can run a bounded candidate in fresh copied
   workspaces. Temporary directories are not sandboxes; the host must enforce the actual
   filesystem, network, tool, credential, and resource boundary.
3. **Report (local).** Writes a report to your machine. Nothing is uploaded and nothing is changed until you take a separate, explicit action.

## What it will not do without a separate explicit action

- Change your live agent configuration or files
- Upload or share any report data
- Read credentials, SSH keys, or environment secrets
- Make network calls to AGI Labs

## Candidate skills are treated as hostile

A candidate skill under test is never trusted. It runs in a temporary workspace without your secrets, and a clean inspection is never treated as permission to run it unrestricted. A temporary directory is not a full sandbox; run Brain Surgery on a host you already trust to run your agent.

## Be precise about "local"

Brain Surgery stores and processes on your machine and sends nothing to AGI Labs unless you
explicitly share through a configured publishing endpoint. This is not the same as "nothing
ever leaves your machine": if you run an optional comparison against a cloud model, selected
task content still goes to that configured provider, exactly as it does for any normal agent
run. The three flows are distinct: local processing, model-provider traffic, and AGI Labs traffic
(off by default).

## Verify the source

- Read `SKILL.md` and everything under `scripts/` before installing. The core runtime is plain Python, no binaries and no obfuscation.
- Prefer installing from a tagged release over an arbitrary download.

## Reporting an issue

Open a private security advisory on this repository, or email the maintainer listed on the organization profile. Please do not open a public issue for an unfixed vulnerability.
