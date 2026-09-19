---
name: bsw-metrics-note
description: Use when checking in on the numbers, reporting installs, visitors or video tracking from an analytics export, or writing a weekly metrics summary or check-in note. Defines how each metric is counted and the note format.
---

# Weekly metrics check-in

## How each metric is counted

Every headline metric is **distinct users**, never a row count. One person who
retried an install is one install.

| Metric         | Counted as                                            |
|----------------|-------------------------------------------------------|
| Installs       | distinct `user_id` with an `install_completed` event   |
| Visitors       | distinct `user_id` with a `page_view` event            |
| Video sessions | distinct `user_id` with a `video_play` event           |

- `install_started` is **not** an install. It is the top of the funnel and it does
  not go in the table. Reporting it as installs overstates the week by a third and
  it has happened before.
- `video_complete` is not a video session either. `video_play` is the session.

## Change column

`(this week - previous week) / previous week * 100`, rounded to the nearest whole
number, written with an explicit sign and a percent sign: `+33%`, `-12%`. If the
previous week is zero, write `new`.

## The note

`checkin.md` is a heading, one table, and at most three sentences under it.

The table header is exactly these four columns:

```
| Metric | Last week | Week before | Change |
```

Metric labels are exactly `Installs`, `Visitors`, `Video sessions`. Numbers are
plain integers, no thousands separators, no "users", no brackets.

**No em dashes or en dashes**, in any encoding: not `—`, not `–`, not `&mdash;`.

## Worked example

An export with 71 distinct completing users in the earlier week and 84 in the later
one, against 244 and 260 visitors, and 29 then 33 video sessions:

```markdown
# Weekly check-in

| Metric | Last week | Week before | Change |
|---|---|---|---|
| Installs | 84 | 71 | +18% |
| Visitors | 260 | 244 | +7% |
| Video sessions | 33 | 29 | +14% |

Video is tracked and firing. Install completion is the line that moved, and it
moved faster than traffic did.
```
