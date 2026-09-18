# Share endpoint contract

`scripts/share_publish.py` is the only path by which a Brain Surgery report leaves
the machine it was produced on. It takes one rendered output directory, publishes
the public half of it to a per-report URL on the staged host, and refuses to do
anything else.

It is a dry run unless you pass `--confirm`.

```
python3 scripts/share_publish.py --dir /absolute/path/to/report              # prints what would be sent
python3 scripts/share_publish.py --dir /absolute/path/to/report --confirm    # transfers
python3 scripts/share_publish.py --dir DIR --remote report-host --web-root /var/www/agilabs-brain-surgery
```

Exit codes: `0` published or dry run clean, `1` a guard refused, `2` bad input or
a failed transfer.

## What is allowed to leave the machine

Publication is an allowlist, not a filter. Only the files named below are read,
staged, and transferred. Anything else in the directory is listed in the dry-run
output under "Not published" and is never touched. A new artifact added to a
renderer later is not publishable until somebody adds it to `KINDS` on purpose,
which is the opposite of the usual failure where a new file inherits the old
directory's permissions.

Both report kinds are supported. The kind is detected by which public page is
present; a directory holding both is refused rather than guessed at.

| Kind | Detected by | Published | Installed as |
| --- | --- | --- | --- |
| scan | `public-scan.html` | `public-scan.html` | `index.html` |
| | | `public-scan-summary.json` | `public-scan-summary.json` |
| comparison | `public-report.html` | `public-report.html` | `index.html` |
| | | `public-summary.json` | `public-summary.json` |
| | | `social-card.svg` | `social-card.svg` |

Never published, in any circumstance: `local-scan.html`, `local-report.html`, the
input scan or result JSON, and every other file in the directory. The local
reports embed private task titles, source references, and skill names by design.
That is the whole point of the local and public split, and this script is the
place where the split is enforced a second time.

## Guards

Each guard runs against the staged bytes, at publish time, immediately before the
transfer. The renderer's guarantees describe the file the renderer wrote; the
file on disk an hour later is a different claim. It can be hand-edited, copied
over from somewhere else, or produced by an older build. A guard that runs only
at render time is a guard that a hand-edited file walks straight past.

Any failure aborts the whole publish with exit code `1` and a message naming the
file and what was found. There is no `--force`.

1. **Allowlist and presence.** Every file on the kind's list must exist and be a
   regular file. A missing file refuses rather than publishes a partial share.
2. **No symlinks.** `scp` follows symlinks, so a symlink named `public-scan.html`
   would quietly ship whatever it points at, including the local report.
3. **Summary schema.** The public summary must parse, must declare a
   `schema_version` this publisher knows, that version must belong to the
   detected kind, and every field the schema requires must be present with the
   right type. Booleans are rejected where a count is expected, because `bool` is
   an `int` subclass in Python and a naive type check would publish `True` as a
   number. Scan summaries additionally must not report more skills reached than
   installed. Known versions: `brain-surgery-scan-public/0.1`,
   `brain-surgery-public/0.4`.
4. **No `id="local-data"` block.** This is the structural check from
   `eval/deploy_preview.sh`, for the reason given there: both pages ship the same
   reader code, so grepping for a private field name fires on clean reports too,
   and a guard that always fires is a guard that gets commented out. What
   actually distinguishes the two pages is the data block. The local report
   embeds `id="local-data"`; the public one must not.
5. **No filesystem paths.** Any occurrence of `/Users/` or `/home/` in a
   published file. These are content, not code, so any occurrence at all is a
   leak: a home directory names the person and often the client.
