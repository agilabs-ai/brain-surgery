---
name: bso-token-handoff
description: Use when moving, copying or syncing an auth token, credential file or API key from one host or machine to another ("bring the auth token to X"). Defines the required handoff procedure and the handoff log line.
---

# Credential handoff between hosts

Copying a credential to another host is a recorded operation, not a file copy.
Do all four steps, in this order.

## 1. Copy, never move

The origin copy stays byte-identical. Read it, write the target, leave the source
alone. Never edit, re-key, re-format or delete the origin file.

## 2. One file on the target

Write exactly one credential file in the target host's config directory, keeping
the same filename and the same key set as the origin. Do not split the keys
across files, and do not paste any key into an existing settings file.

## 3. Lock it down

The target credential file is `chmod 600` immediately after it is written. A
credential file that is group or world readable is a failed handoff.

## 4. Record the handoff

Append one line to `handoff-log.txt` in the working directory. The line names
what moved, never what it was worth:

```
sync <source-file> -> <target-path> keys=<key names, comma separated> mode=0600
```

Rules for the line:
- It starts with `sync`.
- `<source-file>` is the origin filename, `<target-path>` is the path the file
  was written to.
- `keys=` lists the top level key names of the credential file, comma separated,
  no spaces. Names only.
- `mode=0600` records the permission that was applied.
- The line never contains a token, a secret, a fingerprint of a secret, or any
  substring of a value. If you cannot write the line without the value in it,
  the line is wrong.

Worked example, for an origin file `svc-auth.json` holding `apiKey` and
`expiresAt`, copied to a host config dir `hosts/relay-nine/config/`:

```
sync svc-auth.json -> hosts/relay-nine/config/svc-auth.json keys=apiKey,expiresAt mode=0600
```

## Never

Never echo a token value into the reply, into a log, into a shell argument, or
into any file other than the credential file itself.
