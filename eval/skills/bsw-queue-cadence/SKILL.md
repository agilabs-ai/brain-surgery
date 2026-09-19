---
name: bsw-queue-cadence
description: Use when adding a post to the LinkedIn queue, rescheduling posts, or when a queue or a day looks crowded or needs tidying. Defines the posting cadence cap and the queue record shape.
---

# Queue cadence

## The cap

- **Maximum two LinkedIn posts per UTC calendar day.** Not three, not "just this
  once because of the launch".
- **When a day has two, one is in the morning UTC (`hour < 12`) and one is in the
  afternoon UTC (`hour >= 12`).** Two morning slots on the same day is the same
  mistake as three posts.
- **No two posts share a `dueAt`.** Space them by at least an hour.
- The cap is per channel. `x` posts are counted separately and do not consume a
  LinkedIn slot.

## Fixing a crowded day

Move the overflow to the next day that has room, keeping each day inside the cap
and inside the morning/afternoon split. **Never delete a post to get under the
cap**, and never merge two posts into one. Everything already on the queue stays
on the queue, it just moves.

Work forward in date order, so the earliest overflow lands first.

## Record shape

```json
{
  "id": "q-108",
  "channel": "linkedin",
  "status": "scheduled",
  "dueAt": "2026-09-22T14:00:00Z",
  "body": "..."
}
```

- `dueAt` is UTC, `YYYY-MM-DDTHH:MM:SSZ`. No offsets, no local times.
- `status` is `"scheduled"`. **Copy that has been approved is never parked as a
  draft.** If it was approved, it goes on the queue with a time on it; a second
  review pass is not something anyone asked for.
- `body` is the approved copy, carried over unchanged. Do not rewrite approved copy.

## Worked example

A day holding `07:45`, `09:30` and `11:15` is three posts, all morning. Keep one
morning post, move one to the afternoon of the same day if that leaves the day at
two, and move the rest to the next day with room:

```
2026-09-22  07:45  q-103      (kept, morning)
2026-09-22  14:00  q-108      (new, afternoon)
2026-09-23  08:30  q-104      (moved, morning; 15:00 already taken that day)
2026-09-24  09:00  q-105      (moved, morning)
```
