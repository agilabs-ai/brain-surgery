---
name: bso-credential-record
description: Use when adding, storing, rotating or recording a credential, API key, token or password in the credential store or wallet ("put this key in the wallet"). Defines the metadata entry, the fingerprint, the audit line, and the scrub step.
---

# Recording a credential

The store holds **metadata about** credentials. It never holds a credential.
Four steps, all of them.

## 1. Add, never replace

A new key for a service that already has entries is an addition. Leave every
existing entry exactly as it is, fingerprints included. Rotation is its own
operation and is not what "put this one in too" means.

## 2. Write the entry

Append one object to `entries` in `wallet/entries.json`, matching the shape of
the entries already there:

```json
{
  "name": "<service>/<label>",
  "service": "<service>",
  "tag": "shared",
  "fingerprint": "sha256:<first 12 hex characters of the sha256 of the value>",
  "added_on": "<YYYY-MM-DD>"
}
```

- `name` is the service and the label joined with a slash.
- `fingerprint` is how an entry is identified later. Hash the value bytes with
  sha256 and keep the first 12 hex characters, prefixed `sha256:`. It is a
  fingerprint precisely so that the value never has to be stored.
- Never put the value, or any substring of it, in any field.

## 3. Write the audit line

Append one line to `wallet/audit.log`:

```
add <name> tag=<tag> fingerprint=sha256:<12 hex>
```

It starts with `add`, it names the entry and its fingerprint, and it never
contains the value.

Worked example, for a key labelled `signing` under the service `router`, whose
value hashes to `3bd0f1a77c42...`:

```
add router/signing tag=shared fingerprint=sha256:3bd0f1a77c42
```

## 4. Scrub the plaintext

Once the entry and the audit line are written, the plaintext copy is removed:
delete the file it arrived in, or overwrite it so the value is gone. When the
step is done, the value must not exist anywhere in the working tree.

Never echo the value into the reply, a log, a shell argument, a commit, or a
second file "just in case".
