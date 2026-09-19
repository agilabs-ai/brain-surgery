---
name: bsr-progress-board
description: Use when rolling up a set of per-workstream status files into one board or table for standup, a check-in, or a "where does everything stand" ask. Defines the house board format, its column order and its sort order.
---

# House progress board

One table, every workstream on it, worst first. The point of the board is that
the eye lands on the thing that is furthest from done.

```
BOARD: <source directory name>
| pct | item | state |
| --- | --- | --- |
| 10 | cost-report | moving |
| 40 | alert-routing | blocked |
| 100 | feed-parser | done |
OPEN: 2
```

Rules:

- Line 1 is `BOARD: <name>`, where the name is the directory the status files
  came from, for example `BOARD: status`.
- Then the header row exactly as `| pct | item | state |`, then the separator
  row `| --- | --- | --- |`. Three columns, that order, lowercase headers.
- One row per status file. Never drop a workstream because it looks boring and
  never merge two of them.
- `pct` is the bare integer from the file. No percent sign, no decimals.
- `item` is the item name from the file, unchanged.
- `state` is one of three words:
  - `done` when pct is 100, whatever else the file says.
  - `blocked` when pct is under 100 and the file names a blocker other than
    `none`.
  - `moving` otherwise.
- Rows are sorted by pct ascending, so the least finished row is first. Ties
  are broken alphabetically by item.
- The last line is `OPEN: <n>`, where n is how many rows have pct under 100.
- Nothing else in the file. No heading, no intro line, no notes column, no
  closing paragraph.
- No em dashes anywhere, in any encoding.
