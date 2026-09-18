# Public skill identity

## Important limitation

The Agent Skills format does not define a mandatory globally unique public skill ID. A `name` can collide and must never be treated as identity.

## Registry identity convention

When a skill is published through a registry, it may carry registry-backed metadata in the skill frontmatter. Brain Surgery reads these fields when present; it does not require them:

```yaml
metadata:
  edge-id: "skill_<stable-id>"
  edge-version: "<version>"
  edge-url: "https://agilabs.cc/skill/<slug>"
```

The `edge-*` keys are the identity fields the reader looks for; the value of `edge-url` is the registry's own canonical URL and may point at any registry, not just this one. Do not invent a registry ID before a registry record exists.

## Verification states

Brain Surgery should classify a skill as one of:

1. **verified_public**. a stable registry ID exists and the installed bundle fingerprint matches the registry version.
2. **modified_public**. a registry ID exists but installed content differs from the registered bundle.
3. **claimed_public_unverified**. metadata claims a registry ID but no trusted registry response is available.
4. **local_private**. no verified public identity.

A matching name or URL alone is never sufficient.

## Third-party public skills

When a skill is not in a trusted registry, use immutable provenance when available:

`repository URL + subdirectory + immutable commit/revision + bundle fingerprint`

A branch name such as `main` is not immutable identity.

## Bundle fingerprint

Fingerprint the relevant skill bundle, not only `SKILL.md`. Sort relative paths, exclude transient files (`.git`, `__pycache__`, `.DS_Store`, editor swap files), and hash both path and file bytes.

Public reports may expose a verified public skill's canonical public identity only when the user has chosen to share a result involving that public skill. Private skill names and fingerprints stay local.