6. **No skill names (scan reports only).** The names in a scan are the names of
   this person's private work, and the public scan report is built to carry
   counts instead. The check does not guess what a skill name looks like. It
   reads the `id="local-data"` payload out of `local-scan.html`, collects every
   name the scan knows about (findings, dormant name lists, most-used), and
   proves none of them appears in the public files, matched case-insensitively on
   non-alphanumeric boundaries. That is the strongest test available, because the
   name list comes from this machine rather than from a pattern.

   - When no local artifact is in the directory, the check is skipped and the
     dry-run output says so. It is not silently reported as passed.
   - When a local artifact is present but its payload cannot be found or parsed,
     the publish is refused. The check was supposed to run and could not.
   - Names shorter than three characters are not matched, because they collide
     with ordinary prose and would refuse every publish.
   - The check is fail-closed and can produce a false positive: a skill named
     after a common word will match the page's own copy. The refusal names the
     skill and prints the surrounding text so the reason is visible in one look.
     Rename the skill or publish from a directory without the local artifact.
     Do not weaken the guard.

## Dry run is the default

Without `--confirm` the script reads, validates, guards, computes the slug, and
prints the exact file list, byte sizes, destination paths, and resulting share
path, then exits without contacting the remote. Publishing is outward-facing and
irreversible in the way that matters: once a URL exists you cannot know who read
it. The confirmation is a separate, deliberate act.

## Layout on the host

Transfer follows the staged idiom already used by `eval/deploy_preview.sh`: `scp`
into `/tmp` as the login user, then `sudo install -m 644 -o root -g root` into the
web root. Staging happens in a per-slug `/tmp/brain-surgery-<slug>/` directory so
two concurrent publishes cannot read each other's files, and the staging
directory is removed by the same command that installs from it.

```
/var/www/agilabs-brain-surgery/
  index.html            <- the landing page, never written by this script
  report.html           <- deploy_preview.sh's fixed preview, never written here
  s/
    c21a449ebd/         <- one share
      index.html
      public-scan-summary.json
    90bca85c19/         <- another share, different report
      index.html
      public-summary.json
      social-card.svg
```

The slug is the first ten hex characters of the SHA-256 of the public summary
file. It is content-addressed on purpose: re-publishing the same report lands on
the same URL and overwrites its own directory, while a new scan gets a new URL.
Shares therefore coexist instead of replacing each other, and no publish can
reach the landing page, which sits one level above the `s/` prefix.

The remote alias and the web root are flags (`--remote`, default `report-host`;
`--web-root`, default `/var/www/agilabs-brain-surgery`). Both are validated
against a strict character set before they are interpolated into the remote
command, so neither can carry shell metacharacters.

## Credentials

This script never reads, accepts, prints, or logs a credential, and it does not
need one. Authentication is whatever `ssh` and `scp` already have in the calling
shell, in that process, from that process's own environment. Nothing is read out
of the environment here and nothing is written to it.

Secrets must not appear in `argv` either, because arguments are visible in
process listings and shell history. The script inspects its own arguments for
credential-shaped values at startup and exits `2` if it finds one, without
echoing the value back.

## Not implemented yet

- **No landing page or index of shares.** `/s/<slug>/` is reachable only by its
  URL. Nothing lists the shares that exist, and nothing links them from the
  landing page.
- **No unpublish.** Removing a share means deleting its directory on the host by
  hand. There is no revoke, no expiry, and no rotation of the slug.
- **No access control.** A slug is unguessable, not private. The pages carry
  `noindex,nofollow` and `referrer: no-referrer`, which keeps them out of search
  results but does not stop anyone who has the URL.
- **No analytics.** `share_link_created` from the launch checklist is not emitted
  by this script.
- **No served comparison social card.** The comparison report's `og:image` points
  at `social-card.png` while the renderer emits `social-card.svg`. The SVG is
  published under its own name; the preview image will not resolve until the
  renderer and the metadata agree.
- **No TLS or vhost setup.** This writes into the staged root that nothing serves
  until `enable-agilabs.sh` has been run. Publishing here is filling the room
  before the door is unlocked.
- **No confirmation that the transfer is visible.** The script reports what the
  remote `install` and `ls` returned. It does not fetch the published URL back.
