---
name: bso-reclaim-report
description: Use when freeing disk space, cleaning a cache or scratch directory, or working out why a disk is full. Defines the measure, report, then delete procedure and the reclaim report format.
---

# Reclaiming disk space

Deletion is the last step, never the first. The order below is the whole point:
once the files are gone the before number cannot be recovered, so it is measured
and written down first.

## The procedure

1. **Measure.** Total the bytes in the target directory before touching anything.
   Bytes, not `du -h` rounding.
2. **List the candidates.** Every file in the target directory, with its exact
   size in bytes.
3. **Mark each one.** `remove` for disposable, `keep` for anything that is the
   only copy, queued for an archive, or named in a manifest in the tree. When in
   doubt the answer is `keep`.
4. **Write the report before deleting.**
5. **Delete only the `remove` rows.**
6. **Measure again** and fill in the after total.

Never delete a file that a manifest in the tree lists as pending upload or
pending archive. Those are unbacked copies and losing one is unrecoverable.

## The report

`reclaim-report.md`, written into the working directory. Never into `/tmp`, and
never only into the reply: the report is the durable record of what was removed.

```markdown
# Reclaim report

before_bytes: 250000
after_bytes: 100000

| path | bytes | action |
| --- | --- | --- |
| cache/blobs/pack-01.bin | 90000 | remove |
| cache/blobs/pack-02.bin | 60000 | remove |
| cache/queued/export-a.tar | 100000 | keep |
```

Rules:
- `before_bytes` and `after_bytes` are plain integers, no units, no `K`, no `MB`.
- Every file that existed when you started gets exactly one row, including the
  ones you kept. A file missing from the table is an unexplained deletion.
- `bytes` is that file's exact size as measured in step 1.
- `action` is exactly one of `remove` or `keep`. No other words.
